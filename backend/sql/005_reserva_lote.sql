-- 005 — Reserva de lote no disparo de e-mail.
--
-- PROBLEMA QUE ISTO RESOLVE
--
-- O envio selecionava os destinatários 'pendente' e só depois marcava cada um
-- como 'enviado'. Entre a leitura e a escrita há uma janela — e nela cabe um
-- segundo disparo: a tela deu timeout e a pessoa clicou de novo, ou o timer
-- horário coincidiu com um clique manual. Os dois processos leriam a MESMA
-- lista, e a mesma pessoa receberia o e-mail duas vezes.
--
-- A solução é reservar o lote no mesmo comando que o seleciona
-- (UPDATE ... RETURNING com FOR UPDATE SKIP LOCKED, ver services/campanhas.py).
-- Para isso o destinatário precisa de um estado intermediário: 'processando'.
--
-- Quem for reservado mas não chegar a ser enviado (cota acabou no meio) volta
-- para 'pendente' no fim do disparo — senão ficaria preso e nunca mais sairia.
BEGIN;

ALTER TABLE email.recipients DROP CONSTRAINT IF EXISTS recipients_status_check;

ALTER TABLE email.recipients
  ADD CONSTRAINT recipients_status_check
  CHECK (status IN ('pendente', 'processando', 'enviado', 'falhou', 'suprimido'));

COMMENT ON COLUMN email.recipients.status IS
  'pendente = na fila | processando = reservado por um disparo em curso | '
  'enviado = saiu (nunca reenviar) | suprimido = endereço morto | falhou = erro definitivo';

-- Rede de segurança: se um processo morrer no meio (queda de energia, OOM), há
-- linhas presas em 'processando' que ninguém devolveria. Esta função libera as
-- que estão nesse estado há mais de uma hora — tempo muito maior que qualquer
-- disparo real, então não corre risco de liberar lote ativo.
CREATE OR REPLACE FUNCTION email.liberar_reservas_orfas() RETURNS int AS $$
DECLARE liberadas int;
BEGIN
  WITH devolvidas AS (
    UPDATE email.recipients SET status = 'pendente'
     WHERE status = 'processando'
       AND campaign_id IN (
         SELECT id FROM email.campaigns
          WHERE started_at < now() - interval '1 hour'
       )
    RETURNING 1
  )
  SELECT count(*) INTO liberadas FROM devolvidas;
  RETURN liberadas;
END;
$$ LANGUAGE plpgsql;

COMMIT;
