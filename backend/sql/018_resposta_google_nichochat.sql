-- 018 — Resposta do Google publicada pelo NichoChat.
--
-- A resposta que a atendente escreve no CRM não vai mais direto para o Google:
-- o CRM grava Id_localizacao, Review_id e resposta_comentario num contato do
-- NichoChat e dispara o subfluxo "Responder Avaliações Google", que publica
-- pela conexão Google de lá (ver docs/INTEGRACOES.md).
--
-- O NichoChat responde "ok" quando o fluxo DISPAROU, não quando a resposta
-- apareceu no Google. Daí o status novo:
--
--   encaminhada: entregue ao NichoChat, ainda não vista no Google.
--                Vira 'enviada' quando a fila do CRM lê a avaliação e encontra
--                o texto publicado.
--
-- Idempotente: pode rodar de novo.
BEGIN;

ALTER TABLE integra.avaliacao_respostas
  DROP CONSTRAINT IF EXISTS avaliacao_respostas_status_check;
ALTER TABLE integra.avaliacao_respostas
  ADD CONSTRAINT avaliacao_respostas_status_check
  CHECK (status IN ('pendente', 'enviada', 'encaminhada', 'ignorada', 'erro'));

COMMENT ON COLUMN integra.avaliacao_respostas.status IS
  'pendente: vista e avisada | enviada: publicada | encaminhada: entregue ao '
  'NichoChat para publicar no Google, ainda não confirmada | ignorada: abaixo da '
  'nota mínima no automático | erro: a publicação falhou';

COMMIT;
