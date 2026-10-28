"""Números do topo da tela de E-mail e métricas por linha da tabela.

    CRM_TESTE_BANCO=1 DATABASE_URL=postgresql://... WORKER_DESLIGADO=1 \
        uv run pytest tests/test_email_resumo_banco.py

* A tabela de campanhas traz abertura e cliques de cada uma, iguais aos do
  relatório da campanha (mesma view).
* O resumo conta só o que SAIU nos últimos N dias, e as taxas são sobre esses
  enviados.
* A base se divide em fatias que não se sobrepõem: recebem, sem autorização,
  saíram da lista, sem e-mail — e "recebem" é o mesmo número da prévia de
  "Toda a base".
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CRM_TESTE_BANCO") != "1",
    reason="precisa de CRM_TESTE_BANCO=1 e DATABASE_URL de um banco de teste",
)

ADMIN = {
    "id": str(uuid.UUID(int=1)), "email": "teste@crm.local", "papel": "admin",
    "permissoes": {"campanhas:manage", "campanhas:send", "contatos:read"},
}
DOMINIO = "teste-resumo.com"


def _sql(q: str, args=()):
    import psycopg
    from psycopg.rows import dict_row

    from app.config import settings

    with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=True) as c:
        cur = c.execute(q, args)
        return cur.fetchall() if cur.description else None


def _limpar():
    _sql("DELETE FROM email.campaigns WHERE nome LIKE 'TESTE RESUMO %%'")
    _sql("DELETE FROM email.templates WHERE nome LIKE 'TESTE RESUMO %%'")
    _sql("DELETE FROM email.suppressions WHERE email LIKE %s", (f"%@{DOMINIO}",))
    _sql("DELETE FROM crm.contatos WHERE email LIKE %s OR nome LIKE 'TESTE RESUMO %%'",
         (f"%@{DOMINIO}",))


@pytest.fixture()
def cliente():
    from fastapi.testclient import TestClient

    from app.auth import current_user
    from app.main import app

    _limpar()
    app.dependency_overrides[current_user] = lambda: ADMIN
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _limpar()


def _campanha(nome: str, status: str = "enviada") -> str:
    tpl = _sql("INSERT INTO email.templates (nome, assunto, html) "
               "VALUES (%s, 'Oi', '<p>oi</p>') RETURNING id", (f"TESTE RESUMO {nome}",))[0]["id"]
    return _sql("""INSERT INTO email.campaigns (nome, template_id, assunto, status, publico)
                   VALUES (%s, %s, 'Oi', %s, 0) RETURNING id""",
                (f"TESTE RESUMO {nome}", tpl, status))[0]["id"]


def _destinatario(camp, i: int, status="enviado", dias_atras: int = 1, eventos=()):
    rid = _sql(
        """INSERT INTO email.recipients (campaign_id, email, status, sent_at)
           VALUES (%s, %s, %s,
                   CASE WHEN %s = 'enviado' THEN now() - make_interval(days => %s) END)
           RETURNING id""",
        (camp, f"r{i}-{camp}@{DOMINIO}", status, status, dias_atras))[0]["id"]
    for tipo in eventos:
        _sql("INSERT INTO email.events (recipient_id, tipo) VALUES (%s, %s)", (rid, tipo))
    return rid


def test_tabela_traz_abertura_e_cliques_iguais_ao_relatorio(cliente):
    camp = _campanha("tabela")
    # 4 enviados: 2 abriram (um abriu duas vezes), 1 clicou; 1 na fila, 1 preso.
    _destinatario(camp, 1, eventos=("open", "open", "click"))
    _destinatario(camp, 2, eventos=("open",))
    _destinatario(camp, 3)
    _destinatario(camp, 4)
    _destinatario(camp, 5, status="pendente")
    _destinatario(camp, 6, status="processando")

    linha = {c["id"]: c for c in cliente.get("/email/campanhas").json()}[str(camp)]
    rel = cliente.get(f"/email/campanhas/{camp}").json()["stats"]

    assert linha["enviados"] == 4
    s = linha["stats"]
    assert (s["enviados"], s["aberturas"], s["cliques"]) == (4, 2, 1)
    assert (s["pendentes"], s["processando"]) == (1, 1)
    assert float(s["taxa_abertura"]) == 50.0
    assert float(s["taxa_clique"]) == 25.0
    for chave in ("enviados", "aberturas", "cliques", "pendentes"):
        assert s[chave] == rel[chave]
    assert float(s["taxa_abertura"]) == float(rel["taxa_abertura"])


def test_campanha_sem_envio_vem_sem_taxa(cliente):
    camp = _campanha("rascunho", status="rascunho")
    linha = {c["id"]: c for c in cliente.get("/email/campanhas").json()}[str(camp)]
    assert linha["stats"]["enviados"] == 0
    assert linha["stats"]["taxa_abertura"] is None


def test_resumo_conta_so_o_que_saiu_no_periodo(cliente):
    antes = cliente.get("/email/resumo", params={"dias": 30}).json()

    recente = _campanha("recente")
    _destinatario(recente, 1, dias_atras=2, eventos=("open", "click"))
    _destinatario(recente, 2, dias_atras=3, eventos=("open", "unsubscribe"))
    _destinatario(recente, 3, dias_atras=3)
    _destinatario(recente, 4, status="pendente")
    antiga = _campanha("antiga")
    _destinatario(antiga, 1, dias_atras=45, eventos=("open",))

    r = cliente.get("/email/resumo", params={"dias": 30}).json()
    assert r["dias"] == 30
    assert r["enviados"] - antes["enviados"] == 3
    assert r["campanhas"] - antes["campanhas"] == 1
    assert r["aberturas"] - antes["aberturas"] == 2
    assert r["cliques"] - antes["cliques"] == 1
    assert r["descadastros"] - antes["descadastros"] == 1
    if antes["enviados"] == 0:
        assert float(r["taxa_abertura"]) == pytest.approx(66.7)
        assert float(r["taxa_clique"]) == pytest.approx(33.3)
    # Vazio só quando CAMPANHA_FROM_EMAIL não está no .env (banco de teste).
    assert isinstance(r["remetente"], str)


def test_base_em_fatias_que_batem_com_a_previa(cliente):
    antes = cliente.get("/email/resumo").json()["base"]

    def contato(nome, email, opt_in):
        _sql("INSERT INTO crm.contatos (nome, email, opt_in_email, origem) "
             "VALUES (%s, %s, %s, 'Importação')", (f"TESTE RESUMO {nome}", email, opt_in))

    contato("a", f"a@{DOMINIO}", None)    # nunca perguntado: recebe
    contato("b", f"b@{DOMINIO}", True)    # autorizou: recebe
    contato("c", f"c@{DOMINIO}", False)   # não autorizou
    contato("d", f"d@{DOMINIO}", True)    # saiu da lista (abaixo)
    contato("e", f"e@{DOMINIO}", False)   # não autorizou E saiu: conta só em "saíram"
    contato("f", None, None)              # sem e-mail
    _sql("INSERT INTO email.suppressions (email, motivo) VALUES (%s, 'descadastro'), (%s, 'bounce')",
         (f"d@{DOMINIO}", f"e@{DOMINIO}"))

    depois = cliente.get("/email/resumo").json()["base"]
    delta = {k: depois[k] - antes[k] for k in depois}
    assert delta == {"recebem": 2, "sem_autorizacao": 1, "sairam": 2, "sem_email": 1}

    previa = cliente.post("/email/segmentos/previa", json={}).json()
    assert previa["com_email"] == depois["recebem"]
