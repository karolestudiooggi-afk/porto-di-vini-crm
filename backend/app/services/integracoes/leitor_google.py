"""Leitura automática das avaliações do Google — pelo NichoChat.

O CRM não lê o Google sozinho. Ele pede ao NichoChat, que já tem a conexão
Google funcionando:

  1. a cada 29 minutos (`GOOGLE_LEITURA_INTERVALO_MIN`) o CRM dispara, no
     contato `NICHOCHAT_CONTATO_USER_ID`, o subfluxo de busca
     (`NICHOCHAT_BUSCA_GOOGLE_SUBFLUXO`);
  2. o subfluxo lê as unidades e separa as avaliações criadas nos últimos
     30 minutos, em blocos de até 2.900 caracteres;
  3. e manda cada bloco por POST ao CRM — `/webhooks/nichochat/avaliacoes-google`,
     com a chave `WEBHOOK_GOOGLE_KEY` no cabeçalho `X-API-Key`;
  4. o CRM guarda em `integra.avaliacoes_google`, que é de onde a fila lê.

O fluxo olha 30 minutos para trás e o CRM dispara a cada 29, contando do
último disparo: as janelas se encostam, cada avaliação cai numa busca só (o
alerta de negativa do fluxo não sai dobrado) e disparo que falha é repetido em
1 minuto. Avaliação que chega de novo é a mesma (`reviewId`) e não duplica.

O corpo aceito é o bloco como o fluxo manda — a lista de avaliações:

    [{"unidade": "UnidadeCentro", "idUnidade": "1234567890123456789",
      "comentario": "(Translated by Google) …\\n\\n(Original)\\n…",
      "notaReview": "ONE", "reviewId": "…", "displayName": "…",
      "dataHora": "2026-10-13T15:05:00.000000Z", "url": "…"}, …]

(também `{"result": […]}`, `{"avaliacoes": […]}` ou qualquer um deles como
texto JSON). Corpo vazio ou `[]` = a busca rodou e não achou nada novo.
Comentário maior que o bloco vem em pedaços, um por POST, com `parte` e
`totalPartes`; o CRM junta (ver `receber`). Opcional por item: `resposta`
(texto já publicado no Google).

Roda dentro da API, como o agente do iFood: sobe junto (ver `app/main.py`), e
`WORKER_DESLIGADO` desliga. Um disparo avulso pelo terminal:

    cd backend && uv run python -m app.services.integracoes.leitor_google
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.config import settings
from app.services.integracoes import google, nichochat, store
from app.services.integracoes.comum import momento

logger = logging.getLogger("integracoes.leitor_google")

ORIGEM = "google"
ESPERA_INICIAL_SEG = 45
TEMPO_MAXIMO_SEG = 2 * 60
# O laço confere a hora do último disparo a cada minuto, e um disparo que
# falhou é repetido nesse prazo (ver `espera_seg`).
_CONFERE_SEG = 60
_REPETIR_FALHA_SEG = 60

# Onde a lista pode vir dentro do corpo. "result" é a saída do JavaScript do
# fluxo; as outras, para o caso de o corpo ser montado à mão.
_CHAVES_LISTA = ("result", "avaliacoes", "reviews", "data")


def intervalo_min() -> int:
    # Teto de 30: o fluxo só olha os últimos 30 minutos. Disparar mais espaçado
    # que isso deixaria avaliação de fora sem ninguém perceber. O padrão é 29.
    return min(30, max(5, settings.google_leitura_intervalo_min))


# ---------------------------------------------------------------------------
# O que chega do NichoChat
# ---------------------------------------------------------------------------

def itens_do_corpo(corpo: Any) -> list:
    """A lista de avaliações, venha como vier (ver o topo do arquivo).

    Corpo vazio é "nada novo" (lista vazia): é o que o fluxo manda quando a
    busca não achou avaliação, e serve para o CRM saber que a leitura rodou.

    ValueError quando não dá para achar uma lista — a rota devolve 422 com o
    motivo, que é o que quem está montando o fluxo precisa ver.
    """
    for _ in range(4):
        if corpo is None:
            return []
        if isinstance(corpo, list):
            return corpo
        if isinstance(corpo, (str, bytes)):
            if not corpo.strip():
                return []
            try:
                corpo = json.loads(corpo)
            except ValueError as exc:
                raise ValueError("o corpo não é JSON válido") from exc
            continue
        if isinstance(corpo, dict):
            for chave in _CHAVES_LISTA:
                if chave in corpo:
                    corpo = corpo[chave]
                    break
            else:
                raise ValueError('não achei a lista de avaliações no corpo (esperado "result")')
            continue
        break
    raise ValueError("a lista de avaliações não veio como lista")


def nota(valor: Any) -> int:
    """'ONE'…'FIVE' (como o Google manda) ou 1…5. Fora disso, 0."""
    if isinstance(valor, bool):
        return 0
    if isinstance(valor, (int, float)):
        n = int(valor)
    else:
        texto = str(valor or "").strip().upper()
        if texto in google.ESTRELAS:
            return google.ESTRELAS[texto]
        if not texto.isdigit():
            return 0
        n = int(texto)
    return n if 1 <= n <= 5 else 0


def chave_de_nome(texto: Any) -> str:
    """'Shopping D. Centro', 'ShoppingDCentro' e 'shopping-d-centro' viram a mesma
    chave: sem acento, sem pontuação, minúsculo."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sem_acento if c.isalnum()).lower()


def normalizar_item(item: dict) -> dict:
    """Um item do fluxo no formato de `google.normalizar` (o que a fila usa)."""
    resposta = str(item.get("resposta") or "").strip()
    return {
        "id": str(item.get("reviewId") or "").strip(),
        "nota": nota(item.get("notaReview")),
        # O Google manda "(Translated by Google) … (Original) …" quando o idioma
        # difere do da conta; vale o que o cliente escreveu.
        "comentario": google.original(item.get("comentario")),
        "autor": str(item.get("displayName") or "").strip() or None,
        "criada_em": momento(item.get("dataHora")),
        "atualizada_em": None,
        "respostas": [{"texto": resposta, "de": "MERCHANT",
                       "criada_em": momento(item.get("respostaData"))}] if resposta else [],
    }


def pedaco(item: dict) -> tuple[int, int] | None:
    """(parte, totalPartes) quando o comentário veio dividido; None quando
    veio inteiro (sem os campos, ou totalPartes 1)."""
    try:
        parte = int(item.get("parte") or 0)
        total = int(item.get("totalPartes") or 0)
    except (TypeError, ValueError):
        return None
    if total <= 1 or not 1 <= parte <= total:
        return None
    return parte, total


# Marca o comentário a que ainda falta pedaço. Some quando o resto chega.
INCOMPLETO = " […]"


def juntar_pedacos(partes: list[dict]) -> tuple[dict, bool]:
    """Os pedaços guardados de uma avaliação viram um item só, com o
    comentário inteiro (na ordem de `parte`). Devolve (item, completo)."""
    partes = sorted(partes, key=lambda p: p["parte"])
    total = max(p["total"] for p in partes)
    item = {k: v for k, v in partes[0]["item"].items() if k not in ("parte", "totalPartes")}
    item["comentario"] = "".join(str(p["item"].get("comentario") or "") for p in partes)
    return item, len(partes) >= total


async def receber(conn: AsyncConnection, corpo: Any) -> dict:
    """Guarda o que o NichoChat mandou e devolve o resumo para ele.

    A unidade sai do `idUnidade`; se vier vazio ou desconhecido, do nome
    (`unidade`). Item sem unidade conhecida ou sem `reviewId` é ignorado e
    volta na resposta com o motivo.

    Comentário longo chega em pedaços, um por POST (`parte` / `totalPartes`,
    mesmo `reviewId`): cada pedaço é guardado e a avaliação é gravada com o
    texto juntado até ali — completa quando chega o último.
    """
    itens = itens_do_corpo(corpo)
    lojas = await store.lojas(conn, ORIGEM)
    por_id = {l["loja_id"]: l for l in lojas}
    por_nome = {chave_de_nome(l["nome"]): l for l in lojas}

    novas = 0
    unidades: set[str] = set()
    ignoradas: list[dict] = []
    faltando: list[str] = []
    for item in itens:
        if not isinstance(item, dict):
            ignoradas.append({"reviewId": None, "motivo": "item não é um objeto"})
            continue
        review_id = str(item.get("reviewId") or "").strip()
        completo = True
        if review_id and (p := pedaco(item)):
            partes = await store.guardar_parte_google(conn, review_id, *p, item)
            item, completo = juntar_pedacos(partes)
            if completo:
                await store.apagar_partes_google(conn, review_id)
            else:
                faltando.append(review_id)
        av = normalizar_item(item)
        if not completo:
            av["comentario"] = (av["comentario"] or "") + INCOMPLETO
        if not av["id"]:
            ignoradas.append({"reviewId": None, "motivo": "sem reviewId"})
            continue
        loja = (por_id.get(str(item.get("idUnidade") or "").strip())
                or por_nome.get(chave_de_nome(item.get("unidade"))))
        if loja is None:
            ignoradas.append({
                "reviewId": av["id"],
                "motivo": f"unidade desconhecida: {item.get('idUnidade') or item.get('unidade')!r}"})
            continue
        n, _mudadas = await store.gravar_google(
            conn, loja["loja_id"], [av], preservar_resposta=not av["respostas"])
        novas += n
        unidades.add(loja["loja_id"])

    # O fluxo varre todas as unidades: todas foram lidas agora, inclusive as
    # que não tiveram avaliação nova — é o que tira o "aguardando a primeira
    # leitura" da tela.
    ativas = [l for l in lojas if l["ativo"]]
    for l in ativas:
        await store.marcar_leitura(conn, l["loja_id"])
    confirmadas = await store.confirmar_encaminhadas_google(conn)
    await store.registrar_execucao(conn, {
        "lojas": len(ativas), "encontradas": novas, "respondidas": confirmadas,
        "erros": len(ignoradas), "duracao_ms": 0}, ORIGEM)
    logger.info("NichoChat entregou %s avaliações do Google: %s novas, %s ignoradas",
                len(itens), novas, len(ignoradas))
    return {"recebidas": len(itens), "novas": novas, "unidades": len(unidades),
            "confirmadas": confirmadas, "ignoradas": ignoradas,
            **({"aguardando_partes": faltando} if faltando else {})}


# ---------------------------------------------------------------------------
# A confirmação da resposta
# ---------------------------------------------------------------------------
#
# O subfluxo "Responder Comentários - Google My Business", depois de publicar, avisa o CRM:
#
#   POST /webhooks/nichochat/resposta-google
#   {"reviewId": "{{review_id_resposta}}", "idUnidade": "{{ID_localizacao_resposta}}",
#    "resposta": "{{resposta_comentario}}"}
#
# e, se não conseguiu publicar, {"reviewId": "…", "status": "erro", "erro": "…"}.
# Sem esse aviso em 15 minutos, a avaliação volta para a fila com "não apareceu
# no Google" (ver `_encaminhamento` em routers/integracoes.py).
#
# O fluxo monta esse JSON colando a resposta entre aspas. Resposta com quebra
# de linha ou com aspas deixa o corpo inválido — e é comum. Aí o aviso vale
# pelo reviewId, e o texto publicado é o que o CRM mandou (`_aviso_de_texto`).

_CHAVES_REVIEW = ("reviewId", "review_id_resposta", "Review_id", "review_id")
# Marca o aviso salvo de um corpo inválido: o texto vem do que o CRM enviou.
_TEXTO_DO_CRM = "_texto_do_crm"

def _primeiro(item: dict, *chaves: str) -> str:
    for chave in chaves:
        valor = item.get(chave)
        if valor not in (None, ""):
            return str(valor).strip()
    return ""


def _aviso_de_texto(texto: str) -> dict | None:
    """O aviso de um corpo que não é JSON válido (ver acima): o reviewId, a
    unidade e se é aviso de falha. None quando nem o reviewId aparece."""
    def campo(nome: str) -> str:
        m = re.search(rf'"{nome}"\s*:\s*"([^"\\]*)"', texto)
        return m.group(1).strip() if m else ""

    review_id = next((v for v in map(campo, _CHAVES_REVIEW) if v), "")
    if not review_id:
        return None
    item = {"reviewId": review_id, "idUnidade": campo("idUnidade"), _TEXTO_DO_CRM: True}
    if campo("status"):
        item["status"] = campo("status")
        item["erro"] = campo("erro")
    return item


def confirmacoes_do_corpo(corpo: Any) -> list[dict]:
    """Um aviso ou uma lista deles, como objeto, lista, `{"result": …}` ou texto."""
    for _ in range(4):
        if isinstance(corpo, (str, bytes)):
            texto = corpo.decode("utf-8", "replace") if isinstance(corpo, bytes) else corpo
            try:
                corpo = json.loads(texto)
            except ValueError as exc:
                aviso = _aviso_de_texto(texto)
                if aviso is None:
                    raise ValueError("o corpo não é JSON válido") from exc
                return [aviso]
            continue
        if isinstance(corpo, dict) and "result" in corpo and not _primeiro(
                corpo, *_CHAVES_REVIEW):
            corpo = corpo["result"]
            continue
        break
    itens = corpo if isinstance(corpo, list) else [corpo]
    if not all(isinstance(i, dict) for i in itens):
        raise ValueError("cada aviso precisa ser um objeto com reviewId")
    return itens


def _falhou(item: dict) -> bool:
    status = str(item.get("status", "")).strip().lower()
    return status in ("erro", "error", "falhou", "fail", "failed") or item.get("ok") is False


async def confirmar_resposta(conn: AsyncConnection, corpo: Any) -> dict:
    """Grava o aviso do NichoChat: publicada (sai da fila) ou falhou (volta
    com o motivo). Devolve o que foi feito com cada aviso."""
    feitos: list[dict] = []
    for item in confirmacoes_do_corpo(corpo):
        review_id = _primeiro(item, *_CHAVES_REVIEW)
        if not review_id:
            feitos.append({"reviewId": None, "resultado": "ignorado", "motivo": "sem reviewId"})
            continue
        if _falhou(item):
            erro = _primeiro(item, "erro", "error", "mensagem", "message") or "sem detalhe"
            marcado = await store.resposta_falhou_google(conn, review_id, erro)
            feitos.append({"reviewId": review_id, "resultado": "falha registrada" if marcado
                           else "ignorado", **({} if marcado else {
                               "motivo": "nenhuma resposta do CRM esperando por este aviso"})})
            continue
        texto = _primeiro(item, "resposta", "resposta_comentario", "comment", "comentario")
        if not texto and item.get(_TEXTO_DO_CRM):
            texto = await store.resposta_encaminhada_google(conn, review_id) or ""
        if not texto:
            feitos.append({"reviewId": review_id, "resultado": "ignorado",
                           "motivo": "nenhuma resposta do CRM esperando por este aviso"
                           if item.get(_TEXTO_DO_CRM) else "sem o texto publicado (resposta)"})
            continue
        confirmado = await store.resposta_publicada_google(conn, review_id, texto)
        feitos.append({"reviewId": review_id,
                       "resultado": "publicada" if confirmado else "resposta gravada"})
    logger.info("NichoChat confirmou %s resposta(s) do Google", len(feitos))
    return {"avisos": feitos}


# ---------------------------------------------------------------------------
# O disparo da busca
# ---------------------------------------------------------------------------

async def rodar(conn: AsyncConnection) -> dict | None:
    """Dispara a busca no NichoChat. None quando não disparou (sem
    configuração, ou outro disparo em andamento)."""
    if not nichochat.busca_configurada():
        await conn.rollback()
        logger.info("NichoChat não configurado; a busca do Google não roda")
        return None
    if not await store.tomar_trava(conn, ORIGEM):
        logger.info("já existe um disparo da busca do Google em andamento, ignorando")
        return None
    try:
        erro = None
        try:
            await nichochat.disparar_busca_google()
        except nichochat.ErroNichoChat as exc:
            erro = str(exc)
            logger.warning("busca do Google no NichoChat: %s", erro)
        await store.marcar_disparo(conn, ORIGEM, erro)
        if erro is None:
            # O fluxo só faz POST quando acha avaliação nova. Disparo aceito é o
            # sinal de que as unidades foram lidas — sem isto, numa madrugada
            # quieta a tela diria "lida há 8 h" com a busca rodando normal.
            for loja in await store.lojas(conn, ORIGEM, apenas_ativas=True):
                await store.marcar_leitura(conn, loja["loja_id"])
        await conn.commit()
        return {"disparado": erro is None, "erro": erro}
    finally:
        await conn.rollback()
        await store.soltar_trava(conn, ORIGEM)


async def rodar_na_api() -> None:
    """Um disparo dentro da API, com conexão própria do pool."""
    from app.db import get_pool  # import tardio: o pool só existe com a API de pé

    try:
        async with get_pool().connection() as conn:
            await asyncio.wait_for(rodar(conn), timeout=TEMPO_MAXIMO_SEG)
    except Exception:
        logger.exception("disparo da busca do Google falhou")


def espera_seg(estado: dict) -> float:
    """Quanto falta para o próximo disparo, contado do ÚLTIMO — qualquer um: o
    agendado, o "Ler agora" ou o de antes de a API reiniciar.

    Contar do último (e não somar o intervalo a cada volta) é o que mantém as
    janelas encostadas: com 29 min de intervalo e o fluxo olhando 30 para trás,
    a folga é de 1 minuto, e não pode ir sendo comida pelo tempo de cada disparo
    nem sumir num reinício da API. Disparo que falhou é repetido em 1 minuto.
    """
    if estado.get("minutos") is None:
        return 0.0
    passo = _REPETIR_FALHA_SEG if estado.get("ultimo_disparo_erro") else intervalo_min() * 60
    return max(0.0, passo - estado["minutos"] * 60)


async def _proxima_espera() -> float:
    from app.db import get_pool  # import tardio: o pool só existe com a API de pé

    async with get_pool().connection() as conn:
        estado = await store.estado_disparo(conn, ORIGEM)
        await conn.commit()
    return espera_seg(estado)


async def agendar() -> None:
    """Dispara a busca a cada `intervalo_min()`, dentro do processo da API.

    Olha a hora do último disparo a cada minuto (no máximo) e dispara quando
    der o intervalo. Disparo que falha não derruba o laço; só o desligamento da
    API encerra.
    """
    logger.info("busca do Google no NichoChat agendada: a cada %s min", intervalo_min())
    await asyncio.sleep(ESPERA_INICIAL_SEG)
    while True:
        try:
            espera = await _proxima_espera() if nichochat.busca_configurada() else None
        except Exception:
            logger.exception("não deu para ler a hora do último disparo do Google")
            espera = _CONFERE_SEG
        if espera is None:
            # Sem configuração não há o que disparar; confere de novo depois.
            await asyncio.sleep(intervalo_min() * 60)
            continue
        if espera > 0:
            # Dorme no máximo 1 min: um "Ler agora" no meio recomeça a contagem.
            await asyncio.sleep(min(espera, _CONFERE_SEG))
            continue
        await rodar_na_api()
        # Folga mínima entre tentativas: se o disparo nem chegou a ser marcado
        # (outro em andamento), não fica girando.
        await asyncio.sleep(_CONFERE_SEG)


async def _principal() -> None:
    async with await AsyncConnection.connect(
        settings.database_url, row_factory=dict_row, prepare_threshold=None
    ) as conn:
        print(await asyncio.wait_for(rodar(conn), timeout=TEMPO_MAXIMO_SEG))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_principal())
