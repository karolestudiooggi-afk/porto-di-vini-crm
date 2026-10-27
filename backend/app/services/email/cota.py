"""Controle de cota do provedor.

O plano contratado tem teto por hora e por mês. Estourar não gera aviso: o
provedor simplesmente recusa a conexão, e a campanha para no meio — parte do
público recebeu, parte não.

Por isso a cota é consultada ANTES de cada lote, e o disparo reserva apenas o
que cabe na janela atual. O que sobra fica pendente e sai na próxima rodada, com
a campanha permanecendo em `enviando`. Nenhum destinatário é perdido nem recebe
duas vezes: quem já foi tem `sent_at` preenchido e sai do lote seguinte.
"""

from dataclasses import dataclass

from psycopg import AsyncConnection

from app.config import settings


@dataclass(frozen=True)
class Cota:
    """Quanto ainda cabe agora, e por quê."""

    disponivel_hora: int
    disponivel_mes: int
    enviados_hora: int
    enviados_mes: int

    @property
    def disponivel(self) -> int:
        """O menor dos dois tetos — é ele que limita de verdade."""
        return max(0, min(self.disponivel_hora, self.disponivel_mes))

    @property
    def motivo_bloqueio(self) -> str | None:
        """Texto para a UI quando não cabe nada. None quando há espaço."""
        if self.disponivel_mes <= 0:
            return (
                f"Cota mensal do plano esgotada ({self.enviados_mes} de "
                f"{settings.smtp_limite_mes}). Reabre no dia 1º."
            )
        if self.disponivel_hora <= 0:
            return (
                f"Limite de {settings.smtp_limite_hora} e-mails por hora atingido "
                f"({self.enviados_hora} nesta hora). Retoma na próxima hora cheia."
            )
        return None


async def consultar(conn: AsyncConnection) -> Cota:
    """Lê o consumo real (view sobre recipients.sent_at) e devolve o que resta.

    A margem (`smtp_margem`) fica de fora do disponível de propósito: protege
    contra qualquer envio concorrente que o CRM não contabilize — um teste manual
    pelo painel do provedor, por exemplo.
    """
    row = await (
        await conn.execute("SELECT enviados_hora, enviados_mes FROM email.vw_consumo")
    ).fetchone()

    enviados_hora = row["enviados_hora"] if row else 0
    enviados_mes = row["enviados_mes"] if row else 0

    return Cota(
        disponivel_hora=settings.smtp_limite_hora - settings.smtp_margem - enviados_hora,
        disponivel_mes=settings.smtp_limite_mes - settings.smtp_margem - enviados_mes,
        enviados_hora=enviados_hora,
        enviados_mes=enviados_mes,
    )
