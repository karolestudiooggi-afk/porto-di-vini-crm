"""Webhooks de parceiros.

Rotas PÚBLICAS no sentido de não exigirem sessão do CRM — quem chama é o sistema
do parceiro, que não tem usuário. A autenticação é por chave no cabeçalho.

Três princípios aqui, todos aprendidos do jeito difícil em integrações:

1. **Gravar antes de processar.** O payload cru entra no banco na primeira linha.
   Se o processamento falhar, o dado está salvo e dá para reprocessar.

2. **Responder 200 mesmo em erro de processamento.** Parceiro que recebe 500
   costuma reenviar em loop — e alguns desligam a integração depois de N falhas.
   O erro fica registrado do nosso lado, onde a gente resolve.

3. **Nunca vazar detalhe interno na resposta.** Quem chama é um sistema externo.
"""

import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from psycopg import AsyncConnection

from app.config import settings
from app.db import get_conn
from app.services import alphacode
from app.services.integracoes import leitor_google

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _confere(chave_recebida: str | None, esperada: str) -> bool:
    """Compara a chave em tempo constante. Chave vazia no .env = recusa tudo.

    `compare_digest` em vez de `==` porque comparação comum vaza, pelo tempo de
    resposta, quantos caracteres iniciais estavam certos — dá para descobrir a
    chave byte a byte.
    """
    esperada = (esperada or "").strip()
    if not esperada:
        return False
    return hmac.compare_digest((chave_recebida or "").strip(), esperada)


def _autorizado(chave_recebida: str | None) -> bool:
    return _confere(chave_recebida, settings.webhook_alphacode_key)


@router.post("/alphacode")
async def alphacode_webhook(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    conn: AsyncConnection = Depends(get_conn),
):
    """Recebe cadastro de cliente e pedidos do Alpha Code."""
    if not _autorizado(x_api_key):
        raise HTTPException(401, detail="chave inválida")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, detail="corpo não é JSON válido")

    if not isinstance(payload, dict):
        raise HTTPException(400, detail="corpo deve ser um objeto JSON")

    evento = payload.get("event")
    evento_id = await alphacode.registrar_evento(conn, "alphacode", evento, payload)
    await conn.commit()

    tratador = alphacode.TRATADORES.get(evento)
    if tratador is None:
        await conn.execute(
            "UPDATE integra.webhook_eventos SET status='ignorado', processado_em=now() "
            "WHERE id=%s", (evento_id,))
        await conn.commit()
        logger.info("Evento não tratado do Alpha Code: %r", evento)
        return {"recebido": True, "processado": False, "motivo": "evento não tratado"}

    try:
        resultado = await tratador(conn, payload)
        await conn.execute(
            "UPDATE integra.webhook_eventos SET status='processado', processado_em=now() "
            "WHERE id=%s", (evento_id,))
        await conn.commit()
        return {"recebido": True, "processado": resultado.get("ok", True)}

    except Exception as exc:
        # Rollback do processamento, mas o evento cru permanece: ele foi gravado
        # e commitado antes de tudo, justamente para sobreviver a este caminho.
        await conn.rollback()
        await conn.execute(
            "UPDATE integra.webhook_eventos SET status='erro', erro=%s, processado_em=now() "
            "WHERE id=%s", (str(exc)[:1000], evento_id))
        await conn.commit()
        logger.exception("Falha ao processar webhook %s do Alpha Code", evento_id)
        # 200 de propósito: ver o princípio 2 no topo do arquivo.
        return {"recebido": True, "processado": False}


def _chave_do_nichochat(x_api_key: str | None, authorization: str | None) -> None:
    chave = x_api_key
    if not chave and authorization and authorization.lower().startswith("bearer "):
        chave = authorization[7:]
    if not _confere(chave, settings.webhook_google_key):
        raise HTTPException(401, detail="chave inválida")


async def _receber_do_nichochat(request: Request, conn: AsyncConnection, evento: str, processar):
    """Grava o corpo cru, processa e marca o evento.

    Corpo em formato desconhecido volta 422 com o motivo — é o que ajuda quem
    está montando o fluxo. Erro nosso ao gravar volta 200 (princípio 2), com o
    evento guardado para reprocessar.
    """
    bruto = await request.body()
    try:
        corpo = json.loads(bruto or b"null")
    except ValueError:
        corpo = bruto.decode("utf-8", "replace")
    evento_id = await alphacode.registrar_evento(
        conn, "nichochat", evento,
        corpo if isinstance(corpo, (dict, list)) else {"bruto": corpo})
    await conn.commit()

    async def marcar(status: str, erro: str | None = None) -> None:
        await conn.execute(
            "UPDATE integra.webhook_eventos SET status=%s, erro=%s, processado_em=now() "
            "WHERE id=%s", (status, erro, evento_id))
        await conn.commit()

    try:
        resultado = await processar(conn, corpo)
    except ValueError as exc:
        await conn.rollback()
        await marcar("erro", str(exc)[:1000])
        raise HTTPException(422, detail=f"formato não reconhecido: {exc}") from exc
    except Exception as exc:
        await conn.rollback()
        await marcar("erro", str(exc)[:1000])
        logger.exception("Falha ao gravar o que o NichoChat enviou (evento %s)", evento_id)
        return {"recebido": True, "processado": False}

    await conn.commit()
    await marcar("processado")
    return {"recebido": True, "processado": True, **resultado}


@router.post("/nichochat/avaliacoes-google")
async def avaliacoes_google_webhook(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
    conn: AsyncConnection = Depends(get_conn),
):
    """Recebe do NichoChat as avaliações novas do Google.

    Quem chama é o subfluxo "Buscar Novos comentários", que o CRM dispara a
    cada 29 minutos: um POST por bloco de avaliações (a lista, como o fluxo
    monta), e corpo vazio quando não há nada novo; ver leitor_google.py.

    Chave em `X-API-Key` (ou `Authorization: Bearer`), igual a WEBHOOK_GOOGLE_KEY.
    """
    _chave_do_nichochat(x_api_key, authorization)
    return await _receber_do_nichochat(request, conn, "avaliacoes_google", leitor_google.receber)


@router.post("/nichochat/resposta-google")
async def resposta_google_webhook(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
    conn: AsyncConnection = Depends(get_conn),
):
    """Recebe do NichoChat a confirmação de que a resposta foi publicada no Google.

    Quem chama é o subfluxo "Responder Comentários - Google My Business", depois de publicar:
    `{"reviewId": "…", "idUnidade": "…", "resposta": "texto publicado"}` — ou,
    se não conseguiu, `{"reviewId": "…", "status": "erro", "erro": "motivo"}`.
    Mesma chave da entrega das avaliações.
    """
    _chave_do_nichochat(x_api_key, authorization)
    return await _receber_do_nichochat(request, conn, "resposta_google",
                                       leitor_google.confirmar_resposta)
