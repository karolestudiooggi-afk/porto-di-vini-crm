-- Dados da PORTO DI VINO — o que as migrations não trazem de propósito.
--
-- Rodar DEPOIS das migrations 001→021 (o ./scripts/instalar.sh e o
-- ./scripts/atualizar.sh já rodam):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/sql/seeds/cliente.sql
--
-- Pode rodar de novo: nada aqui duplica.
--
-- Este CRM só tem o módulo de e-mail (campanhas). NPS, Parceiros e Integrações
-- estão desligados, então não há contas de avaliação nem lojas aqui.
BEGIN;

-- ---------------------------------------------------------------------------
-- E-mail: remetente das campanhas
-- ---------------------------------------------------------------------------
-- O MESMO endereço de CAMPANHA_FROM_EMAIL no .env:
--   "Porto Di Vino <borabrindar@portodivino.com.br>"
-- Precisa estar verificado no painel do SendPulse e ter SPF/DKIM no DNS do
-- portodivino.com.br (docs/DNS-PORTODIVINO.md).
--
-- Histórico: contato@ (provisório) e depois site@. Os antigos ficam na tabela,
-- inativos — campanhas já enviadas continuam mostrando por onde saíram.

-- Só um padrão por vez: tira o padrão de quem não é o borabrindar@...
UPDATE email.remetentes SET padrao = false
 WHERE padrao AND email <> 'borabrindar@portodivino.com.br';

-- ...e põe nele.
INSERT INTO email.remetentes (email, nome, padrao) VALUES
  ('borabrindar@portodivino.com.br', 'Porto Di Vino', true)
ON CONFLICT (email) DO UPDATE SET padrao = true, ativo = true;

UPDATE email.remetentes SET ativo = false
 WHERE email IN ('contato@portodivino.com.br', 'site@portodivino.com.br');

COMMIT;
