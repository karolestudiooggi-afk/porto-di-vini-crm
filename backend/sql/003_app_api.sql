-- Migração 003 — suporte da aplicação FastAPI: RBAC, auditoria e notas manuais.
--
-- O Supabase continua responsável por autenticar e emitir o JWT. Este schema
-- controla quais usuários autenticados podem acessar cada recurso da API.

BEGIN;

CREATE SCHEMA IF NOT EXISTS app;

CREATE OR REPLACE FUNCTION app.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS app.papeis (
  id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nome text UNIQUE NOT NULL,
  descricao text
);

CREATE TABLE IF NOT EXISTS app.papel_permissoes (
  papel_id smallint NOT NULL REFERENCES app.papeis(id) ON DELETE CASCADE,
  permissao text NOT NULL,
  PRIMARY KEY (papel_id, permissao)
);

CREATE TABLE IF NOT EXISTS app.usuarios (
  id uuid PRIMARY KEY, -- mesmo id de auth.users no Supabase
  nome text,
  email text UNIQUE NOT NULL,
  papel_id smallint NOT NULL REFERENCES app.papeis(id),
  status text NOT NULL DEFAULT 'ativo'
    CHECK (status IN ('ativo', 'inativo')),
  ultimo_acesso timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.auditoria (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  usuario_id uuid,
  acao text NOT NULL,
  recurso text NOT NULL,
  detalhe jsonb,
  ip text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_auditoria_created_at
  ON app.auditoria (created_at DESC);

DROP TRIGGER IF EXISTS trg_usuarios_updated_at ON app.usuarios;
CREATE TRIGGER trg_usuarios_updated_at
  BEFORE UPDATE ON app.usuarios
  FOR EACH ROW EXECUTE FUNCTION app.set_updated_at();

-- Campo editorial: o sync e enriquecimentos não devem sobrescrevê-lo.
ALTER TABLE crm.contatos
  ADD COLUMN IF NOT EXISTS observacoes text;
ALTER TABLE crm.contatos
  ADD COLUMN IF NOT EXISTS tags_manuais text[] NOT NULL DEFAULT '{}';
ALTER TABLE crm.contatos
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
ALTER TABLE crm.contatos
  ADD COLUMN IF NOT EXISTS deleted_by uuid;

COMMENT ON COLUMN crm.contatos.tags_manuais IS
  'Tags adicionadas por importação ou operação do CRM; o sync Domani não sobrescreve.';
COMMENT ON COLUMN crm.contatos.deleted_at IS
  'Exclusão lógica. Nova atividade Domani posterior a este instante restaura a ficha.';

CREATE INDEX IF NOT EXISTS ix_contatos_ativos
  ON crm.contatos (id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS gin_contatos_tags_manuais
  ON crm.contatos USING gin (tags_manuais);

INSERT INTO app.papeis (nome, descricao) VALUES
  ('admin', 'Acesso administrativo'),
  ('operador', 'Consulta e operação cotidiana do CRM')
ON CONFLICT (nome) DO UPDATE SET descricao = EXCLUDED.descricao;

INSERT INTO app.papel_permissoes (papel_id, permissao)
SELECT p.id, permissao
FROM app.papeis p
CROSS JOIN (VALUES
  ('contatos:read'),
  ('contatos:write'),
  ('contatos:export'),
  ('contatos:import'),
  ('contatos:delete'),
  ('dashboard:read'),
  ('usuarios:read'),
  ('usuarios:manage'),
  ('auditoria:read'),
  ('campanhas:manage')
) AS permissoes(permissao)
WHERE p.nome = 'admin'
ON CONFLICT DO NOTHING;

INSERT INTO app.papel_permissoes (papel_id, permissao)
SELECT p.id, permissao
FROM app.papeis p
-- Operador faz TUDO com os dados. Só a gestão de acessos e o log de auditoria
-- ficam com o admin — quem é auditado não controla o registro.
CROSS JOIN (VALUES
  ('contatos:read'),
  ('contatos:write'),
  ('contatos:export'),
  ('contatos:import'),
  ('contatos:delete'),
  ('dashboard:read'),
  ('campanhas:manage'),
  ('campanhas:send'),
  ('avaliacoes:manage')
) AS permissoes(permissao)
WHERE p.nome = 'operador'
ON CONFLICT DO NOTHING;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA app TO postgres';
    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA app TO postgres';
    EXECUTE 'GRANT ALL ON ALL SEQUENCES IN SCHEMA app TO postgres';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT ALL ON TABLES TO postgres';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT ALL ON SEQUENCES TO postgres';
  END IF;
END $$;

COMMIT;
