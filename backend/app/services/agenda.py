"""Continuação automática de campanhas.

Duas situações que exigem alguém (ou algo) voltar depois:

1. **Campanha maior que a cota horária.** 5.000 destinatários com teto de 2.500/h
   saem em duas levas. Sem isto, a segunda leva só sairia se uma pessoa lembrasse
   de abrir a tela e clicar de novo — e a metade da base ficaria sem receber.

2. **Campanha agendada.** `agendada_para` só é uma data no banco até alguém agir
   sobre ela.

Roda pelo `crm-agenda.timer`, de hora em hora. É seguro rodar a qualquer
momento e quantas vezes for: o controle de quem já recebeu está no status de cada
destinatário, não neste processo.
"""

import asyncio
import logging

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.config import settings
from app.services import campanhas, cota as cota_svc

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("agenda")

# Autor registrado na auditoria quando o disparo é automático, para o log
# distinguir do que foi clicado por uma pessoa.
SISTEMA = "00000000-0000-0000-0000-000000000000"


async def _pendentes(conn: AsyncConnection) -> list[dict]:
    """Campanhas que devem sair agora.

    Duas famílias:
      - `enviando` com destinatário pendente (a leva que faltou);
      - `agendada` cuja hora já chegou.

    `rascunho` NUNCA entra: campanha rascunho é a que ninguém mandou disparar.
    """
    return await (
        await conn.execute(
            """
            SELECT id, nome, status FROM email.campaigns
             WHERE (
                     status = 'enviando'
                 AND EXISTS (SELECT 1 FROM email.recipients r
                              WHERE r.campaign_id = campaigns.id AND r.status = 'pendente')
                   )
                OR (status = 'agendada' AND agendada_para <= now())
             ORDER BY agendada_para NULLS FIRST, created_at
            """
        )
    ).fetchall()


async def rodar() -> None:
    async with await AsyncConnection.connect(
        settings.database_url, row_factory=dict_row, prepare_threshold=None
    ) as conn:
        # Devolve à fila quem ficou preso em 'processando' por um disparo que
        # morreu (queda do processo, reinício do servidor). Sem isso, essas
        # pessoas nunca mais receberiam — ficariam num estado que ninguém revisa.
        orfas = await (await conn.execute("SELECT email.liberar_reservas_orfas() AS n")).fetchone()
        if orfas["n"]:
            logger.info("%s destinatário(s) presos foram devolvidos à fila.", orfas["n"])
        await conn.commit()

        cota = await cota_svc.consultar(conn)
        if cota.disponivel <= 0:
            logger.info("Sem cota agora (%s). Nada a fazer.", cota.bloqueio)
            return

        fila = await _pendentes(conn)
        if not fila:
            logger.info("Nenhuma campanha para continuar.")
            return

        for c in fila:
            logger.info("Continuando '%s' (%s)…", c["nome"], c["status"])
            try:
                r = await campanhas.disparar(conn, str(c["id"]), SISTEMA)
                logger.info(
                    "'%s': %s enviado(s), %s na fila.",
                    c["nome"], r["enviados"], r["restantes"],
                )
                if r["restantes"] > 0:
                    # Cota acabou no meio: as demais campanhas da fila também não
                    # vão passar. Parar aqui evita marcar falha em série.
                    logger.info("Cota esgotada — o restante fica para a próxima janela.")
                    break
            except Exception:
                logger.exception("Falha ao continuar a campanha %s", c["id"])


if __name__ == "__main__":
    asyncio.run(rodar())
