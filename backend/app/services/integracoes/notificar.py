"""Avisa o NichoChat sobre uma avaliação do iFood.

Este é o único webhook de SAÍDA do módulo. O iFood não envia webhook de
avaliação: lá o fluxo é sempre consulta, e é o agente que descobre o que chegou.

O aviso sai quando a avaliação é **vista**, não quando é respondida. Com o modo
manual como padrão, esperar a resposta significaria nunca avisar ninguém — e é
justamente o alerta que precisa chegar primeiro.

O sistema envia TODAS as avaliações, sem filtro. O que é caso crítico e para
quem vai o aviso é decisão do fluxo no NichoChat: manter essa regra em dois
lugares só garantiria que um dos dois ficaria desatualizado.

O corpo é o mesmo que o Domani Avaliações enviava, para o fluxo que já existe
continuar funcionando sem ajuste. A diferença é o `link`, que agora abre a
avaliação dentro do CRM.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

EVENTO_NOVA = "avaliacao_nova"
EVENTO_RESPONDIDA = "avaliacao_respondida"


def nivel(nota: int) -> str:
    """Traduz a nota em algo que o fluxo roteia sem comparar número."""
    if nota <= 2:
        return "negativa"
    if nota == 3:
        return "neutra"
    return "positiva"


def destino(cfg: dict) -> str:
    """O webhook da configuração; sem ele, o do ambiente como reserva."""
    return (cfg.get("webhook_url") or "").strip() or settings.nichochat_webhook_url


def link(loja_id: str, review_id: str) -> str:
    base = settings.app_url.rstrip("/")
    return f"{base}/integracoes?" + urlencode(
        {"origem": "ifood", "loja": loja_id, "avaliacao": review_id})


def montar(evento: str, loja: dict, av: dict) -> dict:
    """`av` é a avaliação já normalizada (ver ifood.normalizar)."""
    corpo = {
        "evento": evento,
        "cliente": settings.cliente_nome,
        "merchant_id": loja["loja_id"],
        "loja": loja["nome"],
        "avaliacao_id": av["id"],
        "nota": av["nota"],
        "comentario": av["comentario"],
        "nivel": nivel(av["nota"]),
        "prazo_horas": int((av.get("prazo_seg") or 0) // 3600),
        # Leva quem recebeu o alerta direto à avaliação, em vez de mandar a
        # pessoa procurar na fila.
        "link": link(loja["loja_id"], av["id"]),
    }
    if loja.get("cidade"):
        corpo["cidade"] = loja["cidade"]
    if av.get("pedido"):
        corpo["pedido"] = av["pedido"]
    if av.get("criada_em"):
        corpo["criada_em"] = av["criada_em"].isoformat()
    return corpo


async def _enviar(url: str, corpo: dict) -> None:
    """Falha aqui não interrompe nada: a avaliação já foi vista e, se for o
    caso, já foi respondida no iFood."""
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            res = await cli.post(url, json=corpo)
        if res.status_code >= 300:
            logger.warning("webhook devolveu %s para %s da avaliação %s",
                           res.status_code, corpo["evento"], corpo["avaliacao_id"])
    except Exception:
        logger.warning("webhook de avaliação falhou (ignorado)", exc_info=True)


async def nova(cfg: dict, loja: dict, av: dict) -> None:
    await _enviar(destino(cfg), montar(EVENTO_NOVA, loja, av))


async def respondida(cfg: dict, loja: dict, av: dict, resposta: str, origem: str) -> None:
    """`origem` diz quem publicou: 'manual' (pela tela) ou 'agente'."""
    corpo = montar(EVENTO_RESPONDIDA, loja, av)
    corpo["resposta"] = resposta
    corpo["origem"] = origem
    await _enviar(destino(cfg), corpo)
