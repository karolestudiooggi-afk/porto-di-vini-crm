"""E-mail transacional: convite de acesso e definição de senha.

Separado do disparador de campanha de propósito. São coisas diferentes:

- transacional é uma mensagem por vez, para quem está esperando por ela, e
  precisa chegar (por isso usa o SMTP com melhor reputação);
- campanha é volume, com cota e ritmo controlados.

Misturar os dois num provedor só faz o convite de acesso cair no spam junto com
a campanha promocional — e a pessoa fica sem conseguir entrar.
"""

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.config import settings

logger = logging.getLogger(__name__)


def enviar(destino: str, assunto: str, html: str, texto: str) -> None:
    """Envia uma mensagem transacional. Levanta a exceção do smtplib se falhar."""
    cfg = settings.smtp_transacional()
    nome_rem, endereco_rem = parseaddr(cfg["from_email"])

    msg = EmailMessage()
    msg["From"] = formataddr((nome_rem or "CRM", endereco_rem))
    msg["To"] = destino
    msg["Subject"] = assunto
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")

    if not cfg["host"]:
        logger.warning("SMTP transacional não configurado — e-mail para %s não saiu.", destino)
        raise RuntimeError(
            "O envio de e-mail não está configurado neste servidor. Preencha "
            "EMAIL_HOST (ou CAMPANHA_SMTP_HOST) no .env."
        )

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
        s.ehlo()
        if cfg["use_tls"]:
            s.starttls()
            s.ehlo()
        if cfg["user"]:
            s.login(cfg["user"], cfg["password"])
        s.send_message(msg)


def convite(destino: str, link: str, quem_convidou: str, papel: str) -> None:
    """Convite de acesso ao CRM."""
    html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;
padding:32px 24px;color:#18181b;">
  <h1 style="margin:0 0 16px;font-size:20px;">Seu acesso ao CRM</h1>
  <p style="margin:0 0 12px;font-size:14px;line-height:1.6;">
    {quem_convidou} convidou você para o CRM, com o perfil <strong>{papel}</strong>.
  </p>
  <p style="margin:0 0 24px;font-size:14px;line-height:1.6;">
    Clique no botão abaixo para criar sua senha e entrar.
  </p>
  <p style="margin:0 0 24px;">
    <a href="{link}" style="background:#E56D23;color:#fff;padding:12px 28px;
    border-radius:8px;text-decoration:none;display:inline-block;font-weight:bold;">
      Criar minha senha
    </a>
  </p>
  <p style="margin:0;font-size:12px;color:#71717a;line-height:1.6;">
    O link vale por 7 dias e só pode ser usado uma vez.<br>
    Se você não esperava este convite, ignore este e-mail.
  </p>
</div>"""
    texto = (
        f"{quem_convidou} convidou você para o CRM ({papel}).\n\n"
        f"Crie sua senha em: {link}\n\n"
        "O link vale por 7 dias e só pode ser usado uma vez."
    )
    enviar(destino, "Seu acesso ao CRM", html, texto)
