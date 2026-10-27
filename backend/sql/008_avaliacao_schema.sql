-- 008 — Módulo de avaliação/NPS: QR na mesa, nota do cliente.
--
-- O cliente escaneia o QR na mesa, dá a nota e comenta. Nota máxima é levada ao
-- Google; nota baixa dispara alerta interno na hora, para a casa poder agir com o
-- cliente ainda ali.
--
-- SEED DAS UNIDADES
--
-- Em outros CRMs as unidades vêm do campo `unidade` da ficha, que o bot preenche.
-- Aqui esse campo não existe — a base do Domani não tem unidade. Então cria-se
-- uma conta única com o nome do cliente, e novas unidades são acrescentadas pela
-- tela (ou por INSERT) quando houver mais de um ponto.
BEGIN;
CREATE SCHEMA IF NOT EXISTS avaliacao;

-- Slug de URL a partir do nome da unidade: minúsculo, sem acento, `_` no lugar de
-- símbolo. É o que vai no QR (/avaliar/{slug}). IMMUTABLE para poder indexar.
CREATE OR REPLACE FUNCTION crm.fn_slug(txt text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT nullif(
    trim(both '_' from
      regexp_replace(
        lower(translate(coalesce(txt, ''),
          'áàâãäéèêëíìîïóòôõöúùûüçñ', 'aaaaaeeeeiiiiooooouuuucn')),
        '[^a-z0-9]+', '_', 'g')),
    '');
$$;

-- Uma "conta" por unidade (o slug vai no QR: /avaliar/{slug}).
CREATE TABLE IF NOT EXISTS avaliacao.contas (
  slug            text PRIMARY KEY,
  nome            text NOT NULL,
  google_url      text,                      -- review do Google (nota 5 é mandada pra cá)
  webhook_url     text,                      -- webhook NichoChat p/ alerta de nota baixa
  limite_promotor int  NOT NULL DEFAULT 4,   -- nota >= limite = promotor
  ativo           boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now());

-- Cada resposta do cliente final.
CREATE TABLE IF NOT EXISTS avaliacao.respostas (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug       text NOT NULL REFERENCES avaliacao.contas(slug),
  nota       int  NOT NULL,
  categoria  text NOT NULL,          -- promotor|neutro|detrator
  comentario text NOT NULL DEFAULT '',
  nome       text,
  whatsapp   text,
  colaborador text,                  -- quem atendeu (garçom), opcional
  contato_id bigint,                 -- vínculo com crm.contatos, se casar por telefone
  created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_respostas_slug        ON avaliacao.respostas (slug);
CREATE INDEX IF NOT EXISTS ix_respostas_created     ON avaliacao.respostas (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_respostas_colaborador ON avaliacao.respostas (colaborador);

-- As contas (uma por unidade, ou uma só para a marca) ficam em
-- backend/sql/seeds/cliente.sql — modelo em seeds/cliente.exemplo.sql.

INSERT INTO app.papel_permissoes (papel_id, permissao)
SELECT id, 'avaliacoes:manage' FROM app.papeis WHERE nome IN ('admin','operador')
ON CONFLICT DO NOTHING;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA avaliacao TO postgres';
    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA avaliacao TO postgres';
    EXECUTE 'GRANT ALL ON ALL SEQUENCES IN SCHEMA avaliacao TO postgres';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA avaliacao GRANT ALL ON TABLES TO postgres';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA avaliacao GRANT ALL ON SEQUENCES TO postgres';
  END IF;
END $$;

COMMIT;
