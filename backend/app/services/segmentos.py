"""Quem recebe a campanha.

Um segmento é um SELECT sobre `crm.contatos` — a base não é duplicada aqui. O
público de uma campanha é sempre o mesmo que a tela de Contatos mostraria com os
mesmos filtros, e isso não é coincidência: é o mesmo WHERE.

REGRAS QUE NUNCA SÃO OPCIONAIS
------------------------------
Três exclusões são aplicadas em toda campanha, independente do filtro escolhido.
Elas não são parâmetro porque não existe caso legítimo de desligá-las:

1. **Sem e-mail não entra.** Óbvio, mas precisa ser dito: o `total` do segmento e
   o `com_email` são números diferentes, e é o segundo que vira destinatário.

2. **Recusa explícita é respeitada.** `opt_in_email = false` significa que a
   pessoa disse "não quero". Nunca entra. Quem tem `null` (nunca foi perguntado)
   entra, porque o cadastro na plataforma é a base de relacionamento — mas
   basta um clique no descadastro para virar supressão permanente.

3. **Supressão é definitiva.** Quem descadastrou, deu bounce permanente ou marcou
   como spam sai da base de envio para sempre. Reenviar para endereço morto
   derruba a reputação do domínio e leva as campanhas seguintes para o spam de
   todo mundo — inclusive de quem queria receber.

4. **Ficha excluída não recebe.** A exclusão é lógica no CRM; a pessoa sumiu das
   listas de propósito e não pode reaparecer numa campanha.
"""

from psycopg import AsyncConnection

# Colunas que viram variável de template (ver services/render.py).
_SELECT = """
SELECT c.id, c.nome, c.primeiro_nome, c.email, c.canal, c.status,
       c.idioma, c.origem, c.tags, c.tags_manuais, c.etiquetas,
       c.last_interaction
FROM crm.contatos c
"""

# As quatro regras acima, em SQL. Aplicadas SEMPRE.
_REGRAS = """
      c.deleted_at IS NULL
  AND c.email_norm IS NOT NULL
  AND coalesce(c.opt_in_email, true) IS TRUE
  AND NOT EXISTS (
        SELECT 1 FROM email.suppressions s WHERE s.email = c.email_norm
      )
"""


def _where(seg: dict) -> tuple[str, list, str]:
    """WHERE + args + rótulo legível do segmento.

    O rótulo é guardado na campanha (`segmento_label`) para o relatório dizer
    para quem foi, mesmo que os filtros mudem de significado depois.
    """
    where = [_REGRAS]
    args: list = []
    partes: list[str] = []

    if seg.get("canal"):
        where.append("c.canal = %s")
        args.append(seg["canal"])
        partes.append(f"canal {seg['canal']}")

    if seg.get("status"):
        where.append("c.status = %s")
        args.append(seg["status"])
        partes.append(f"status {seg['status']}")

    if seg.get("idioma"):
        where.append("c.idioma = %s")
        args.append(seg["idioma"])
        partes.append(f"idioma {seg['idioma']}")

    if seg.get("origem"):
        where.append("c.origem = %s")
        args.append(seg["origem"])
        partes.append(f"origem {seg['origem']}")

    if seg.get("tags"):
        # Tag Domani OU manual: para quem monta a campanha as duas são "tag".
        where.append("(c.tags && %s OR c.tags_manuais && %s)")
        args.extend([seg["tags"], seg["tags"]])
        partes.append("tags " + ", ".join(seg["tags"]))

    if seg.get("etiquetas"):
        where.append("c.etiquetas && %s")
        args.append(seg["etiquetas"])
        partes.append("etiquetas " + ", ".join(seg["etiquetas"]))

    if seg.get("interagiu_dias"):
        where.append("c.last_interaction >= now() - make_interval(days => %s)")
        args.append(int(seg["interagiu_dias"]))
        partes.append(f"interagiu nos últimos {seg['interagiu_dias']} dias")

    # Exclusão por período: "não recebeu nos últimos N dias".
    #
    # Serve para não incomodar quem acabou de receber outra campanha. Sem isso,
    # duas campanhas na mesma semana podem cair na mesma caixa — e é assim que
    # uma base se cansa e começa a marcar como spam.
    #
    # Quem NUNCA recebeu entra sempre (o LEFT JOIN devolve NULL).
    if seg.get("sem_email_dias"):
        # Também exclui quem está AGENDADO numa campanha viva: montar várias
        # campanhas no mesmo dia faria cada uma pegar as mesmas pessoas, porque
        # nenhuma saiu ainda. Cancelada ou falha não conta — quem estava lá não
        # recebeu nada.
        where.append("""
          NOT EXISTS (
            SELECT 1 FROM email.recipients r
              JOIN email.campaigns cp ON cp.id = r.campaign_id
             WHERE r.contato_id = c.id
               AND (
                     (r.status = 'enviado'
                      AND r.sent_at >= now() - make_interval(days => %s))
                  OR (r.status IN ('pendente', 'processando')
                      AND cp.status NOT IN ('cancelada', 'falhou'))
               )
          )
        """)
        args.append(int(seg["sem_email_dias"]))
        partes.append(f"sem e-mail há {seg['sem_email_dias']} dias")

    if seg.get("ids"):
        where.append("c.id = ANY(%s)")
        args.append(list(seg["ids"]))
        partes.append(f"seleção manual ({len(seg['ids'])})")

    label = " · ".join(partes) if partes else "Toda a base elegível"
    return " AND ".join(where), args, label


async def resolver(conn: AsyncConnection, seg: dict) -> list[dict]:
    """Linhas do segmento — usado na materialização dos destinatários."""
    where, args, _ = _where(seg)
    return await (
        await conn.execute(f"{_SELECT} WHERE {where} ORDER BY c.id", args)
    ).fetchall()


async def previa(conn: AsyncConnection, seg: dict) -> dict:
    """Prévia para a tela: quantos, quantos recebem e uma amostra.

    `total` e `com_email` são iguais aqui porque as regras já excluem quem não tem
    e-mail — o campo é mantido para o front não precisar saber disso, e para o
    número não mudar de significado se as regras evoluírem.
    """
    where, args, label = _where(seg)
    linhas = await (
        await conn.execute(f"{_SELECT} WHERE {where} ORDER BY c.id LIMIT 5000", args)
    ).fetchall()

    total = (
        await (
            await conn.execute(
                f"SELECT count(*) AS n FROM crm.contatos c WHERE {where}", args
            )
        ).fetchone()
    )["n"]

    return {
        "total": total,
        "com_email": total,
        "label": label,
        "amostra": [
            {"id": r["id"], "nome": r["nome"], "email": r["email"]} for r in linhas[:6]
        ],
    }


async def contar_excluidos(conn: AsyncConnection, seg: dict) -> dict:
    """Quem o filtro pegaria mas as regras barraram.

    Serve para a tela explicar a diferença entre "300 contatos com este filtro" e
    "271 vão receber" — sem isso o operador acha que o sistema perdeu gente.
    """
    where, args, _ = _where(seg)
    # Mesmo filtro, mas sem as regras: a diferença é o que foi barrado.
    sem_regras = where.replace(_REGRAS, " TRUE ")
    row = await (
        await conn.execute(
            f"""
            SELECT
              count(*) FILTER (WHERE c.email_norm IS NULL)              AS sem_email,
              count(*) FILTER (WHERE c.opt_in_email IS FALSE)           AS recusou,
              count(*) FILTER (WHERE c.deleted_at IS NOT NULL)         AS excluido,
              count(*) FILTER (
                WHERE EXISTS (SELECT 1 FROM email.suppressions s
                              WHERE s.email = c.email_norm)
              )                                                          AS suprimido
            FROM crm.contatos c WHERE {sem_regras}
            """,
            args,
        )
    ).fetchone()
    return dict(row)
