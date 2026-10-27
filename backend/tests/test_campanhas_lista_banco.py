"""A lista de campanhas mostra o mesmo "Enviados" que o relatório.

    CRM_TESTE_BANCO=1 DATABASE_URL=postgresql://... WORKER_DESLIGADO=1 \
        uv run pytest tests/test_campanhas_lista_banco.py

O caso real: a campanha "09.10" aparecia ENVIANDO com 0 enviados na lista,
enquanto o relatório já mostrava quem recebeu. A coluna da campanha só era
gravada no fim da leva — durante o envio, ou com a leva interrompida por um
reinício da API, ela ficava em 0.
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


def _sql(q: str, args=()):
    import psycopg
    from psycopg.rows import dict_row

    from app.config import settings

    with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=True) as c:
        cur = c.execute(q, args)
        return cur.fetchall() if cur.description else None


def _limpar():
    _sql("DELETE FROM email.campaigns WHERE nome LIKE 'TESTE LISTA %%'")
    _sql("DELETE FROM email.templates WHERE nome LIKE 'TESTE LISTA %%'")


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


def test_lista_conta_os_enviados_mesmo_com_a_leva_no_meio(cliente):
    tpl = _sql("INSERT INTO email.templates (nome, assunto, html) "
               "VALUES ('TESTE LISTA tpl', 'Oi', '<p>oi</p>') RETURNING id")[0]["id"]
    # Leva interrompida: 3 já saíram, 1 ficou preso, 2 na fila — e a coluna
    # da campanha ainda em 0, como a leva deixou.
    camp = _sql("""INSERT INTO email.campaigns (nome, template_id, assunto, status, publico, enviados)
                   VALUES ('TESTE LISTA 09.10', %s, 'Oi', 'enviando', 6, 0) RETURNING id""",
                (tpl,))[0]["id"]
    for i, status in enumerate(["enviado", "enviado", "enviado", "processando", "pendente", "pendente"]):
        _sql("INSERT INTO email.recipients (campaign_id, email, status, sent_at) "
             "VALUES (%s, %s, %s, CASE WHEN %s = 'enviado' THEN now() END)",
             (camp, f"lista{i}@teste-lista.com", status, status))

    lista = {c["id"]: c for c in cliente.get("/email/campanhas").json()}
    rel = cliente.get(f"/email/campanhas/{camp}").json()
    assert lista[str(camp)]["enviados"] == 3
    assert lista[str(camp)]["enviados"] == rel["stats"]["enviados"]
