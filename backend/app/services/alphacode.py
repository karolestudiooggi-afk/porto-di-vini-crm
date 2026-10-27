"""Processamento dos webhooks do Alpha Code (PDV).

Dois eventos:

    customer.created     → cadastro de cliente
    consumption.created  → pedido, com itens

O fluxo é sempre o mesmo: grava o payload cru, processa, marca o resultado. Se o
processamento falhar, o evento fica com status 'erro' e o payload continua lá —
dá para corrigir o código e reprocessar sem perder nada.
"""

import logging
import re
from datetime import datetime
from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Json

logger = logging.getLogger(__name__)


def normalizar_telefone(bruto: str | None) -> str | None:
    """Deixa o telefone no formato que o CRM usa: com DDI 55 e o 9º dígito.

    O Alpha Code envia `21999990000` — 11 dígitos, sem DDI. O Domani grava com o
    55 na frente. Sem esta função, a MESMA pessoa entraria como duas fichas: uma
    vinda do bot e outra do PDV, e o histórico de consumo nunca encontraria o
    contato certo.

    A `crm.fn_phone_canon` não resolve sozinha porque ela só acrescenta o nono
    dígito quando o número já tem DDI.
    """
    if not bruto:
        return None
    d = re.sub(r"\D", "", bruto)
    if not d:
        return None

    # Já veio com DDI: deixa a função do banco cuidar do 9º dígito.
    if d.startswith("55") and len(d) in (12, 13):
        return d
    # 10 ou 11 dígitos = número nacional sem DDI.
    if len(d) in (10, 11):
        return f"55{d}"
    return d


def _data(valor: Any) -> datetime | None:
    """Aceita os dois formatos que o Alpha Code usa nos exemplos."""
    if not valor:
        return None
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        logger.warning("Data em formato desconhecido: %r", texto)
        return None


def _num(valor: Any) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


async def registrar_evento(
    conn: AsyncConnection, origem: str, evento: str | None, payload: dict
) -> int:
    """Grava o payload cru ANTES de processar. Devolve o id do evento."""
    row = await (
        await conn.execute(
            """INSERT INTO integra.webhook_eventos (origem, evento, payload)
               VALUES (%s, %s, %s) RETURNING id""",
            (origem, evento, Json(payload)),
        )
    ).fetchone()
    return row["id"]


async def _achar_ou_criar_contato(conn: AsyncConnection, cliente: dict) -> int | None:
    """Encontra a ficha do cliente ou cria uma nova.

    A ordem de busca vai do identificador mais confiável para o menos:

      1. uuid do Alpha Code — não muda nunca;
      2. telefone canônico  — o que o Domani também usa;
      3. e-mail normalizado.

    Sem essa cascata, um cliente que já conversou no WhatsApp e depois pediu pelo
    PDV viraria duas fichas, e o histórico ficaria partido em dois.
    """
    uuid = (cliente.get("uuid") or "").strip() or None
    telefone = normalizar_telefone(cliente.get("phone"))
    email = (cliente.get("email") or "").strip().lower() or None
    nome = (cliente.get("name") or "").strip() or None
    documento = (cliente.get("document") or "").strip() or None

    if not (uuid or telefone or email):
        return None  # sem nenhum identificador não há como ligar a ninguém

    achado = await (
        await conn.execute(
            """SELECT id FROM crm.contatos
                WHERE (%s::text IS NOT NULL AND alphacode_uuid = %s)
                   OR (%s::text IS NOT NULL AND telefone_norm = crm.fn_phone_canon(%s))
                   OR (%s::text IS NOT NULL AND email_norm = crm.fn_email_norm(%s))
                ORDER BY (alphacode_uuid = %s) DESC NULLS LAST, id
                LIMIT 1""",
            (uuid, uuid, telefone, telefone, email, email, uuid),
        )
    ).fetchone()

    if achado:
        # COALESCE em tudo: o PDV completa o que falta, nunca apaga o que o CRM
        # já sabe. `alphacode_uuid` é a exceção — se veio, é a identidade oficial.
        await conn.execute(
            """UPDATE crm.contatos SET
                 alphacode_uuid = coalesce(%s, alphacode_uuid),
                 nome           = coalesce(nome, %s),
                 telefone       = coalesce(telefone, %s),
                 email          = coalesce(email, %s),
                 documento      = coalesce(documento, %s),
                 origens        = (SELECT array_agg(DISTINCT e ORDER BY e)
                                     FROM unnest(origens || ARRAY['Alpha Code']) e)
               WHERE id = %s""",
            (uuid, nome, telefone, email, documento, achado["id"]),
        )
        return achado["id"]

    novo = await (
        await conn.execute(
            """INSERT INTO crm.contatos
                 (alphacode_uuid, nome, primeiro_nome, sobrenome, telefone, email,
                  documento, origem, origens)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'Alpha Code',ARRAY['Alpha Code'])
               RETURNING id""",
            (uuid, nome,
             (cliente.get("firstName") or "").strip() or None,
             (cliente.get("lastName") or "").strip() or None,
             telefone, email, documento),
        )
    ).fetchone()
    return novo["id"]


async def processar_cliente(conn: AsyncConnection, payload: dict) -> dict:
    """`customer.created` — cria ou completa a ficha."""
    cliente = payload.get("customer") or {}
    contato_id = await _achar_ou_criar_contato(conn, cliente)
    if contato_id is None:
        return {"ok": False, "motivo": "cliente sem telefone, e-mail ou uuid"}
    return {"ok": True, "contato_id": contato_id}


async def processar_consumo(conn: AsyncConnection, payload: dict) -> dict:
    """`consumption.created` — registra o pedido e liga ao cliente."""
    cliente = payload.get("customer") or {}
    consumo = payload.get("consumption") or {}

    pedido_uuid = (consumo.get("orderUuid") or "").strip() or None
    pedido_id = str(consumo.get("orderId") or "").strip() or None

    contato_id = await _achar_ou_criar_contato(conn, cliente)

    # ON CONFLICT DO NOTHING sobre (origem, pedido_uuid): reenvio do mesmo pedido
    # — retry do parceiro, falha de rede — não vira consumo duplicado, e o
    # faturamento não infla.
    inserido = await (
        await conn.execute(
            """INSERT INTO crm.consumos
                 (contato_id, pedido_uuid, pedido_id, valor, subtotal, desconto,
                  taxa_entrega, situacao, ocorrido_em,
                  cliente_nome, cliente_telefone, cliente_email, cliente_doc)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               -- O índice é PARCIAL (WHERE pedido_uuid IS NOT NULL); o Postgres
               -- exige a mesma condição aqui para reconhecê-lo. Sem ela:
               -- "there is no unique or exclusion constraint matching".
               ON CONFLICT (origem, pedido_uuid) WHERE pedido_uuid IS NOT NULL
               DO NOTHING
               RETURNING id""",
            (
                contato_id, pedido_uuid, pedido_id,
                _num(consumo.get("amount")), _num(consumo.get("subtotal")),
                _num(consumo.get("discount")), _num(consumo.get("deliveryFee")),
                (consumo.get("status") or "").strip() or None,
                _data(consumo.get("date")),
                (cliente.get("name") or "").strip() or None,
                normalizar_telefone(cliente.get("phone")),
                (cliente.get("email") or "").strip().lower() or None,
                (cliente.get("document") or "").strip() or None,
            ),
        )
    ).fetchone()

    if inserido is None:
        return {"ok": True, "duplicado": True, "pedido_uuid": pedido_uuid}

    consumo_id = inserido["id"]
    for item in consumo.get("items") or []:
        await conn.execute(
            """INSERT INTO crm.consumo_itens
                 (consumo_id, sku, nome, quantidade, preco_unit, total)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (consumo_id,
             (item.get("sku") or "").strip() or None,
             (item.get("name") or "").strip() or None,
             _num(item.get("quantity")), _num(item.get("unitPrice")),
             _num(item.get("total"))),
        )

    return {"ok": True, "consumo_id": consumo_id, "contato_id": contato_id}


# Eventos que sabemos tratar. Qualquer outro é registrado como 'ignorado' — se o
# parceiro passar a mandar algo novo, aparece no log em vez de sumir.
TRATADORES = {
    "customer.created": processar_cliente,
    "consumption.created": processar_consumo,
}
