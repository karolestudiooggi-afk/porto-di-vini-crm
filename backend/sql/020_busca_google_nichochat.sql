-- 020 — Busca das avaliações do Google pelo NichoChat.
--
-- A leitura automática (019) passa a vir do NichoChat: a cada 29 minutos o CRM
-- dispara o subfluxo de busca no contato NICHOCHAT_CONTATO_USER_ID, e o
-- NichoChat devolve as avaliações novas por POST
-- (/webhooks/nichochat/avaliacoes-google). Aqui fica o resultado do último
-- disparo, para a tela dizer se a busca está rodando ou se o NichoChat recusou.
--
-- Precisa da 019 aplicada antes. Idempotente: pode rodar de novo.
BEGIN;

ALTER TABLE integra.agente_estado
  ADD COLUMN IF NOT EXISTS ultimo_disparo_em   timestamptz,
  ADD COLUMN IF NOT EXISTS ultimo_disparo_erro text;

INSERT INTO integra.agente_estado (origem) VALUES ('google')
ON CONFLICT (origem) DO NOTHING;

COMMIT;
