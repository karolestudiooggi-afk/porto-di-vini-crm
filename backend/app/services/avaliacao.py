"""Regras do módulo de avaliação/NPS: classificação, gravação e apuração.

NPS = %promotores − %detratores, reportado como inteiro de −100 a 100.
Promotor: nota >= limite da conta (default 4). Detrator: nota <= 2. Neutro: o meio.
"""

import logging

import httpx
from psycopg import AsyncConnection

logger = logging.getLogger(__name__)


def classificar(nota: int, limite_promotor: int) -> str:
    if nota >= limite_promotor:
        return "promotor"
    if nota <= 2:
        return "detrator"
    return "neutro"


async def get_conta(conn: AsyncConnection, slug: str) -> dict | None:
    row = await (await conn.execute(
        "SELECT slug, nome, google_url, webhook_url, limite_promotor, ativo "
        "FROM avaliacao.contas WHERE slug=%s", (slug,))).fetchone()
    return dict(row) if row else None


async def listar_contas(conn: AsyncConnection) -> list[dict]:
    return await (await conn.execute(
        "SELECT slug, nome, google_url, webhook_url, limite_promotor, ativo "
        "FROM avaliacao.contas ORDER BY nome")).fetchall()


async def colaboradores_da_unidade(conn: AsyncConnection, slug: str) -> list[str]:
    """Quem pode ser indicado como "quem te atendeu" na tela do QR.

    Neste CRM a base não tem tabela de atendimento, então a lista sai de quem já
    foi citado em avaliações anteriores. Começa vazia — e o campo simplesmente
    não aparece na tela — e vai se formando conforme os clientes respondem.

    Lista fechada em vez de campo livre de propósito: nome digitado vem sujo
    ("joao", "João", "Joao P") e o NPS por pessoa não agrupa.
    """
    rows = await (await conn.execute(
        """SELECT DISTINCT colaborador AS v
             FROM avaliacao.respostas
            WHERE slug = %s AND colaborador IS NOT NULL AND colaborador <> ''
            ORDER BY 1""", (slug,))).fetchall()
    return [r["v"] for r in rows]


async def salvar_resposta(conn: AsyncConnection, slug: str, nota: int, categoria: str,
                          comentario: str, nome: str | None, whatsapp: str | None,
                          colaborador: str | None = None) -> str:
    """Grava a resposta e tenta vincular a uma ficha existente pelo telefone."""
    contato_id = None
    if whatsapp:
        c = await (await conn.execute(
            "SELECT id FROM crm.contatos WHERE telefone_norm = crm.fn_phone_canon(%s) LIMIT 1",
            (whatsapp,))).fetchone()
        contato_id = c["id"] if c else None
    row = await (await conn.execute(
        """INSERT INTO avaliacao.respostas
             (slug, nota, categoria, comentario, nome, whatsapp, colaborador, contato_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (slug, nota, categoria, comentario[:2000], nome, whatsapp,
         colaborador, contato_id))).fetchone()
    return str(row["id"])


async def alertar_whatsapp(webhook_url: str, nome_unidade: str, nota: int, comentario: str,
                           cliente: str, whatsapp: str, colaborador: str = "") -> None:
    """Dispara o webhook do NichoChat em nota baixa.

    Falha de webhook é logada e engolida de propósito: o cliente final já respondeu,
    e não faz sentido mostrar erro a ele porque o alerta interno não subiu.
    """
    if not webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as cli:
            await cli.post(webhook_url, json={
                "tipo": "alerta_avaliacao_baixa",
                "unidade": nome_unidade,
                "colaborador": colaborador or "",
                "nota": nota,
                "comentario": comentario or "(sem comentário)",
                "cliente": cliente or "anônimo",
                "whatsapp": whatsapp or "",
            })
    except Exception:
        logger.warning("Falha ao chamar webhook de avaliação baixa (ignorado)", exc_info=True)


def _nps(promotores: int, detratores: int, total: int) -> int:
    if total <= 0:
        return 0
    return round((promotores - detratores) / total * 100)


async def resumo_nps(conn: AsyncConnection, janela: int | None = None) -> dict:
    """Painel: NPS geral, por unidade, por colaborador e últimas respostas."""
    filtro, args = "", []
    if janela is not None:
        filtro = " AND r.created_at >= (now() - make_interval(days => %s))"
        args = [janela]

    por_unidade_rows = await (await conn.execute(
        f"""SELECT c.slug, c.nome,
                   count(r.id) AS total,
                   count(*) FILTER (WHERE r.categoria='promotor') AS promotores,
                   count(*) FILTER (WHERE r.categoria='neutro')   AS neutros,
                   count(*) FILTER (WHERE r.categoria='detrator') AS detratores
            FROM avaliacao.contas c
            LEFT JOIN avaliacao.respostas r ON r.slug = c.slug{filtro}
            WHERE c.ativo
            GROUP BY c.slug, c.nome ORDER BY total DESC""", args)).fetchall()

    por_unidade, tot = [], {"t": 0, "p": 0, "n": 0, "d": 0}
    for l in por_unidade_rows:
        tot["t"] += l["total"]; tot["p"] += l["promotores"]
        tot["n"] += l["neutros"]; tot["d"] += l["detratores"]
        por_unidade.append({
            **l, "nps": _nps(l["promotores"], l["detratores"], l["total"])})

    # Corte por profissional: numa barbearia a nota é do barbeiro tanto quanto da loja.
    por_colab_rows = await (await conn.execute(
        f"""SELECT r.colaborador,
                   count(*) AS total,
                   count(*) FILTER (WHERE r.categoria='promotor') AS promotores,
                   count(*) FILTER (WHERE r.categoria='neutro')   AS neutros,
                   count(*) FILTER (WHERE r.categoria='detrator') AS detratores
            FROM avaliacao.respostas r
            WHERE r.colaborador IS NOT NULL{filtro}
            GROUP BY r.colaborador ORDER BY total DESC""", args)).fetchall()
    por_colaborador = [
        {**l, "nps": _nps(l["promotores"], l["detratores"], l["total"])}
        for l in por_colab_rows
    ]

    ultimas_rows = await (await conn.execute(
        """SELECT id, slug, nota, categoria, comentario, nome, whatsapp, colaborador, created_at
           FROM avaliacao.respostas ORDER BY created_at DESC LIMIT 30""")).fetchall()
    ultimas = [dict(r) | {"id": str(r["id"])} for r in ultimas_rows]

    return {
        "nps": _nps(tot["p"], tot["d"], tot["t"]), "total": tot["t"],
        "promotores": tot["p"], "neutros": tot["n"], "detratores": tot["d"],
        "por_unidade": por_unidade, "por_colaborador": por_colaborador,
        "ultimas": ultimas,
    }
