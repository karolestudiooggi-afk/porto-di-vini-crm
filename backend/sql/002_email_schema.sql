-- Migração 002 — estrutura do disparador de e-mail.
--
-- A base de clientes continua em `crm.contatos`;
-- este schema armazena templates, campanhas e seu histórico operacional.
-- Não cria API, RBAC, bucket de imagens nem habilita SMTP.

BEGIN;

CREATE SCHEMA IF NOT EXISTS email;

CREATE OR REPLACE FUNCTION email.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS email.templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome text NOT NULL,
  assunto text NOT NULL DEFAULT '',
  html text NOT NULL DEFAULT '',
  design jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_templates_updated_at ON email.templates;
CREATE TRIGGER trg_templates_updated_at
  BEFORE UPDATE ON email.templates
  FOR EACH ROW EXECUTE FUNCTION email.set_updated_at();

CREATE TABLE IF NOT EXISTS email.campaigns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome text NOT NULL,
  template_id uuid NOT NULL REFERENCES email.templates(id),
  assunto text NOT NULL DEFAULT '',
  html_snapshot text NOT NULL DEFAULT '',
  segmento jsonb NOT NULL DEFAULT '{}'::jsonb,
  segmento_label text,
  remetente text,
  status text NOT NULL DEFAULT 'rascunho'
    CHECK (status IN ('rascunho', 'agendada', 'enviando', 'enviada', 'falhou', 'cancelada')),
  publico integer NOT NULL DEFAULT 0 CHECK (publico >= 0),
  com_email integer NOT NULL DEFAULT 0 CHECK (com_email >= 0),
  agendada_para timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_campaigns_updated_at ON email.campaigns;
CREATE TRIGGER trg_campaigns_updated_at
  BEFORE UPDATE ON email.campaigns
  FOR EACH ROW EXECUTE FUNCTION email.set_updated_at();

CREATE INDEX IF NOT EXISTS ix_campaigns_status_agendada
  ON email.campaigns (status, agendada_para);
CREATE INDEX IF NOT EXISTS ix_campaigns_created_at
  ON email.campaigns (created_at DESC);

-- Snapshot do público. `vars` conserva os valores usados na personalização mesmo
-- que a ficha seja enriquecida depois. O contato pode ser apagado sem perder o
-- histórico da campanha.
CREATE TABLE IF NOT EXISTS email.recipients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid NOT NULL REFERENCES email.campaigns(id) ON DELETE CASCADE,
  contato_id bigint REFERENCES crm.contatos(id) ON DELETE SET NULL,
  email text NOT NULL CHECK (btrim(email) <> ''),
  email_norm text GENERATED ALWAYS AS (crm.fn_email_norm(email)) STORED,
  nome text,
  vars jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente', 'enviado', 'falhou', 'suprimido')),
  erro text,
  sent_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_recipients_campaign_email
  ON email.recipients (campaign_id, email_norm);
CREATE INDEX IF NOT EXISTS ix_recipients_campaign_status
  ON email.recipients (campaign_id, status);
CREATE INDEX IF NOT EXISTS ix_recipients_contato
  ON email.recipients (contato_id) WHERE contato_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS email.events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  recipient_id uuid NOT NULL REFERENCES email.recipients(id) ON DELETE CASCADE,
  tipo text NOT NULL CHECK (tipo IN ('open', 'click')),
  url text,
  ip text,
  user_agent text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_events_recipient
  ON email.events (recipient_id);
CREATE INDEX IF NOT EXISTS ix_events_created_at
  ON email.events (created_at DESC);

CREATE TABLE IF NOT EXISTS email.suppressions (
  email text PRIMARY KEY,
  motivo text NOT NULL DEFAULT 'descadastro'
    CHECK (motivo IN ('descadastro', 'bounce', 'reclamacao', 'manual')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (email = crm.fn_email_norm(email))
);

-- A API futura normalmente conecta como `postgres`. Os grants continuam seguros
-- quando a migration for aplicada por outro superusuário do Supabase.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA crm, email TO postgres';
    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA crm, email TO postgres';
    EXECUTE 'GRANT ALL ON ALL SEQUENCES IN SCHEMA crm, email TO postgres';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA crm GRANT ALL ON TABLES TO postgres';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA crm GRANT ALL ON SEQUENCES TO postgres';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA email GRANT ALL ON TABLES TO postgres';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA email GRANT ALL ON SEQUENCES TO postgres';
  END IF;
END $$;

COMMIT;
