"""Configuração, lojas e histórico das integrações.

A tabela `integra.avaliacao_respostas` é o mecanismo de idempotência do iFood:
sem ela, uma reexecução do agente tentaria responder de novo, receberia 422 e
não haveria como desfazer.
"""

from __future__ import annotations

import json

from psycopg import AsyncConnection

ORIGENS = ("ifood", "google")

MODO_MANUAL = "manual"
MODO_AUTOMATICO = "automatico"

# Passada presa há mais tempo que isto é tratada como morta (processo caiu no
# meio) e a trava é tomada por quem vier depois.
_TRAVA_EXPIRA_MIN = 15


# --------------------------------- config ----------------------------------

async def config_interna(conn: AsyncConnection, origem: str) -> dict:
    """A configuração da origem. Chave e modelo da OpenAI não moram aqui: vêm só
    do .env do servidor (ver redator.escrever)."""
    row = await (await conn.execute(
        """SELECT origem, ativo, modo, tom, assinatura, prompt, nota_minima,
                  webhook_url, observacoes, atualizado_em
             FROM integra.config WHERE origem = %s""", (origem,))).fetchone()
    if row is None:
        # Migration aplicada pela metade ou linha apagada à mão: o padrão seguro
        # é manual, que não publica nada sem alguém aprovar.
        return {"origem": origem, "ativo": True, "modo": MODO_MANUAL, "tom": None,
                "assinatura": None, "prompt": None, "nota_minima": 4,
                "webhook_url": None, "observacoes": None, "atualizado_em": None}
    return dict(row)


async def config(conn: AsyncConnection, origem: str) -> dict:
    """A configuração como vai para a tela."""
    return await config_interna(conn, origem)


async def salvar_config(conn: AsyncConnection, origem: str, campos: dict,
                        usuario_id: str | None) -> dict:
    permitidos = {"ativo", "modo", "tom", "assinatura", "prompt", "nota_minima",
                  "webhook_url", "observacoes"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    # Texto em branco vira NULL, para "vazio = padrão do sistema" valer de fato.
    for k, v in list(campos.items()):
        if isinstance(v, str):
            campos[k] = v.strip() or None

    if campos:
        sets = ", ".join(f"{k} = %s" for k in campos)
        await conn.execute(
            f"""INSERT INTO integra.config (origem) VALUES (%s)
                ON CONFLICT (origem) DO NOTHING""", (origem,))
        await conn.execute(
            f"""UPDATE integra.config
                   SET {sets}, atualizado_em = now(), atualizado_por = %s
                 WHERE origem = %s""",
            [*campos.values(), usuario_id, origem])
    return await config(conn, origem)


def automatico(cfg: dict) -> bool:
    return bool(cfg.get("ativo")) and cfg.get("modo") == MODO_AUTOMATICO


# ---------------------------------- lojas ----------------------------------

_COLUNAS_LOJA = "origem, loja_id, nome, cidade, ativo, assinatura, conta_id, criado_em"


async def lojas(conn: AsyncConnection, origem: str, apenas_ativas: bool = False) -> list[dict]:
    filtro = " AND ativo" if apenas_ativas else ""
    rows = await (await conn.execute(
        f"""SELECT {_COLUNAS_LOJA} FROM integra.lojas
             WHERE origem = %s{filtro}
             ORDER BY ativo DESC, lower(nome)""", (origem,))).fetchall()
    return [dict(r) for r in rows]


async def loja(conn: AsyncConnection, origem: str, loja_id: str) -> dict | None:
    row = await (await conn.execute(
        f"SELECT {_COLUNAS_LOJA} FROM integra.lojas WHERE origem = %s AND loja_id = %s",
        (origem, loja_id))).fetchone()
    return dict(row) if row else None


async def vincular_contas_google(conn: AsyncConnection, achadas: list[dict]) -> int:
    """Grava a conta dona de cada unidade Google já cadastrada.

    Também completa a cidade quando ela está em branco. Não cria loja nova: o
    que entra na fila da equipe é decisão de quem administra, não efeito
    colateral de conectar uma conta que enxerga perfis de outras casas.
    """
    n = 0
    for a in achadas:
        res = await conn.execute(
            """UPDATE integra.lojas
                  SET conta_id = %s,
                      cidade   = coalesce(cidade, nullif(%s, ''))
                WHERE origem = 'google' AND loja_id = %s""",
            (a["conta_id"], a.get("cidade") or "", a["loja_id"]))
        n += res.rowcount
    return n


def assinatura_efetiva(loja_: dict, cfg: dict) -> str | None:
    return (loja_.get("assinatura") or "").strip() or (cfg.get("assinatura") or "").strip() or None


# -------------------------------- respostas --------------------------------

async def processadas(conn: AsyncConnection, origem: str, ids: list[str]) -> dict[str, dict]:
    """Os ids já tratados, para nunca responder duas vezes."""
    if not ids:
        return {}
    rows = await (await conn.execute(
        """SELECT review_id, status, resposta, erro, via, tentativas, atualizado_em
             FROM integra.avaliacao_respostas
            WHERE origem = %s AND review_id = ANY(%s)""", (origem, ids))).fetchall()
    return {r["review_id"]: dict(r) for r in rows}


async def registrar(conn: AsyncConnection, origem: str, loja_id: str, av: dict, *,
                    resposta: str = "", status: str, erro: str = "",
                    via: str | None = None, usuario_id: str | None = None) -> None:
    """Grava (ou atualiza) o que aconteceu com uma avaliação."""
    await conn.execute(
        """INSERT INTO integra.avaliacao_respostas
             (origem, review_id, loja_id, nota, comentario, autor,
              resposta, status, erro, via, usuario_id, tentativas)
           VALUES (%s, %s, %s, %s, %s, %s, nullif(%s, ''), %s, nullif(%s, ''), %s, %s,
                   CASE WHEN %s = 'erro' THEN 1 ELSE 0 END)
           ON CONFLICT (origem, review_id) DO UPDATE
             SET resposta      = EXCLUDED.resposta,
                 status        = EXCLUDED.status,
                 erro          = EXCLUDED.erro,
                 via           = EXCLUDED.via,
                 usuario_id    = EXCLUDED.usuario_id,
                 -- Conta falhas seguidas e zera assim que sai do erro, para o
                 -- agente desistir de um erro real sem desistir de um tropeço.
                 tentativas    = CASE WHEN EXCLUDED.status = 'erro'
                                      THEN integra.avaliacao_respostas.tentativas + 1
                                      ELSE 0 END,
                 atualizado_em = now()
           -- Uma resposta publicada nunca é rebaixada. Tentar responder de novo
           -- no iFood devolve 422; sem esta guarda, esse erro apagaria do
           -- histórico o texto que continua público. A exceção é 'encaminhada':
           -- no Google a resposta pode ser corrigida, e o texto novo seguiu
           -- para o NichoChat publicar no lugar do antigo.
           WHERE NOT (integra.avaliacao_respostas.status = 'enviada'
                      AND EXCLUDED.status NOT IN ('enviada', 'encaminhada'))""",
        (origem, av["id"], loja_id, av.get("nota"), av.get("comentario"),
         av.get("autor"), resposta, status, (erro or "")[:2000], via, usuario_id,
         status))


async def confirmar_publicadas(conn: AsyncConnection, origem: str, ids: list[str]) -> None:
    """'encaminhada' → 'enviada' quando a resposta já aparece na plataforma.

    `atualizado_em` fica como está: é a hora em que a atendente enviou.
    """
    if ids:
        await conn.execute(
            """UPDATE integra.avaliacao_respostas SET status = 'enviada'
                WHERE origem = %s AND status = 'encaminhada' AND review_id = ANY(%s)""",
            (origem, ids))


async def historico(conn: AsyncConnection, origem: str, *, loja_id: str | None = None,
                    status: str | None = None, limite: int = 200) -> list[dict]:
    """O que foi publicado, ignorado ou falhou — do mais recente para o mais antigo.

    `pendente` fica de fora: é marcação interna do agente, não um desfecho.
    Loja excluída continua aparecendo, com o nome marcado.
    """
    rows = await (await conn.execute(
        """SELECT a.review_id, a.loja_id,
                  coalesce(l.nome, '(loja removida)') AS loja,
                  a.nota, a.comentario, a.autor, a.resposta, a.status, a.erro,
                  a.via, u.email AS usuario, a.atualizado_em
             FROM integra.avaliacao_respostas a
             LEFT JOIN integra.lojas l ON l.origem = a.origem AND l.loja_id = a.loja_id
             LEFT JOIN app.usuarios u ON u.id = a.usuario_id
            WHERE a.origem = %s
              AND a.status <> 'pendente'
              AND (%s::text IS NULL OR a.loja_id = %s)
              AND (%s::text IS NULL OR a.status = %s)
            ORDER BY a.atualizado_em DESC
            LIMIT %s""",
        (origem, loja_id, loja_id, status, status, max(1, min(limite, 500))))).fetchall()
    return [dict(r) for r in rows]


async def numeros(conn: AsyncConnection, origem: str) -> dict:
    """Os contadores do topo da tela.

    'encaminhada' (Google: a atendente respondeu e o NichoChat está publicando)
    conta como respondida — é o trabalho da equipe que o número mede.
    """
    row = await (await conn.execute(
        """SELECT
             count(*) FILTER (WHERE status IN ('enviada', 'encaminhada')
                                AND atualizado_em >= date_trunc('day', now() AT TIME ZONE 'America/Sao_Paulo')
                                                     AT TIME ZONE 'America/Sao_Paulo') AS respondidas_hoje,
             count(*) FILTER (WHERE status IN ('enviada', 'encaminhada')
                                AND atualizado_em >= now() - interval '7 days')  AS respondidas_7d,
             count(*) FILTER (WHERE status = 'erro'
                                AND atualizado_em >= now() - interval '7 days')  AS erros_7d
             FROM integra.avaliacao_respostas WHERE origem = %s""", (origem,))).fetchone()
    return dict(row)


# ---------------------------------- agente ---------------------------------

async def tomar_trava(conn: AsyncConnection, origem: str = "ifood") -> bool:
    """Reivindica a passada. Devolve False se já há outra em andamento.

    Atômico num UPDATE só: com dois disparos juntos (a passada agendada e o
    botão "Rodar agora"), um vence e o outro desiste.
    """
    await conn.execute(
        "INSERT INTO integra.agente_estado (origem) VALUES (%s) ON CONFLICT DO NOTHING",
        (origem,))
    row = await (await conn.execute(
        f"""UPDATE integra.agente_estado SET rodando_desde = now()
             WHERE origem = %s
               AND (rodando_desde IS NULL
                    OR rodando_desde < now() - interval '{_TRAVA_EXPIRA_MIN} minutes')
            RETURNING origem""", (origem,))).fetchone()
    await conn.commit()
    return row is not None


async def soltar_trava(conn: AsyncConnection, origem: str = "ifood") -> None:
    await conn.execute(
        "UPDATE integra.agente_estado SET rodando_desde = NULL WHERE origem = %s", (origem,))
    await conn.commit()


async def rodando(conn: AsyncConnection, origem: str = "ifood") -> bool:
    row = await (await conn.execute(
        f"""SELECT 1 FROM integra.agente_estado
             WHERE origem = %s
               AND rodando_desde > now() - interval '{_TRAVA_EXPIRA_MIN} minutes'""",
        (origem,))).fetchone()
    return row is not None


async def registrar_execucao(conn: AsyncConnection, e: dict, origem: str = "ifood") -> None:
    await conn.execute(
        """INSERT INTO integra.agente_execucoes
             (origem, lojas, encontradas, respondidas, erros, duracao_ms)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (origem, e["lojas"], e["encontradas"], e["respondidas"], e["erros"], e["duracao_ms"]))


async def minutos_desde_ultima(conn: AsyncConnection, origem: str = "ifood") -> float | None:
    row = await (await conn.execute(
        """SELECT extract(epoch FROM now() - max(iniciado_em)) / 60 AS m
             FROM integra.agente_execucoes WHERE origem = %s""", (origem,))).fetchone()
    return float(row["m"]) if row and row["m"] is not None else None


async def execucoes(conn: AsyncConnection, origem: str = "ifood", limite: int = 30) -> list[dict]:
    rows = await (await conn.execute(
        """SELECT iniciado_em, lojas, encontradas, respondidas, erros,
                  coalesce(duracao_ms, 0) AS duracao_ms
             FROM integra.agente_execucoes
            WHERE origem = %s
            ORDER BY iniciado_em DESC LIMIT %s""", (origem, limite))).fetchall()
    return [dict(r) for r in rows]


# ------------------------ Google: avaliações lidas -------------------------
#
# A leitura automática (leitor_google.py) guarda aqui o que o Google mostrou.
# A fila, a visão geral e a tela de responder leem daqui, e não do Google ao
# vivo: a fila já está pronta quando a atendente abre o CRM.

_COLUNAS_GOOGLE = ("review_id, loja_id, nota, comentario, autor, criada_em, "
                   "atualizada_em, resposta, resposta_em, chegou_em")


def av_google(row: dict) -> dict:
    """A linha guardada no mesmo formato de `google.normalizar`, que é o que a
    tela e as regras de resposta já consomem."""
    resposta = (row.get("resposta") or "").strip()
    return {
        "id": row["review_id"],
        "nota": row.get("nota") or 0,
        "score": None,
        "comentario": row.get("comentario") or "",
        "autor": row.get("autor"),
        "criada_em": row.get("criada_em"),
        "atualizada_em": row.get("atualizada_em"),
        "status": None,
        "pendente": not resposta,
        "respostas": [{"texto": resposta, "de": "MERCHANT",
                       "criada_em": row.get("resposta_em")}] if resposta else [],
        "prazo_seg": None,
        "prazo_perc": None,
        "urgencia": "",
        "pedido": None,
        "campos": {},
        "chegou_em": row.get("chegou_em"),
    }


async def gravar_google(conn: AsyncConnection, loja_id: str, avs: list[dict], *,
                        preservar_resposta: bool = False) -> tuple[int, int]:
    """Guarda as avaliações. Devolve (novas, mudadas).

    `preservar_resposta`: a fonte não diz se já há resposta (é o caso do que o
    NichoChat manda: só avaliação nova). Aí uma resposta já guardada não é
    apagada por um item que veio sem ela — senão a avaliação respondida
    voltaria para a fila na próxima entrega.

    Só conta como mudada a que mudou de verdade (nota, texto, resposta…).
    """
    novas = mudadas = 0
    for av in avs:
        if not av.get("id"):
            continue
        resposta = av["respostas"][0] if av.get("respostas") else None
        row = await (await conn.execute(
            """INSERT INTO integra.avaliacoes_google AS g
                 (review_id, loja_id, nota, comentario, autor, criada_em,
                  atualizada_em, resposta, resposta_em)
               VALUES (%(id)s, %(loja)s, %(nota)s, %(comentario)s, %(autor)s, %(criada)s,
                       %(atualizada)s, %(resposta)s, %(resposta_em)s)
               ON CONFLICT (review_id) DO UPDATE
                 SET loja_id = EXCLUDED.loja_id, nota = EXCLUDED.nota,
                     comentario = EXCLUDED.comentario, autor = EXCLUDED.autor,
                     criada_em = coalesce(EXCLUDED.criada_em, g.criada_em),
                     atualizada_em = CASE WHEN %(preservar)s
                         THEN coalesce(EXCLUDED.atualizada_em, g.atualizada_em)
                         ELSE EXCLUDED.atualizada_em END,
                     resposta = CASE WHEN %(preservar)s
                         THEN coalesce(EXCLUDED.resposta, g.resposta)
                         ELSE EXCLUDED.resposta END,
                     resposta_em = CASE WHEN %(preservar)s
                         THEN coalesce(EXCLUDED.resposta_em, g.resposta_em)
                         ELSE EXCLUDED.resposta_em END,
                     mudou_em = now()
               WHERE (g.loja_id, g.nota, g.comentario, g.autor, g.atualizada_em,
                      g.resposta, g.resposta_em)
                     IS DISTINCT FROM
                     (EXCLUDED.loja_id, EXCLUDED.nota, EXCLUDED.comentario, EXCLUDED.autor,
                      CASE WHEN %(preservar)s THEN coalesce(EXCLUDED.atualizada_em, g.atualizada_em)
                           ELSE EXCLUDED.atualizada_em END,
                      CASE WHEN %(preservar)s THEN coalesce(EXCLUDED.resposta, g.resposta)
                           ELSE EXCLUDED.resposta END,
                      CASE WHEN %(preservar)s THEN coalesce(EXCLUDED.resposta_em, g.resposta_em)
                           ELSE EXCLUDED.resposta_em END)
               RETURNING (xmax = 0) AS nova""",
            {"id": av["id"], "loja": loja_id, "nota": av.get("nota"),
             "comentario": av.get("comentario") or None, "autor": av.get("autor"),
             "criada": av.get("criada_em"), "atualizada": av.get("atualizada_em"),
             "resposta": resposta["texto"] if resposta else None,
             "resposta_em": resposta.get("criada_em") if resposta else None,
             "preservar": preservar_resposta})).fetchone()
        if row is not None:
            if row["nova"]:
                novas += 1
            else:
                mudadas += 1
    return novas, mudadas


# Pedaço que nunca se completou (um POST se perdeu) não fica para sempre.
_PARTES_EXPIRAM_DIAS = 7


async def guardar_parte_google(conn: AsyncConnection, review_id: str, parte: int,
                               total: int, item: dict) -> list[dict]:
    """Guarda um pedaço de comentário e devolve todos os que já chegaram dessa
    avaliação, em ordem (ver 021_partes_google.sql)."""
    await conn.execute(
        """DELETE FROM integra.avaliacoes_google_partes
            WHERE recebida_em < now() - make_interval(days => %s)""", (_PARTES_EXPIRAM_DIAS,))
    await conn.execute(
        """INSERT INTO integra.avaliacoes_google_partes (review_id, parte, total, item)
           VALUES (%s, %s, %s, %s::jsonb)
           ON CONFLICT (review_id, parte) DO UPDATE
             SET total = EXCLUDED.total, item = EXCLUDED.item, recebida_em = now()""",
        (review_id, parte, total, json.dumps(item, ensure_ascii=False)))
    rows = await (await conn.execute(
        """SELECT parte, total, item FROM integra.avaliacoes_google_partes
            WHERE review_id = %s ORDER BY parte""", (review_id,))).fetchall()
    return [dict(r) for r in rows]


async def apagar_partes_google(conn: AsyncConnection, review_id: str) -> None:
    await conn.execute(
        "DELETE FROM integra.avaliacoes_google_partes WHERE review_id = %s", (review_id,))


async def marcar_disparo(conn: AsyncConnection, origem: str, erro: str | None) -> None:
    """Resultado do último disparo da busca no NichoChat (None = aceito)."""
    await conn.execute(
        """UPDATE integra.agente_estado
              SET ultimo_disparo_em = now(), ultimo_disparo_erro = %s
            WHERE origem = %s""", ((erro or "")[:1000] or None, origem))


async def estado_disparo(conn: AsyncConnection, origem: str) -> dict:
    row = await (await conn.execute(
        """SELECT ultimo_disparo_em, ultimo_disparo_erro,
                  extract(epoch FROM now() - ultimo_disparo_em) / 60 AS minutos
             FROM integra.agente_estado WHERE origem = %s""", (origem,))).fetchone()
    if row is None:
        return {"ultimo_disparo_em": None, "ultimo_disparo_erro": None, "minutos": None}
    d = dict(row)
    d["minutos"] = float(d["minutos"]) if d["minutos"] is not None else None
    return d


async def marcar_leitura(conn: AsyncConnection, loja_id: str, *, media=None, total=None,
                         erro: str | None = None) -> None:
    """Fecha a leitura de uma unidade: média e total do perfil, ou o erro.

    Com erro, a unidade fica com o que já tinha; `lida_em` só anda quando leu.
    """
    if erro:
        await conn.execute(
            """INSERT INTO integra.google_leitura (loja_id, erro, erro_em)
               VALUES (%s, %s, now())
               ON CONFLICT (loja_id) DO UPDATE SET erro = EXCLUDED.erro, erro_em = now()""",
            (loja_id, erro[:1000]))
    else:
        await conn.execute(
            # Média e total só vêm quando a fonte manda (o NichoChat não
            # manda): uma entrega sem eles não apaga o que já se sabia.
            """INSERT INTO integra.google_leitura (loja_id, media, total, lida_em)
               VALUES (%s, %s, %s, now())
               ON CONFLICT (loja_id) DO UPDATE
                 SET media = coalesce(EXCLUDED.media, integra.google_leitura.media),
                     total = coalesce(EXCLUDED.total, integra.google_leitura.total),
                     lida_em = now(), erro = NULL, erro_em = NULL""",
            (loja_id, media, total))


async def leituras_google(conn: AsyncConnection) -> dict[str, dict]:
    rows = await (await conn.execute(
        "SELECT loja_id, media, total, lida_em, erro, erro_em FROM integra.google_leitura"
    )).fetchall()
    return {r["loja_id"]: dict(r) for r in rows}


async def avaliacao_google(conn: AsyncConnection, review_id: str) -> dict | None:
    row = await (await conn.execute(
        f"SELECT {_COLUNAS_GOOGLE} FROM integra.avaliacoes_google WHERE review_id = %s",
        (review_id,))).fetchone()
    return av_google(dict(row)) if row else None


async def avaliacoes_google(conn: AsyncConnection, loja_id: str, *, sem_resposta: bool,
                            limite: int = 50, deslocamento: int = 0) -> tuple[list[dict], int]:
    """As avaliações guardadas de uma unidade, da mais nova para a mais antiga.

    Devolve (página, total que atende ao filtro).
    """
    filtro = " AND resposta IS NULL" if sem_resposta else ""
    total = (await (await conn.execute(
        f"SELECT count(*) AS n FROM integra.avaliacoes_google WHERE loja_id = %s{filtro}",
        (loja_id,))).fetchone())["n"]
    rows = await (await conn.execute(
        f"""SELECT {_COLUNAS_GOOGLE} FROM integra.avaliacoes_google
             WHERE loja_id = %s{filtro}
             ORDER BY criada_em DESC NULLS LAST, review_id
             LIMIT %s OFFSET %s""",
        (loja_id, limite, deslocamento))).fetchall()
    return [av_google(dict(r)) for r in rows], total


async def pendentes_google_por_loja(conn: AsyncConnection, prazo_encaminhada) -> dict[str, int]:
    """Quantas esperam resposta em cada unidade.

    Fora da conta: a que o CRM já respondeu e o Google ainda não mostra
    ('enviada' nos últimos 7 dias, ou 'encaminhada' ao NichoChat dentro do
    prazo de publicar).
    """
    rows = await (await conn.execute(
        """SELECT g.loja_id, count(*) AS n
             FROM integra.avaliacoes_google g
             LEFT JOIN integra.avaliacao_respostas r
               ON r.origem = 'google' AND r.review_id = g.review_id
            WHERE g.resposta IS NULL
              AND NOT coalesce(
                    (r.status = 'enviada' AND r.atualizado_em > now() - interval '7 days')
                 OR (r.status = 'encaminhada' AND r.atualizado_em > now() - %s), false)
            GROUP BY g.loja_id""", (prazo_encaminhada,))).fetchall()
    return {r["loja_id"]: r["n"] for r in rows}


async def confirmar_encaminhadas_google(conn: AsyncConnection) -> int:
    """'encaminhada' → 'enviada' quando a avaliação guardada já tem o texto
    enviado (veio na confirmação do NichoChat, numa entrega com `resposta`, ou
    da conexão direta com o Google).

    Compara sem diferença de espaços e quebras de linha. `atualizado_em` fica
    como está: é a hora em que a atendente enviou.
    """
    res = await conn.execute(
        r"""UPDATE integra.avaliacao_respostas r SET status = 'enviada'
              FROM integra.avaliacoes_google g
             WHERE r.origem = 'google' AND r.status = 'encaminhada'
               AND g.review_id = r.review_id AND g.resposta IS NOT NULL
               AND btrim(regexp_replace(g.resposta, '\s+', ' ', 'g'))
                 = btrim(regexp_replace(coalesce(r.resposta, ''), '\s+', ' ', 'g'))""")
    return res.rowcount


async def resposta_encaminhada_google(conn: AsyncConnection, review_id: str) -> str | None:
    """O texto que o CRM entregou ao NichoChat e ainda espera confirmação."""
    row = await (await conn.execute(
        """SELECT resposta FROM integra.avaliacao_respostas
            WHERE origem = 'google' AND review_id = %s AND status = 'encaminhada'""",
        (review_id,))).fetchone()
    return row["resposta"] if row else None


async def resposta_publicada_google(conn: AsyncConnection, review_id: str, texto: str) -> bool:
    """O NichoChat confirmou que publicou `texto` na avaliação.

    Grava a resposta na avaliação (ela sai da fila) e, se o registro do CRM
    estava 'encaminhada' com esse mesmo texto, vira 'enviada'. Texto diferente
    do último enviado (uma confirmação atrasada de um envio anterior) atualiza
    só a avaliação. Devolve se o registro foi confirmado.
    """
    await conn.execute(
        """UPDATE integra.avaliacoes_google
              SET resposta = %s, resposta_em = now(), mudou_em = now()
            WHERE review_id = %s""", (texto, review_id))
    res = await conn.execute(
        r"""UPDATE integra.avaliacao_respostas SET status = 'enviada', erro = NULL
             WHERE origem = 'google' AND review_id = %s AND status = 'encaminhada'
               AND btrim(regexp_replace(coalesce(resposta, ''), '\s+', ' ', 'g'))
                 = btrim(regexp_replace(%s, '\s+', ' ', 'g'))""", (review_id, texto))
    return res.rowcount > 0


async def resposta_falhou_google(conn: AsyncConnection, review_id: str, erro: str) -> bool:
    """O NichoChat avisou que NÃO conseguiu publicar. A avaliação volta para a
    fila com o motivo. Só mexe no que ainda estava esperando ('encaminhada')."""
    res = await conn.execute(
        """UPDATE integra.avaliacao_respostas
              SET status = 'erro', erro = %s, tentativas = tentativas + 1,
                  atualizado_em = now()
            WHERE origem = 'google' AND review_id = %s AND status = 'encaminhada'""",
        (f"o NichoChat não publicou no Google: {erro}"[:2000], review_id))
    return res.rowcount > 0
