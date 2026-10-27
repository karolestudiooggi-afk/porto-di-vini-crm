-- 013 — Integrações: avaliações do iFood e do Google Meu Negócio dentro do CRM.
--
-- Até aqui as avaliações do iFood eram respondidas num painel separado (o
-- "Domani Avaliações", em Go) e as do Google só pelo fluxo do NichoChat. Esta
-- migration traz as duas para a aba Integrações do CRM.
--
-- O desenho é o mesmo para as duas origens, de propósito: uma tabela de lojas,
-- uma de configuração, uma de respostas. O que muda entre iFood e Google fica
-- no código que conversa com cada API, não no banco.
--
--   lojas               → unidades: merchant no iFood, location no Google
--   config              → modo, tom de voz, prompt e webhook, por origem
--   tokens              → cache do token do iFood e a conexão OAuth do Google
--   avaliacao_respostas → uma linha por avaliação vista ou respondida
--   agente_execucoes    → uma linha por passada do agente do iFood
--   agente_estado       → trava para não rodar duas passadas ao mesmo tempo
BEGIN;

CREATE SCHEMA IF NOT EXISTS integra;

-- ---------------------------------------------------------------------------
-- Lojas
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS integra.lojas (
  origem      text NOT NULL CHECK (origem IN ('ifood', 'google')),
  -- iFood: o merchant UUID (não o código numérico do portal).
  -- Google: o id numérico da location, sem o prefixo "locations/".
  loja_id     text NOT NULL,
  nome        text NOT NULL,
  cidade      text,
  ativo       boolean NOT NULL DEFAULT true,
  -- Vazia herda a assinatura da config. Serve para a unidade assinar com o
  -- próprio nome ("Equipe Cliente Exemplo Centro").
  assinatura  text,
  -- Só Google: a conta dona da location. A API de avaliações exige
  -- accounts/{conta}/locations/{loja}; é preenchida sozinha ao conectar.
  conta_id    text,
  criado_em   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (origem, loja_id)
);

-- ---------------------------------------------------------------------------
-- Configuração por origem
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS integra.config (
  origem       text PRIMARY KEY CHECK (origem IN ('ifood', 'google')),
  ativo        boolean NOT NULL DEFAULT true,

  -- manual: ninguém publica sozinho; a equipe responde pela tela, com o botão
  --   de sugestão da IA para não escrever do zero.
  -- automatico: o agente publica a partir de nota_minima. Só vale no iFood.
  modo         text NOT NULL DEFAULT 'manual'
               CHECK (modo IN ('manual', 'automatico')),

  tom          text,
  assinatura   text,
  -- Prompt completo. Vazio usa o padrão do sistema para aquela origem.
  prompt       text,
  -- Nota mínima que o agente responde sozinho. 4 = só nota 4 e 5.
  nota_minima  int NOT NULL DEFAULT 4 CHECK (nota_minima BETWEEN 1 AND 5),
  -- Webhook do canal no NichoChat, para o aviso de avaliação nova/respondida.
  webhook_url  text,
  -- Vazio usa OPENAI_MODEL do ambiente.
  openai_model text,

  atualizado_em  timestamptz NOT NULL DEFAULT now(),
  atualizado_por uuid
);

-- Como no painel de origem: chave própria da OpenAI (vazia usa a do ambiente)
-- e anotações internas. Em ALTER, e não no CREATE, para a migration também
-- atualizar um banco onde a primeira versão dela já tinha sido aplicada.
ALTER TABLE integra.config
  ADD COLUMN IF NOT EXISTS openai_api_key text,
  ADD COLUMN IF NOT EXISTS observacoes    text;

INSERT INTO integra.config (origem) VALUES ('ifood'), ('google')
ON CONFLICT (origem) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Tokens
-- ---------------------------------------------------------------------------
--
-- iFood: só o access_token (6h, sem refresh — client_credentials de novo).
-- Google: o refresh_token é a conexão em si. Sai daqui, a integração cai e
-- alguém precisa clicar em "Conectar Google" outra vez. A API do CRM nunca
-- devolve estas colunas.

CREATE TABLE IF NOT EXISTS integra.tokens (
  origem        text PRIMARY KEY CHECK (origem IN ('ifood', 'google')),
  access_token  text,
  expira_em     timestamptz,
  refresh_token text,
  conta_email   text,
  conectado_em  timestamptz,
  conectado_por uuid
);

-- ---------------------------------------------------------------------------
-- Respostas
-- ---------------------------------------------------------------------------
--
-- É o mecanismo de idempotência do iFood: resposta publicada não pode ser
-- editada nem removida, e tentar responder de novo devolve 422. Toda avaliação
-- que o agente vê vira uma linha aqui, inclusive as que ele decide ignorar.
--
-- Sem chave estrangeira para a loja de propósito: o histórico do que foi
-- publicado precisa sobreviver à exclusão dela.

CREATE TABLE IF NOT EXISTS integra.avaliacao_respostas (
  origem      text NOT NULL CHECK (origem IN ('ifood', 'google')),
  review_id   text NOT NULL,
  loja_id     text NOT NULL,
  nota        int,
  comentario  text,
  autor       text,
  resposta    text,
  -- pendente: vista e avisada, aguardando resposta manual
  -- enviada:  resposta publicada
  -- ignorada: abaixo da nota mínima no modo automático
  -- erro:     a publicação falhou
  status      text NOT NULL
              CHECK (status IN ('pendente', 'enviada', 'ignorada', 'erro')),
  erro        text,
  -- Quem publicou: uma pessoa pela tela, ou o agente.
  via         text CHECK (via IN ('manual', 'agente')),
  usuario_id  uuid,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (origem, review_id)
);

CREATE INDEX IF NOT EXISTS ix_aval_respostas_loja
  ON integra.avaliacao_respostas (origem, loja_id, atualizado_em DESC);
CREATE INDEX IF NOT EXISTS ix_aval_respostas_data
  ON integra.avaliacao_respostas (origem, atualizado_em DESC);

-- ---------------------------------------------------------------------------
-- Agente do iFood
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS integra.agente_execucoes (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  origem       text NOT NULL DEFAULT 'ifood',
  iniciado_em  timestamptz NOT NULL DEFAULT now(),
  lojas        int NOT NULL DEFAULT 0,
  encontradas  int NOT NULL DEFAULT 0,
  respondidas  int NOT NULL DEFAULT 0,
  erros        int NOT NULL DEFAULT 0,
  duracao_ms   int
);

CREATE INDEX IF NOT EXISTS ix_agente_execucoes_data
  ON integra.agente_execucoes (origem, iniciado_em DESC);

-- Trava de execução. Duas passadas ao mesmo tempo tentariam responder as
-- mesmas avaliações, e a segunda receberia 422 sem ter como desfazer.
--
-- É uma linha, e não pg_advisory_lock, porque a conexão pode passar por pooler
-- em modo transação, onde trava de sessão não se sustenta.
CREATE TABLE IF NOT EXISTS integra.agente_estado (
  origem        text PRIMARY KEY,
  rodando_desde timestamptz
);

INSERT INTO integra.agente_estado (origem) VALUES ('ifood')
ON CONFLICT (origem) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Unidades
-- ---------------------------------------------------------------------------
--
-- As lojas do iFood e as unidades do Google do cliente NÃO vêm aqui: ficam em
-- backend/sql/seeds/cliente.sql (modelo em seeds/cliente.exemplo.sql).

-- ---------------------------------------------------------------------------
-- Permissões
-- ---------------------------------------------------------------------------
--
-- Duas, pela mesma lógica de campanhas:manage × campanhas:send:
--
--   integracoes:manage → ver a fila e responder. É rotina, fica com quem opera.
--   integracoes:config → conectar conta, cadastrar loja, ligar o automático.
--                        Muda o que é publicado em nome da casa sem ninguém
--                        olhar, então é decisão de quem administra.

INSERT INTO app.papel_permissoes (papel_id, permissao)
SELECT id, 'integracoes:manage' FROM app.papeis WHERE nome IN ('admin', 'operador')
ON CONFLICT DO NOTHING;

INSERT INTO app.papel_permissoes (papel_id, permissao)
SELECT id, 'integracoes:config' FROM app.papeis WHERE nome = 'admin'
ON CONFLICT DO NOTHING;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA integra TO postgres';
    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA integra TO postgres';
    EXECUTE 'GRANT ALL ON ALL SEQUENCES IN SCHEMA integra TO postgres';
  END IF;
END $$;

COMMIT;
