-- 016 — Tripadvisor e Reclame Aqui, lidos pelos e-mails de notificação.
--
-- Nenhuma das duas plataformas serve por API para o que o CRM precisa:
--   * Tripadvisor: a Content API devolve só as 5 avaliações mais recentes de
--     cada local e proíbe guardar o conteúdo — não dá relatório nem histórico;
--   * Reclame Aqui: a API é paga, com preço sob consulta.
-- As duas, porém, avisam a empresa por e-mail a cada avaliação ou reclamação
-- nova. É esse e-mail que o CRM lê: uma caixa recebe as notificações, o CRM
-- passa por ela de tempos em tempos, guarda o e-mail original e extrai o que
-- importa (unidade, nota, texto, autor, link).
--
--   monitor_caixa    → onde a leitura parou na caixa (e a trava da passada)
--   monitor_emails   → cada e-mail lido, com o original, para reprocessar
--                      quando o leitor melhorar — nada se perde
--   monitor_itens    → a avaliação/reclamação extraída de cada e-mail
--   monitor_config   → por plataforma: ligado, quem avisar e para onde
--   monitor_ajustes  → palavras de crise (procon, processo, vidro…)
--   monitor_unidades → de qual unidade é cada local do Tripadvisor
--
-- Responder continua sendo na própria plataforma. Aqui é leitura, alerta e
-- relatório.
BEGIN;

CREATE SCHEMA IF NOT EXISTS integra;

-- ---------------------------------------------------------------------------
-- Caixa de leitura
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS integra.monitor_caixa (
  id             boolean PRIMARY KEY DEFAULT true CHECK (id),
  -- O IMAP numera as mensagens por UID dentro de uma "validade". Se a validade
  -- muda (caixa recriada), os UIDs antigos não valem mais e a leitura recomeça
  -- pela data — a deduplicação por Message-ID evita repetir o que já entrou.
  uidvalidity    bigint,
  ultimo_uid     bigint NOT NULL DEFAULT 0,
  lendo_desde    timestamptz,
  ultima_leitura timestamptz,
  ultimo_erro    text,
  ultimo_erro_em timestamptz
);
INSERT INTO integra.monitor_caixa (id) VALUES (true) ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- E-mails lidos
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS integra.monitor_emails (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  message_id  text NOT NULL,
  -- NULL = não é de nenhuma das plataformas (ou não foi reconhecido).
  origem      text CHECK (origem IS NULL OR origem IN ('tripadvisor', 'reclameaqui')),
  remetente   text,
  assunto     text,
  enviado_em  timestamptz,
  lido_em     timestamptz NOT NULL DEFAULT now(),
  via         text NOT NULL DEFAULT 'imap' CHECK (via IN ('imap', 'upload')),
  -- O e-mail como chegou. Só das plataformas: e-mail que não é delas fica
  -- registrado (para a tela dizer "X ignorados") mas sem conteúdo.
  bruto       bytea,
  situacao    text NOT NULL DEFAULT 'processado'
              CHECK (situacao IN ('processado', 'ignorado', 'erro')),
  motivo      text
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_monitor_emails_msgid ON integra.monitor_emails (message_id);
CREATE INDEX IF NOT EXISTS ix_monitor_emails_lido ON integra.monitor_emails (lido_em DESC);

-- ---------------------------------------------------------------------------
-- Itens: avaliações e reclamações
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS integra.monitor_itens (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email_id     bigint REFERENCES integra.monitor_emails(id) ON DELETE SET NULL,
  origem       text NOT NULL CHECK (origem IN ('tripadvisor', 'reclameaqui')),
  -- avaliacao  → Tripadvisor: avaliação nova
  -- reclamacao → Reclame Aqui: reclamação nova
  -- interacao  → Reclame Aqui: o consumidor respondeu (réplica, mensagem)
  -- resultado  → Reclame Aqui: o consumidor avaliou o atendimento (nota 0–10)
  tipo         text NOT NULL
               CHECK (tipo IN ('avaliacao', 'reclamacao', 'interacao', 'resultado')),
  -- Id da avaliação/reclamação na plataforma, quando o e-mail traz.
  externo_id   text,
  -- Tripadvisor: o id do local (o "d123456" do link).
  loja_id      text,
  unidade      text,
  nota         numeric(3, 1),
  nota_maxima  smallint,
  titulo       text,
  texto        text,
  autor        text,
  cidade       text,
  -- Link para a avaliação/reclamação na plataforma (onde se responde).
  link         text,
  ocorrido_em  timestamptz NOT NULL,
  criado_em    timestamptz NOT NULL DEFAULT now(),
  nivel        text CHECK (nivel IS NULL OR nivel IN ('negativa', 'neutra', 'positiva')),
  critico      boolean NOT NULL DEFAULT false,
  palavras     text[] NOT NULL DEFAULT '{}',
  -- regra = o leitor entendeu o layout; ia = completado pela IA; parcial =
  -- faltou campo e não havia IA para completar (o e-mail original está salvo).
  extraido_por text NOT NULL DEFAULT 'regra'
               CHECK (extraido_por IN ('regra', 'ia', 'parcial')),
  tratado_em   timestamptz,
  tratado_por  uuid,
  observacao   text,
  avisado_em   timestamptz
);

-- Um e-mail vira no máximo um item (é o que permite reprocessar no lugar).
CREATE UNIQUE INDEX IF NOT EXISTS ux_monitor_itens_email
  ON integra.monitor_itens (email_id) WHERE email_id IS NOT NULL;
-- A mesma avaliação avisada duas vezes (aviso + lembrete) é UMA avaliação.
-- Interação e resultado não entram: uma reclamação tem várias réplicas.
CREATE UNIQUE INDEX IF NOT EXISTS ux_monitor_itens_externo
  ON integra.monitor_itens (origem, tipo, externo_id)
  WHERE externo_id IS NOT NULL AND tipo IN ('avaliacao', 'reclamacao');
CREATE INDEX IF NOT EXISTS ix_monitor_itens_data
  ON integra.monitor_itens (origem, ocorrido_em DESC);
CREATE INDEX IF NOT EXISTS ix_monitor_itens_criticos
  ON integra.monitor_itens (origem, ocorrido_em DESC) WHERE critico;

-- ---------------------------------------------------------------------------
-- Configuração por plataforma
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS integra.monitor_config (
  origem         text PRIMARY KEY CHECK (origem IN ('tripadvisor', 'reclameaqui')),
  ativo          boolean NOT NULL DEFAULT true,
  -- Quando avisar o NichoChat:
  --   nenhum    → só guarda
  --   criticos  → só quando aparece palavra de crise
  --   negativos → crise OU nota baixa / reclamação nova (padrão)
  --   todos     → tudo o que chega
  aviso          text NOT NULL DEFAULT 'negativos'
                 CHECK (aviso IN ('nenhum', 'criticos', 'negativos', 'todos')),
  webhook_url    text,
  atualizado_em  timestamptz NOT NULL DEFAULT now(),
  atualizado_por uuid
);
INSERT INTO integra.monitor_config (origem) VALUES ('tripadvisor'), ('reclameaqui')
ON CONFLICT (origem) DO NOTHING;

-- Palavras de crise: valem para as duas plataformas. Combinam pelo começo da
-- palavra e sem acento ("procon" pega "Procon", "intoxica" pega "intoxicação").
-- A lista inicial é um ponto de partida; cada cliente ajusta pela tela.
CREATE TABLE IF NOT EXISTS integra.monitor_ajustes (
  id                boolean PRIMARY KEY DEFAULT true CHECK (id),
  palavras_criticas text[] NOT NULL DEFAULT ARRAY[
    'procon', 'processo', 'processar', 'advogado', 'justiça', 'judicial',
    'juizado', 'indenização', 'polícia', 'delegacia', 'boletim de ocorrência',
    'roubo', 'roubaram', 'furto', 'furtaram', 'golpe',
    'vidro', 'barata', 'inseto', 'larva', 'bicho', 'cabelo', 'mosca',
    'intoxicação', 'intoxicado', 'intoxicada', 'passei mal', 'passou mal',
    'hospital', 'vômito', 'diarreia', 'alergia', 'agressão', 'assédio',
    'discriminação', 'racismo'
  ],
  atualizado_em  timestamptz NOT NULL DEFAULT now(),
  atualizado_por uuid
);
INSERT INTO integra.monitor_ajustes (id) VALUES (true) ON CONFLICT DO NOTHING;

-- Unidade de cada local do Tripadvisor (o id "d…" do link). Preenchida quando
-- alguém corrige a unidade de uma avaliação na tela: as próximas daquele local
-- já chegam com a unidade certa.
CREATE TABLE IF NOT EXISTS integra.monitor_unidades (
  origem   text NOT NULL CHECK (origem IN ('tripadvisor', 'reclameaqui')),
  loja_id  text NOT NULL,
  unidade  text NOT NULL,
  PRIMARY KEY (origem, loja_id)
);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA integra TO postgres';
    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA integra TO postgres';
    EXECUTE 'GRANT ALL ON ALL SEQUENCES IN SCHEMA integra TO postgres';
  END IF;
END $$;

COMMIT;
