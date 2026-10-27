"""Avaliações do Google chegando pelo NichoChat, num Postgres de verdade
(migrations até a 021; as unidades do Google são criadas pelo próprio teste).

    CRM_TESTE_BANCO=1 DATABASE_URL=postgresql://... WORKER_DESLIGADO=1 \
        uv run pytest tests/test_leitura_google_banco.py

O NichoChat é um dublê; o banco é de verdade. As avaliações de teste têm id
`TESTE_*` e são apagadas no fim. Nunca aponte para o banco de produção.
"""

from __future__ import annotations

import copy
import json
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CRM_TESTE_BANCO") != "1",
    reason="precisa de CRM_TESTE_BANCO=1 e DATABASE_URL de um banco de teste",
)

ADMIN = {
    "id": str(uuid.UUID(int=1)), "email": "teste@crm.local", "papel": "admin",
    "permissoes": {"integracoes:manage", "integracoes:config"},
}
CHAVE = "chave-do-fluxo"
RIO_SUL = "1000000000000000013"
NY = "1000000000000000001"

# As unidades do Google do teste (o template não traz unidade nenhuma).
UNIDADES = [
    (NY, "Praca Central Hall"),
    ("1000000000000000006", "Shopping Centro (Recife)"),
    ("1000000000000000007", "Shopping Sol"),
    ("1000000000000000010", "Paraíso"),
    (RIO_SUL, "Unidade Sul"),
]

# O JSON que o fluxo de busca devolve.
JSON_DO_FLUXO = {"status": "ok", "result": [
    {"unidade": "ShoppingCentroRecife", "idUnidade": "1000000000000000006", "comentario": "",
     "notaReview": "FOUR", "reviewId": "TESTE_BARRA_DENTRO", "displayName": "Cliente Teste Barra",
     "dataHora": "2026-10-13T15:28:00.000000Z"},
    {"unidade": "PracaCentralHall", "idUnidade": NY,
     "comentario": "(Translated by Google) Great pizza and excellent service!\n\n(Original)\n"
                   "Pizza ótima e atendimento excelente!",
     "notaReview": "FIVE", "reviewId": "TESTE_NY_DENTRO", "displayName": "Cliente Teste NY",
     "dataHora": "2026-10-13T15:20:00.000000Z"},
    {"unidade": "ShoppingSol", "idUnidade": "1000000000000000007",
     "comentario": "(Translated by Google) Loved the service from Ana!\n\n(Original)\n"
                   "Amei o atendimento da Ana!",
     "notaReview": "FIVE", "reviewId": "TESTE_PLAZA_DENTRO", "displayName": "Cliente Teste Plaza",
     "dataHora": "2026-10-13T15:12:00.000000Z"},
    {"unidade": "UnidadeSul", "idUnidade": RIO_SUL,
     "comentario": "(Translated by Google) The pizza arrived cold and the order took more than "
                   "an hour.\n\n(Original)\nA pizza chegou fria e o pedido demorou mais de uma hora.",
     "notaReview": "ONE", "reviewId": "TESTE_UNIDADESUL_DENTRO", "displayName": "Cliente Teste Unidade Sul",
     "dataHora": "2026-10-13T15:05:00.000000Z"},
], "executionTime": "2ms"}


def _sql(q: str, args=()):
    import psycopg
    from psycopg.rows import dict_row

    from app.config import settings

    with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=True) as c:
        cur = c.execute(q, args)
        return cur.fetchall() if cur.description else None


def _limpar():
    _sql("DELETE FROM integra.avaliacoes_google WHERE review_id LIKE 'TESTE%%'")
    _sql("DELETE FROM integra.avaliacoes_google_partes WHERE review_id LIKE 'TESTE%%'")
    _sql("DELETE FROM integra.avaliacao_respostas WHERE review_id LIKE 'TESTE%%'")
    _sql("DELETE FROM integra.google_leitura")
    _sql("DELETE FROM integra.agente_execucoes WHERE origem = 'google'")
    _sql("DELETE FROM integra.webhook_eventos WHERE origem = 'nichochat'")
    _sql("""UPDATE integra.agente_estado
               SET rodando_desde = NULL, ultimo_disparo_em = NULL, ultimo_disparo_erro = NULL
             WHERE origem = 'google'""")


@pytest.fixture
def cliente(monkeypatch):
    from fastapi.testclient import TestClient

    from app.auth import current_user
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "webhook_google_key", CHAVE)
    monkeypatch.setattr(settings, "domani_api_url", "https://nicho.teste/api")
    monkeypatch.setattr(settings, "domani_api_key", "k")
    monkeypatch.setattr(settings, "nichochat_contato_user_id", "5521999990001")
    monkeypatch.setattr(settings, "nichochat_busca_google_subfluxo", "f000000s4861057")
    monkeypatch.setattr(settings, "nichochat_resposta_contato_user_id", "5531999990002")
    monkeypatch.setattr(settings, "nichochat_resposta_google_subfluxo", "f000000s4868429")
    _limpar()
    for loja_id, nome in UNIDADES:
        _sql("""INSERT INTO integra.lojas (origem, loja_id, nome) VALUES ('google', %s, %s)
                ON CONFLICT (origem, loja_id) DO NOTHING""", (loja_id, nome))
    app.dependency_overrides[current_user] = lambda: ADMIN
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _limpar()
    _sql("DELETE FROM integra.lojas WHERE origem = 'google' AND loja_id = ANY(%s)",
         ([u[0] for u in UNIDADES],))


def _entregar(cliente, corpo, chave=CHAVE, como_texto=False):
    dados = json.dumps(corpo) if not isinstance(corpo, str) else corpo
    if como_texto:  # o NichoChat pode mandar a variável já serializada
        dados = json.dumps(dados)
    return cliente.post("/webhooks/nichochat/avaliacoes-google", content=dados,
                        headers={"X-API-Key": chave, "Content-Type": "application/json"})


def _guardadas() -> dict[str, dict]:
    return {r["review_id"]: r for r in _sql(
        "SELECT * FROM integra.avaliacoes_google WHERE review_id LIKE 'TESTE%%'")}


# ------------------------------ o recebimento -------------------------------

def test_json_do_fluxo_entra_na_fila_da_unidade_certa(cliente):
    r = _entregar(cliente, JSON_DO_FLUXO)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert (corpo["recebidas"], corpo["novas"], corpo["ignoradas"]) == (4, 4, [])

    g = _guardadas()
    assert g["TESTE_UNIDADESUL_DENTRO"]["loja_id"] == RIO_SUL
    assert g["TESTE_UNIDADESUL_DENTRO"]["nota"] == 1
    # Fica o que o cliente escreveu, sem a tradução automática.
    assert g["TESTE_UNIDADESUL_DENTRO"]["comentario"] == "A pizza chegou fria e o pedido demorou mais de uma hora."
    assert g["TESTE_NY_DENTRO"]["autor"] == "Cliente Teste NY"
    assert g["TESTE_BARRA_DENTRO"]["comentario"] is None
    assert all(v["resposta"] is None for v in g.values())

    # Todas as unidades ficam como lidas, mesmo sem avaliação nova.
    assert _sql("SELECT count(*) AS n FROM integra.google_leitura WHERE lida_em IS NOT NULL")[0]["n"] == len(UNIDADES)
    ev = _sql("SELECT status FROM integra.webhook_eventos WHERE origem='nichochat'")
    assert [e["status"] for e in ev] == ["processado"]

    # A mesma avaliação chegando de novo (um "Ler agora" no meio, uma
    # repetição do NichoChat) não duplica.
    assert _entregar(cliente, JSON_DO_FLUXO).json()["novas"] == 0
    assert len(_guardadas()) == 4


def test_aceita_lista_pura_e_corpo_serializado_como_texto(cliente):
    lista = copy.deepcopy(JSON_DO_FLUXO["result"][:1])
    assert _entregar(cliente, lista).json()["novas"] == 1
    outra = copy.deepcopy(JSON_DO_FLUXO)
    assert _entregar(cliente, outra, como_texto=True).json()["novas"] == 3


def test_unidade_pelo_nome_quando_falta_o_id_e_desconhecida_e_ignorada(cliente):
    corpo = {"result": [
        {"unidade": "Paraiso", "idUnidade": "", "notaReview": "TWO",
         "reviewId": "TESTE_PARAISO", "dataHora": "2026-10-13T15:00:00Z"},
        {"unidade": "Filial Nova", "idUnidade": "999", "notaReview": "FIVE",
         "reviewId": "TESTE_NOVA", "dataHora": "2026-10-13T15:00:00Z"},
        {"unidade": "UnidadeSul", "idUnidade": RIO_SUL, "notaReview": "FIVE"},
    ]}
    r = _entregar(cliente, corpo).json()
    assert r["novas"] == 1
    assert _guardadas()["TESTE_PARAISO"]["loja_id"] == "1000000000000000010"
    assert [i["reviewId"] for i in r["ignoradas"]] == ["TESTE_NOVA", None]


def test_resposta_ja_vista_nao_e_apagada_por_entrega_sem_resposta(cliente):
    item = copy.deepcopy(JSON_DO_FLUXO["result"][3])
    _entregar(cliente, [{**item, "resposta": "Sentimos muito!"}])
    assert _guardadas()["TESTE_UNIDADESUL_DENTRO"]["resposta"] == "Sentimos muito!"
    # A próxima entrega traz a mesma avaliação sem resposta (o fluxo não manda).
    _entregar(cliente, [item])
    assert _guardadas()["TESTE_UNIDADESUL_DENTRO"]["resposta"] == "Sentimos muito!"


def test_resposta_encaminhada_que_volta_publicada_vira_enviada(cliente):
    item = copy.deepcopy(JSON_DO_FLUXO["result"][3])
    _entregar(cliente, [item])
    _sql("""INSERT INTO integra.avaliacao_respostas
              (origem, review_id, loja_id, nota, resposta, status, via)
            VALUES ('google', 'TESTE_UNIDADESUL_DENTRO', %s, 1, %s, 'encaminhada', 'manual')""",
         (RIO_SUL, "Sentimos muito, Ana.\nVolte sempre."))
    r = _entregar(cliente, [{**item, "resposta": "Sentimos muito, Ana. Volte sempre."}]).json()
    assert r["confirmadas"] == 1
    assert _sql("SELECT status FROM integra.avaliacao_respostas "
                "WHERE review_id='TESTE_UNIDADESUL_DENTRO'")[0]["status"] == "enviada"


def test_chave_errada_recusa_e_formato_estranho_explica(cliente):
    assert _entregar(cliente, JSON_DO_FLUXO, chave="outra").status_code == 401
    assert _entregar(cliente, JSON_DO_FLUXO, chave="").status_code == 401
    r = _entregar(cliente, {"status": "ok", "executionTime": "2ms"})
    assert r.status_code == 422 and "result" in r.json()["detail"]
    assert _guardadas() == {}


def test_busca_sem_novidade_marca_as_unidades_como_lidas(cliente):
    # O fluxo manda o bloco vazio quando não achou nada; o corpo pode chegar
    # vazio ou como "[]".
    for corpo in ("", "[]"):
        _sql("DELETE FROM integra.google_leitura")
        r = _entregar(cliente, corpo)
        assert r.status_code == 200, r.text
        assert (r.json()["recebidas"], r.json()["novas"]) == (0, 0)
        assert _sql("SELECT count(*) AS n FROM integra.google_leitura "
                    "WHERE lida_em IS NOT NULL")[0]["n"] == len(UNIDADES)
    assert _guardadas() == {}


def test_bloco_do_fluxo_novo_e_comentario_em_pedacos(cliente):
    # Como o fluxo novo manda: um POST por bloco (a lista pura), e o comentário
    # que não cabe num bloco em pedaços, um POST cada, fora de ordem até.
    base = {k: v for k, v in JSON_DO_FLUXO["result"][3].items() if k != "comentario"}
    base["reviewId"] = "TESTE_LONGO"
    original = "A pizza chegou fria. " * 60
    texto = "(Translated by Google) The pizza arrived cold. " * 60 + "\n\n(Original)\n" + original
    cortes = [texto[:1500], texto[1500:2800], texto[2800:]]
    pedacos = [[{**base, "comentario": c, "parte": i + 1, "totalPartes": 3,
                 "url": "https://business.google.com/n/x"}] for i, c in enumerate(cortes)]

    r = _entregar(cliente, pedacos[1]).json()
    assert r["novas"] == 1 and r["aguardando_partes"] == ["TESTE_LONGO"]
    assert _guardadas()["TESTE_LONGO"]["comentario"].endswith("[…]")

    r = _entregar(cliente, pedacos[2]).json()
    assert r["novas"] == 0 and r["aguardando_partes"] == ["TESTE_LONGO"]

    r = _entregar(cliente, pedacos[0]).json()
    assert "aguardando_partes" not in r
    g = _guardadas()["TESTE_LONGO"]
    assert g["comentario"] == original.strip() and g["loja_id"] == RIO_SUL
    # Os pedaços não ficam guardados depois de juntados.
    assert _sql("SELECT count(*) AS n FROM integra.avaliacoes_google_partes "
                "WHERE review_id = 'TESTE_LONGO'")[0]["n"] == 0

    # Uma avaliação curta no bloco seguinte entra normalmente.
    r = _entregar(cliente, [JSON_DO_FLUXO["result"][0]]).json()
    assert r["novas"] == 1


# ------------------------------- o disparo ---------------------------------

async def _disparo(monkeypatch, falha: str | None = None):
    import psycopg
    from psycopg.rows import dict_row

    from app.config import settings
    from app.services.integracoes import leitor_google, nichochat

    chamadas = []

    async def disparar(**_k):
        chamadas.append(settings.nichochat_busca_google_subfluxo)
        if falha:
            raise nichochat.ErroNichoChat(falha)

    monkeypatch.setattr(nichochat, "disparar_busca_google", disparar)
    async with await psycopg.AsyncConnection.connect(
            settings.database_url, row_factory=dict_row) as conn:
        return await leitor_google.rodar(conn), chamadas


async def test_disparo_pede_a_busca_e_a_tela_mostra_se_falhou(cliente, monkeypatch):
    r, chamadas = await _disparo(monkeypatch)
    assert r == {"disparado": True, "erro": None} and chamadas == ["f000000s4861057"]
    estado = _sql("SELECT * FROM integra.agente_estado WHERE origem='google'")[0]
    assert estado["ultimo_disparo_em"] and estado["ultimo_disparo_erro"] is None
    assert estado["rodando_desde"] is None
    # O fluxo só faz POST quando há avaliação nova: disparo aceito já conta
    # como as unidades lidas.
    lidas = "SELECT count(*) AS n FROM integra.google_leitura WHERE lida_em IS NOT NULL"
    assert _sql(lidas)[0]["n"] == len(UNIDADES)

    _sql("DELETE FROM integra.google_leitura")
    r, _ = await _disparo(monkeypatch, falha="NichoChat respondeu HTTP 400: Sub flow not found")
    assert r["disparado"] is False
    assert _sql(lidas)[0]["n"] == 0
    resumo = cliente.get("/integracoes/google/resumo").json()
    assert "Sub flow not found" in resumo["erro"]


async def test_sem_chave_do_nichochat_nao_dispara(cliente, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "domani_api_key", "")
    r, chamadas = await _disparo(monkeypatch)
    assert r is None and chamadas == []


# --------------------------- as telas leem do banco --------------------------

def test_visao_geral_e_fila_mostram_o_que_chegou(cliente):
    sem_leitura = cliente.get(f"/integracoes/google/lojas/{RIO_SUL}/avaliacoes").json()
    assert "ainda não chegaram" in sem_leitura["erro"]

    _entregar(cliente, JSON_DO_FLUXO)
    # TESTE_NY_DENTRO acabou de ser encaminhada ao NichoChat: sai da conta.
    _sql("""INSERT INTO integra.avaliacao_respostas
              (origem, review_id, loja_id, nota, resposta, status, via)
            VALUES ('google', 'TESTE_NY_DENTRO', %s, 5, 'Obrigado!', 'encaminhada', 'manual')""", (NY,))

    resumo = cliente.get("/integracoes/google/resumo").json()
    linhas = {l["loja_id"]: l for l in resumo["lojas"]}
    assert linhas[RIO_SUL]["pendentes"] >= 1 and linhas[RIO_SUL]["erro"] is None
    assert resumo["ultima_execucao"]["encontradas"] == 4
    assert resumo["erro"] is None and resumo["leitura"]["intervalo_min"] == 29

    fila = cliente.get(f"/integracoes/google/lojas/{RIO_SUL}/avaliacoes").json()
    item = next(a for a in fila["avaliacoes"] if a["id"] == "TESTE_UNIDADESUL_DENTRO")
    assert item["nota"] == 1 and not item["respondida"]

    ny = cliente.get(f"/integracoes/google/lojas/{NY}/avaliacoes").json()
    item = next(a for a in ny["avaliacoes"] if a["id"] == "TESTE_NY_DENTRO")
    assert item["encaminhamento"] == "aguardando" and item["respondida"]


# --------------------- a confirmação da resposta (opção A) -------------------

def _confirmar(cliente, corpo, chave=CHAVE):
    return cliente.post("/webhooks/nichochat/resposta-google", content=json.dumps(corpo),
                        headers={"X-API-Key": chave, "Content-Type": "application/json"})


def _encaminhar(review_id: str, loja: str, texto: str):
    _sql("""INSERT INTO integra.avaliacao_respostas
              (origem, review_id, loja_id, nota, resposta, status, via)
            VALUES ('google', %s, %s, 1, %s, 'encaminhada', 'manual')""", (review_id, loja, texto))


def _registro(review_id: str) -> dict:
    return _sql("SELECT status, erro FROM integra.avaliacao_respostas WHERE review_id=%s",
                (review_id,))[0]


def test_confirmacao_tira_da_fila_e_marca_publicada(cliente):
    _entregar(cliente, JSON_DO_FLUXO)
    _encaminhar("TESTE_UNIDADESUL_DENTRO", RIO_SUL, "Sentimos muito, Ana.\nVolte sempre.")

    # Antes do aviso: na fila como "enviada ao NichoChat".
    fila = cliente.get(f"/integracoes/google/lojas/{RIO_SUL}/avaliacoes").json()
    assert next(a for a in fila["avaliacoes"]
                if a["id"] == "TESTE_UNIDADESUL_DENTRO")["encaminhamento"] == "aguardando"

    # O subfluxo publica e avisa (o NichoChat pode juntar a quebra de linha).
    r = _confirmar(cliente, {"reviewId": "TESTE_UNIDADESUL_DENTRO", "idUnidade": RIO_SUL,
                             "resposta": "Sentimos muito, Ana. Volte sempre."})
    assert r.status_code == 200, r.text
    assert r.json()["avisos"] == [{"reviewId": "TESTE_UNIDADESUL_DENTRO", "resultado": "publicada"}]
    assert _registro("TESTE_UNIDADESUL_DENTRO")["status"] == "enviada"
    assert _guardadas()["TESTE_UNIDADESUL_DENTRO"]["resposta"] == "Sentimos muito, Ana. Volte sempre."
    fila = cliente.get(f"/integracoes/google/lojas/{RIO_SUL}/avaliacoes").json()
    assert "TESTE_UNIDADESUL_DENTRO" not in [a["id"] for a in fila["avaliacoes"]]


def test_confirmacao_com_json_quebrado_pela_resposta_vale_pelo_review_id(cliente):
    # O fluxo do NichoChat cola a resposta entre aspas no corpo: com quebra de
    # linha e aspas no texto, o JSON chega inválido.
    _entregar(cliente, JSON_DO_FLUXO)
    texto = 'Sentimos muito, Ana.\nA "Casa" vai melhorar.'
    _encaminhar("TESTE_UNIDADESUL_DENTRO", RIO_SUL, texto)
    corpo = ('{\n  "reviewId": "TESTE_UNIDADESUL_DENTRO",\n  "idUnidade": "' + RIO_SUL + '",\n'
             '  "resposta": "' + texto + '"\n}')
    with pytest.raises(ValueError):
        json.loads(corpo)
    r = cliente.post("/webhooks/nichochat/resposta-google", content=corpo.encode(),
                     headers={"X-API-Key": CHAVE, "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["avisos"] == [{"reviewId": "TESTE_UNIDADESUL_DENTRO", "resultado": "publicada"}]
    assert _registro("TESTE_UNIDADESUL_DENTRO")["status"] == "enviada"
    # Vale o texto que o CRM mandou.
    assert _guardadas()["TESTE_UNIDADESUL_DENTRO"]["resposta"] == texto

    # Corpo quebrado sem nenhuma resposta esperando não marca nada.
    r = cliente.post("/webhooks/nichochat/resposta-google",
                     content=corpo.replace("TESTE_UNIDADESUL_DENTRO", "TESTE_OUTRA").encode(),
                     headers={"X-API-Key": CHAVE, "Content-Type": "application/json"})
    assert r.json()["avisos"][0]["resultado"] == "ignorado"


def test_aviso_de_falha_devolve_para_a_fila_com_o_motivo(cliente):
    _entregar(cliente, JSON_DO_FLUXO)
    _encaminhar("TESTE_UNIDADESUL_DENTRO", RIO_SUL, "Oi")
    r = _confirmar(cliente, {"reviewId": "TESTE_UNIDADESUL_DENTRO", "status": "erro",
                             "erro": "review not found"}).json()
    assert r["avisos"][0]["resultado"] == "falha registrada"
    reg = _registro("TESTE_UNIDADESUL_DENTRO")
    assert reg["status"] == "erro" and "review not found" in reg["erro"]
    fila = cliente.get(f"/integracoes/google/lojas/{RIO_SUL}/avaliacoes").json()
    item = next(a for a in fila["avaliacoes"] if a["id"] == "TESTE_UNIDADESUL_DENTRO")
    assert not item["respondida"]


def test_resposta_da_automacao_tambem_tira_da_fila(cliente):
    # Avaliação que o CRM não encaminhou (a automação de 4 e 5 respondeu).
    _entregar(cliente, JSON_DO_FLUXO)
    r = _confirmar(cliente, {"result": [{"reviewId": "TESTE_NY_DENTRO", "resposta": "Obrigado!"}]})
    assert r.json()["avisos"][0]["resultado"] == "resposta gravada"
    assert _guardadas()["TESTE_NY_DENTRO"]["resposta"] == "Obrigado!"


def test_confirmacao_exige_a_chave_e_explica_o_formato(cliente):
    assert _confirmar(cliente, {"reviewId": "x", "resposta": "y"}, chave="outra").status_code == 401
    assert _confirmar(cliente, "isto não é json").status_code == 422
    r = _confirmar(cliente, {"reviewId": "TESTE_X"}).json()
    assert r["avisos"][0]["resultado"] == "ignorado"


# ------------------- configuração: o vínculo é o NichoChat -------------------

def test_configuracao_mostra_a_ligacao_com_o_nichochat(cliente):
    antes = cliente.get("/integracoes").json()["google"]["nichochat"]
    assert antes["api_configurada"] and antes["entrega_configurada"]
    assert antes["contato_user_id"] == "5521999990001"
    assert antes["subfluxo_busca"] == "f000000s4861057"
    assert antes["url_entrega"].endswith("/api/webhooks/nichochat/avaliacoes-google")
    assert antes["ultima_entrega_em"] is None

    unidades = cliente.get("/integracoes/google/lojas").json()
    assert all(u["lida_em"] is None for u in unidades)

    _entregar(cliente, JSON_DO_FLUXO)
    depois = cliente.get("/integracoes").json()["google"]["nichochat"]
    assert depois["ultima_entrega_em"] is not None
    # Sem conexão direta com o Google, toda unidade ativa fica "lida", não "sem vínculo".
    unidades = cliente.get("/integracoes/google/lojas").json()
    assert all(u["lida_em"] for u in unidades if u["ativo"])


def test_avaliacao_que_nao_chegou_explica_sem_falar_em_conta_google(cliente):
    r = cliente.post(f"/integracoes/google/lojas/{RIO_SUL}/avaliacoes/NAO_EXISTE/sugerir")
    assert r.status_code == 404
    # Fala a língua da atendente: o que fazer, sem falar em fluxo nem em conta.
    detalhe = r.json()["detail"]
    assert "ainda não chegou" in detalhe and "Ler agora" in detalhe
    assert "conta Google" not in detalhe and "NichoChat" not in detalhe
