"""Agente do iFood: a rotina agendada.

Como avaliação não tem webhook, o agente acorda de tempos em tempos, consulta
cada loja, avisa o NichoChat do que chegou e — só no modo automático — responde
o que estiver dentro da nota mínima. Depois volta a dormir.

O que já foi publicado nunca é tentado de novo (422, sem desfazer). O resto é
reavaliado a cada passada: avaliação que falhou volta para a fila de tentativas
até `MAX_TENTATIVAS`, e baixar a nota mínima passa a alcançar o que antes ficou
de fora.

Como no painel de origem, o agente roda SOZINHO dentro do processo da API: sobe
junto com ela (ver `agendar`, ligado no lifespan em `app/main.py`), espera 30
segundos e passa a rodar a cada 15 minutos. Não há timer nem cron para instalar.
`WORKER_DESLIGADO=1` no `.env` desliga.

Duas outras formas de disparar a mesma passada, as duas seguras de coincidir com
a agendada — a trava em `integra.agente_estado` deixa passar uma só:

  - o botão "Rodar agora" da tela;
  - `uv run python -m app.services.integracoes.agente`, que faz uma passada e
    encerra (o equivalente ao `domani worker` do binário original).
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.config import settings
from app.services.integracoes import ifood, notificar, redator, store

logger = logging.getLogger("integracoes.agente")

INTERVALO_MIN = 15
# Espera antes da primeira rodada, para não concorrer com a subida da API.
ESPERA_INICIAL_SEG = 30
TEMPO_MAXIMO_SEG = 10 * 60
_FOLGA_ENTRE_PASSADAS_MIN = 2
_PAUSA_ENTRE = 0.5

# Quantas vezes o agente tenta responder uma avaliação que falhou antes de
# desistir. Erro de momento (IA fora do ar, token vencido no fim da passada,
# rede caindo) se resolve na tentativa seguinte; erro real, não.
MAX_TENTATIVAS = 3


async def processar(conn: AsyncConnection, api: ifood.Ifood, cfg: dict, loja: dict,
                    e: dict) -> None:
    """Uma loja. Cada avaliação nova é avisada e, conforme o modo, respondida."""
    try:
        crus = await api.listar_pendentes(loja["loja_id"])
    except (ifood.ErroIfood, ifood.NaoConfigurado, httpx.HTTPError) as exc:
        e["erros"] += 1
        logger.warning("[%s] %s", loja["nome"], exc)
        return

    e["encontradas"] += len(crus)
    if not crus:
        return

    pendentes = [ifood.normalizar(r) for r in crus]
    vistas = await store.processadas(conn, "ifood", [a["id"] for a in pendentes])
    assinatura = store.assinatura_efetiva(loja, cfg)

    for av in pendentes:
        visto = vistas.get(av["id"])

        # O aviso sai uma vez só, na primeira vez que a avaliação aparece, e
        # sai para todas: é o fluxo do NichoChat que decide o que fazer com
        # cada uma. A linha registrada é o que impede o aviso repetido.
        if visto is None:
            await notificar.nova(cfg, loja, av)

        # Já publicada: nada a fazer. Tentar de novo devolveria 422, e não
        # haveria como desfazer.
        if visto and visto["status"] == "enviada":
            continue

        if not store.automatico(cfg):
            # A equipe responde pela tela. A linha guardada aqui só serve para
            # não avisar de novo na próxima passada.
            if visto is None:
                await store.registrar(conn, "ifood", loja["loja_id"], av,
                                      status="pendente")
                await conn.commit()
            continue

        if av["nota"] < cfg["nota_minima"]:
            # Reavaliado a cada passada, e não decidido de uma vez: baixar a
            # nota mínima passa a alcançar o que já estava marcado.
            if visto is None or visto["status"] != "ignorada":
                await store.registrar(conn, "ifood", loja["loja_id"], av,
                                      status="ignorada")
                await conn.commit()
            continue

        # Falha de momento não pode ser definitiva, mas erro real também não
        # pode virar laço infinito. Esgotado o limite, a avaliação fica para
        # alguém responder pela tela.
        if visto and visto["status"] == "erro" \
                and (visto.get("tentativas") or 0) >= MAX_TENTATIVAS:
            continue

        try:
            texto = await redator.escrever(
                "ifood", cfg, av["nota"], av["comentario"], assinatura)
        except redator.ErroRedator as exc:
            e["erros"] += 1
            await store.registrar(conn, "ifood", loja["loja_id"], av,
                                  status="erro", erro=str(exc), via="agente")
            await conn.commit()
            continue

        try:
            await api.responder(loja["loja_id"], av["id"], texto)
        except (ifood.ErroIfood, ValueError, httpx.HTTPError) as exc:
            e["erros"] += 1
            await store.registrar(conn, "ifood", loja["loja_id"], av, resposta=texto,
                                  status="erro", erro=str(exc), via="agente")
            await conn.commit()
            continue

        e["respondidas"] += 1
        # Commit ANTES do aviso: a resposta já está pública. Se o processo cair
        # agora, a linha "enviada" é o que impede uma segunda tentativa.
        await store.registrar(conn, "ifood", loja["loja_id"], av, resposta=texto,
                              status="enviada", via="agente")
        await conn.commit()
        await notificar.respondida(cfg, loja, av, texto, "agente")

        await asyncio.sleep(_PAUSA_ENTRE)


async def rodar(conn: AsyncConnection) -> dict | None:
    """Uma passada completa por todas as lojas ativas.

    Devolve o resumo da passada, ou None se já havia outra em andamento.
    """
    if not await store.tomar_trava(conn):
        logger.info("já existe uma passada em andamento, ignorando")
        return None

    inicio = time.monotonic()
    e = {"lojas": 0, "encontradas": 0, "respondidas": 0, "erros": 0, "duracao_ms": 0}
    try:
        cfg = await store.config_interna(conn, "ifood")
        if not cfg["ativo"]:
            logger.info("integração iFood pausada na configuração; nada a fazer")
            return e

        api = ifood.Ifood(conn)
        for loja in await store.lojas(conn, "ifood", apenas_ativas=True):
            e["lojas"] += 1
            await processar(conn, api, cfg, loja, e)

        e["duracao_ms"] = int((time.monotonic() - inicio) * 1000)
        await store.registrar_execucao(conn, e)
        await conn.commit()
        logger.info("%s lojas | %s pendentes | %s respondidas | %s erros | %sms",
                    e["lojas"], e["encontradas"], e["respondidas"], e["erros"],
                    e["duracao_ms"])
        return e
    finally:
        # Rollback primeiro: se a passada morreu no meio de uma transação, a
        # conexão está em estado de erro e o UPDATE da trava falharia junto.
        await conn.rollback()
        await store.soltar_trava(conn)


async def rodar_na_api(agendada: bool = False) -> None:
    """Uma passada dentro da API: a agendada, ou a do botão "Rodar agora".

    Usa uma conexão própria do pool: a da requisição é devolvida quando a
    resposta sai, muito antes de a passada terminar.
    """
    from app.db import get_pool  # import tardio: o pool só existe com a API de pé

    try:
        async with get_pool().connection() as conn:
            if agendada:
                # Com mais de um processo da API (uvicorn --workers N), cada um
                # tem o seu relógio. A trava impede passadas simultâneas; isto
                # impede passadas em fila, uma logo atrás da outra. A janela é
                # curta de propósito: uma passada manual não deve atrasar a
                # agendada em mais do que isto.
                desde = await store.minutos_desde_ultima(conn)
                await conn.commit()
                if desde is not None and desde < _FOLGA_ENTRE_PASSADAS_MIN:
                    return
            await asyncio.wait_for(rodar(conn), timeout=TEMPO_MAXIMO_SEG)
    except Exception:
        logger.exception("passada do agente falhou")


async def agendar() -> None:
    """Mantém o agente rodando em intervalo fixo, dentro do processo da API.

    Uma passada que falha não derruba o laço: o erro vai para o log e a próxima
    sai no horário. Só o cancelamento (a API desligando) encerra.
    """
    logger.info("agente do iFood agendado: a cada %s min", INTERVALO_MIN)
    await asyncio.sleep(ESPERA_INICIAL_SEG)
    while True:
        await rodar_na_api(agendada=True)
        await asyncio.sleep(INTERVALO_MIN * 60)


async def _principal() -> None:
    async with await AsyncConnection.connect(
        settings.database_url, row_factory=dict_row, prepare_threshold=None
    ) as conn:
        await asyncio.wait_for(rodar(conn), timeout=TEMPO_MAXIMO_SEG)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_principal())
