-- Migração 004 — o que falta para DISPARAR de verdade.
--
-- A 002 modelou o disparador; esta migração acrescenta o que o envio real exige:
-- controle de cota do provedor, supressão automática por bounce e a trilha de
-- quem disparou o quê.
--
-- Todo plano de provedor SMTP tem limites. Exemplo (SendPulse Basic 25k):
--   • 25.000 e-mails por mês
--   • 2.500 e-mails por hora
--   • 5 endereços de remetente autorizados
-- Os do cliente vão no .env (SMTP_LIMITE_MES, SMTP_LIMITE_HORA).
-- Estourar qualquer um deles faz o provedor recusar a conexão no meio da
-- campanha — parte do público recebe, parte não, e não há como saber onde parou
-- sem consultar o banco. Por isso o controle é feito ANTES de cada envio.

BEGIN;

-- ---------------------------------------------------------------------------
-- Consumo do provedor
-- ---------------------------------------------------------------------------
-- Deliberadamente uma VIEW sobre `recipients`, e não uma tabela de contador:
-- contador paralelo desanda (envio que falha no meio, rollback, reprocessamento)
-- e passa a mentir justamente quando mais importa. `sent_at` é o fato.
CREATE OR REPLACE VIEW email.vw_consumo AS
SELECT
  -- Janela MÓVEL de 60 minutos, não hora cheia. O provedor conta assim; com
  -- date_trunc('hour') daria para mandar 2.500 às 10h59 e mais 2.500 às 11h01,
  -- 5.000 em dois minutos, e a conexão seria cortada no meio da segunda leva.
  count(*) FILTER (WHERE sent_at >= now() - interval '1 hour')   AS enviados_hora,
  -- Mês no fuso da operação (e do faturamento), não em UTC: perto da virada do
  -- mês os dois discordam por 3 horas.
  count(*) FILTER (
    WHERE sent_at >= (date_trunc('month', now() AT TIME ZONE 'America/Sao_Paulo')
                      AT TIME ZONE 'America/Sao_Paulo')
  )                                                              AS enviados_mes,
  count(*) FILTER (WHERE sent_at >= now() - interval '24 hours') AS enviados_24h,
  max(sent_at)                                                   AS ultimo_envio
FROM email.recipients
WHERE status = 'enviado' AND sent_at IS NOT NULL;

COMMENT ON VIEW email.vw_consumo IS
  'Consumo do plano do provedor, derivado de recipients.sent_at. Fonte única: '
  'não existe contador paralelo que possa divergir.';

-- ---------------------------------------------------------------------------
-- Remetentes autorizados
-- ---------------------------------------------------------------------------
-- O provedor só aceita envio a partir de endereços verificados no painel dele
-- (5 no plano atual). Se a campanha usar outro, o envio é recusado. Manter a
-- lista aqui permite validar na criação da campanha, e não no meio do disparo.
CREATE TABLE IF NOT EXISTS email.remetentes (
  email      text PRIMARY KEY CHECK (email = crm.fn_email_norm(email)),
  nome       text NOT NULL,
  padrao     boolean NOT NULL DEFAULT false,
  ativo      boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Só um remetente padrão por vez.
CREATE UNIQUE INDEX IF NOT EXISTS ux_remetentes_padrao
  ON email.remetentes ((padrao)) WHERE padrao;

-- ---------------------------------------------------------------------------
-- Rastreio do disparo
-- ---------------------------------------------------------------------------
ALTER TABLE email.campaigns
  ADD COLUMN IF NOT EXISTS disparada_por uuid,
  -- Quantos já foram processados. Permite retomar de onde parou quando a
  -- campanha excede a cota horária e precisa continuar depois.
  ADD COLUMN IF NOT EXISTS enviados int NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ultimo_erro text;

COMMENT ON COLUMN email.campaigns.enviados IS
  'Processados até agora. Uma campanha maior que a cota horária fica em '
  '"enviando" e retoma na janela seguinte — nunca é perdida no meio.';

-- ---------------------------------------------------------------------------
-- Bounce e reclamação
-- ---------------------------------------------------------------------------
-- Quando o provedor avisa que um endereço não existe (hard bounce) ou que o
-- destinatário marcou como spam, aquele e-mail tem que sair da base de envio na
-- hora. Continuar mandando para endereço morto derruba a reputação do domínio e
-- leva o resto das campanhas para a caixa de spam.
ALTER TABLE email.suppressions
  ADD COLUMN IF NOT EXISTS detalhe text,
  ADD COLUMN IF NOT EXISTS recipient_id uuid;

CREATE INDEX IF NOT EXISTS ix_suppressions_motivo
  ON email.suppressions (motivo, created_at DESC);

-- A view de consumo roda a CADA mensagem enviada. Sem este índice ela varre a
-- tabela inteira de destinatários toda vez.
CREATE INDEX IF NOT EXISTS ix_recipients_sent_at
  ON email.recipients (sent_at) WHERE sent_at IS NOT NULL;

-- O remetente do cliente NÃO vem aqui: fica em backend/sql/seeds/cliente.sql
-- (modelo em seeds/cliente.exemplo.sql). Precisa estar verificado no painel do
-- provedor, e o SPF/DKIM/DMARC precisa estar no DNS do domínio DESTE endereço —
-- não no do login SMTP, que costuma ser outro.

-- ---------------------------------------------------------------------------
-- Permissão
-- ---------------------------------------------------------------------------
INSERT INTO app.papel_permissoes (papel_id, permissao)
SELECT id, 'campanhas:manage' FROM app.papeis WHERE nome IN ('admin', 'operador')
ON CONFLICT DO NOTHING;

-- Só admin dispara de verdade. Operador monta e prevê; o disparo consome cota e
-- não tem desfazer.
INSERT INTO app.papel_permissoes (papel_id, permissao)
SELECT id, 'campanhas:send' FROM app.papeis WHERE nome = 'admin'
ON CONFLICT DO NOTHING;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA email TO postgres';
    EXECUTE 'GRANT ALL ON ALL SEQUENCES IN SCHEMA email TO postgres';
  END IF;
END $$;

COMMIT;
