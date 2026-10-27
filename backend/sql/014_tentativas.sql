-- 014 — Erro passageiro deixa de ser definitivo.
--
-- Até aqui o agente pulava qualquer avaliação que já tivesse uma linha em
-- integra.avaliacao_respostas, qualquer que fosse o status. Uma falha de
-- momento — OpenAI fora do ar, 401 no fim da passada, rede caindo — gravava
-- 'erro' e aquela avaliação nunca mais era tentada: só respondendo na mão.
--
-- Agora o agente tenta de novo, com limite. A coluna conta as tentativas que
-- falharam em sequência e zera assim que a avaliação sai do erro.

BEGIN;

ALTER TABLE integra.avaliacao_respostas
  ADD COLUMN IF NOT EXISTS tentativas int NOT NULL DEFAULT 0;

COMMENT ON COLUMN integra.avaliacao_respostas.tentativas IS
  'Falhas seguidas ao tentar responder. Zera quando a avaliação sai do erro. '
  'O agente desiste ao chegar no limite definido em agente.MAX_TENTATIVAS.';

-- Linhas de 'erro' que já existem começam com uma tentativa gasta, não zero:
-- elas falharam uma vez antes desta migration.
UPDATE integra.avaliacao_respostas
   SET tentativas = 1
 WHERE status = 'erro' AND tentativas = 0;

COMMIT;
