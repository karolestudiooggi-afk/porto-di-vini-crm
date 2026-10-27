-- 017 — Chave de API e lojas só no servidor.
--
-- Regra da casa: nenhuma chave de API é digitada, guardada ou mostrada pela
-- tela. A chave e o modelo da OpenAI ficam SÓ no .env (OPENAI_API_KEY,
-- OPENAI_MODEL). Esta migration apaga o que tenha sido salvo pela tela antiga.
--
-- ANTES DE RODAR: confira que o .env da API tem OPENAI_API_KEY. Se a chave só
-- existia na tela, a sugestão por IA para até ela ir para o .env.
--
-- As lojas (iFood) e unidades (Google) também passam a ser cadastradas aqui,
-- por SQL (backend/sql/seeds/cliente.sql). A tela só lista.
BEGIN;

UPDATE integra.config SET openai_api_key = NULL, openai_model = NULL
 WHERE openai_api_key IS NOT NULL OR openai_model IS NOT NULL;

COMMENT ON COLUMN integra.config.openai_api_key IS
  'Sem uso desde a 017: a chave da OpenAI fica só no .env (OPENAI_API_KEY).';
COMMENT ON COLUMN integra.config.openai_model IS
  'Sem uso desde a 017: o modelo fica só no .env (OPENAI_MODEL).';

-- ---------------------------------------------------------------------------
-- Lojas do iFood
-- ---------------------------------------------------------------------------
-- loja_id = o MERCHANT UUID (Developer Portal do iFood), não o código numérico
-- do Portal do Parceiro. Idempotente: rodar de novo não duplica nem desfaz
-- ajuste de nome/cidade.
--
-- Para acrescentar uma loja: uma linha nova no VALUES e rodar este arquivo de
-- novo. Para tirar da fila sem perder o histórico:
--   UPDATE integra.lojas SET ativo = false WHERE origem = 'ifood' AND loja_id = '…';
--
-- INSERT INTO integra.lojas (origem, loja_id, nome, cidade) VALUES
--   ('ifood', '00000000-0000-0000-0000-000000000000', 'Unidade Centro', 'Rio de Janeiro'),
--   ('ifood', '…', '…', '…')
-- ON CONFLICT (origem, loja_id) DO NOTHING;

COMMIT;
