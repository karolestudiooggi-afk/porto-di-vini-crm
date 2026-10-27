# Integração Alpha Code (PDV)

Para clientes que usam o PDV Alpha Code. Ele envia um POST a cada cliente
cadastrado e a cada pedido. É esta integração que dá ao CRM os dados de consumo
— ticket médio, faturamento, frequência — que o Domani sozinho não fornece.
Não tem interruptor em `cliente.ts`: sem `WEBHOOK_ALPHACODE_KEY` o webhook
recusa tudo e o gráfico de consumo do dashboard fica vazio.

## O que passar para o parceiro

**URL:** `https://crmportodivino.estudiodomaniai.com.br/api/webhooks/alphacode`

**Método:** POST · **Content-Type:** `application/json`

**Autenticação:** cabeçalho `X-API-Key` com a chave combinada.

Gerar a chave:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Guardar em `WEBHOOK_ALPHACODE_KEY` no `.env` e reiniciar a API. Sem ela
preenchida o webhook recusa tudo com 401 — padrão seguro, para não aceitar POST
de qualquer origem gravando na base do cliente.

## Eventos tratados

| `event` | O que faz |
|---|---|
| `customer.created` | cria ou completa a ficha do cliente |
| `consumption.created` | registra o pedido com itens e liga ao cliente |

Evento diferente desses é registrado como `ignorado` — aparece no log em vez de
sumir em silêncio.

## Decisões que importam

**O payload cru é gravado ANTES de processar** (`integra.webhook_eventos`).
Quando o formato do parceiro mudar — e muda —, dá para corrigir o código e
reprocessar. Sem isso, o dado daquele período estaria perdido.

**A resposta é 200 mesmo quando o processamento falha.** Parceiro que recebe 500
costuma reenviar em loop, e alguns desligam a integração depois de N falhas. O
erro fica registrado do nosso lado, que é onde a gente resolve.

**Telefone ganha o DDI 55.** O Alpha Code envia `21999990000`; o Domani grava
`5521999990000`. Sem normalizar, a mesma pessoa viraria duas fichas e o histórico
de consumo nunca acharia o contato certo.

**Identidade em cascata:** uuid do Alpha Code → telefone canônico → e-mail. O
uuid é o mais confiável porque não muda; telefone e e-mail mudam.

**Idempotência por `orderUuid`.** Reenvio do mesmo pedido (retry, falha de rede)
não vira consumo duplicado nem infla o faturamento. É índice único no banco, não
checagem no código.

## Conferir se está chegando

```sql
-- últimos eventos recebidos
select id, evento, status, recebido_em, erro
  from integra.webhook_eventos
 where origem = 'alphacode'
 order by recebido_em desc limit 20;

-- eventos com erro (para reprocessar)
select id, evento, erro, payload
  from integra.webhook_eventos
 where origem = 'alphacode' and status = 'erro';

-- consumo por cliente
select * from crm.vw_consumo_cliente order by total_gasto desc limit 20;
```

## Testar antes de ligar em produção

```bash
curl -X POST https://crmportodivino.estudiodomaniai.com.br/api/webhooks/alphacode \
  -H "X-API-Key: SUA-CHAVE" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "customer.created",
    "version": 1,
    "customer": {
      "uuid": "teste-0001", "name": "Cliente Teste",
      "phone": "21999990000", "email": "teste@exemplo.com"
    }
  }'
```

Resposta esperada: `{"recebido": true, "processado": true}`.

Depois confira se a ficha apareceu:

```sql
select id, nome, telefone, telefone_norm, origem
  from crm.contatos where alphacode_uuid = 'teste-0001';
```

O `telefone_norm` deve estar como `5521999990000` — com o DDI.

## Outros parceiros

Um sistema novo (reservas, outro PDV) segue o mesmo desenho: rota própria em
`/webhooks/<parceiro>`, chave própria no `.env`, payload cru gravado em
`integra.webhook_eventos` antes de processar.
