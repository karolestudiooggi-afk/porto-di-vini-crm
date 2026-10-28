"""Orquestração do disparo.

Duas etapas separadas de propósito:

**Materializar** (`materializar`) — congela o público numa lista de destinatários.
A partir daí, mudança na base não altera quem vai receber aquela campanha. Sem
esse congelamento, um sync rodando durante o disparo mudaria o público no meio.

**Enviar** (`disparar`) — percorre os pendentes respeitando cota e ritmo. É
retomável: chamar de novo continua de onde parou, nunca reenvia.

A garantia contra envio duplicado tem três camadas, porque uma só sempre falha
em algum canto:
  1. índice único `(campaign_id, email_norm)` — o mesmo e-mail não entra duas
     vezes na mesma campanha, nem que o segmento traga a pessoa duplicada;
  2. `status` do destinatário — o loop só olha `pendente`;
  3. `status` da campanha — `enviada` não dispara de novo.
"""

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal

from psycopg import AsyncConnection
from psycopg.types.json import Json

from app.services import cota as cota_svc
from app.services import parceiros, render, segmentos
from app.services.sender import (
    Conexao, ErroPermanente, ErroTemporario, remetente_da_campanha, respirar,
)

logger = logging.getLogger(__name__)


async def materializar(conn: AsyncConnection, campaign_id: str) -> int:
    """Congela o público da campanha. Idempotente: rodar de novo não duplica."""
    camp = await (
        await conn.execute(
            "SELECT segmento, status, lista FROM email.campaigns WHERE id = %s",
            (campaign_id,),
        )
    ).fetchone()
    if camp is None:
        raise ValueError("campanha não encontrada")

    inseridos = 0
    if camp["lista"] == "parceiros":
        # Aba Parceiros: o público sai de email.parceiros, nunca de crm.contatos.
        for p in await parceiros.resolver(conn, camp["segmento"] or {}):
            res = await conn.execute(
                """INSERT INTO email.recipients (campaign_id, parceiro_id, email, nome, vars)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (campaign_id, email_norm) DO NOTHING""",
                (campaign_id, p["id"], p["email"], p["nome"] or p["empresa"],
                 Json(render.variaveis_de(parceiros.variaveis(p)))),
            )
            inseridos += res.rowcount or 0
    else:
        for c in await segmentos.resolver(conn, camp["segmento"] or {}):
            vars_ = render.variaveis_de(c)
            # ON CONFLICT: o índice único absorve duplicata do segmento e torna a
            # materialização repetível sem efeito colateral.
            res = await conn.execute(
                """INSERT INTO email.recipients (campaign_id, contato_id, email, nome, vars)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (campaign_id, email_norm) DO NOTHING""",
                (campaign_id, c["id"], c["email"], c["nome"], Json(vars_)),
            )
            inseridos += res.rowcount or 0

    await conn.execute(
        """UPDATE email.campaigns
              SET publico = (SELECT count(*) FROM email.recipients WHERE campaign_id = %s),
                  com_email = (SELECT count(*) FROM email.recipients WHERE campaign_id = %s)
            WHERE id = %s""",
        (campaign_id, campaign_id, campaign_id),
    )
    return inseridos


async def _suprimir(
    conn: AsyncConnection, email: str, motivo: str, detalhe: str, recipient_id: str,
    tipo_bounce: str | None = "hard",
) -> None:
    """Tira o endereço da base de envio e registra o evento.

    O evento fica ligado ao destinatário, então o relatório da campanha consegue
    dizer QUANTOS bounces ela causou — não só que a base encolheu.
    """
    await conn.execute(
        """INSERT INTO email.suppressions
             (email, motivo, detalhe, recipient_id, tipo_bounce)
           VALUES (crm.fn_email_norm(%s), %s, %s, %s, %s)
           ON CONFLICT (email) DO NOTHING""",
        (email, motivo, detalhe[:2000], recipient_id, tipo_bounce),
    )
    if motivo == "bounce":
        await conn.execute(
            """INSERT INTO email.events (recipient_id, tipo, url)
               VALUES (%s, %s, %s)""",
            (recipient_id, f"bounce_{tipo_bounce or 'hard'}", detalhe[:500]),
        )


_LIMITE_ERRO_REPETIDO = 5
_EMAIL_NO_TEXTO = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def _assinatura_erro(texto: str) -> str:
    """O erro sem o endereço do destinatário, para comparar um com o outro.

    Muitos provedores repetem o e-mail na mensagem ("<joao@x.com> rejected").
    Sem tirar o endereço, a mesma recusa nunca pareceria igual.
    """
    return _EMAIL_NO_TEXTO.sub("<e-mail>", texto).strip().lower()


async def _desfazer_supressoes(
    conn: AsyncConnection, sequencia: list[tuple[str, str]], erro: str,
) -> None:
    """Devolve à fila quem foi bloqueado por um erro que era da conta.

    Só apaga a supressão criada AGORA para esse destinatário (`recipient_id`):
    quem já estava bloqueado antes, por descadastro ou bounce real, continua.
    """
    for recipient_id, email in sequencia:
        await conn.execute(
            "UPDATE email.recipients SET status='pendente', erro=%s WHERE id=%s",
            (erro[:500], recipient_id),
        )
        await conn.execute(
            "DELETE FROM email.suppressions "
            "WHERE email = crm.fn_email_norm(%s) AND recipient_id = %s",
            (email, recipient_id),
        )
        await conn.execute(
            "DELETE FROM email.events WHERE recipient_id = %s AND tipo LIKE 'bounce_%%'",
            (recipient_id,),
        )


async def _tirar_quem_saiu_da_base(conn: AsyncConnection, campaign_id: str, lista: str | None) -> int:
    """Tira da fila quem deixou de poder receber DEPOIS de entrar nela.

    A fila é montada na criação da campanha e pode esperar dias: campanha
    agendada com antecedência, ou maior que a cota (no aquecimento de domínio,
    300/dia). Nesse meio-tempo a pessoa pode se descadastrar de outra campanha,
    dar bounce, recusar e-mail ou ser excluída do CRM. As regras de
    `segmentos`/`parceiros` só valem na hora de montar a fila; sem esta
    conferência, ela receberia mesmo assim — descadastro que não vale na hora
    é o caminho mais curto para a denúncia de spam.

    Marca como `suprimido` (fica no relatório, com o motivo) em vez de apagar.
    """
    res = await conn.execute(
        """UPDATE email.recipients r
              SET status = 'suprimido',
                  erro = 'saiu da base depois de entrar na fila '
                         '(descadastro, bounce, recusa de e-mail ou ficha excluída)'
            WHERE r.campaign_id = %s
              AND r.status = 'pendente'
              AND (
                    EXISTS (SELECT 1 FROM email.suppressions s WHERE s.email = r.email_norm)
                 OR EXISTS (SELECT 1 FROM email.supressoes_lista l
                             WHERE l.lista = %s AND l.email = r.email_norm)
                 OR EXISTS (SELECT 1 FROM crm.contatos c
                             WHERE c.id = r.contato_id
                               AND (c.deleted_at IS NOT NULL OR c.opt_in_email IS FALSE))
                  )""",
        (campaign_id, lista or "clientes"),
    )
    tirados = getattr(res, "rowcount", 0) or 0
    if tirados:
        logger.info("Campanha %s: %s destinatário(s) saíram da base e não vão receber.",
                    campaign_id, tirados)
    await conn.commit()
    return tirados


async def disparar(conn: AsyncConnection, campaign_id: str, usuario_id: str) -> dict:
    """Envia os pendentes da campanha, respeitando a cota do plano.

    Devolve um resumo do que aconteceu nesta passada — inclusive quando parou por
    cota, para a tela poder explicar em vez de só dizer que terminou.
    """
    camp = await (
        await conn.execute(
            """SELECT c.id, c.assunto, c.status, c.remetente, c.lista,
                      coalesce(nullif(c.html_snapshot, ''), t.html) AS html
                 FROM email.campaigns c
                 LEFT JOIN email.templates t ON t.id = c.template_id
                WHERE c.id = %s""",
            (campaign_id,),
        )
    ).fetchone()
    if camp is None:
        raise ValueError("campanha não encontrada")
    if camp["status"] == "enviada":
        raise ValueError("esta campanha já foi enviada; crie uma nova para reenviar")
    if camp["status"] == "cancelada":
        raise ValueError("campanha cancelada")

    await materializar(conn, campaign_id)
    await _tirar_quem_saiu_da_base(conn, campaign_id, camp["lista"])

    cota = await cota_svc.consultar(conn)
    if cota.disponivel <= 0:
        raise RuntimeError(cota_svc.mensagem_de_bloqueio(cota))

    # RESERVA ATÔMICA DO LOTE
    #
    # Não basta SELECIONAR os pendentes e depois enviar: se dois disparos rodarem
    # ao mesmo tempo — a tela deu timeout, a pessoa clicou de novo, ou o timer
    # coincidiu com um clique — os dois leriam a MESMA lista e a mesma pessoa
    # receberia duas vezes.
    #
    # Aqui o lote é marcado como 'processando' no mesmo comando que o seleciona.
    # O `FOR UPDATE SKIP LOCKED` faz o segundo processo pular as linhas já
    # reservadas pelo primeiro em vez de esperar por elas. Quem chegar depois
    # simplesmente não encontra nada para fazer.
    pendentes = await (
        await conn.execute(
            """UPDATE email.recipients SET status = 'processando'
                WHERE id IN (
                  SELECT id FROM email.recipients
                   WHERE campaign_id = %s AND status = 'pendente'
                   ORDER BY created_at
                   LIMIT %s
                   FOR UPDATE SKIP LOCKED
                )
                RETURNING id, email, nome, vars""",
            (campaign_id, cota.disponivel),
        )
    ).fetchall()
    await conn.commit()

    total_pendentes = (
        await (
            await conn.execute(
                "SELECT count(*) AS n FROM email.recipients "
                "WHERE campaign_id = %s AND status = 'pendente'",
                (campaign_id,),
            )
        ).fetchone()
    )["n"]

    await conn.execute(
        """UPDATE email.campaigns
              SET status = 'enviando',
                  started_at = coalesce(started_at, now()),
                  disparada_por = %s
            WHERE id = %s""",
        (usuario_id, campaign_id),
    )
    await conn.commit()

    # Cada aba sai pelo seu remetente: clientes pelo CAMPANHA_FROM_EMAIL,
    # parceiros pelo CAMPANHA_FROM_EMAIL_PARCEIROS. O gravado na campanha vale; campanha antiga cai no do público.
    remetente = remetente_da_campanha(camp["remetente"], camp["lista"])
    enviados = falhas = suprimidos = 0

    # Trava contra erro de CONTA disfarçado de bounce.
    #
    # Endereço inválido de verdade dá erro variado, um por destinatário. Quando
    # VÁRIOS seguidos recebem exatamente a mesma recusa, o problema é do envio
    # (conta vencida, suspensa, remetente bloqueado) — e bloquear esses clientes
    # seria apagar a base. Foi o que aconteceu: "554 5.9.1 Account expired" em
    # 900 destinatários seguidos, todos bloqueados.
    sequencia: list[tuple[str, str]] = []
    erro_sequencia: str | None = None
    erro_conta: str | None = None

    with Conexao() as smtp:
        for r in pendentes:
            # Recheca a cota a cada mensagem: outro disparo pode estar correndo
            # em paralelo, e a janela móvel se fecha durante o loop.
            atual = await cota_svc.consultar(conn)
            if atual.disponivel <= 0:
                logger.info("Cota esgotada no meio do disparo — pausando campanha %s", campaign_id)
                break

            assunto, corpo = render.montar(
                camp["html"] or "", camp["assunto"] or "", r["vars"] or {}, str(r["id"]),
                camp["lista"],
            )
            try:
                smtp.enviar(
                    remetente=remetente,
                    para=r["email"],
                    nome_destino=r["nome"],
                    assunto=assunto,
                    html=corpo,
                    cabecalhos=render.cabecalhos_unsubscribe(str(r["id"])),
                )
                await conn.execute(
                    "UPDATE email.recipients SET status='enviado', sent_at=now(), erro=NULL "
                    "WHERE id=%s",
                    (r["id"],),
                )
                # O contador da campanha anda junto, na mesma transação: antes
                # ele só era gravado no fim da leva, e a lista ficava em 0
                # durante o envio (ou para sempre, se a leva morresse no meio).
                await conn.execute(
                    "UPDATE email.campaigns SET enviados = enviados + 1 WHERE id=%s",
                    (campaign_id,),
                )
                enviados += 1
                sequencia, erro_sequencia = [], None

            except ErroPermanente as exc:
                # Endereço morto: marca e suprime para nunca mais tentar.
                await conn.execute(
                    "UPDATE email.recipients SET status='suprimido', erro=%s WHERE id=%s",
                    (str(exc)[:500], r["id"]),
                )
                await _suprimir(conn, r["email"], "bounce", str(exc), str(r["id"]))
                suprimidos += 1

                assinatura = _assinatura_erro(str(exc))
                if assinatura == erro_sequencia:
                    sequencia.append((str(r["id"]), r["email"]))
                else:
                    erro_sequencia, sequencia = assinatura, [(str(r["id"]), r["email"])]

                if len(sequencia) >= _LIMITE_ERRO_REPETIDO:
                    await _desfazer_supressoes(conn, sequencia, str(exc))
                    suprimidos -= len(sequencia)
                    erro_conta = str(exc)[:300]
                    await conn.commit()
                    logger.error(
                        "Campanha %s parada: %s destinatários seguidos com o mesmo erro "
                        "(%s). Tratado como problema da conta de envio, ninguém bloqueado.",
                        campaign_id, len(sequencia), erro_conta,
                    )
                    break
                await conn.commit()
                await respirar()
                continue

            except ErroTemporario as exc:
                sequencia, erro_sequencia = [], None
                # Continua pendente: entra na próxima janela sem intervenção.
                await conn.execute(
                    "UPDATE email.recipients SET erro=%s WHERE id=%s",
                    (str(exc)[:500], r["id"]),
                )
                falhas += 1

            # Commit por mensagem: se o processo cair, o que já saiu está gravado
            # e ninguém recebe duas vezes ao retomar.
            await conn.commit()
            await respirar()

    # O lote foi reservado inteiro, mas o loop pode ter parado antes do fim (cota
    # esgotada no meio). Quem sobrou reservado volta a 'pendente', senão ficaria
    # preso em 'processando' para sempre e nunca mais seria enviado.
    await conn.execute(
        "UPDATE email.recipients SET status = 'pendente' "
        "WHERE campaign_id = %s AND status = 'processando'",
        (campaign_id,),
    )
    await conn.commit()

    restantes = (
        await (
            await conn.execute(
                "SELECT count(*) AS n FROM email.recipients "
                "WHERE campaign_id = %s AND status = 'pendente'",
                (campaign_id,),
            )
        ).fetchone()
    )["n"]

    concluida = restantes == 0
    total_enviados = (
        await (
            await conn.execute(
                "SELECT count(*) AS n FROM email.recipients "
                "WHERE campaign_id = %s AND status = 'enviado'",
                (campaign_id,),
            )
        ).fetchone()
    )["n"]
    # "Enviada" com zero enviados mentia na tela: as campanhas de outubro
    # apareciam como concluídas sem ter saído nada. Erro de conta ou fila vazia
    # sem nenhum envio vira "falhou" — e pode ser disparada de novo.
    if erro_conta or (concluida and total_enviados == 0):
        situacao = "falhou"
    else:
        situacao = "enviada" if concluida else "enviando"
    await conn.execute(
        """UPDATE email.campaigns
              SET status = %s,
                  completed_at = CASE WHEN %s THEN now() ELSE completed_at END,
                  enviados = (SELECT count(*) FROM email.recipients
                               WHERE campaign_id = %s AND status = 'enviado')
            WHERE id = %s""",
        (situacao, concluida and not erro_conta, campaign_id, campaign_id),
    )
    await conn.commit()

    return {
        "enviados": enviados,
        "falhas_temporarias": falhas,
        "suprimidos": suprimidos,
        "restantes": restantes,
        "concluida": concluida,
        "simulado": Conexao().simulado,
        "erro_conta": erro_conta,
        "aviso": (
            f"Envio parado: o provedor recusou vários clientes seguidos com o mesmo "
            f"erro ({erro_conta}). Isso é problema da conta de envio, não dos "
            "endereços — ninguém foi bloqueado. Resolva com o provedor e dispare de novo."
            if erro_conta
            else None
            if concluida
            else f"{restantes} destinatário(s) na fila. O envio continua "
            "quando a cota do provedor liberar."
        ),
    }


async def relatorio(conn: AsyncConnection, campaign_id: str) -> dict | None:
    """Números da campanha para a tela de relatório."""
    camp = await (
        await conn.execute(
            """SELECT c.*, t.nome AS template_nome
                 FROM email.campaigns c
                 LEFT JOIN email.templates t ON t.id = c.template_id
                WHERE c.id = %s""",
            (campaign_id,),
        )
    ).fetchone()
    if camp is None:
        return None

    # Uma consulta só: a view já traz contagens e taxas calculadas, com as
    # divisões protegidas contra zero.
    stats = await (
        await conn.execute(
            "SELECT * FROM email.vw_metricas_campanha WHERE campaign_id = %s",
            (campaign_id,),
        )
    ).fetchone()

    # Campanha recém-criada ainda não tem linha na view.
    if stats is None:
        stats = {
            "enviados": 0, "pendentes": 0, "suprimidos": 0, "publico": 0,
            "aberturas": 0, "cliques": 0, "bounce_hard": 0, "bounce_soft": 0,
            "descadastros": 0, "taxa_abertura": None, "taxa_clique": None,
            "taxa_bounce_hard": None, "taxa_bounce_soft": None,
            "taxa_descadastro": None,
        }

    return {"campanha": dict(camp), "stats": dict(stats)}


async def resumo_periodo(conn: AsyncConnection, dias: int) -> dict:
    """Resultado dos e-mails que saíram nos últimos `dias`.

    O período é o do ENVIO de cada e-mail, não o da criação da campanha: uma
    campanha de 8 mil que saiu ao longo de três semanas conta só o que saiu
    dentro da janela. Aberturas, cliques e descadastros são pessoas distintas
    entre esses destinatários — os mesmos critérios da vw_metricas_campanha.
    """
    row = await (
        await conn.execute(
            """
            WITH env AS (
              SELECT r.id, r.campaign_id
                FROM email.recipients r
               WHERE r.status = 'enviado'
                 AND r.sent_at >= now() - make_interval(days => %s)
            ),
            ev AS (
              SELECT count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'open')        AS aberturas,
                     count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'click')       AS cliques,
                     count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'unsubscribe') AS descadastros,
                     count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'bounce_hard') AS bounce_hard
                FROM email.events e
                JOIN env ON env.id = e.recipient_id
            )
            SELECT (SELECT count(*) FROM env)                     AS enviados,
                   (SELECT count(DISTINCT campaign_id) FROM env)  AS campanhas,
                   ev.aberturas, ev.cliques, ev.descadastros, ev.bounce_hard
              FROM ev
            """,
            (dias,),
        )
    ).fetchone()
    d = dict(row)
    env = d["enviados"]

    def taxa(n: int):
        return round(Decimal(100) * n / env, 1) if env else None

    return d | {
        "dias": dias,
        "taxa_abertura": taxa(d["aberturas"]),
        "taxa_clique": taxa(d["cliques"]),
        "taxa_descadastro": taxa(d["descadastros"]),
    }


async def disparar_em_background(campaign_id: str, usuario_id: str) -> None:
    """Roda o disparo fora do request HTTP.

    POR QUE ISTO EXISTE
    -------------------
    O envio é lento por natureza: uma pausa entre mensagens protege a reputação
    do domínio. Com 10 mil destinatários isso dá horas — e prender o navegador
    todo esse tempo é inviável. Pior: qualquer timeout de proxy no caminho
    derrubaria a conexão no meio, e quem está olhando não saberia se saiu ou não.

    Aqui o request responde na hora e o envio continua no processo. A tela
    acompanha pelo relatório, que se atualiza sozinho enquanto a campanha está
    `enviando`.

    A conexão do request morre quando ele termina, então esta função abre a
    PRÓPRIA — é o mesmo que o `agenda.py` faz.
    """
    from psycopg.rows import dict_row

    from app.config import settings

    try:
        async with await AsyncConnection.connect(
            settings.database_url, row_factory=dict_row, prepare_threshold=None
        ) as conn:
            resultado = await disparar(conn, campaign_id, usuario_id)
            logger.info(
                "Campanha %s: %s enviado(s), %s na fila.",
                campaign_id, resultado["enviados"], resultado["restantes"],
            )
    except Exception:
        # Nada a propagar — ninguém está esperando esta resposta. O que importa é
        # ficar no log, e a campanha continua em 'enviando' com os pendentes
        # intactos: o timer horário retoma sozinho.
        logger.exception("Falha no disparo em segundo plano da campanha %s", campaign_id)
