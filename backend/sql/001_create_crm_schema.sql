-- Migração 001 — ficha unificada de contatos do cliente.
--
-- O Domani é a única fonte atual. Fontes futuras devem permanecer em schemas
-- próprios e enriquecer `crm.contatos` explicitamente.
-- Idempotente e transacional. Reversão total: DROP SCHEMA crm CASCADE.

BEGIN;

CREATE SCHEMA IF NOT EXISTS crm;

-- Telefone brasileiro canônico. Celular BR com 12 dígitos e sem o nono dígito
-- recebe o 9 após o DDD. Números fora de 10–13 dígitos viram NULL.
CREATE OR REPLACE FUNCTION crm.fn_phone_canon(raw text)
RETURNS text
LANGUAGE sql IMMUTABLE
AS $$
  WITH d AS (
    SELECT regexp_replace(coalesce(raw, ''), '[^0-9]', '', 'g') AS t
  )
  SELECT CASE
    WHEN length(t) = 12
      AND left(t, 2) = '55'
      AND substring(t, 5, 1) IN ('6','7','8','9')
      THEN left(t, 4) || '9' || right(t, 8)
    ELSE t
  END
  FROM d
  WHERE length((SELECT t FROM d)) BETWEEN 10 AND 13;
$$;

CREATE OR REPLACE FUNCTION crm.fn_email_norm(raw text)
RETURNS text
LANGUAGE sql IMMUTABLE
AS $$
  SELECT nullif(lower(btrim(coalesce(raw, ''))), '');
$$;

CREATE OR REPLACE FUNCTION crm.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS crm.contatos (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

  -- Identidade compartilhável entre fontes
  telefone      text,
  telefone_norm text GENERATED ALWAYS AS (crm.fn_phone_canon(telefone)) STORED,
  email         text,
  email_norm    text GENERATED ALWAYS AS (crm.fn_email_norm(email)) STORED,
  user_ns       text,
  domani_user_id text,
  canal          text,
  origem         text,
  origens        text[] NOT NULL DEFAULT '{}',

  -- Cadastro nativo do Domani
  nome             text,
  primeiro_nome    text,
  sobrenome        text,
  genero           text,
  locale           text,
  idioma           text,
  url_foto_perfil  text,

  -- Engajamento nativo do Domani
  status             text,
  subscribed         timestamptz,
  last_interaction   timestamptz,
  last_message_at    timestamptz,
  last_message_type  text,

  -- Consentimento nativo relacionado a e-mail
  opt_in_email       boolean,
  opted_in_email     boolean,
  opted_in_through   text,

  -- Classificação
  tags       text[] NOT NULL DEFAULT '{}',
  etiquetas  text[] NOT NULL DEFAULT '{}',

  -- Controle
  domani_synced_at timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE crm.contatos IS
  'Ficha unificada de contatos do cliente. Domani é a fonte inicial; fontes futuras enriquecem esta tabela.';
COMMENT ON COLUMN crm.contatos.user_ns IS
  'Identificador técnico do contato dentro do Domani.';
COMMENT ON COLUMN crm.contatos.domani_user_id IS
  'Identificador do usuário no canal social; não deve ser interpretado como telefone.';
COMMENT ON COLUMN crm.contatos.origens IS
  'Todas as fontes que contribuíram para a ficha.';

CREATE UNIQUE INDEX IF NOT EXISTS ux_contatos_user_ns
  ON crm.contatos (user_ns) WHERE user_ns IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_contatos_telefone_norm
  ON crm.contatos (telefone_norm) WHERE telefone_norm IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_contatos_canal_domani_user
  ON crm.contatos (canal, domani_user_id)
  WHERE canal IS NOT NULL AND domani_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_contatos_email_norm
  ON crm.contatos (email_norm) WHERE email_norm IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_contatos_canal
  ON crm.contatos (canal);
CREATE INDEX IF NOT EXISTS ix_contatos_status
  ON crm.contatos (status);
CREATE INDEX IF NOT EXISTS ix_contatos_last_interaction
  ON crm.contatos (last_interaction DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_contatos_last_message_at
  ON crm.contatos (last_message_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS gin_contatos_tags
  ON crm.contatos USING gin (tags);
CREATE INDEX IF NOT EXISTS gin_contatos_etiquetas
  ON crm.contatos USING gin (etiquetas);
CREATE INDEX IF NOT EXISTS gin_contatos_origens
  ON crm.contatos USING gin (origens);

DROP TRIGGER IF EXISTS trg_contatos_updated_at ON crm.contatos;
CREATE TRIGGER trg_contatos_updated_at
  BEFORE UPDATE ON crm.contatos
  FOR EACH ROW EXECUTE FUNCTION crm.set_updated_at();

COMMIT;
