"""Registro das respostas do Google encaminhadas ao NichoChat, num Postgres de verdade.

Roda só com banco de teste (migrations até a 018 aplicadas):

    CRM_TESTE_BANCO=1 DATABASE_URL=postgresql://... WORKER_DESLIGADO=1 \
        uv run pytest tests/test_integracoes_banco.py

Nunca aponte para o banco de produção: o teste grava e apaga avaliações com id
`teste-nicho-*`.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CRM_TESTE_BANCO") != "1",
    reason="precisa de CRM_TESTE_BANCO=1 e DATABASE_URL de um banco de teste",
)

LOJA = "1000000000000000013"


@pytest.fixture
async def conn():
    import psycopg
    from psycopg.rows import dict_row

    from app.config import settings

    async with await psycopg.AsyncConnection.connect(
            settings.database_url, row_factory=dict_row, autocommit=True) as c:
        await c.execute("DELETE FROM integra.avaliacao_respostas WHERE review_id LIKE 'teste-nicho-%%'")
        yield c
        await c.execute("DELETE FROM integra.avaliacao_respostas WHERE review_id LIKE 'teste-nicho-%%'")


def _av(rid: str) -> dict:
    return {"id": rid, "nota": 2, "comentario": "Demorou", "autor": "Ana"}


async def _linha(conn, rid: str) -> dict:
    return await (await conn.execute(
        "SELECT * FROM integra.avaliacao_respostas WHERE origem = 'google' AND review_id = %s",
        (rid,))).fetchone()


async def test_correcao_de_resposta_publicada_volta_para_encaminhada(conn):
    from app.services.integracoes import store

    rid = "teste-nicho-1"
    await store.registrar(conn, "google", LOJA, _av(rid), resposta="Antiga", status="enviada",
                          via="manual")
    # No Google a resposta pode ser corrigida: o texto novo segue para o NichoChat.
    await store.registrar(conn, "google", LOJA, _av(rid), resposta="Nova", status="encaminhada",
                          via="manual")
    linha = await _linha(conn, rid)
    assert (linha["status"], linha["resposta"]) == ("encaminhada", "Nova")

    # Erro depois de publicada continua não rebaixando.
    await store.confirmar_publicadas(conn, "google", [rid])
    await store.registrar(conn, "google", LOJA, _av(rid), resposta="Outra", status="erro",
                          erro="x", via="manual")
    linha = await _linha(conn, rid)
    assert (linha["status"], linha["resposta"]) == ("enviada", "Nova")


async def test_confirmacao_mantem_a_hora_do_envio_e_entra_nos_numeros(conn):
    from app.services.integracoes import store

    rid = "teste-nicho-2"
    antes = await store.numeros(conn, "google")
    await store.registrar(conn, "google", LOJA, _av(rid), resposta="Obrigado!",
                          status="encaminhada", via="manual")
    enviada_em = (await _linha(conn, rid))["atualizado_em"]

    depois = await store.numeros(conn, "google")
    assert depois["respondidas_hoje"] == antes["respondidas_hoje"] + 1

    filtrado = await store.historico(conn, "google", status="encaminhada")
    assert rid in [h["review_id"] for h in filtrado]

    await store.confirmar_publicadas(conn, "google", [rid])
    linha = await _linha(conn, rid)
    assert linha["status"] == "enviada" and linha["atualizado_em"] == enviada_em
    assert (await store.numeros(conn, "google"))["respondidas_hoje"] == depois["respondidas_hoje"]
