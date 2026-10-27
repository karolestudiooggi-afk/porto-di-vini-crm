-- Dados da PORTO DI VINO — o que as migrations não trazem de propósito.
--
-- Rodar DEPOIS das migrations 001→021 (o ./scripts/instalar.sh e o
-- ./scripts/atualizar.sh já rodam):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/sql/seeds/cliente.sql
--
-- Pode rodar de novo: nada aqui duplica nem desfaz o que foi ajustado depois.
--
-- Este CRM só tem o módulo de e-mail (campanhas). NPS, Parceiros e Integrações
-- estão desligados, então não há contas de avaliação nem lojas aqui.
BEGIN;

-- ---------------------------------------------------------------------------
-- E-mail: remetente das campanhas
-- ---------------------------------------------------------------------------
-- O MESMO endereço de CAMPANHA_FROM_EMAIL no .env:
--   "Porto Di Vino <site@portodivino.com.br>"
-- Precisa estar verificado no painel do SendPulse e ter SPF/DKIM no DNS do
-- portodivino.com.br (docs/DNS-PORTODIVINO.md). A caixa site@ já existe na
-- Porto: recebe as respostas dos clientes e o e-mail de verificação.

-- A primeira instalação usou contato@ como provisório: renomeia.
UPDATE email.remetentes
   SET email = 'site@portodivino.com.br', nome = 'Porto Di Vino'
 WHERE email = 'contato@portodivino.com.br'
   AND NOT EXISTS (SELECT 1 FROM email.remetentes WHERE email = 'site@portodivino.com.br');

INSERT INTO email.remetentes (email, nome, padrao) VALUES
  ('site@portodivino.com.br', 'Porto Di Vino', true)
ON CONFLICT (email) DO NOTHING;

COMMIT;
