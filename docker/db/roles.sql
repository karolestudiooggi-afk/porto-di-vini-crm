-- Senha dos papéis internos do Supabase = POSTGRES_PASSWORD.
-- Roda uma vez só, no primeiro boot do banco (initdb), como no compose oficial
-- (supabase/supabase, docker/volumes/db/roles.sql). Diferença: aqui só os
-- papéis das peças que este CRM sobe (auth, storage, rest), e cada ALTER só
-- acontece se o papel existir — sem webhooks/Edge Functions, o
-- supabase_functions_admin nem é criado.
\set pgpass `echo "$POSTGRES_PASSWORD"`
SELECT set_config('crm.pgpass', :'pgpass', false);

DO $$
DECLARE
  papel text;
BEGIN
  FOREACH papel IN ARRAY ARRAY['authenticator', 'pgbouncer', 'supabase_auth_admin', 'supabase_storage_admin']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = papel) THEN
      EXECUTE format('ALTER USER %I WITH PASSWORD %L', papel, current_setting('crm.pgpass'));
    END IF;
  END LOOP;
END $$;

SELECT set_config('crm.pgpass', '', false);
