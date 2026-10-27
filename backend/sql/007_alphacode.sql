-- 007 — Integração Alpha Code (PDV): consumo e cadastro por webhook.
--
-- O Alpha Code envia um POST a cada cliente cadastrado (`customer.created`) e a
-- cada pedido (`consumption.created`). Esta migration cria onde guardar.
--
-- Três tabelas, com papéis distintos:
--
--   webhook_eventos  → o payload CRU, como chegou. Gravado ANTES de processar.
--   consumos         → o pedido, já normalizado e ligado à ficha do cliente.
--   consumo_itens    → os itens do pedido.
--
-- POR QUE GUARDAR O PAYLOAD CRU
--
-- Quando o formato do parceiro mudar (e muda), o processamento quebra. Com o
-- payload salvo, dá para corrigir o código e reprocessar; sem ele, o dado
-- daquele período está perdido para sempre. É a diferença entre um susto e um
-- prejuízo.
BEGIN;

CREATE SCHEMA IF NOT EXISTS integra;

-- ---------------------------------------------------------------------------
-- Recebimento cru
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS integra.webhook_eventos (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  origem      text NOT NULL,              -- 'alphacode', 'tagme', ...
  evento      text,                       -- customer.created | consumption.created
  payload     jsonb NOT NULL,
  -- Estado do processamento. 'ignorado' é para evento que reconhecemos mas não
  -- tratamos — melhor registrar do que descartar em silêncio.
  status      text NOT NULL DEFAULT 'recebido'
    CHECK (status IN ('recebido', 'processado', 'ignorado', 'erro')),
  erro        text,
  recebido_em timestamptz NOT NULL DEFAULT now(),
  processado_em timestamptz
);

CREATE INDEX IF NOT EXISTS ix_webhook_origem_data
  ON integra.webhook_eventos (origem, recebido_em DESC);
CREATE INDEX IF NOT EXISTS ix_webhook_erro
  ON integra.webhook_eventos (status) WHERE status = 'erro';

COMMENT ON TABLE integra.webhook_eventos IS
  'Payload cru de cada webhook recebido, antes de qualquer processamento. '
  'Permite reprocessar quando o formato do parceiro mudar.';

-- ---------------------------------------------------------------------------
-- Consumo
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS crm.consumos (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  contato_id    bigint REFERENCES crm.contatos(id) ON DELETE SET NULL,
  origem        text NOT NULL DEFAULT 'alphacode',

  -- Identificador do pedido no sistema de origem. É a chave da idempotência:
  -- o parceiro pode reenviar o mesmo pedido (retry, falha de rede) e não pode
  -- virar dois consumos.
  pedido_uuid   text,
  pedido_id     text,

  valor         numeric(12,2),   -- total pago (amount)
  subtotal      numeric(12,2),
  desconto      numeric(12,2),
  taxa_entrega  numeric(12,2),
  situacao      text,
  ocorrido_em   timestamptz,

  -- Snapshot de quem era o cliente no momento do pedido. Guardado porque a ficha
  -- pode mudar (ou ser apagada) e o histórico do pedido não deve mudar junto.
  cliente_nome     text,
  cliente_telefone text,
  cliente_email    text,
  cliente_doc      text,

  criado_em     timestamptz NOT NULL DEFAULT now()
);

-- Idempotência: o mesmo pedido não entra duas vezes, nem que o parceiro reenvie.
CREATE UNIQUE INDEX IF NOT EXISTS ux_consumos_pedido_uuid
  ON crm.consumos (origem, pedido_uuid) WHERE pedido_uuid IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_consumos_contato    ON crm.consumos (contato_id, ocorrido_em DESC);
CREATE INDEX IF NOT EXISTS ix_consumos_ocorrido   ON crm.consumos (ocorrido_em DESC);

CREATE TABLE IF NOT EXISTS crm.consumo_itens (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  consumo_id   bigint NOT NULL REFERENCES crm.consumos(id) ON DELETE CASCADE,
  sku          text,
  nome         text,
  quantidade   numeric(12,3),
  preco_unit   numeric(12,2),
  total        numeric(12,2)
);

CREATE INDEX IF NOT EXISTS ix_consumo_itens_consumo ON crm.consumo_itens (consumo_id);

-- Identificador do cliente no PDV, para casar sem depender de telefone/e-mail.
ALTER TABLE crm.contatos
  ADD COLUMN IF NOT EXISTS alphacode_uuid text,
  ADD COLUMN IF NOT EXISTS documento      text;

CREATE UNIQUE INDEX IF NOT EXISTS ux_contatos_alphacode
  ON crm.contatos (alphacode_uuid) WHERE alphacode_uuid IS NOT NULL;

COMMENT ON COLUMN crm.contatos.alphacode_uuid IS
  'UUID do cliente no Alpha Code. É a chave de identidade mais confiável entre '
  'os dois sistemas — telefone e e-mail mudam, este não.';

-- ---------------------------------------------------------------------------
-- Visão de consumo por cliente
-- ---------------------------------------------------------------------------
--
-- É esta view que finalmente dá ao CRM os números que faltavam: ticket médio,
-- total gasto, frequência. Até aqui o Domani era a única fonte e não fornecia
-- nada disso.

CREATE OR REPLACE VIEW crm.vw_consumo_cliente AS
SELECT
  c.id AS contato_id,
  count(*)                                   AS pedidos,
  sum(k.valor)                               AS total_gasto,
  round(avg(k.valor), 2)                     AS ticket_medio,
  min(k.ocorrido_em)                         AS primeiro_pedido,
  max(k.ocorrido_em)                         AS ultimo_pedido,
  (current_date - max(k.ocorrido_em)::date)  AS dias_desde_ultimo_pedido
FROM crm.contatos c
JOIN crm.consumos k ON k.contato_id = c.id
GROUP BY c.id;

COMMENT ON VIEW crm.vw_consumo_cliente IS
  'Consumo agregado por cliente. Derivado de crm.consumos — sempre fresco, sem '
  'passo de apply que possa divergir.';

COMMIT;
