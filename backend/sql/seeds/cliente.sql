-- Dados da PORTO DI VINO — o que as migrations não trazem de propósito.
--
-- Rodar DEPOIS das migrations 001→021:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/sql/seeds/cliente.sql
--
-- Pode rodar de novo: tudo é ON CONFLICT DO NOTHING — reaplicar não desfaz o
-- que foi ajustado depois. Para MUDAR um valor já gravado, use UPDATE.
--
-- Este CRM só tem o módulo de e-mail (campanhas). NPS, Parceiros e Integrações
-- estão desligados, então não há contas de avaliação nem lojas aqui.
BEGIN;

-- ---------------------------------------------------------------------------
-- E-mail: remetente das campanhas
-- ---------------------------------------------------------------------------
-- O MESMO endereço de CAMPANHA_FROM_EMAIL no .env. Precisa:
--   1. existir como caixa de verdade (recebe as respostas e a verificação);
--   2. estar verificado no painel do SendPulse;
--   3. ter SPF/DKIM/DMARC no DNS do portodivino.com.br (docs/DNS-PORTODIVINO.md).
--
-- A CONFIRMAR com a Porto qual caixa assina as campanhas. Se mudar depois:
--   UPDATE email.remetentes SET email = 'novo@portodivino.com.br'
--    WHERE email = 'contato@portodivino.com.br';
INSERT INTO email.remetentes (email, nome, padrao) VALUES
  ('contato@portodivino.com.br', 'Porto Di Vino', true)
ON CONFLICT (email) DO NOTHING;

COMMIT;
