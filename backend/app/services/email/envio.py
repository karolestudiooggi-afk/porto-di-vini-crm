"""O disparo em si.

Fluxo de um envio:

    materializar público → (por destinatário) checar supressão → renderizar
    → enviar por SMTP → marcar sent_at → pausar → repetir até acabar a cota

Decisões que sustentam o "sem falhas" pedido:

**Materialização em snapshot.** O público vira linhas em `email.recipients` antes
do primeiro envio. A partir daí a campanha tem uma lista congelada: reprocessar
não recalcula segmento nem pega gente nova no meio do caminho.

**Idempotência por índice único.** `(campaign_id, email_norm)` no banco. Chamar
`/send` duas vezes não duplica ninguém — o INSERT conflita e é ignorado, e quem
já tem `sent_at` sai do lote seguinte.

**Uma conexão SMTP para o lote.** Abrir e fechar por mensagem é lento e alguns
provedores tratam como comportamento suspeito.

**Falha individual não derruba o lote.** Erro de um endereço marca aquela linha
como `falhou` com o motivo e segue. Erro de conexão (provedor fora, credencial
errada) para tudo — insistir 2.000 vezes contra um servidor recusando piora a
reputação do IP.

**Bounce imediato vira supressão.** Se o servidor recusa o destinatário na hora
(código 550), o endereço não existe: entra em `suppressions` no mesmo instante.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from psycopg import AsyncConnection

from app.config import settings
from app.services.email import cota as cota_svc
from app.services.email import render, segmentos

logger = logging.getLogger(__name__)


class EnvioBloqueado(Exception):
    """Impede o disparo antes de começar (cota, remetente, público vazio)."""


async def _remetente(conn: AsyncConnection, escolhido: str | None) -> tuple[str, str]:
    """Resolve o remetente e valida contra a lista autorizada.

    O provedor só aceita endereços verificados no painel dele. Usar outro faz o
    envio ser recusado — e descobrir isso no meio do disparo é o pior momento.
    """
    if escolhido:
        row = await (
            await conn.execute(
                "SELECT email, nome FROM email.remetentes "
                "WHERE email = crm.fn_email_norm(%s) AND ativo",
                (escolhido,),
            )
        ).fetchone()
        if row is None:
            raise EnvioBloqueado(
                f"O remetente {escolhido} não está autorizado no provedor. "
                "Cadastre-o antes de disparar."
            )
        return row["email"], row["nome"]

    row = await (
        await conn.execute(
            "SELECT email, nome FROM email.remetentes WHERE padrao AND ativo LIMIT 1"
        )
    ).fetchone()
    if row is None:
        raise EnvioBloqueado(
            "Nenhum remetente padrão configurado. Cadastre ao menos um endereço "
            "verificado no provedor."
        )
    return row["email"], row["nome"]


async def materializar(conn: AsyncConnection, campaign_id: str) -> int:
    """Cria as linhas de destinatário a partir do segmento salvo.

    Idempotente: rodar de novo não duplica (índice único) e não remove quem já
    está lá. Devolve quantos existem no total.
    """
    camp = await (
        await conn.execute(
            "SELECT segmento FROM email.campaigns WHERE id = %s", (campaign_id,)
        )
    ).fetchone()
    if camp is None:
        raise EnvioBloqueado("Campanha não encontrada.")

    publico = await segmentos.resolver(conn, camp["segmento"] or {})

    for pessoa in publico:
        await conn.execute(
            """INSERT INTO email.recipients (campaign_id, contato_id, email, nome, vars)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (campaign_id, email_norm) DO NOTHING""",
            (
                campaign_id,
                pessoa["id"],
                pessoa["email"],
                pessoa["nome"],
                __import__("json").dumps(render.vars_de_contato(pessoa)),
            ),
        )

    total = await (
        await conn.execute(
            "SELECT count(*) AS n FROM email.recipients WHERE campaign_id = %s",
            (campaign_id,),
        )
    ).fetchone()
    return total["n"]


def _mensagem(
    de_email: str,
    de_nome: str,
    para: str,
    assunto: str,
    html_final: str,
    recipient_id: str,
) -> EmailMessage:
    """Monta a mensagem com os cabeçalhos que um envio em volume exige."""
    msg = EmailMessage()
    msg["From"] = formataddr((de_nome, de_email))
    msg["To"] = para
    msg["Subject"] = assunto
    msg["Message-ID"] = make_msgid()

    url_desc = render.link_descadastro(recipient_id)
    # RFC 8058: o par abaixo é o que habilita o botão nativo de descadastro do
    # Gmail/Outlook. Sem ele, quem quer sair marca como spam — e cada denúncia
    # pesa muito mais na reputação do domínio que um descadastro.
    msg["List-Unsubscribe"] = f"<{url_desc}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    # Sinaliza que é comunicação em massa: evita autorresposta de férias voltando
    # como bounce e sujando a métrica.
    msg["Precedence"] = "bulk"
    msg["Auto-Submitted"] = "auto-generated"

    msg.set_content(render.montar_texto(html_final))
    msg.add_alternative(html_final, subtype="html")
    return msg


class _Conexao:
    """Conexão SMTP reaproveitada pelo lote inteiro."""

    def __init__(self) -> None:
        self.smtp: smtplib.SMTP | None = None

    def __enter__(self) -> "_Conexao":
        if settings.email_dry_run:
            return self
        self.smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
        if settings.smtp_use_tls:
            self.smtp.starttls()
        self.smtp.login(settings.smtp_user, settings.smtp_password)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.smtp is not None:
            try:
                self.smtp.quit()
            except Exception:  # a conexão já pode ter caído; não é erro do envio
                pass

    def enviar(self, msg: EmailMessage) -> None:
        if settings.email_dry_run or self.smtp is None:
            logger.info("[DRY RUN] para=%s assunto=%s", msg["To"], msg["Subject"])
            return
        self.smtp.send_message(msg)


async def disparar(conn: AsyncConnection, campaign_id: str, usuario_id: str) -> dict:
    """Envia o que couber na cota atual. Devolve o resultado do lote.

    Se a campanha for maior que a cota, o status fica em `enviando` e o restante
    sai na próxima chamada — nenhum destinatário é perdido nem recebe duas vezes.
    """
    camp = await (
        await conn.execute(
            """SELECT id, assunto, html_snapshot, remetente, status
               FROM email.campaigns WHERE id = %s""",
            (campaign_id,),
        )
    ).fetchone()
    if camp is None:
        raise EnvioBloqueado("Campanha não encontrada.")
    if camp["status"] == "enviada":
        raise EnvioBloqueado("Esta campanha já foi enviada.")
    if camp["status"] == "cancelada":
        raise EnvioBloqueado("Esta campanha foi cancelada.")
    if not (camp["html_snapshot"] or "").strip():
        raise EnvioBloqueado("A campanha não tem conteúdo. Salve o template antes.")

    de_email, de_nome = await _remetente(conn, camp["remetente"])

    total = await materializar(conn, campaign_id)
    if total == 0:
        raise EnvioBloqueado(
            "Nenhum destinatário elegível: o público está vazio depois de "
            "excluir quem não tem e-mail, se descadastrou ou recusou contato."
        )

    cota = await cota_svc.consultar(conn)
    if cota.disponivel <= 0:
        raise EnvioBloqueado(cota.motivo_bloqueio or "Cota do provedor esgotada.")

    pendentes = await (
        await conn.execute(
            """SELECT id::text, email, email_norm, nome, vars
               FROM email.recipients
               WHERE campaign_id = %s AND status = 'pendente'
               ORDER BY created_at
               LIMIT %s""",
            (campaign_id, cota.disponivel),
        )
    ).fetchall()

    await conn.execute(
        """UPDATE email.campaigns
           SET status = 'enviando',
               started_at = coalesce(started_at, now()),
               disparada_por = %s
           WHERE id = %s""",
        (usuario_id, campaign_id),
    )

    enviados = falhas = suprimidos = 0

    with _Conexao() as conexao:
        for r in pendentes:
            # Segunda checagem de supressão: alguém pode ter se descadastrado
            # entre a montagem do público e este instante. É barato e evita o
            # pior erro possível — mandar para quem acabou de pedir para sair.
            bloqueado = await (
                await conn.execute(
                    "SELECT 1 FROM email.suppressions WHERE email = %s",
                    (r["email_norm"],),
                )
            ).fetchone()
            if bloqueado:
                await conn.execute(
                    "UPDATE email.recipients SET status='suprimido', "
                    "erro='descadastrado antes do envio' WHERE id = %s",
                    (r["id"],),
                )
                suprimidos += 1
                continue

            try:
                html_final = render.montar_html(
                    camp["html_snapshot"], r["id"], r["vars"] or {}
                )
                assunto = render.aplicar_vars(camp["assunto"], r["vars"] or {})
                conexao.enviar(
                    _mensagem(de_email, de_nome, r["email"], assunto, html_final, r["id"])
                )
                await conn.execute(
                    "UPDATE email.recipients SET status='enviado', sent_at=now(), "
                    "erro=NULL WHERE id = %s",
                    (r["id"],),
                )
                enviados += 1

            except smtplib.SMTPRecipientsRefused as e:
                # O servidor recusou o destinatário: endereço inexistente. Sai da
                # base de envio agora — insistir queima a reputação do domínio.
                await conn.execute(
                    "UPDATE email.recipients SET status='falhou', erro=%s WHERE id=%s",
                    (str(e)[:500], r["id"]),
                )
                await conn.execute(
                    """INSERT INTO email.suppressions (email, motivo, detalhe, recipient_id)
                       VALUES (%s, 'bounce', %s, %s)
                       ON CONFLICT (email) DO NOTHING""",
                    (r["email_norm"], str(e)[:500], r["id"]),
                )
                falhas += 1

            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                    smtplib.SMTPAuthenticationError) as e:
                # Problema da conexão, não do destinatário. Parar aqui: os
                # pendentes continuam pendentes e saem na próxima chamada.
                await conn.execute(
                    "UPDATE email.campaigns SET ultimo_erro = %s WHERE id = %s",
                    (f"conexão SMTP: {e}"[:500], campaign_id),
                )
                logger.error("Disparo interrompido (conexão SMTP): %s", e)
                break

            except Exception as e:  # falha isolada: registra e segue
                await conn.execute(
                    "UPDATE email.recipients SET status='falhou', erro=%s WHERE id=%s",
                    (str(e)[:500], r["id"]),
                )
                falhas += 1

            # Espaça as mensagens para não bater no teto por hora nem parecer
            # rajada. Em dry run não faz sentido esperar.
            if not settings.email_dry_run:
                await asyncio.sleep(settings.smtp_intervalo_seg)

    restam = await (
        await conn.execute(
            "SELECT count(*) AS n FROM email.recipients "
            "WHERE campaign_id = %s AND status = 'pendente'",
            (campaign_id,),
        )
    ).fetchone()

    concluida = restam["n"] == 0
    await conn.execute(
        """UPDATE email.campaigns
           SET status = CASE WHEN %s THEN 'enviada' ELSE 'enviando' END,
               completed_at = CASE WHEN %s THEN now() ELSE completed_at END,
               enviados = enviados + %s
           WHERE id = %s""",
        (concluida, concluida, enviados, campaign_id),
    )

    return {
        "enviados": enviados,
        "falhas": falhas,
        "suprimidos": suprimidos,
        "restantes": restam["n"],
        "concluida": concluida,
        "dry_run": settings.email_dry_run,
    }
