from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from psycopg import AsyncConnection

from app.auth import require_perm
from app.db import get_conn
from app.schemas.dashboard import (
    DashboardAtividade,
    DashboardConsumo,
    DashboardDistribuicoes,
    DashboardResumo,
)


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _completar_dias(rows: list[dict], hoje: date, dias: int, zeros: dict) -> list[dict]:
    """Devolve UM ponto por dia da janela, com zero onde não houve movimento.

    Sem isso o gráfico só recebia os dias com dado, e como ele espaça os pontos
    por igual, um buraco de 12 dias sem pedido (o webhook parado de 25/09 a
    07/10) aparecia como uma linha contínua — exatamente o problema que o
    gráfico existe para mostrar.

    Sem nenhum dado na janela devolve lista vazia, para a tela mostrar o estado
    "aguardando" em vez de uma linha zerada que pareceria "não houve venda".
    """
    if not rows:
        return []
    por_dia = {r["data"]: r for r in rows}
    inicio = hoje - timedelta(days=dias - 1)
    return [
        por_dia.get(inicio + timedelta(days=i), {"data": inicio + timedelta(days=i), **zeros})
        for i in range(dias)
    ]


async def _hoje(conn: AsyncConnection) -> date:
    """Hoje no fuso da operação — o servidor roda em UTC."""
    row = await (await conn.execute(
        "SELECT (now() AT TIME ZONE 'America/Sao_Paulo')::date AS d")).fetchone()
    return row["d"]


async def _count_by(conn: AsyncConnection, column: str) -> list[dict]:
    allowed = {"canal", "status", "origem", "idioma"}
    if column not in allowed:
        raise ValueError(f"coluna de distribuição inválida: {column}")
    return await (
        await conn.execute(
            f"""SELECT {column} AS valor, count(*) AS total
                FROM crm.contatos
                WHERE {column} IS NOT NULL AND deleted_at IS NULL
                GROUP BY {column}
                ORDER BY total DESC, valor"""
        )
    ).fetchall()


@router.get("/resumo", response_model=DashboardResumo)
async def resumo(
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("dashboard:read")),
) -> dict:
    row = await (
        await conn.execute(
            """SELECT count(*) AS total_contatos,
                      count(*) FILTER (WHERE telefone_norm IS NOT NULL) AS contatos_com_telefone,
                      count(*) FILTER (WHERE email_norm IS NOT NULL) AS contatos_com_email,
                      count(*) FILTER (WHERE last_interaction IS NOT NULL) AS contatos_com_interacao,
                      count(*) FILTER (
                        WHERE opt_in_email IS TRUE OR opted_in_email IS TRUE
                      ) AS contatos_com_opt_in_email,
                      count(*) FILTER (
                        WHERE last_interaction >= now() - interval '30 days'
                      ) AS interacoes_ultimos_30_dias,
                      max(domani_synced_at) AS domani_ultima_sincronizacao
               FROM crm.contatos
               WHERE deleted_at IS NULL"""
        )
    ).fetchone()
    # Consumo entra no resumo só quando existe. Enquanto o PDV não mandar nada,
    # os campos ficam nulos — e a tela mostra "—" em vez de R$ 0,00, que seria
    # afirmar que não houve faturamento.
    consumo = await (
        await conn.execute(
            """SELECT count(*)             AS pedidos_total,
                      sum(valor)           AS faturamento_total,
                      round(avg(valor), 2) AS ticket_medio,
                      count(*) FILTER (
                        WHERE ocorrido_em >= now() - interval '30 days'
                      )                    AS pedidos_30_dias,
                      sum(valor) FILTER (
                        WHERE ocorrido_em >= now() - interval '30 days'
                      )                    AS faturamento_30_dias,
                      count(DISTINCT contato_id) AS clientes_com_pedido,
                      max(ocorrido_em)     AS ultimo_pedido
               FROM crm.consumos"""
        )
    ).fetchone()

    fontes = ["Domani"]
    if consumo["pedidos_total"]:
        fontes.append("Alpha Code")

    return {**row, **consumo, "fontes_ativas": fontes}


@router.get("/distribuicoes", response_model=DashboardDistribuicoes)
async def distribuicoes(
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("dashboard:read")),
) -> dict:
    return {
        "por_canal": await _count_by(conn, "canal"),
        "por_status": await _count_by(conn, "status"),
        "por_origem": await _count_by(conn, "origem"),
        "por_idioma": await _count_by(conn, "idioma"),
    }


@router.get("/atividade", response_model=DashboardAtividade)
async def atividade(
    dias: int = Query(default=30, ge=1, le=365),
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("dashboard:read")),
) -> dict:
    rows = await (
        await conn.execute(
            """SELECT (last_interaction AT TIME ZONE 'America/Sao_Paulo')::date AS data,
                      count(*) AS total
               FROM crm.contatos
               WHERE last_interaction >= now() - make_interval(days => %s)
                 AND deleted_at IS NULL
               GROUP BY 1 ORDER BY 1""",
            (dias,),
        )
    ).fetchall()
    serie = _completar_dias(rows, await _hoje(conn), dias, {"total": 0})
    return {"dias": dias, "serie": serie}


@router.get("/consumo", response_model=DashboardConsumo)
async def consumo(
    dias: int = Query(default=30, ge=1, le=365),
    conn: AsyncConnection = Depends(get_conn),
    _: dict = Depends(require_perm("dashboard:read")),
) -> dict:
    """Faturamento e pedidos por dia, e o que mais sai.

    Vem de `crm.consumos`, alimentado pelo webhook do Alpha Code. Sem PDV ligado,
    devolve listas vazias — a tela mostra o estado real em vez de inventar número.
    """
    serie = await (
        await conn.execute(
            """SELECT ocorrido_em::date AS data,
                      count(*)          AS pedidos,
                      sum(valor)        AS faturamento
               FROM crm.consumos
               WHERE ocorrido_em >= now() - make_interval(days => %s)
               GROUP BY 1 ORDER BY 1""",
            (dias,),
        )
    ).fetchall()
    serie = _completar_dias(serie, await _hoje(conn), dias,
                            {"pedidos": 0, "faturamento": 0})

    itens = await (
        await conn.execute(
            """SELECT i.nome,
                      sum(i.quantidade) AS quantidade,
                      sum(i.total)      AS faturamento
               FROM crm.consumo_itens i
               JOIN crm.consumos k ON k.id = i.consumo_id
               WHERE k.ocorrido_em >= now() - make_interval(days => %s)
                 AND i.nome IS NOT NULL
               GROUP BY i.nome
               ORDER BY quantidade DESC
               LIMIT 10""",
            (dias,),
        )
    ).fetchall()

    return {"dias": dias, "serie": serie, "itens": itens}
