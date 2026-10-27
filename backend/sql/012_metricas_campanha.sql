-- 012 — Métricas de campanha: bounce, descadastro e taxas.
--
-- O relatório mostrava só aberturas e cliques em número absoluto. Faltavam:
--
--   * PERCENTUAIS — "300 aberturas" não diz nada sem saber de quantos enviados.
--   * BOUNCE — e a distinção entre hard (caixa não existe) e soft (temporário),
--     que exigem reações opostas: um suprime, o outro volta para a fila.
--   * DESCADASTRO por campanha — é o sinal mais direto de que o conteúdo ou a
--     frequência incomodaram, e hoje ficava só na tabela de supressões, sem
--     ligação com a campanha que o causou.
BEGIN;

-- `email.events` só aceitava 'open' e 'click'. Bounce e descadastro passam a ser
-- eventos de primeira classe, ligados ao destinatário e à campanha.
ALTER TABLE email.events DROP CONSTRAINT IF EXISTS events_tipo_check;
ALTER TABLE email.events
  ADD CONSTRAINT events_tipo_check
  CHECK (tipo IN ('open', 'click', 'bounce_hard', 'bounce_soft', 'unsubscribe'));

COMMENT ON COLUMN email.events.tipo IS
  'open | click | bounce_hard (caixa não existe, suprime) | '
  'bounce_soft (temporário, volta para a fila) | unsubscribe';

CREATE INDEX IF NOT EXISTS ix_events_tipo ON email.events (tipo, created_at DESC);

-- Distinção que faltava na supressão. Hard e soft exigem reações opostas:
-- insistir num hard queima a reputação; suprimir por um soft perde um contato
-- válido que só estava com a caixa cheia.
ALTER TABLE email.suppressions
  ADD COLUMN IF NOT EXISTS tipo_bounce text
    CHECK (tipo_bounce IS NULL OR tipo_bounce IN ('hard', 'soft'));

COMMENT ON COLUMN email.suppressions.tipo_bounce IS
  'hard = caixa inexistente (definitivo) | soft = falha temporária | '
  'NULL = supressão por descadastro ou reclamação, não por bounce';

-- ---------------------------------------------------------------------------
-- Métricas por campanha
-- ---------------------------------------------------------------------------
--
-- As taxas usam ENVIADOS como base, não o público total: quem não recebeu não
-- pode abrir. Dividir pelo público inflaria o denominador e faria a campanha
-- parecer pior do que foi.

CREATE OR REPLACE VIEW email.vw_metricas_campanha AS
WITH base AS (
  SELECT
    r.campaign_id,
    count(*) FILTER (WHERE r.status = 'enviado')   AS enviados,
    count(*) FILTER (WHERE r.status = 'suprimido') AS suprimidos,
    count(*) FILTER (WHERE r.status = 'pendente')  AS pendentes,
    count(*)                                        AS total
  FROM email.recipients r
  GROUP BY r.campaign_id
),
eventos AS (
  SELECT
    r.campaign_id,
    -- DISTINCT por destinatário: a mesma pessoa abrindo três vezes conta uma.
    -- Sem isso, a taxa passa de 100% e ninguém entende.
    count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'open')        AS aberturas,
    count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'click')       AS cliques,
    count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'bounce_hard') AS bounce_hard,
    count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'bounce_soft') AS bounce_soft,
    count(DISTINCT e.recipient_id) FILTER (WHERE e.tipo = 'unsubscribe') AS descadastros
  FROM email.events e
  JOIN email.recipients r ON r.id = e.recipient_id
  GROUP BY r.campaign_id
)
SELECT
  c.id AS campaign_id,
  coalesce(b.enviados, 0)      AS enviados,
  coalesce(b.pendentes, 0)     AS pendentes,
  coalesce(b.suprimidos, 0)    AS suprimidos,
  coalesce(b.total, 0)         AS publico,
  coalesce(v.aberturas, 0)     AS aberturas,
  coalesce(v.cliques, 0)       AS cliques,
  coalesce(v.bounce_hard, 0)   AS bounce_hard,
  coalesce(v.bounce_soft, 0)   AS bounce_soft,
  coalesce(v.descadastros, 0)  AS descadastros,
  -- NULLIF evita divisão por zero: campanha sem envio devolve NULL, e a tela
  -- mostra "—" em vez de 0%, que afirmaria que ninguém abriu.
  round(100.0 * coalesce(v.aberturas, 0)    / nullif(b.enviados, 0), 1) AS taxa_abertura,
  round(100.0 * coalesce(v.cliques, 0)      / nullif(b.enviados, 0), 1) AS taxa_clique,
  round(100.0 * coalesce(v.bounce_hard, 0)  / nullif(b.enviados, 0), 1) AS taxa_bounce_hard,
  round(100.0 * coalesce(v.bounce_soft, 0)  / nullif(b.enviados, 0), 1) AS taxa_bounce_soft,
  round(100.0 * coalesce(v.descadastros, 0) / nullif(b.enviados, 0), 1) AS taxa_descadastro
FROM email.campaigns c
LEFT JOIN base b    ON b.campaign_id = c.id
LEFT JOIN eventos v ON v.campaign_id = c.id;

COMMENT ON VIEW email.vw_metricas_campanha IS
  'Métricas por campanha, com taxas sobre ENVIADOS (quem não recebeu não abre). '
  'Aberturas e cliques contam destinatários distintos, não eventos.';

-- ---------------------------------------------------------------------------
-- Último contato por pessoa
-- ---------------------------------------------------------------------------
--
-- Para o filtro "não recebeu comunicação na última semana": permite montar
-- campanha sem incomodar quem acabou de receber outra.

CREATE OR REPLACE VIEW crm.vw_ultimo_email AS
SELECT
  r.contato_id,
  max(r.sent_at) AS ultimo_email_em,
  count(*)       AS emails_recebidos
FROM email.recipients r
WHERE r.status = 'enviado' AND r.sent_at IS NOT NULL AND r.contato_id IS NOT NULL
GROUP BY r.contato_id;

COMMENT ON VIEW crm.vw_ultimo_email IS
  'Quando cada contato recebeu e-mail pela última vez. Base do filtro de '
  'exclusão por período — evita mandar duas campanhas seguidas para a mesma pessoa.';

COMMIT;
