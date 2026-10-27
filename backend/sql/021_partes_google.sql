-- 021 — Comentário do Google que chega em pedaços.
--
-- O fluxo "Buscar Novos comentários" do NichoChat manda as avaliações em blocos
-- de até 2.900 caracteres, um POST por bloco. Comentário maior que isso vem
-- dividido: um POST por pedaço, cada um com o mesmo reviewId e `parte` /
-- `totalPartes`. Os pedaços ficam aqui até o CRM juntar o texto; a avaliação
-- em integra.avaliacoes_google já aparece com o que chegou e se completa
-- quando chega o resto.
--
-- Precisa da 019 aplicada antes. Idempotente: pode rodar de novo.
BEGIN;

CREATE TABLE IF NOT EXISTS integra.avaliacoes_google_partes (
  review_id   text NOT NULL,
  parte       int  NOT NULL CHECK (parte >= 1),
  total       int  NOT NULL CHECK (total >= 1),
  -- O item como o fluxo mandou (o comentário é só o pedaço).
  item        jsonb NOT NULL,
  recebida_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (review_id, parte)
);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    EXECUTE 'GRANT ALL ON integra.avaliacoes_google_partes TO postgres';
  END IF;
END $$;

COMMIT;
