"""Envio propriamente dito.

Uma conexão SMTP para toda a campanha (abrir e fechar por mensagem é lento e o
provedor trata como abuso), com pausa entre mensagens e checagem de cota a cada
envio.

O disparo é **retomável**: se a cota horária acabar no meio, a campanha fica em
`enviando` com os pendentes intactos e continua na janela seguinte. Nada é
perdido e ninguém recebe duas vezes — o `status` do destinatário é o controle.
"""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

from app.config import settings

logger = logging.getLogger(__name__)


class ErroPermanente(Exception):
    """Falha que não adianta repetir: caixa inexistente, domínio inválido.

    Vira supressão imediata — insistir em endereço morto é o que derruba a
    reputação do domínio de envio.
    """


class ErroTemporario(Exception):
    """Falha que pode passar: caixa cheia, servidor fora, limite momentâneo.

    O destinatário fica pendente e entra na próxima janela.
    """


@dataclass
class Remetente:
    nome: str
    email: str

    def formatado(self) -> str:
        return formataddr((self.nome, self.email))


def remetente_padrao() -> Remetente:
    """Lê o remetente do .env (`CAMPANHA_FROM_EMAIL`)."""
    nome, endereco = parseaddr(settings.campanha_from_email)
    return Remetente(nome=nome or settings.cliente_nome, email=endereco)


def texto_da_lista(lista: str) -> str:
    """O remetente ("Nome <email>") de cada aba do e-mail, vindo do .env."""
    if lista == "parceiros":
        return settings.campanha_from_email_parceiros
    return settings.campanha_from_email


def remetente_da_campanha(gravado: str | None, lista: str) -> Remetente:
    """O remetente com que a campanha sai.

    Vale o que foi gravado na campanha ao criá-la; campanha antiga, sem nada
    gravado, usa o da lista. Endereço ilegível também cai no da lista —
    nunca num From vazio, que o provedor recusaria no meio do disparo.
    """
    nome, endereco = parseaddr(gravado or "")
    if "@" not in endereco:
        nome, endereco = parseaddr(texto_da_lista(lista))
    padrao = (f"{settings.cliente_nome} Parcerias" if lista == "parceiros"
              else settings.cliente_nome)
    return Remetente(nome=nome or padrao, email=endereco)


# Códigos SMTP 5xx que costumam significar "este endereço não existe".
#
# Atenção: 5xx não basta para decidir. O provedor usa a mesma faixa para recusar
# o ENVIO por motivo nosso — cota estourada, remetente não verificado, conta
# suspensa. Nesses casos o destinatário está correto e suprimi-lo seria um erro
# grave: ele nunca mais receberia nada, por uma falha que não era dele.
_PERMANENTES = {550, 551, 553, 554, 501}

# Frases que indicam problema NA CONTA DE ENVIO, não no destinatário. Quando
# aparecem, o erro é tratado como temporário mesmo vindo com código 5xx.
_NOSSO_PROBLEMA = (
    "quota exceeded",
    "sending quota",
    "rate limit",
    "too many",
    "sender address",
    "not verified",
    "unverified",
    "account is",
    "suspended",
    "daily limit",
    "message limit",
    # Conta vencida ou sem pagamento: o provedor responde, por exemplo,
    # "554 5.9.1 Account expired", e o 554 sozinho pareceria endereço inválido —
    # a base inteira viraria "bounce" por uma falha da conta, não dos endereços.
    "expired",
    "5.9.1",
    "payment",
    "billing",
    "subscription",
    "insufficient",
)


def _classificar(exc: smtplib.SMTPResponseException) -> Exception:
    """Traduz a resposta do servidor em permanente ou temporário.

    A frase pesa mais que o código: `554 Sending quota exceeded` é 5xx, mas o
    endereço do destinatário está perfeito — quem estourou o limite fomos nós.
    """
    codigo = getattr(exc, "smtp_code", 0)
    detalhe = getattr(exc, "smtp_error", b"")
    texto = detalhe.decode(errors="ignore") if isinstance(detalhe, bytes) else str(detalhe)
    baixo = texto.lower()

    if any(frase in baixo for frase in _NOSSO_PROBLEMA):
        return ErroTemporario(f"{codigo} {texto} (limite ou configuração do provedor)")
    if codigo in _PERMANENTES:
        return ErroPermanente(f"{codigo} {texto}")
    return ErroTemporario(f"{codigo} {texto}")


class Conexao:
    """Sessão SMTP reaproveitada por toda a campanha.

    Em modo simulação (`EMAIL_DRY_RUN=true`, o padrão) nada é aberto: o envio é
    registrado no log e a campanha percorre todo o fluxo — materialização,
    renderização, contabilidade — sem tocar no provedor. É assim que se testa uma
    campanha sem gastar cota nem incomodar cliente.
    """

    def __init__(self) -> None:
        self._smtp: smtplib.SMTP | None = None
        self.simulado = settings.email_dry_run

    def __enter__(self) -> "Conexao":
        if self.simulado:
            logger.warning(
                "EMAIL_DRY_RUN=true — nenhuma mensagem sairá de verdade. "
                "Para disparar, defina EMAIL_DRY_RUN=false no .env."
            )
            return self
        self._smtp = smtplib.SMTP(
            settings.campanha_smtp_host, settings.campanha_smtp_port, timeout=30
        )
        self._smtp.ehlo()
        if settings.campanha_smtp_use_tls:
            self._smtp.starttls()
            self._smtp.ehlo()
        if settings.campanha_smtp_user:
            self._smtp.login(
                settings.campanha_smtp_user, settings.campanha_smtp_password
            )
        return self

    def __exit__(self, *_exc) -> None:
        if self._smtp is not None:
            try:
                self._smtp.quit()
            except Exception:  # a conexão já pode ter caído; não é erro do disparo
                logger.debug("Falha ao encerrar SMTP (ignorada)", exc_info=True)
            self._smtp = None

    def enviar(
        self,
        *,
        remetente: Remetente,
        para: str,
        nome_destino: str | None,
        assunto: str,
        html: str,
        cabecalhos: dict[str, str],
    ) -> None:
        """Envia uma mensagem. Levanta ErroPermanente ou ErroTemporario."""
        msg = self._mensagem(
            remetente=remetente, para=para, nome_destino=nome_destino,
            assunto=assunto, html=html, cabecalhos=cabecalhos,
        )

        if self.simulado:
            logger.info("[simulado] -> %s | %s", para, assunto)
            return

        assert self._smtp is not None
        try:
            self._smtp.send_message(msg)
        except smtplib.SMTPResponseException as exc:
            raise _classificar(exc) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            # A recusa no RCPT também passa pela checagem de frase: um provedor
            # com a conta suspensa recusa TODO destinatário, e sem isso cada um
            # seria bloqueado como endereço inválido.
            codigo, texto = next(iter(exc.recipients.values()), (0, b""))
            raise _classificar(smtplib.SMTPResponseException(codigo, texto)) from exc
        except (smtplib.SMTPServerDisconnected, OSError) as exc:
            # Conexão caiu: é temporário, e o destinatário continua pendente.
            raise ErroTemporario(str(exc)) from exc

    def _mensagem(
        self,
        *,
        remetente: Remetente,
        para: str,
        nome_destino: str | None,
        assunto: str,
        html: str,
        cabecalhos: dict[str, str],
    ) -> EmailMessage:
        """Monta o MIME da mensagem."""
        msg = EmailMessage()
        msg["From"] = remetente.formatado()
        msg["To"] = formataddr((nome_destino or "", para))
        msg["Subject"] = assunto
        # Message-ID com o domínio do remetente: sem ele, alguns servidores geram
        # um próprio e o DKIM pode não fechar.
        msg["Message-ID"] = make_msgid(domain=remetente.email.split("@")[-1])
        for chave, valor in cabecalhos.items():
            msg[chave] = valor

        # Alternativa em texto puro antes do HTML: exigência de qualquer filtro
        # anti-spam sério, e o que aparece em cliente que bloqueia HTML.
        msg.set_content(
            "Este e-mail é em HTML. Se você está lendo isto, seu leitor não "
            "suporta o formato."
        )
        msg.add_alternative(html, subtype="html")
        return msg


async def respirar() -> None:
    """Pausa entre mensagens, para não parecer rajada.

    2.500/hora dá uma a cada 1,44 s. O padrão de 1,5 s deixa folga e mantém o
    ritmo abaixo do teto mesmo com variação de latência do servidor.
    """
    await asyncio.sleep(settings.smtp_intervalo_seg)
