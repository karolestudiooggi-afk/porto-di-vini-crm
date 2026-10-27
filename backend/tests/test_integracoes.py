"""Integrações (iFood e Google Meu Negócio).

Como o resto da suíte, nada aqui toca banco nem rede: as plataformas são
simuladas com `httpx.MockTransport` e a conexão por um dublê mínimo. O que se
testa são as regras que, quebradas, geram dano que não dá para desfazer —
resposta duplicada, texto fora do limite, publicação sem aprovação.
"""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.main import app
from app.rbac import PERMISSOES
from app.services.integracoes import agente, google, ifood, notificar, redator, store
from app.services.integracoes.comum import momento


AGORA = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


class Resultado:
    def __init__(self, linhas=None):
        self._linhas = linhas or []
        self.rowcount = len(self._linhas)

    async def fetchone(self):
        return self._linhas[0] if self._linhas else None

    async def fetchall(self):
        return self._linhas


class ConexaoFalsa:
    """Responde `SELECT ... integra.tokens` com o que estiver em `token`."""

    def __init__(self, token=None):
        self.token = token
        self.sqls: list[str] = []
        self.commits = 0

    async def execute(self, sql, args=None):
        self.sqls.append(" ".join(sql.split()))
        if sql.lstrip().upper().startswith("SELECT") and "integra.tokens" in sql:
            return Resultado([self.token] if self.token else [])
        return Resultado()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def cliente(tratador) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(tratador))


@pytest.fixture
def credenciais(monkeypatch):
    monkeypatch.setattr(settings, "ifood_client_id", "cid")
    monkeypatch.setattr(settings, "ifood_client_secret", "seg")
    monkeypatch.setattr(settings, "google_client_id", "gid")
    monkeypatch.setattr(settings, "google_client_secret", "gseg")
    monkeypatch.setattr(settings, "openai_api_key", "sk-teste")


# ----------------------------- leitura de datas -----------------------------

def test_momento_aceita_os_formatos_das_duas_plataformas():
    assert momento("2026-09-17T14:44:24Z") == datetime(2026, 9, 17, 14, 44, 24, tzinfo=timezone.utc)
    # O Google manda 9 casas decimais; o strptime só aceita 6.
    assert momento("2026-09-17T14:44:24.123456789Z").microsecond == 123456
    assert momento("2026-09-17T14:44:24.000-0300").utcoffset() == timedelta(hours=-3)
    # Sem fuso é UTC, para a conta do prazo nunca misturar aware com naive.
    assert momento("2026-09-17T14:44:24").tzinfo is timezone.utc
    assert momento("lixo") is None and momento(None) is None and momento("") is None


# ---------------------------------- iFood ----------------------------------

def test_nota_arredonda_meio_para_cima():
    # round() do Python daria 2 para 2.5 (bancário); o painel antigo mostrava 3.
    assert [ifood.nota(x) for x in (1.5, 2.5, 4.4, 4.5, 5)] == [2, 3, 4, 5, 5]
    assert ifood.nota(None) == 0 and ifood.nota("x") == 0


def test_pendente_so_quando_ainda_aceita_resposta():
    assert ifood.pendente({"status": "NOT_REPLIED"})
    assert not ifood.pendente({"status": "REPLIED"})
    assert not ifood.pendente({"status": "PUBLISHED"})
    assert not ifood.pendente({"status": "NOT_REPLIED", "discarded": True})
    assert not ifood.pendente({"status": "DISCARDED"})
    # V1 não traz status: respondida é a que veio com reply.
    assert ifood.pendente({"comment": "oi"})
    assert not ifood.pendente({"reply": "obrigado"})
    assert not ifood.pendente({"replies": [{"text": "obrigado", "from": "MERCHANT"}]})
    # Réplica do CLIENTE não conta como resposta da loja.
    assert ifood.pendente({"replies": [{"text": "e aí?", "from": "CUSTOMER"}]})


def test_prazo_e_urgencia():
    criada = AGORA - timedelta(days=4, hours=6)
    sobra = ifood.restante(criada, AGORA)
    assert sobra == timedelta(hours=18)
    assert ifood.urgencia(sobra, respondida=False) == "quente"
    assert ifood.urgencia(timedelta(hours=30), False) == "morno"
    assert ifood.urgencia(timedelta(days=3), False) == "frio"
    assert ifood.urgencia(sobra, respondida=True) == ""
    assert ifood.restante(AGORA - timedelta(days=9), AGORA) == timedelta(0)
    assert ifood.restante(None, AGORA) == ifood.PRAZO_RESPOSTA


def test_normalizar_ifood():
    av = ifood.normalizar({
        "id": "r1", "score": 1.5, "comment": "  fria  ", "status": "NOT_REPLIED",
        "createdAt": "2026-10-03T06:00:00Z", "order": {"id": "o1", "shortId": "9121"},
    }, AGORA)
    assert av["nota"] == 2 and av["comentario"] == "fria" and av["pedido"] == "9121"
    assert av["pendente"] and av["urgencia"] == "quente"
    assert av["prazo_seg"] == 18 * 3600 and av["prazo_perc"] == 85
    assert av["autor"] is None


def test_query_nao_corrige_pagina_acima_do_teto():
    # De propósito: o cenário de homologação é pedir 80 e ver o 400 da API.
    q = ifood.montar_query(pagina=0, page_size=80, de=AGORA - timedelta(days=1),
                           ate=AGORA, contar=True)
    assert "pageSize=80" in q and "page=1" in q and "addCount=true" in q
    assert "dateFrom=2026-10-06T12%3A00%3A00Z" in q


async def test_token_ifood_nao_usa_o_que_guardou_depois_de_vencer(credenciais):
    """Uma passada dura até 10 minutos, a mesma margem do token.

    Sem reconferir o vencimento do que está guardado na instância, o fim da
    passada sairia com um token morto e geraria 401 em série — bem onde
    ninguém está olhando.
    """
    pedidos = []

    def tratador(request):
        pedidos.append(request)
        return httpx.Response(200, json={"accessToken": "novo", "expiresIn": 21600})

    conn = ConexaoFalsa()
    api = ifood.Ifood(conn, cliente(tratador))

    # Guardado na instância, mas vencendo em 9 min: dentro da margem de 10.
    api._tok = "velho"
    api._tok_expira = datetime.now(timezone.utc) + timedelta(minutes=9)

    assert await api.token() == "novo"
    assert len(pedidos) == 1, "deveria ter pedido um token novo"

    # Agora com 6h de folga: reaproveita sem tocar na rede.
    assert await api.token() == "novo"
    assert len(pedidos) == 1


async def test_token_ifood_reaproveita_o_do_banco(credenciais):
    def tratador(request):
        raise AssertionError("não deveria pedir token novo")

    conn = ConexaoFalsa({"access_token": "guardado",
                         "expira_em": datetime.now(timezone.utc) + timedelta(hours=3)})
    assert await ifood.Ifood(conn, cliente(tratador)).token() == "guardado"


async def test_token_ifood_renova_perto_de_expirar_e_grava(credenciais):
    pedidos = []

    def tratador(request):
        pedidos.append(request)
        return httpx.Response(200, json={"accessToken": "novo", "expiresIn": 21600})

    # Faltam 5 min: dentro da margem de 10, então renova.
    conn = ConexaoFalsa({"access_token": "velho",
                         "expira_em": datetime.now(timezone.utc) + timedelta(minutes=5)})
    api = ifood.Ifood(conn, cliente(tratador))
    assert await api.token() == "novo"
    assert b"grantType=client_credentials" in pedidos[0].content
    assert any("INSERT INTO integra.tokens" in s for s in conn.sqls) and conn.commits == 1
    # Segunda chamada na mesma instância não vai nem ao banco nem à rede.
    assert await api.token() == "novo" and len(pedidos) == 1


async def test_ifood_sem_credencial_nao_chama_nada():
    api = ifood.Ifood(ConexaoFalsa())
    api.client_id = api._segredo = ""
    with pytest.raises(ifood.NaoConfigurado):
        await api.token()


async def test_listar_pendentes_percorre_paginas_com_janela(credenciais, monkeypatch):
    async def sem_pausa(_):
        return None
    monkeypatch.setattr(ifood.asyncio, "sleep", sem_pausa)
    vistos = []

    def tratador(request):
        if "oauth/token" in str(request.url):
            return httpx.Response(200, json={"accessToken": "t", "expiresIn": 21600})
        p = int(request.url.params["page"])
        vistos.append(dict(request.url.params))
        cheia = [{"id": f"p{p}-{i}", "status": "REPLIED"} for i in range(50)]
        ultima = [{"id": "a", "status": "NOT_REPLIED"}, {"id": "b", "status": "REPLIED"}]
        return httpx.Response(200, json={"reviews": cheia if p == 1 else ultima})

    pend = await ifood.Ifood(ConexaoFalsa(), cliente(tratador)).listar_pendentes("m1")
    assert [r["id"] for r in pend] == ["a"]
    assert len(vistos) == 2 and vistos[0]["pageSize"] == "50"
    # Sem dateFrom a API devolveria só 7 dias e avaliação no prazo se perderia.
    assert "dateFrom" in vistos[0] and "dateTo" in vistos[0]


async def test_ifood_erros_sobem_com_o_que_a_api_disse(credenciais):
    def tratador(request):
        if "oauth/token" in str(request.url):
            return httpx.Response(200, json={"accessToken": "t", "expiresIn": 21600})
        if request.url.path.endswith("/answers"):
            return httpx.Response(422, text='{"message":"already replied"}')
        if request.url.path.endswith("/reviews/nao-existe"):
            return httpx.Response(404)
        return httpx.Response(403, text="forbidden")

    api = ifood.Ifood(ConexaoFalsa(), cliente(tratador))
    with pytest.raises(ifood.NaoEncontrada):
        await api.obter("m1", "nao-existe")
    with pytest.raises(ifood.SemPermissao) as sem:
        await api.listar_pagina("m1")
    assert "não autorizou" in str(sem.value)
    with pytest.raises(ifood.ErroIfood) as exc:
        await api.responder_sem_validar("m1", "r1", "qualquer texto aqui")
    assert exc.value.status == 422 and "already replied" in str(exc.value)


async def test_responder_do_agente_valida_tamanho_antes_de_sair(credenciais):
    def tratador(request):
        raise AssertionError("texto inválido não pode chegar à rede")

    api = ifood.Ifood(ConexaoFalsa(), cliente(tratador))
    with pytest.raises(ValueError):
        await api.responder("m1", "r1", "curto")
    with pytest.raises(ValueError):
        await api.responder("m1", "r1", "x" * 301)


# ---------------------------------- Google ---------------------------------

def test_original_descarta_a_traducao_automatica():
    assert google.original(
        "(Translated by Google) Slow service\n\n(Original)\nAtendimento demorado"
    ) == "Atendimento demorado"
    assert google.original("Tudo ótimo") == "Tudo ótimo"
    assert google.original(None) == ""


def test_normalizar_google():
    av = google.normalizar({
        "reviewId": "g1", "reviewer": {"displayName": "Ana"}, "starRating": "TWO",
        "comment": "Demorou", "createTime": "2026-10-01T12:00:00.123456789Z",
    })
    assert av["nota"] == 2 and av["autor"] == "Ana" and av["pendente"]
    assert av["respostas"] == [] and av["prazo_seg"] is None

    respondida = google.normalizar({
        "reviewId": "g2", "reviewer": {"displayName": "X", "isAnonymous": True},
        "starRating": "FIVE", "reviewReply": {"comment": "Obrigado!"},
    })
    assert not respondida["pendente"] and respondida["autor"] is None
    assert respondida["respostas"][0]["texto"] == "Obrigado!"
    # Só estrelas, sem texto: comentário vazio, e continua pendente.
    assert google.normalizar({"reviewId": "g3", "starRating": "FOUR"})["comentario"] == ""


def test_state_do_oauth_so_vale_assinado_e_no_prazo(monkeypatch):
    import jwt as pyjwt

    state = google.gerar_state("usuario-1")
    assert google.ler_state(state) == "usuario-1"
    assert google.ler_state("forjado") is None
    assert google.ler_state("") is None
    # Um JWT de sessão do próprio CRM (mesmo segredo) não serve de state.
    sessao = pyjwt.encode({"sub": "usuario-1"}, settings.supabase_jwt_secret, algorithm="HS256")
    assert google.ler_state(sessao) is None
    vencido = pyjwt.encode(
        {"sub": "usuario-1", "aud": google._AUDIENCIA_STATE,
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.supabase_jwt_secret, algorithm="HS256")
    assert google.ler_state(vencido) is None


def test_url_de_autorizacao_pede_acesso_permanente(credenciais, monkeypatch):
    monkeypatch.setattr(settings, "google_redirect_uri", "")
    url = httpx.URL(google.url_autorizacao("st"))
    assert url.params["access_type"] == "offline" and url.params["prompt"] == "consent"
    assert google.ESCOPO in url.params["scope"]
    assert url.params["redirect_uri"] == settings.app_url.rstrip("/") + "/api/integracoes/google/callback"


def test_erro_google_explica_os_tropecos_de_projeto_novo():
    cota = google.ErroGoogle(429, json.dumps(
        {"error": {"code": 429, "message": "Quota exceeded for quota metric 'Requests'"}}))
    assert "Quota exceeded" in str(cota) and "Business Profile API" in str(cota)
    desligada = google.ErroGoogle(403, json.dumps(
        {"error": {"message": "My Business API has not been used in project 1 before"}}))
    assert "ative esta API" in str(desligada)
    assert str(google.ErroGoogle(500, "<html>")) == "Google respondeu HTTP 500: <html>"


async def test_google_sem_conexao_nao_chama_nada(credenciais):
    def tratador(request):
        raise AssertionError("sem refresh_token não há o que chamar")

    with pytest.raises(google.NaoConectado):
        await google.Google(ConexaoFalsa(), cliente(tratador)).listar_contas()


async def test_google_conexao_revogada_limpa_o_token(credenciais):
    def tratador(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    conn = ConexaoFalsa({"access_token": None, "expira_em": None, "refresh_token": "morto"})
    with pytest.raises(google.NaoConectado) as exc:
        await google.Google(conn, cliente(tratador)).token()
    assert "conecte de novo" in str(exc.value)
    # Limpa E commita: a rota vai levantar erro, e o rollback desfaria a limpeza.
    assert any("SET refresh_token = NULL" in s for s in conn.sqls) and conn.commits == 1


async def test_google_responder_valida_e_publica(credenciais):
    enviados = []

    def tratador(request):
        enviados.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"comment": "ok"})

    conn = ConexaoFalsa({"access_token": "acc", "refresh_token": "ref",
                         "expira_em": datetime.now(timezone.utc) + timedelta(minutes=30)})
    api = google.Google(conn, cliente(tratador))
    with pytest.raises(ValueError):
        await api.responder("111", "222", "r1", "   ")
    with pytest.raises(ValueError):
        # 2.100 "ã" são 4.200 bytes: o limite do Google é em bytes, não em letras.
        await api.responder("111", "222", "r1", "ã" * 2100)
    assert enviados == []

    await api.responder("111", "222", "r1", "  Obrigado!  ")
    assert enviados == [("PUT", "/v4/accounts/111/locations/222/reviews/r1/reply",
                         {"comment": "Obrigado!"})]


async def test_descobrir_liga_cada_unidade_a_conta_dona(credenciais):
    def tratador(request):
        if request.url.path == "/v1/accounts":
            return httpx.Response(200, json={"accounts": [
                {"name": "accounts/1", "accountName": "Pessoal"},
                {"name": "accounts/2", "accountName": "Grupo"}]})
        if request.url.path == "/v1/accounts/1/locations":
            return httpx.Response(200, json={})
        assert request.url.params["readMask"]  # a API recusa sem readMask
        return httpx.Response(200, json={"locations": [
            {"name": "locations/900", "title": "Paraíso",
             "storefrontAddress": {"locality": "Niterói"}}]})

    conn = ConexaoFalsa({"access_token": "acc", "refresh_token": "ref",
                         "expira_em": datetime.now(timezone.utc) + timedelta(minutes=30)})
    assert await google.Google(conn, cliente(tratador)).descobrir() == [{
        "loja_id": "900", "conta_id": "2", "conta_nome": "Grupo",
        "nome": "Paraíso", "cidade": "Niterói"}]


# --------------------------------- redator ---------------------------------

def test_prompt_padrao_por_origem():
    assert "tom cordial e profissional" in redator.prompt_padrao("ifood")
    assert "tom leve e direto" in redator.prompt_padrao("ifood", " leve e direto ")
    assert "Nunca ultrapasse 300" in redator.prompt_padrao("ifood")
    # O nome vem de CLIENTE_NOME (no servidor, o .env da Porto).
    assert settings.cliente_nome in redator.prompt_padrao("google")
    # As proibições que protegem a casa estão nos dois.
    for origem in ("ifood", "google"):
        assert "cupom" in redator.prompt_padrao(origem)


def test_acabamento_ifood_nunca_passa_de_300():
    assert redator.acabamento("ifood", '"Obrigado pela visita!"', "Equipe MJ") == \
        "Obrigado pela visita! Equipe MJ"
    # Assinatura que estouraria o limite fica de fora, em vez de cortar o texto.
    longo = "a" * 295
    assert redator.acabamento("ifood", longo, "Equipe MJ") == longo
    cortado = redator.acabamento("ifood", "b" * 400)
    assert len(cortado) == 300 and cortado.endswith("...")
    with pytest.raises(redator.ErroRedator):
        redator.acabamento("ifood", "oi")


def test_acabamento_google():
    assert redator.acabamento("google", ' "Obrigado!" ', "Equipe Exemplo") == "Obrigado!\nEquipe Exemplo"
    assert len(redator.acabamento("google", "ã" * 5000).encode()) <= google.MAX_BYTES
    with pytest.raises(redator.ErroRedator):
        redator.acabamento("google", '""')


async def test_escrever_usa_prompt_proprio_e_modelo_do_servidor(credenciais):
    visto = {}

    def tratador(request):
        visto.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": "Agradecemos a avaliação e o carinho."}}]})

    texto = await redator.escrever(
        "ifood", {"prompt": "REGRAS DA CASA", "openai_model": "gpt-x", "tom": "ignorado"},
        5, "", http=cliente(tratador))
    assert texto == "Agradecemos a avaliação e o carinho."
    # Modelo gravado no banco (de antes desta mudança) é ignorado: vale o .env.
    assert visto["model"] == settings.openai_model
    assert visto["messages"][0]["content"] == "REGRAS DA CASA"
    assert visto["messages"][1]["content"] == "Nota: 5 de 5\nComentário do cliente: (sem comentário)"


async def test_escrever_sem_chave_e_com_erro_da_ia(credenciais, monkeypatch):
    def tratador(request):
        return httpx.Response(401, json={"error": {"message": "Incorrect API key"}})

    with pytest.raises(redator.ErroRedator) as exc:
        await redator.escrever("google", {}, 5, "ótimo", http=cliente(tratador))
    assert "Incorrect API key" in str(exc.value)

    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(redator.ErroRedator) as exc:
        await redator.escrever("google", {}, 5, "ótimo")
    assert "OPENAI_API_KEY" in str(exc.value)


# -------------------------------- notificação -------------------------------

def test_nivel_pela_nota():
    assert [notificar.nivel(n) for n in (1, 2, 3, 4, 5)] == \
        ["negativa", "negativa", "neutra", "positiva", "positiva"]


def test_corpo_do_aviso_mantem_o_contrato_do_painel_antigo(monkeypatch):
    monkeypatch.setattr(settings, "app_url", "https://crm.exemplo.com/")
    av = ifood.normalizar({
        "id": "r1", "score": 2, "comment": "vou acionar o procon",
        "status": "NOT_REPLIED", "createdAt": "2026-10-06T18:00:00Z",
        "order": {"shortId": "9121"}}, AGORA)
    corpo = notificar.montar(
        notificar.EVENTO_NOVA, {"loja_id": "m1", "nome": "Unidade Centro", "cidade": "Rio"}, av)
    # As chaves que o fluxo do NichoChat já lê.
    assert {"evento", "cliente", "merchant_id", "loja", "cidade", "avaliacao_id", "pedido",
            "nota", "comentario", "criada_em", "nivel", "prazo_horas", "link"} <= set(corpo)
    assert corpo["evento"] == "avaliacao_nova" and corpo["nivel"] == "negativa"
    assert corpo["prazo_horas"] == 102 and corpo["cliente"] == settings.cliente_nome
    assert corpo["link"] == "https://crm.exemplo.com/integracoes?origem=ifood&loja=m1&avaliacao=r1"


def test_destino_cai_no_webhook_do_ambiente(monkeypatch):
    monkeypatch.setattr(settings, "nichochat_webhook_url", "https://reserva")
    assert notificar.destino({"webhook_url": " https://da-tela "}) == "https://da-tela"
    assert notificar.destino({"webhook_url": None}) == "https://reserva"


# ---------------------------------- agente ---------------------------------

class ApiFalsa:
    def __init__(self, crus):
        self.crus = crus
        self.publicadas = []

    async def listar_pendentes(self, loja_id):
        return self.crus

    async def responder(self, loja_id, review_id, texto):
        self.publicadas.append((review_id, texto))


@pytest.fixture
def cena(monkeypatch):
    """Substitui banco, IA e webhook; devolve o que cada um recebeu."""
    reg = {"registros": [], "avisos": [], "vistas": {}}

    async def processadas(conn, origem, ids):
        return {i: reg["vistas"][i] for i in ids if i in reg["vistas"]}

    async def registrar(conn, origem, loja_id, av, **kw):
        reg["registros"].append((av["id"], kw["status"], kw.get("via")))

    async def nova(cfg, loja, av):
        reg["avisos"].append(("nova", av["id"]))

    async def respondida(cfg, loja, av, texto, origem):
        reg["avisos"].append(("respondida", av["id"], origem))

    async def escrever(origem, cfg, nota, comentario, assinatura=None, http=None):
        return f"Resposta para nota {nota}, obrigado."

    async def sem_pausa(_):
        return None

    monkeypatch.setattr(store, "processadas", processadas)
    monkeypatch.setattr(store, "registrar", registrar)
    monkeypatch.setattr(notificar, "nova", nova)
    monkeypatch.setattr(notificar, "respondida", respondida)
    monkeypatch.setattr(redator, "escrever", escrever)
    monkeypatch.setattr(agente.asyncio, "sleep", sem_pausa)
    return reg


def _cruas():
    return [
        {"id": "alta", "score": 5, "status": "NOT_REPLIED", "comment": "ótimo"},
        {"id": "baixa", "score": 2, "status": "NOT_REPLIED", "comment": "ruim"},
    ]


LOJA = {"loja_id": "m1", "nome": "Centro", "cidade": None, "assinatura": None}


def _contagem():
    return {"lojas": 0, "encontradas": 0, "respondidas": 0, "erros": 0}


async def test_agente_em_modo_manual_avisa_e_nunca_publica(cena):
    api, e = ApiFalsa(_cruas()), _contagem()
    cfg = {"ativo": True, "modo": "manual", "nota_minima": 1}
    await agente.processar(ConexaoFalsa(), api, cfg, LOJA, e)

    assert api.publicadas == []
    assert cena["avisos"] == [("nova", "alta"), ("nova", "baixa")]
    assert cena["registros"] == [("alta", "pendente", None), ("baixa", "pendente", None)]
    assert e["encontradas"] == 2 and e["respondidas"] == 0


async def test_agente_automatico_respeita_a_nota_minima(cena):
    api, e = ApiFalsa(_cruas()), _contagem()
    cfg = {"ativo": True, "modo": "automatico", "nota_minima": 4}
    await agente.processar(ConexaoFalsa(), api, cfg, LOJA, e)

    assert [p[0] for p in api.publicadas] == ["alta"]
    assert ("baixa", "ignorada", None) in cena["registros"]
    assert ("alta", "enviada", "agente") in cena["registros"]
    # A baixa também é avisada: quem decide o que fazer com ela é o NichoChat.
    assert ("nova", "baixa") in cena["avisos"]
    assert ("respondida", "alta", "agente") in cena["avisos"]
    assert e["respondidas"] == 1


async def test_agente_avisa_uma_vez_so(cena):
    # O aviso é o que não pode repetir: o fluxo do NichoChat reagiria de novo.
    cena["vistas"] = {"alta": {"status": "pendente"}, "baixa": {"status": "ignorada"}}
    api, e = ApiFalsa(_cruas()), _contagem()
    await agente.processar(ConexaoFalsa(), api,
                           {"ativo": True, "modo": "manual", "nota_minima": 1}, LOJA, e)
    assert cena["avisos"] == []
    # Nem regrava o que já estava registrado do mesmo jeito.
    assert cena["registros"] == []


async def test_agente_nunca_republica_o_que_ja_saiu(cena):
    # Responder de novo devolve 422 e não há como desfazer: é a única decisão
    # que o agente toma uma vez e nunca revisa.
    cena["vistas"] = {"alta": {"status": "enviada"}, "baixa": {"status": "enviada"}}
    api, e = ApiFalsa(_cruas()), _contagem()
    await agente.processar(ConexaoFalsa(), api,
                           {"ativo": True, "modo": "automatico", "nota_minima": 1}, LOJA, e)
    assert api.publicadas == [] and cena["registros"] == []


async def test_baixar_a_nota_minima_alcanca_o_que_ficou_de_fora(cena):
    # A nota 2 foi ignorada quando o corte era 4. Com o corte em 1, ela passa
    # a ser respondida: a decisão é reavaliada a cada passada, não congelada.
    cena["vistas"] = {"baixa": {"status": "ignorada"}}
    api, e = ApiFalsa(_cruas()[1:]), _contagem()
    await agente.processar(ConexaoFalsa(), api,
                           {"ativo": True, "modo": "automatico", "nota_minima": 1}, LOJA, e)
    assert [p[0] for p in api.publicadas] == ["baixa"]
    assert ("baixa", "enviada", "agente") in cena["registros"]


async def test_trocar_de_manual_para_automatico_alcanca_a_fila(cena):
    cena["vistas"] = {"alta": {"status": "pendente"}}
    api, e = ApiFalsa(_cruas()[:1]), _contagem()
    await agente.processar(ConexaoFalsa(), api,
                           {"ativo": True, "modo": "automatico", "nota_minima": 1}, LOJA, e)
    assert [p[0] for p in api.publicadas] == ["alta"]


async def test_erro_passageiro_e_tentado_de_novo_ate_o_limite(cena):
    # Falha de momento (IA fora do ar, token vencido, rede) não pode tirar a
    # avaliação do alcance do agente para sempre.
    cena["vistas"] = {"alta": {"status": "erro", "tentativas": 1}}
    api, e = ApiFalsa(_cruas()[:1]), _contagem()
    await agente.processar(ConexaoFalsa(), api,
                           {"ativo": True, "modo": "automatico", "nota_minima": 1}, LOJA, e)
    assert [p[0] for p in api.publicadas] == ["alta"]

    # Esgotado o limite, para de tentar: erro real não vira laço infinito.
    cena["registros"].clear()
    cena["vistas"] = {"alta": {"status": "erro", "tentativas": agente.MAX_TENTATIVAS}}
    api2 = ApiFalsa(_cruas()[:1])
    await agente.processar(ConexaoFalsa(), api2,
                           {"ativo": True, "modo": "automatico", "nota_minima": 1}, LOJA, e)
    assert api2.publicadas == [] and cena["registros"] == []


async def test_agente_pausado_nao_e_automatico():
    assert not store.automatico({"ativo": False, "modo": "automatico"})
    assert not store.automatico({"ativo": True, "modo": "manual"})
    assert store.automatico({"ativo": True, "modo": "automatico"})


async def test_agente_registra_erro_quando_o_ifood_recusa(cena):
    class ApiRecusa(ApiFalsa):
        async def responder(self, loja_id, review_id, texto):
            raise ifood.ErroIfood(422, "already replied")

    e = _contagem()
    await agente.processar(ConexaoFalsa(), ApiRecusa(_cruas()[:1]),
                           {"ativo": True, "modo": "automatico", "nota_minima": 1}, LOJA, e)
    assert cena["registros"] == [("alta", "erro", "agente")] and e["erros"] == 1
    assert ("respondida", "alta", "agente") not in cena["avisos"]


# ----------------------------------- rotas ----------------------------------

def test_permissoes_do_modulo_existem():
    assert {"integracoes:manage", "integracoes:config"} <= PERMISSOES


def test_rotas_de_integracoes_exigem_sessao():
    paths = app.openapi()["paths"]
    protegidas = [p for p in paths if p.startswith("/integracoes")]
    assert len(protegidas) >= 15
    for caminho in protegidas:
        for metodo, operacao in paths[caminho].items():
            assert operacao.get("security") == [{"HTTPBearer": []}], f"{metodo} {caminho}"
    # O callback é público (validado pelo state) e fica fora da documentação.
    assert "/integracoes/google/callback" not in paths


async def test_callback_do_google_recusa_state_forjado():
    from app.db import get_conn

    async def conexao_falsa():
        yield ConexaoFalsa()

    app.dependency_overrides[get_conn] = conexao_falsa
    try:
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://test") as c:
            r = await c.get("/integracoes/google/callback?code=abc&state=forjado")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 302
    destino = httpx.URL(r.headers["location"])
    assert destino.path == "/integracoes" and destino.params["google"] == "erro"


# ------------------------- agente dentro da API ---------------------------

def test_agente_sobe_ligado_e_worker_desligado_desliga(monkeypatch):
    # Como no painel de origem: sem a variável, o agente roda.
    monkeypatch.setattr(settings, "worker_desligado", "")
    assert settings.agente_ligado
    monkeypatch.setattr(settings, "worker_desligado", "1")
    assert not settings.agente_ligado


async def test_agendar_roda_de_15_em_15_e_sobrevive_a_falha(monkeypatch):
    esperas, passadas = [], []

    async def dormir(seg):
        esperas.append(seg)
        if len(esperas) > 3:
            raise agente.asyncio.CancelledError  # a API desligando

    async def passada(agendada=False):
        passadas.append(agendada)

    monkeypatch.setattr(agente.asyncio, "sleep", dormir)
    monkeypatch.setattr(agente, "rodar_na_api", passada)
    with pytest.raises(agente.asyncio.CancelledError):
        await agente.agendar()

    assert esperas[:3] == [agente.ESPERA_INICIAL_SEG, 15 * 60, 15 * 60]
    assert passadas == [True, True, True]


def test_chave_e_modelo_da_ia_nao_entram_pela_tela():
    """Nenhuma chave de API passa pelo frontend: o PATCH da configuração
    descarta chave e modelo, mesmo que alguém (ou uma tela antiga) mande."""
    from app.schemas.integracoes import ConfigPatch

    patch = ConfigPatch(openai_api_key="sk-x", openai_model="gpt-x", tom="cordial")
    assert patch.model_dump(exclude_unset=True) == {"tom": "cordial"}


async def test_escrever_usa_so_a_chave_do_servidor(credenciais):
    usadas = []

    def tratador(request):
        usadas.append(request.headers["authorization"])
        return httpx.Response(200, json={"choices": [{"message": {
            "content": "Agradecemos a avaliação e o carinho."}}]})

    # Uma chave que tenha ficado gravada no banco é ignorada.
    await redator.escrever("ifood", {"openai_api_key": "sk-da-casa"}, 5, "", http=cliente(tratador))
    assert usadas == ["Bearer sk-teste"]
