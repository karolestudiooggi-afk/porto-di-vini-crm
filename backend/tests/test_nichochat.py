"""Resposta do Google entregue ao NichoChat.

Sem rede e sem banco: o NichoChat é um `httpx.MockTransport` que imita o que a
API de lá devolve, e a rota roda com a conexão e o Google trocados por dublês.
O que se protege aqui:

- a ordem: os três campos são gravados ANTES de o subfluxo disparar;
- o corpo do disparo é exatamente o combinado (user_id + sub_flow_ns);
- duas respostas nunca se cruzam no contato que é o mesmo para todas;
- a tela não diz "publicada" antes de o Google mostrar o texto.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.main import app
from app.routers import integracoes as rotas
from app.services.integracoes import google, nichochat, store

BASE = "https://nicho.teste/api"

# O de verdade, guardado antes de o `sem_pausa` trocar asyncio.sleep.
_ceder = asyncio.sleep

CAMPOS = [
    # A busca por nome do NichoChat é "contém": vem o campo parecido junto.
    {"name": "ID_localizacao_resposta", "var_ns": "f000000v18014675", "var_type": "text"},
    # O antigo continua existindo no NichoChat; não pode ser confundido.
    {"name": "Id_localizacao", "var_ns": "f000000v17895779", "var_type": "text"},
    {"name": "review_id_resposta", "var_ns": "f000000v18020889", "var_type": "text"},
    # Outros fluxos usam Review_id; a resposta não pode gravar nele.
    {"name": "Review_id", "var_ns": "f000000v17895781", "var_type": "text"},
    {"name": "resposta_comentario", "var_ns": "f000000v17895785", "var_type": "text"},
    {"name": "Resposta_avaliacao_google", "var_ns": "f000000v17487357", "var_type": "text"},
]


@pytest.fixture(autouse=True)
def configurado(monkeypatch):
    monkeypatch.setattr(settings, "domani_api_url", BASE)
    monkeypatch.setattr(settings, "domani_api_key", "chave-teste")
    # Como veio no pedido, com "+": o código tira, porque o NichoChat grava sem.
    monkeypatch.setattr(settings, "nichochat_contato_user_id", "+5521999990001")
    monkeypatch.setattr(settings, "nichochat_resposta_contato_user_id", "+5531999990002")
    monkeypatch.setattr(settings, "nichochat_resposta_google_subfluxo", "f000000s4868429")
    monkeypatch.setattr(settings, "nichochat_resposta_intervalo_seg", 10.0)
    nichochat._var_ns.clear()
    monkeypatch.setattr(nichochat, "_fila", nichochat._Fila())
    yield
    nichochat._var_ns.clear()


@pytest.fixture
def sem_pausa(monkeypatch):
    pausas: list[float] = []

    async def dormir(segundos):
        pausas.append(segundos)

    monkeypatch.setattr(nichochat.asyncio, "sleep", dormir)
    return pausas


class NichoFalso:
    """Imita a API do NichoChat e anota cada chamada."""

    def __init__(self, campos=CAMPOS, contato=True, disparo=(200, {"status": "ok"}),
                 nao_grava: str | None = None, cria=True):
        self.campos = campos
        # Os contatos que existem no NichoChat: user_id -> user_ns.
        self.contatos = {"5521999990001": "f000000u989920157",
                         "5531999990002": "f000000u990000058"} if contato else {}
        self.cria = cria
        self.disparo = disparo
        # var_ns que o NichoChat "não acha" na gravação (fica fora do matched_items).
        self.nao_grava = nao_grava
        self.chamadas: list[tuple] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        caminho = request.url.path.removeprefix("/api")
        corpo = json.loads(request.content) if request.content else None
        self.chamadas.append((request.method, caminho, dict(request.url.params), corpo,
                              request.headers.get("authorization")))
        if caminho == "/subscriber/get-info-by-user-id":
            uid = request.url.params["user_id"]
            if uid not in self.contatos:
                return httpx.Response(400, json={"message": "subscriber not found"})
            return httpx.Response(200, json={"status": "ok", "data": {
                "user_ns": self.contatos[uid], "user_id": uid}})
        if caminho == "/subscriber/create" and request.method == "POST":
            if not self.cria:
                return httpx.Response(422, json={"message": "The phone field is invalid."})
            uid = corpo["phone"].lstrip("+")
            self.contatos[uid] = f"f000000u{uid[-9:]}"
            return httpx.Response(200, json={"status": "ok", "data": {
                "user_ns": self.contatos[uid], "user_id": uid}})
        if caminho == "/flow/user-fields":
            nome = request.url.params["name"].lower()
            achados = [c for c in self.campos if nome in c["name"].lower()]
            return httpx.Response(200, json={"status": "ok", "data": achados})
        if caminho in ("/subscriber/set-user-field", "/subscriber/set-user-fields"):
            # Como na VPS: gravar é PUT; POST devolve 405.
            if request.method != "PUT":
                return httpx.Response(405, json={"message": (
                    f"The {request.method} method is not supported for route "
                    f"api{caminho}. Supported methods: PUT.")})
            casados = [{**c, "value": d["value"]} for d in corpo["data"] for c in self.campos
                       if c["var_ns"] == d["var_ns"] and c["var_ns"] != self.nao_grava]
            return httpx.Response(200, json={"status": "ok", "matched_items": casados})
        if caminho == "/subscriber/send-sub-flow-by-user-id":
            status, resposta = self.disparo
            return httpx.Response(status, json=resposta)
        return httpx.Response(404, json={"message": "rota não existe"})

    def gravacoes(self) -> list[tuple]:
        return [c for c in self.chamadas if c[1] == "/subscriber/set-user-fields"]

    def gravados(self) -> dict[str, str]:
        return {d["var_ns"]: d["value"] for c in self.gravacoes() for d in c[3]["data"]}

    def caminhos(self) -> list[str]:
        return [c[1] for c in self.chamadas]


async def enviar(nicho, location_id="1", review_id="r1", texto="texto"):
    await nichochat.enviar_resposta_google(
        location_id, review_id, texto, transporte=httpx.MockTransport(nicho))


# ------------------------------- o envio -----------------------------------

async def test_grava_os_tres_campos_e_so_depois_dispara_o_subfluxo(sem_pausa):
    nicho = NichoFalso()
    await enviar(nicho, "1000000000000000013", "AbFvOqm", "  Obrigado, Ana!  ")

    assert nicho.gravados() == {
        "f000000v18014675": "1000000000000000013",
        "f000000v18020889": "AbFvOqm",
        "f000000v17895785": "Obrigado, Ana!",
    }
    # O disparo é a ÚLTIMA chamada: o fluxo lê os campos assim que começa.
    metodo, caminho, _params, corpo, auth = nicho.chamadas[-1]
    assert (metodo, caminho) == ("POST", "/subscriber/send-sub-flow-by-user-id")
    # A resposta vai no contato das respostas (NICHOCHAT_RESPOSTA_CONTATO_USER_ID), não no da busca.
    assert corpo == {"user_id": "5531999990002", "sub_flow_ns": "f000000s4868429"}
    assert all(c[4] == "Bearer chave-teste" for c in nicho.chamadas)
    # Os três numa gravação só (PUT), no contato certo, antes do disparo.
    assert [(c[0], c[3]["user_ns"]) for c in nicho.gravacoes()] == [("PUT", "f000000u990000058")]
    assert "/subscriber/create" not in nicho.caminhos()
    assert nicho.caminhos()[-2:] == ["/subscriber/set-user-fields",
                                     "/subscriber/send-sub-flow-by-user-id"]


async def test_campos_sao_achados_uma_vez_so(sem_pausa):
    nicho = NichoFalso()
    await enviar(nicho, review_id="r1", texto="um")
    await enviar(nicho, review_id="r2", texto="dois")
    assert nicho.caminhos().count("/flow/user-fields") == 3


async def test_contato_que_nao_existe_e_criado_antes_de_gravar(sem_pausa):
    nicho = NichoFalso(contato=False)
    await enviar(nicho, "1000000000000000013", "AbFvOqm", "Obrigado!")
    criacao = [c for c in nicho.chamadas if c[1] == "/subscriber/create"]
    assert [(c[0], c[3]) for c in criacao] == [
        ("POST", {"phone": "+5531999990002", "first_name": "CRM", "last_name": "Respostas Google"})]
    # Criou, gravou no contato novo e só então disparou.
    assert [c[3]["user_ns"] for c in nicho.gravacoes()] == [nicho.contatos["5531999990002"]]
    assert nicho.caminhos()[-1] == "/subscriber/send-sub-flow-by-user-id"
    # Da segunda vez ele já existe: não cria de novo.
    await enviar(nicho, "1000000000000000013", "AbFvOqm2", "Obrigado!")
    assert nicho.caminhos().count("/subscriber/create") == 1


async def test_contato_que_nao_da_para_criar_explica_e_nao_dispara(sem_pausa):
    nicho = NichoFalso(contato=False, cria=False)
    with pytest.raises(nichochat.ErroNichoChat) as exc:
        await enviar(nicho)
    assert "5531999990002 não existe no NichoChat e não deu para criá-lo" in str(exc.value)
    assert "phone field is invalid" in str(exc.value)
    assert "/subscriber/set-user-fields" not in nicho.caminhos()
    assert "/subscriber/send-sub-flow-by-user-id" not in nicho.caminhos()


async def test_campo_que_falta_no_nichochat_nao_e_trocado_pelo_parecido(sem_pausa):
    # Sem "resposta_comentario", a busca ainda devolve "Resposta_avaliacao_google".
    # Gravar nele mandaria o texto para o campo errado.
    nicho = NichoFalso(campos=[c for c in CAMPOS if c["name"] != "resposta_comentario"])
    with pytest.raises(nichochat.ErroNichoChat) as exc:
        await enviar(nicho)
    assert "resposta_comentario não existe" in str(exc.value)
    assert "f000000v17487357" not in nicho.gravados()
    assert "/subscriber/send-sub-flow-by-user-id" not in nicho.caminhos()


async def test_campo_nao_gravado_nao_dispara_o_fluxo(sem_pausa):
    # Se um campo não for gravado, o fluxo leria o valor da resposta ANTERIOR
    # e publicaria na avaliação errada.
    nicho = NichoFalso(nao_grava="f000000v18020889")
    with pytest.raises(nichochat.ErroNichoChat) as exc:
        await enviar(nicho)
    assert "f000000v18020889" in str(exc.value)
    assert "/subscriber/send-sub-flow-by-user-id" not in nicho.caminhos()


async def test_recusa_do_disparo_sobe_com_a_mensagem_de_la(sem_pausa):
    nicho = NichoFalso(disparo=(400, {"message": "Sub flow not found"}))
    with pytest.raises(nichochat.ErroNichoChat) as exc:
        await enviar(nicho)
    assert "HTTP 400: Sub flow not found" in str(exc.value)


async def test_chave_recusada_aponta_o_escopo(sem_pausa):
    nicho = NichoFalso(disparo=(401, {"message": "Unauthenticated."}))
    with pytest.raises(nichochat.ErroNichoChat) as exc:
        await enviar(nicho)
    assert "Manage Flow" in str(exc.value)


async def test_instabilidade_passageira_e_tentada_de_novo(sem_pausa):
    respostas = iter([httpx.Response(503), httpx.Response(200, json={"status": "ok"})])
    nicho = NichoFalso()
    original = nicho.__call__

    def tratador(request):
        if request.url.path.endswith("/send-sub-flow-by-user-id"):
            nicho.chamadas.append(("POST", "disparo", {}, None, None))
            return next(respostas)
        return original(request)

    await enviar(tratador)
    assert nicho.caminhos().count("disparo") == 2


async def test_sem_chave_no_servidor_nao_chama_nada(monkeypatch, sem_pausa):
    monkeypatch.setattr(settings, "domani_api_key", "")
    nicho = NichoFalso()
    with pytest.raises(nichochat.NaoConfigurado):
        await enviar(nicho)
    assert nicho.chamadas == []


async def test_duas_respostas_juntas_nunca_se_cruzam_no_contato(sem_pausa):
    """O contato é o mesmo para todas. A segunda só começa a gravar depois que
    a primeira disparou o fluxo, e ainda espera o intervalo."""
    nicho = NichoFalso()
    nichochat._fila.relogio = lambda: 1000.0  # relógio parado: espera o intervalo inteiro

    async def rede_de_verdade(request):
        # Cada chamada cede a vez, como uma requisição real: sem a trava, as
        # duas respostas se intercalariam aqui.
        await _ceder(0)
        return nicho(request)

    await asyncio.gather(
        enviar(rede_de_verdade, review_id="primeira", texto="texto 1"),
        enviar(rede_de_verdade, review_id="segunda", texto="texto 2"),
    )

    eventos = []
    for c in nicho.chamadas:
        if c[1] == "/subscriber/set-user-fields":
            eventos.extend((c[1], d["value"]) for d in c[3]["data"])
        elif c[1] in ("/subscriber/get-info-by-user-id", "/subscriber/send-sub-flow-by-user-id"):
            eventos.append((c[1], None))
    disparos = [i for i, (caminho, _v) in enumerate(eventos)
                if caminho == "/subscriber/send-sub-flow-by-user-id"]
    assert len(disparos) == 2
    primeiro = {v for _c, v in eventos[:disparos[0]]}
    segundo = {v for _c, v in eventos[disparos[0] + 1:disparos[1]]}
    # Cada disparo leva só os seus campos: nada da outra resposta no meio.
    assert {"primeira", "texto 1"} <= primeiro and not primeiro & {"segunda", "texto 2"}
    assert {"segunda", "texto 2"} <= segundo and not segundo & {"primeira", "texto 1"}
    assert sem_pausa == [10.0]


# ------------------- a fila não diz "publicada" antes -----------------------

AGORA = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)


def _av(resposta: str | None = None) -> dict:
    return {"id": "r1", "pendente": not resposta, "urgencia": "",
            "respostas": [{"texto": resposta}] if resposta else []}


def _reg(status="encaminhada", resposta="Obrigado!\nVolte sempre.", ha=timedelta(minutes=2)):
    return {"review_id": "r1", "status": status, "resposta": resposta,
            "atualizado_em": AGORA - ha}


def test_encaminhada_so_vira_publicada_quando_o_texto_esta_no_google():
    # Mesmo texto, com a quebra de linha que o Google pode ter normalizado.
    assert rotas._encaminhamento(_av("Obrigado!  Volte sempre."), _reg(), AGORA) == "publicada"
    assert rotas._encaminhamento(_av(), _reg(), AGORA) == "aguardando"
    assert rotas._encaminhamento(_av(), _reg(ha=timedelta(minutes=20)), AGORA) == "sem_confirmacao"
    # Havia uma resposta antiga e a nova não substituiu.
    assert rotas._encaminhamento(_av("Obrigado!"), _reg(ha=timedelta(hours=1)), AGORA) == "sem_confirmacao"
    assert rotas._encaminhamento(_av("Obrigado!"), _reg(status="enviada"), AGORA) is None
    assert rotas._encaminhamento(_av(), None, AGORA) is None


def test_item_sai_da_fila_so_enquanto_espera_o_nichochat():
    agora = datetime.now(timezone.utc)
    recente = {**_reg(), "atualizado_em": agora - timedelta(minutes=1)}
    antiga = {**_reg(), "atualizado_em": agora - timedelta(hours=2)}
    assert rotas._item(_av(), recente)["respondida"] is True
    assert rotas._item(_av(), recente)["encaminhamento"] == "aguardando"
    # Passou o prazo e o Google não mostra: volta para a fila, com aviso.
    assert rotas._item(_av(), antiga)["respondida"] is False
    assert rotas._item(_av(), antiga)["encaminhamento"] == "sem_confirmacao"


async def test_confirmacao_promove_o_registro_para_enviada(monkeypatch):
    promovidas = []

    async def confirmar(_conn, origem, ids):
        promovidas.append((origem, ids))

    monkeypatch.setattr(store, "confirmar_publicadas", confirmar)
    item = rotas._item(_av("Obrigado! Volte sempre."), _reg())
    await rotas._confirmar_publicadas(None, [item])
    assert promovidas == [("google", ["r1"])]
    assert item["registro"]["status"] == "enviada" and item["encaminhamento"] is None


# ------------------------------ a rota -------------------------------------

ADMIN = {"id": "00000000-0000-0000-0000-000000000001", "email": "teste@crm.local",
         "papel": "admin", "permissoes": {"integracoes:manage"}}

LOJA = {"origem": "google", "loja_id": "1000000000000000013", "nome": "Unidade Sul",
        "conta_id": "111", "ativo": True}


class Conexao:
    def __init__(self):
        self.commits = 0

    async def execute(self, *_a, **_k):
        raise AssertionError("a rota não deveria tocar o banco direto neste teste")

    async def commit(self):
        self.commits += 1


@pytest.fixture
def rota(monkeypatch):
    from app.auth import current_user
    from app.db import get_conn

    estado = {"conn": Conexao(), "registros": [], "enviados": [], "auditoria": [],
              "lidas_no_google": [], "gravadas": []}

    async def conexao():
        yield estado["conn"]

    async def loja(_conn, origem, loja_id):
        assert (origem, loja_id) == ("google", LOJA["loja_id"])
        return LOJA

    async def guardada(_conn, review_id):
        # Como a leitura automática deixou no banco.
        if estado.get("fora_do_banco"):
            return None
        return store.av_google({"review_id": review_id, "loja_id": LOJA["loja_id"], "nota": 2,
                                "comentario": "Demorou", "autor": "Ana"})

    async def obter(self, conta_id, loja_id, review_id):
        estado["lidas_no_google"].append(review_id)
        return {"reviewId": review_id, "starRating": "TWO", "comment": "Demorou",
                "reviewer": {"displayName": "Ana"}}

    async def gravar(_conn, loja_id, avs):
        estado["gravadas"].extend(a["id"] for a in avs)
        return (len(avs), 0)

    async def publicar_direto(*_a, **_k):
        raise AssertionError("a resposta não pode sair direto para o Google")

    async def enviar(location_id, review_id, texto, **_k):
        estado["enviados"].append((location_id, review_id, texto))
        if estado.get("falha"):
            raise nichochat.ErroNichoChat(estado["falha"])

    async def registrar(_conn, origem, loja_id, av, **kw):
        estado["registros"].append({"origem": origem, "loja_id": loja_id, "id": av["id"], **kw})

    async def auditar(_conn, *args):
        estado["auditoria"].append(args)

    monkeypatch.setattr(rotas, "_loja", loja)
    monkeypatch.setattr(store, "avaliacao_google", guardada)
    monkeypatch.setattr(store, "gravar_google", gravar)
    monkeypatch.setattr(google.Google, "obter", obter)
    monkeypatch.setattr(google.Google, "responder", publicar_direto)
    monkeypatch.setattr(nichochat, "enviar_resposta_google", enviar)
    monkeypatch.setattr(store, "registrar", registrar)
    monkeypatch.setattr(rotas, "registrar", auditar)
    app.dependency_overrides[current_user] = lambda: ADMIN
    app.dependency_overrides[get_conn] = conexao
    yield estado
    app.dependency_overrides.clear()


async def _responder(texto: str) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as c:
        return await c.post(
            f"/integracoes/google/lojas/{LOJA['loja_id']}/avaliacoes/AbFvOqm/responder",
            json={"texto": texto})


async def test_rota_entrega_ao_nichochat_e_registra_encaminhada(rota):
    r = await _responder("  Obrigado, Ana!  ")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "encaminhada": True}
    assert rota["enviados"] == [("1000000000000000013", "AbFvOqm", "Obrigado, Ana!")]
    assert [(x["status"], x["resposta"], x["via"]) for x in rota["registros"]] == [
        ("encaminhada", "Obrigado, Ana!", "manual")]
    assert rota["auditoria"][0][3] == {"loja": "Unidade Sul", "via": "nichochat"}
    # Veio da leitura automática: publicar não depende do Google responder agora.
    assert rota["lidas_no_google"] == []


async def test_avaliacao_que_nao_chegou_pelo_nichochat_nao_vai_ao_google_sem_conexao(rota):
    # A unidade tem conta_id (sobra de uma conexão antiga), mas o Google não
    # está configurado nem conectado: não tenta, e explica pelo NichoChat.
    rota["fora_do_banco"] = True
    r = await _responder("Obrigado!")
    assert r.status_code == 404
    assert "ainda não chegou" in r.json()["detail"]
    assert rota["lidas_no_google"] == [] and rota["enviados"] == []


async def test_com_conexao_direta_busca_no_google_a_que_ainda_nao_chegou(rota, monkeypatch):
    async def conectado(self):
        return {"conta_email": "x@y", "conectado_em": None}

    monkeypatch.setattr(google.Google, "configurado", property(lambda self: True))
    monkeypatch.setattr(google.Google, "conexao", conectado)
    rota["fora_do_banco"] = True
    r = await _responder("Obrigado!")
    assert r.status_code == 200, r.text
    assert rota["lidas_no_google"] == ["AbFvOqm"] and rota["gravadas"] == ["AbFvOqm"]
    assert rota["enviados"] == [("1000000000000000013", "AbFvOqm", "Obrigado!")]


async def test_rota_registra_a_falha_do_nichochat_e_mostra_a_mensagem(rota):
    rota["falha"] = "NichoChat respondeu HTTP 400: Sub flow not found"
    r = await _responder("Obrigado!")
    assert r.status_code == 400
    assert "Sub flow not found" in r.json()["detail"]
    assert [x["status"] for x in rota["registros"]] == ["erro"]
    # Commita antes de levantar: senão o rollback apagaria o registro da falha.
    assert rota["conn"].commits == 1


async def test_rota_recusa_texto_que_o_google_nao_aceitaria(rota):
    r = await _responder("ã" * 2100)  # 4.200 bytes
    assert r.status_code == 422
    assert rota["enviados"] == [] and rota["registros"] == []


async def test_rota_sem_chave_no_servidor_avisa_o_que_falta(rota, monkeypatch):
    monkeypatch.setattr(settings, "domani_api_key", "")
    r = await _responder("Obrigado!")
    assert r.status_code == 400 and "DOMANI_API_KEY" in r.json()["detail"]
    assert rota["enviados"] == []


# ------------------------------ a busca -------------------------------------

async def test_busca_dispara_o_subfluxo_novo_no_contato_do_rick(sem_pausa, monkeypatch):
    monkeypatch.setattr(settings, "nichochat_busca_google_subfluxo", "f000000s4861057")
    nicho = NichoFalso()
    await nichochat.disparar_busca_google(transporte=httpx.MockTransport(nicho))
    # Confere o contato e dispara; a busca não grava campo nenhum pelo CRM.
    assert [(c[0], c[1], c[3]) for c in nicho.chamadas] == [
        ("GET", "/subscriber/get-info-by-user-id", None),
        ("POST", "/subscriber/send-sub-flow-by-user-id",
         {"user_id": "5521999990001", "sub_flow_ns": "f000000s4861057"})]
    assert nicho.chamadas[0][2] == {"user_id": "5521999990001"}
    assert all(c[4] == "Bearer chave-teste" for c in nicho.chamadas)


async def test_busca_cria_o_contato_do_rick_se_ele_sumir(sem_pausa, monkeypatch):
    monkeypatch.setattr(settings, "nichochat_busca_google_subfluxo", "f000000s4861057")
    nicho = NichoFalso(contato=False)
    await nichochat.disparar_busca_google(transporte=httpx.MockTransport(nicho))
    assert [c[3] for c in nicho.chamadas if c[1] == "/subscriber/create"] == [
        {"phone": "+5521999990001", "first_name": "CRM", "last_name": "Busca Google"}]
    assert nicho.caminhos()[-1] == "/subscriber/send-sub-flow-by-user-id"


async def test_busca_sem_chave_nao_chama_nada(sem_pausa, monkeypatch):
    monkeypatch.setattr(settings, "domani_api_key", "")
    nicho = NichoFalso()
    with pytest.raises(nichochat.NaoConfigurado):
        await nichochat.disparar_busca_google(transporte=httpx.MockTransport(nicho))
    assert nicho.chamadas == []
