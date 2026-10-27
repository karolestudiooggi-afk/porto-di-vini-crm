"""Quem recebe uma campanha.

O disparador não é dono da base — quem é dono é o CRM. Um segmento aqui é um
SELECT sobre `crm.contatos`, reaproveitando os mesmos filtros da tela de
contatos, para o público da campanha nunca divergir do que a equipe viu na tela.

REGRAS QUE NENHUM SEGMENTO PODE BURLAR
--------------------------------------
Estas quatro valem para todo envio, em qualquer modo de segmentação. Não são
opção de tela: estão no SQL, abaixo, e são a diferença entre um disparador e um
gerador de spam.

1. **Tem e-mail.** Óbvio, mas precisa ser explícito: contato sem e-mail entra na
   contagem do público e some na hora do envio, o que faz o relatório mentir.
   Aqui ele é excluído desde o início — `publico` e `com_email` já saem certos.

2. **Não está suprimido.** Quem se descadastrou, deu bounce ou marcou como spam
   nunca mais recebe. Isso não é preferência: é o que mantém o domínio fora das
   listas de bloqueio. E é verificado DUAS vezes — aqui, e de novo no momento do
   envio (services/email/envio.py), porque alguém pode se descadastrar entre a
   montagem do público e o disparo.

3. **Não disse não.** `opt_in_email = false` é uma recusa explícita do titular.
   A base é de clientes cadastrados na plataforma, o que dá base legal para o
   contato; mas quem pediu para sair, sai. `NULL` (nunca perguntado) recebe.

4. **Não foi excluído.** `deleted_at IS NULL` — a exclusão no CRM é lógica, e
   ficha excluída não pode voltar pela porta dos fundos numa campanha.

5. **Um e-mail, uma vez.** Duas fichas com o mesmo endereço (acontece: mesma
   pessoa em dois cadastros) recebem UMA mensagem. O `DISTINCT ON (email_norm)`
   garante isso já na origem, além do índice único por campanha no banco.
"""

from psycopg import AsyncConnection

# Colunas que todo segmento devolve: identidade + o que alimenta as variáveis do
# template (ver render.py::vars_de_contato).
_SELECT = """
SELECT DISTINCT ON (c.email_norm)
       c.id, c.nome, c.primeiro_nome, c.email, c.email_norm,
       c.canal, c.status, c.idioma, c.origem,
       c.last_interaction,
       ARRAY(SELECT DISTINCT t FROM unnest(
         coalesce(c.tags, '{}') || coalesce(c.tags_manuais, '{}')) t ORDER BY t) AS tags
FROM crm.contatos c
"""

# As cinco regras inegociáveis, em SQL.
_GUARDAS = """
      c.deleted_at IS NULL
  AND c.email_norm IS NOT NULL
  AND c.email_norm <> ''
  AND coalesce(c.opt_in_email, true) = true
  AND NOT EXISTS (
        SELECT 1 FROM email.suppressions s WHERE s.email = c.email_norm
      )
"""

# Ordem do DISTINCT ON: entre duas fichas com o mesmo e-mail, fica a que
# interagiu mais recentemente — é a mais provável de estar atualizada.
_ORDEM = "ORDER BY c.email_norm, c.last_interaction DESC NULLS LAST, c.id"


def _where_filtro(seg: dict) -> tuple[str, list, str]:
    """kind='filtro': mesmos cortes da tela de contatos."""
    where: list[str] = []
    args: list = []
    partes: list[str] = []

    for campo, chave in (("canal", "canal"), ("status", "status"),
                         ("idioma", "idioma"), ("origem", "origem")):
        if seg.get(chave):
            where.append(f"c.{campo} = %s")
            args.append(seg[chave])
            partes.append(str(seg[chave]))

    if seg.get("tags"):
        where.append(
            "(coalesce(c.tags,'{}') || coalesce(c.tags_manuais,'{}')) && %s"
        )
        args.append(list(seg["tags"]))
        partes.append(" / ".join(seg["tags"]))

    if seg.get("etiquetas"):
        where.append("c.etiquetas && %s")
        args.append(list(seg["etiquetas"]))
        partes.append(" / ".join(seg["etiquetas"]))

    if seg.get("interagiu_dias"):
        where.append("c.last_interaction >= now() - make_interval(days => %s)")
        args.append(int(seg["interagiu_dias"]))
        partes.append(f"ativos {seg['interagiu_dias']}d")

    label = "Filtro · " + " · ".join(partes) if partes else "Base completa"
    return (" AND ".join(where) if where else "TRUE"), args, label


def montar_sql(seg: dict) -> tuple[str, list, str]:
    """SQL + args + rótulo legível, a partir da definição do segmento."""
    kind = seg.get("kind", "filtro")

    if kind == "selecao":
        ids = list(seg.get("ids") or [])
        sql = f"{_SELECT} WHERE c.id = ANY(%s) AND {_GUARDAS} {_ORDEM}"
        return sql, [ids], f"Seleção manual · {len(ids)} contato(s)"

    where, args, label = _where_filtro(seg)
    sql = f"{_SELECT} WHERE ({where}) AND {_GUARDAS} {_ORDEM}"
    return sql, args, label


async def resolver(conn: AsyncConnection, seg: dict) -> list[dict]:
    """Linhas do público — já sem suprimidos, sem opt-out e sem e-mail repetido."""
    sql, args, _ = montar_sql(seg)
    return await (await conn.execute(sql, args)).fetchall()


async def preview(conn: AsyncConnection, seg: dict) -> dict:
    """Prévia para a tela: total, rótulo e uma amostra.

    `total` aqui já é o número de pessoas que REALMENTE vão receber — as guardas
    são aplicadas antes da contagem. Um preview que promete 800 e entrega 600
    destrói a confiança no relatório.
    """
    sql, args, label = montar_sql(seg)
    rows = await (await conn.execute(sql, args)).fetchall()
    return {
        "total": len(rows),
        "label": label,
        "amostra": [
            {"id": r["id"], "nome": r["nome"], "email": r["email"]} for r in rows[:8]
        ],
    }


async def contar_excluidos(conn: AsyncConnection, seg: dict) -> dict:
    """Quantos o filtro pegaria mas as guardas barraram, e por quê.

    Existe para a tela poder explicar a diferença entre "500 contatos no filtro" e
    "430 vão receber". Sem isso, a pessoa acha que o sistema perdeu gente.
    """
    kind = seg.get("kind", "filtro")
    if kind == "selecao":
        base_where, args = "c.id = ANY(%s)", [list(seg.get("ids") or [])]
    else:
        base_where, args, _ = _where_filtro(seg)

    return await (
        await conn.execute(
            f"""
            SELECT
              count(*) FILTER (WHERE c.email_norm IS NULL OR c.email_norm = '')
                AS sem_email,
              count(*) FILTER (WHERE c.opt_in_email = false)
                AS recusaram,
              count(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM email.suppressions s WHERE s.email = c.email_norm))
                AS suprimidos
            FROM crm.contatos c
            WHERE ({base_where}) AND c.deleted_at IS NULL
            """,
            args,
        )
    ).fetchone()
