"""Campanha agendada: sai na hora, só para o público escolhido, uma vez só — e
quem sai da base depois de entrar na fila não recebe.

    CRM_TESTE_BANCO=1 DATABASE_URL=postgresql://... WORKER_DESLIGADO=1 \
        uv run pytest tests/test_disparo_agendado_banco.py

O caso que motivou o segundo teste: com o aquecimento de domínio (300/dia) e
campanhas agendadas com dias de antecedência, a fila de uma campanha fica
montada por dias. Quem se descadastra de OUTRA campanha nesse meio-tempo, dá
bounce ou é excluído do CRM continuava na fila — e recebia. Descadastro tem
que valer na hora, não só para campanhas criadas depois dele.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CRM_TESTE_BANCO") != "1",
    reason="precisa de CRM_TESTE_BANCO=1 e DATABASE_URL de um banco de teste",
)

ADMIN = {
    "id": str(uuid.UUID(int=1)), "email": "teste@crm.local", "papel": "admin",
    "permissoes": {"campanhas:manage", "campanhas:send", "contatos:read"},
}
DOMINIO = "teste-agenda.com"
TAG = "agenda-teste"


def _sql(q: str, args=()):
    import psycopg
    from psycopg.rows import dict_row

    from app.config import settings

    with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=True) as c:
        cur = c.execute(q, args)
        return cur.fetchall() if cur.description else None


def _limpar():
    _sql("DELETE FROM email.campaigns WHERE nome LIKE 'TESTE AGENDA %%'")
    _sql("DELETE FROM email.templates WHERE nome LIKE 'TESTE AGENDA %%'")
    _sql("DELETE FROM email.suppressions WHERE email LIKE %s", (f"%@{DOMINIO}",))
    _sql("DELETE FROM crm.contatos WHERE email LIKE %s", (f"%@{DOMINIO}",))


def _contato(nome: str, tags=(TAG,), opt_in=True) -> int:
    return _sql(
        """INSERT INTO crm.contatos (nome, email, tags_manuais, opt_in_email, origem)
           VALUES (%s, %s, %s, %s, 'Importação') RETURNING id""",
        (nome, f"{nome}@{DOMINIO}", list(tags), opt_in),
    )[0]["id"]


def _status(camp: str) -> dict[str, str]:
    rows = _sql("SELECT email, status FROM email.recipients WHERE campaign_id = %s", (camp,))
    return {r["email"].split("@")[0]: r["status"] for r in rows}


def _rodar_agenda():
    from app.services import agenda

    asyncio.run(agenda.rodar())


@pytest.fixture()
def cliente(monkeypatch):
    from fastapi.testclient import TestClient

    from app.auth import current_user
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "email_dry_run", True)
    monkeypatch.setattr(settings, "smtp_intervalo_seg", 0)
    _limpar()
    app.dependency_overrides[current_user] = lambda: ADMIN
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _limpar()


def _template() -> str:
    return str(_sql("INSERT INTO email.templates (nome, assunto, html) "
                    "VALUES ('TESTE AGENDA tpl', 'Oi', '<p>oi {{nome}}</p>') RETURNING id")[0]["id"])


def _agendar(cliente, nome: str, quando: datetime) -> str:
    r = cliente.post("/email/campanhas", json={
        "nome": nome, "template_id": _template(), "assunto": "Oi",
        "segmento": {"tags": [TAG]}, "agendada_para": quando.isoformat(),
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "agendada"
    return r.json()["id"]


def test_agendada_sai_na_hora_so_para_o_publico_escolhido_e_uma_vez(cliente):
    _contato("ana")
    _contato("bia")
    _contato("caio", opt_in=False)        # recusou e-mail: nunca entra
    _contato("duda")
    _sql("INSERT INTO email.suppressions (email, motivo) VALUES (%s, 'descadastro')",
         (f"duda@{DOMINIO}",))             # descadastrada antes: nunca entra
    _contato("edu", tags=("outra",))      # fora do filtro

    camp = _agendar(cliente, "TESTE AGENDA 1", datetime.now(timezone.utc) + timedelta(hours=2))
    assert _status(camp) == {"ana": "pendente", "bia": "pendente"}

    # O botão "Disparar" não antecipa campanha agendada.
    assert cliente.post(f"/email/campanhas/{camp}/enviar").status_code == 409

    # O agendador antes da hora não manda nada.
    _rodar_agenda()
    assert _status(camp) == {"ana": "pendente", "bia": "pendente"}
    assert _sql("SELECT status FROM email.campaigns WHERE id = %s", (camp,))[0]["status"] == "agendada"

    # Chegou a hora.
    _sql("UPDATE email.campaigns SET agendada_para = now() - interval '1 minute' WHERE id = %s",
         (camp,))
    _rodar_agenda()
    assert _status(camp) == {"ana": "enviado", "bia": "enviado"}
    assert _sql("SELECT status FROM email.campaigns WHERE id = %s", (camp,))[0]["status"] == "enviada"

    # Rodar de novo não reenvia.
    _rodar_agenda()
    enviados = _sql("SELECT count(*) AS n FROM email.recipients "
                    "WHERE campaign_id = %s AND status = 'enviado'", (camp,))[0]["n"]
    assert enviados == 2


def test_quem_sai_da_base_depois_de_entrar_na_fila_nao_recebe(cliente):
    _contato("ana")
    bia = _contato("bia")
    caio = _contato("caio")
    _contato("duda")

    camp = _agendar(cliente, "TESTE AGENDA 2", datetime.now(timezone.utc) + timedelta(days=1))
    assert set(_status(camp)) == {"ana", "bia", "caio", "duda"}

    # Entre o agendamento e o envio:
    _sql("INSERT INTO email.suppressions (email, motivo) VALUES (%s, 'descadastro')",
         (f"ana@{DOMINIO}",))                                        # descadastrou de outra campanha
    _sql("UPDATE crm.contatos SET deleted_at = now() WHERE id = %s", (bia,))   # excluída no CRM
    _sql("UPDATE crm.contatos SET opt_in_email = false WHERE id = %s", (caio,))  # recusou

    _sql("UPDATE email.campaigns SET agendada_para = now() - interval '1 minute' WHERE id = %s",
         (camp,))
    _rodar_agenda()

    assert _status(camp) == {
        "ana": "suprimido", "bia": "suprimido", "caio": "suprimido", "duda": "enviado",
    }
