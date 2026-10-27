"""Controle da cota do provedor de e-mail.

O plano contratado limita **2.500 e-mails por hora** e **10.000 por mês**. Quando
um deles estoura, o provedor recusa a conexão — e uma campanha grande para no
meio, com parte do público servido e parte não.

Este módulo responde duas perguntas antes de cada disparo:

    "cabe quanto agora?"      -> `disponivel()`
    "posso mandar mais uma?"  -> `pode_enviar()`

A contagem vem da view `email.vw_consumo`, derivada de `recipients.sent_at`.
Não há contador em memória nem tabela paralela de propósito: contador desanda
quando o processo cai no meio do envio, e passa a mentir justamente na hora em
que a informação importa.
"""

from dataclasses import dataclass

from psycopg import AsyncConnection

from app.config import settings


@dataclass(frozen=True)
class Cota:
    """Quanto do plano já foi consumido e quanto ainda cabe."""

    enviados_hora: int
    enviados_dia: int
    enviados_mes: int
    limite_hora: int
    limite_dia: int
    limite_mes: int
    margem: int

    @property
    def resta_hora(self) -> int:
        """Vagas na janela de 60 minutos, já descontada a margem de segurança."""
        return max(0, self.limite_hora - self.margem - self.enviados_hora)

    @property
    def resta_dia(self) -> int:
        """Vagas restantes hoje.

        Durante o aquecimento de domínio esta é a janela que manda: a regra é
        subir o volume DIA a dia. Sem este teto, a cota do mês inteiro poderia
        sair em algumas horas — o oposto de aquecer.
        """
        return max(0, self.limite_dia - self.enviados_dia)

    @property
    def resta_mes(self) -> int:
        """Vagas restantes no plano do mês."""
        return max(0, self.limite_mes - self.margem - self.enviados_mes)

    @property
    def disponivel(self) -> int:
        """O menor dos dois: é o teto real do próximo disparo."""
        return min(self.resta_hora, self.resta_dia, self.resta_mes)

    @property
    def bloqueio(self) -> str | None:
        """Qual limite travou, para a mensagem de erro dizer algo útil."""
        # Ordem do mais demorado de liberar para o mais rápido: o mês só abre no
        # ciclo seguinte, o dia à meia-noite, a hora em minutos. Dizer o pior
        # primeiro evita a falsa esperança de "é só esperar um pouco".
        if self.resta_mes <= 0:
            return "mes"
        if self.resta_dia <= 0:
            return "dia"
        if self.resta_hora <= 0:
            return "hora"
        return None

    def como_dict(self) -> dict:
        return {
            "enviados_hora": self.enviados_hora,
            "enviados_dia": self.enviados_dia,
            "enviados_mes": self.enviados_mes,
            "limite_hora": self.limite_hora,
            "limite_dia": self.limite_dia,
            "limite_mes": self.limite_mes,
            "resta_hora": self.resta_hora,
            "resta_dia": self.resta_dia,
            "resta_mes": self.resta_mes,
            "disponivel": self.disponivel,
            "bloqueio": self.bloqueio,
        }


async def consultar(conn: AsyncConnection) -> Cota:
    """Lê o consumo atual do provedor."""
    row = await (
        await conn.execute(
            "SELECT enviados_hora, enviados_dia, enviados_mes FROM email.vw_consumo"
        )
    ).fetchone()
    return Cota(
        enviados_hora=int(row["enviados_hora"] or 0),
        enviados_dia=int(row["enviados_dia"] or 0),
        enviados_mes=int(row["enviados_mes"] or 0),
        limite_hora=settings.smtp_limite_hora,
        limite_dia=settings.smtp_limite_dia,
        limite_mes=settings.smtp_limite_mes,
        margem=settings.smtp_margem,
    )


def mensagem_de_bloqueio(cota: Cota) -> str:
    """Texto para o operador — diz o que houve e o que fazer, não só que falhou."""
    if cota.bloqueio == "mes":
        return (
            f"Cota mensal do plano esgotada ({cota.enviados_mes} de "
            f"{cota.limite_mes} e-mails). O envio recomeça no ciclo seguinte, ou "
            "após recarga no provedor."
        )
    if cota.bloqueio == "dia":
        return (
            f"Cota de hoje atingida ({cota.enviados_dia} de {cota.limite_dia} "
            "e-mails). A contagem zera à meia-noite e a campanha continua sozinha "
            "com o que ficou na fila."
        )
    if cota.bloqueio == "hora":
        return (
            f"Limite de {cota.limite_hora} e-mails por hora atingido "
            f"({cota.enviados_hora} enviados nos últimos 60 minutos). A campanha "
            "continua sozinha assim que a janela abrir — nada se perde."
        )
    return ""
