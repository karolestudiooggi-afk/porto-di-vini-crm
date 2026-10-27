"""Integração Alpha Code: normalização, identidade e idempotência.

Os payloads aqui são os exemplos reais enviados pelo parceiro.
"""

from app.services.alphacode import _data, _num, normalizar_telefone


CLIENTE = {
    "event": "customer.created",
    "version": 1,
    "sentAt": "2026-08-20T11:30:00-03:00",
    "customer": {
        "id": 123,
        "uuid": "5f98680f-6d84-4abc-8b12-b886a726aa00",
        "name": "Maria Exemplo",
        "firstName": "Maria",
        "lastName": "Lima",
        "phone": "21999990000",
        "email": "maria.exemplo@email.com",
        "document": "12345678900",
        "createdAt": "",
    },
}

CONSUMO = {
    "event": "consumption.created",
    "version": 1,
    "sentAt": "2026-08-20T11:35:00-03:00",
    "customer": {"id": 123, "uuid": "5f98680f-6d84-4abc-8b12-b886a726aa00",
                 "name": "Maria Exemplo", "phone": "21999990000",
                 "email": "maria.exemplo@email.com", "document": "12345678900"},
    "consumption": {
        "orderId": 456,
        "orderUuid": "e350fd9a-3049-42f7-8199-ecbbb8488905",
        "amount": 89.9, "subtotal": 79.9, "discount": 0, "deliveryFee": 10,
        "date": "2026-08-20 11:34:30",
        "status": "Pedido realizado",
        "items": [{"id": 10, "sku": "PIZZA-CALABRESA-G",
                   "name": "Pizza Calabresa Grande",
                   "quantity": 1, "unitPrice": 79.9, "total": 79.9}],
    },
}


def test_telefone_do_pdv_ganha_ddi():
    """O Alpha Code manda sem o 55; o Domani grava com.

    Sem isto, a mesma pessoa vira DUAS fichas — uma do bot e outra do PDV — e o
    histórico de consumo nunca encontra o contato certo.
    """
    assert normalizar_telefone("21999990000") == "5521999990000"
    assert normalizar_telefone("6332221111") == "556332221111"


def test_telefone_que_ja_tem_ddi_nao_e_alterado():
    assert normalizar_telefone("5521999990000") == "5521999990000"
    assert normalizar_telefone("556332221111") == "556332221111"


def test_telefone_aceita_formatacao():
    assert normalizar_telefone("(21) 99999-0000") == "5521999990000"


def test_telefone_vazio_vira_nulo():
    for v in ("", "   ", None, "abc"):
        assert normalizar_telefone(v) is None


def test_data_nos_dois_formatos_do_parceiro():
    """O parceiro usa um formato em `date` e outro em `sentAt`."""
    assert _data("2026-08-20 11:34:30").hour == 11
    assert _data("2026-08-20T11:30:00-03:00").year == 2026


def test_data_desconhecida_nao_quebra():
    """Formato novo não pode derrubar o webhook — vira nulo e segue."""
    assert _data("ontem à tarde") is None
    assert _data("") is None


def test_valores_monetarios():
    assert _num(89.9) == 89.9
    assert _num("79.90") == 79.9
    assert _num(0) == 0
    assert _num(None) is None
    assert _num("") is None


def test_payload_de_cliente_tem_o_que_precisamos():
    c = CLIENTE["customer"]
    assert c["uuid"] and c["phone"] and c["email"]


def test_payload_de_consumo_traz_pedido_e_itens():
    k = CONSUMO["consumption"]
    assert k["orderUuid"]
    assert _num(k["amount"]) == 89.9
    assert len(k["items"]) == 1


def test_idempotencia_e_por_uuid_do_pedido():
    """Reenvio do mesmo pedido não pode virar dois consumos nem inflar o total."""
    import inspect
    from app.services import alphacode

    fonte = inspect.getsource(alphacode.processar_consumo)
    # O índice é parcial: sem repetir o predicado, o Postgres não o reconhece e
    # o INSERT falha com "no unique or exclusion constraint matching".
    assert "ON CONFLICT (origem, pedido_uuid) WHERE pedido_uuid IS NOT NULL" in fonte
    assert "DO NOTHING" in fonte


def test_identidade_busca_do_mais_confiavel_ao_menos():
    """uuid > telefone > e-mail. Sem essa ordem, o cliente vira duas fichas."""
    import inspect
    from app.services import alphacode

    fonte = inspect.getsource(alphacode._achar_ou_criar_contato)
    assert "alphacode_uuid = %s" in fonte
    assert "telefone_norm = crm.fn_phone_canon(%s)" in fonte
    assert "email_norm = crm.fn_email_norm(%s)" in fonte


def test_webhook_grava_cru_antes_de_processar():
    """Se o processamento falhar, o payload tem que sobreviver para reprocesso."""
    import inspect
    from app.routers import webhooks

    fonte = inspect.getsource(webhooks.alphacode_webhook)
    assert fonte.index("registrar_evento") < fonte.index("TRATADORES.get")


def test_chave_comparada_em_tempo_constante():
    """`==` vazaria a chave byte a byte pelo tempo de resposta."""
    import inspect
    from app.routers import webhooks

    # A comparação mora em `_confere`, usada pelas duas chaves (Alpha Code e
    # avaliações do Google pelo NichoChat).
    assert "compare_digest" in inspect.getsource(webhooks._confere)
    assert "_confere" in inspect.getsource(webhooks._autorizado)
    assert "_confere" in inspect.getsource(webhooks._chave_do_nichochat)
    for rota in (webhooks.avaliacoes_google_webhook, webhooks.resposta_google_webhook):
        assert "_chave_do_nichochat" in inspect.getsource(rota)


def test_sem_chave_configurada_recusa_tudo():
    """Padrão seguro: melhor a integração não funcionar do que aceitar qualquer POST."""
    from app.routers.webhooks import _autorizado
    from app.config import settings

    if not settings.webhook_alphacode_key:
        assert _autorizado("qualquer-coisa") is False
        assert _autorizado(None) is False
