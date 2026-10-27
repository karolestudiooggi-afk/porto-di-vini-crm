"""Rotas públicas de rastreio e descadastro.

Chamadas pelo cliente de e-mail do destinatário, que não tem sessão no CRM — por
isso não exigem autenticação. Todas são projetadas para **nunca falhar de forma
visível**: se algo der errado, a pessoa não pode ver um erro dentro do e-mail
dela nem ficar sem conseguir se descadastrar.
"""

import base64
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from psycopg import AsyncConnection

from app.db import get_conn

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tracking"])

# GIF 1x1 transparente.
_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


def _uuid_valido(valor: str) -> bool:
    """`recipient_id` é uuid no banco.

    Sem esta checagem, um link truncado pelo cliente de e-mail (acontece) ou
    adulterado faz o Postgres recusar o cast e a rota devolve 500 — bem na hora
    em que a pessoa está tentando se descadastrar. Valor inválido tem que virar
    "link inválido", não erro de servidor.
    """
    try:
        UUID(valor)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


async def _registrar(
    conn: AsyncConnection, recipient_id: str, tipo: str, url: str | None, req: Request
) -> None:
    """Grava o evento, se o destinatário existir.

    O `WHERE EXISTS` é a proteção contra id forjado: sem ele, qualquer um poderia
    inflar as métricas chamando a URL com um uuid inventado.
    """
    if not _uuid_valido(recipient_id):
        return
    try:
        await conn.execute(
            """INSERT INTO email.events (recipient_id, tipo, url, ip, user_agent)
               SELECT %s, %s, %s, %s, %s
                WHERE EXISTS (SELECT 1 FROM email.recipients WHERE id = %s)""",
            (recipient_id, tipo, url,
             req.client.host if req.client else None,
             req.headers.get("user-agent", "")[:500], recipient_id),
        )
    except Exception:
        # Rastreio nunca pode quebrar a experiência de quem recebeu o e-mail.
        logger.warning("Falha ao registrar evento %s (ignorada)", tipo, exc_info=True)


@router.get("/track/open/{recipient_id}.gif")
async def abertura(
    recipient_id: str, request: Request, conn: AsyncConnection = Depends(get_conn)
):
    """Pixel de abertura.

    Devolve o GIF SEMPRE, mesmo com id inválido — um e-mail com imagem quebrada
    denuncia o rastreio e fica feio na caixa do cliente.

    Vale saber ao ler o relatório: quem lê com imagens bloqueadas não é contado,
    e o pré-carregamento de imagens do Gmail conta aberturas que não houve. O
    número é indicativo, não exato.
    """
    await _registrar(conn, recipient_id, "open", None, request)
    return Response(
        content=_PIXEL,
        media_type="image/gif",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@router.get("/track/click/{recipient_id}")
async def clique(
    recipient_id: str, u: str, request: Request,
    conn: AsyncConnection = Depends(get_conn),
):
    """Registra o clique e encaminha para o destino real.

    Só http(s) é aceito no parâmetro `u`. Sem essa checagem a rota viraria um
    redirecionador aberto — alguém montaria um link do NOSSO domínio apontando
    para um site de golpe, usando nossa reputação.
    """
    if not u.lower().startswith(("http://", "https://")):
        return RedirectResponse("/", status_code=302)
    await _registrar(conn, recipient_id, "click", u[:2000], request)
    return RedirectResponse(u, status_code=302)


_PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Descadastro</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;background:#f4f4f5;margin:0;
padding:48px 16px;color:#18181b;">
<div style="max-width:420px;margin:0 auto;background:#fff;border-radius:12px;
padding:32px;text-align:center;">
<h1 style="margin:0 0 12px;font-size:20px;">%s</h1>
<p style="margin:0;font-size:14px;color:#71717a;line-height:1.5;">%s</p>
</div></body></html>"""


async def _descadastrar(conn: AsyncConnection, recipient_id: str) -> bool:
    """Põe o endereço na lista de supressão. Idempotente."""
    if not _uuid_valido(recipient_id):
        return False
    row = await (await conn.execute(
        """SELECT r.email, coalesce(c.lista, 'clientes') AS lista
             FROM email.recipients r
             LEFT JOIN email.campaigns c ON c.id = r.campaign_id
            WHERE r.id = %s""", (recipient_id,))).fetchone()
    if row is None:
        return False
    if row["lista"] == "parceiros":
        # Descadastro da LISTA de parceiros: o parceiro para de receber proposta
        # comercial, mas se também for cliente continua recebendo as novidades
        # que pediu. Fica guardado por e-mail, então sobrevive a reimportação.
        await conn.execute(
            """INSERT INTO email.supressoes_lista (lista, email, motivo, recipient_id)
               VALUES ('parceiros', crm.fn_email_norm(%s), 'descadastro', %s)
               ON CONFLICT (lista, email) DO NOTHING""",
            (row["email"], recipient_id),
        )
    else:
        await conn.execute(
            """INSERT INTO email.suppressions (email, motivo, detalhe, recipient_id)
               VALUES (crm.fn_email_norm(%s), 'descadastro', 'solicitado pelo destinatário', %s)
               ON CONFLICT (email) DO NOTHING""",
            (row["email"], recipient_id),
        )
    # Evento ligado ao destinatário: é o que permite ao relatório dizer QUANTOS
    # descadastros aquela campanha causou. É o sinal mais direto de que o
    # conteúdo ou a frequência incomodaram.
    await conn.execute(
        """INSERT INTO email.events (recipient_id, tipo)
           VALUES (%s, 'unsubscribe')""",
        (recipient_id,),
    )
    return True


@router.get("/unsubscribe", response_class=HTMLResponse)
async def descadastro_get(r: str, conn: AsyncConnection = Depends(get_conn)):
    """Descadastro pelo link do rodapé."""
    ok = await _descadastrar(conn, r)
    if ok:
        return HTMLResponse(_PAGINA % (
            "Pronto, você foi removido",
            "Não enviaremos mais e-mails para este endereço. Se mudar de ideia, é "
            "só falar com a gente pelo WhatsApp.",
        ))
    return HTMLResponse(_PAGINA % (
        "Link inválido",
        "Não encontramos este cadastro. Talvez o link tenha expirado.",
    ), status_code=404)


@router.post("/unsubscribe", response_class=HTMLResponse)
async def descadastro_post(r: str, conn: AsyncConnection = Depends(get_conn)):
    """Descadastro em um clique (RFC 8058).

    É esta rota que o botão nativo do Gmail e do Outlook chama, via POST, sem
    abrir o navegador. Ter as duas (GET e POST) é requisito para quem envia em
    volume; sem a POST, os provedores rebaixam a entregabilidade.
    """
    await _descadastrar(conn, r)
    # O cliente de e-mail não mostra esta resposta; 200 basta.
    return HTMLResponse("<!doctype html><title>ok</title>ok")
