-- 015 — E-mail para PARCEIROS, separado do e-mail para clientes.
--
-- A base de parceiros (empresas e contatos que a equipe comercial levantou) é
-- fria: nunca recebeu nada do cliente. Misturar esse envio com o dos clientes
-- arriscava duas coisas que dão trabalho para construir — a reputação do
-- remetente principal e a lista de clientes, que não pode receber comunicação
-- comercial B2B.
--
-- Por isso, dentro do mesmo módulo de e-mail:
--   * a base de parceiros é uma tabela PRÓPRIA (não entra em crm.contatos nem
--     aparece na tela de Contatos);
--   * template e campanha ganham `lista` ('clientes' | 'parceiros'): cada aba
--     só enxerga o que é dela. (O nome não é `publico` porque essa coluna já
--     existe na campanha e guarda a CONTAGEM de destinatários.)
--   * a campanha de parceiros sai por outro remetente (parcerias@);
--   * o descadastro de um parceiro vale para a lista de parceiros — ele não
--     some da base de clientes se também for cliente.
--
-- A cota do provedor continua UMA só (mesma conta SMTP): a view
-- email.vw_consumo soma os dois públicos, como o provedor soma.
BEGIN;

-- ---------------------------------------------------------------------------
-- Lista de template e campanha
-- ---------------------------------------------------------------------------
-- Tudo o que já existe é de clientes, e é o padrão: nada muda para as
-- campanhas e templates atuais.
ALTER TABLE email.templates
  ADD COLUMN IF NOT EXISTS lista text NOT NULL DEFAULT 'clientes';
ALTER TABLE email.campaigns
  ADD COLUMN IF NOT EXISTS lista text NOT NULL DEFAULT 'clientes';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'templates_lista_check') THEN
    ALTER TABLE email.templates
      ADD CONSTRAINT templates_lista_check CHECK (lista IN ('clientes', 'parceiros'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'campaigns_lista_check') THEN
    ALTER TABLE email.campaigns
      ADD CONSTRAINT campaigns_lista_check CHECK (lista IN ('clientes', 'parceiros'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_campaigns_lista
  ON email.campaigns (lista, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_templates_lista
  ON email.templates (lista, updated_at DESC);

COMMENT ON COLUMN email.campaigns.lista IS
  'clientes (base crm.contatos, remetente padrão) | parceiros (base '
  'email.parceiros, remetente de parcerias). Define de onde sai o público.';

-- ---------------------------------------------------------------------------
-- Base de parceiros
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email.parceiros (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nome        text,
  empresa     text,
  email       text NOT NULL CHECK (btrim(email) <> ''),
  email_norm  text GENERATED ALWAYS AS (crm.fn_email_norm(email)) STORED,
  telefone    text,
  cargo       text,
  cidade      text,
  tags        text[] NOT NULL DEFAULT '{}',
  observacoes text,
  -- De onde veio: o nome do arquivo importado, ou "manual".
  origem      text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Um e-mail, um parceiro. A importação usa isto para atualizar em vez de
-- duplicar quando a mesma planilha (ou uma versão nova dela) sobe de novo.
CREATE UNIQUE INDEX IF NOT EXISTS ux_parceiros_email ON email.parceiros (email_norm);
CREATE INDEX IF NOT EXISTS gin_parceiros_tags ON email.parceiros USING gin (tags);

DROP TRIGGER IF EXISTS trg_parceiros_updated_at ON email.parceiros;
CREATE TRIGGER trg_parceiros_updated_at
  BEFORE UPDATE ON email.parceiros
  FOR EACH ROW EXECUTE FUNCTION email.set_updated_at();

-- ---------------------------------------------------------------------------
-- Descadastro por lista
-- ---------------------------------------------------------------------------
-- O descadastro de cliente continua em email.suppressions (global, como
-- sempre). O de parceiro fica aqui, por lista, e sobrevive à exclusão da
-- ficha: apagar o parceiro e importar a planilha de novo NÃO pode voltar a
-- mandar e-mail para quem pediu para sair.
CREATE TABLE IF NOT EXISTS email.supressoes_lista (
  lista        text NOT NULL CHECK (lista IN ('parceiros')),
  email        text NOT NULL CHECK (email = crm.fn_email_norm(email)),
  motivo       text NOT NULL DEFAULT 'descadastro'
               CHECK (motivo IN ('descadastro', 'importacao', 'manual')),
  recipient_id uuid,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (lista, email)
);

-- ---------------------------------------------------------------------------
-- Destinatário de campanha de parceiros
-- ---------------------------------------------------------------------------
-- `contato_id` continua sendo o cliente; `parceiro_id` é o parceiro. Uma linha
-- tem um ou outro. SET NULL: apagar o parceiro não apaga o histórico da
-- campanha (quem recebeu, quem abriu).
ALTER TABLE email.recipients
  ADD COLUMN IF NOT EXISTS parceiro_id bigint REFERENCES email.parceiros(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_recipients_parceiro
  ON email.recipients (parceiro_id) WHERE parceiro_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Remetente de parcerias
-- ---------------------------------------------------------------------------
-- O remetente de parcerias do cliente fica em backend/sql/seeds/cliente.sql
-- (modelo em seeds/cliente.exemplo.sql), com padrao = false.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA email TO postgres';
    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA email TO postgres';
    EXECUTE 'GRANT ALL ON ALL SEQUENCES IN SCHEMA email TO postgres';
  END IF;
END $$;

COMMIT;
