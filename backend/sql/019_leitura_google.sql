-- 019 — Leitura automática das avaliações do Google.
--
-- Antes, o CRM só consultava o Google quando alguém abria a tela: nada era
-- guardado e nada rodava sozinho. Agora uma rotina dentro da API lê as
-- unidades a cada 29 minutos (GOOGLE_LEITURA_INTERVALO_MIN) e guarda aqui. A
-- fila, a visão geral e a tela de responder leem desta tabela.
--
-- Idempotente: pode rodar de novo.
BEGIN;

-- Uma linha por avaliação do Google. `resposta` é o que está publicado no
-- Google agora (NULL = sem resposta), como a última leitura viu.
CREATE TABLE IF NOT EXISTS integra.avaliacoes_google (
  review_id     text PRIMARY KEY,
  loja_id       text NOT NULL,
  nota          int,
  comentario    text,
  autor         text,
  criada_em     timestamptz,
  atualizada_em timestamptz,
  resposta      text,
  resposta_em   timestamptz,
  -- Quando o CRM viu a avaliação pela primeira vez.
  chegou_em     timestamptz NOT NULL DEFAULT now(),
  -- Última vez que a leitura encontrou alguma mudança nela.
  mudou_em      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_aval_google_loja
  ON integra.avaliacoes_google (loja_id, criada_em DESC);
CREATE INDEX IF NOT EXISTS ix_aval_google_sem_resposta
  ON integra.avaliacoes_google (loja_id, criada_em DESC) WHERE resposta IS NULL;

-- Como foi a última leitura de cada unidade: média e total do perfil, e o erro
-- se ela falhou (a unidade fica com o que já tinha; as outras seguem).
CREATE TABLE IF NOT EXISTS integra.google_leitura (
  loja_id   text PRIMARY KEY,
  media     numeric(3, 2),
  total     int,
  lida_em   timestamptz,
  erro      text,
  erro_em   timestamptz
);

-- Trava da passada (a mesma tabela do agente do iFood, outra linha).
INSERT INTO integra.agente_estado (origem) VALUES ('google')
ON CONFLICT (origem) DO NOTHING;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA integra TO postgres';
    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA integra TO postgres';
    EXECUTE 'GRANT ALL ON ALL SEQUENCES IN SCHEMA integra TO postgres';
  END IF;
END $$;

COMMIT;
