-- 011 — Cota MENSAL de volta (retorno ao SendPulse).
--
-- A conta no SendPulse foi liberada, e o envio volta a passar por lá enquanto o
-- IP do disparador próprio é aquecido. Com isso o teto muda de natureza:
--
--   disparador próprio  -> capacidade da NOSSA infraestrutura, dividida entre
--                          os clientes. Janela relevante: o DIA.
--   SendPulse           -> PLANO comprado do provedor. Janela: o MÊS.
--
-- A view passa a expor as duas janelas. Trocar de transporte deixa de exigir
-- migration: o código lê a coluna que o transporte atual usa, e as duas estão
-- sempre disponíveis.
--
-- Ver docs/DISPARADOR-PROPRIO.md para o caminho de volta.
BEGIN;

DROP VIEW IF EXISTS email.vw_consumo;

CREATE VIEW email.vw_consumo AS
SELECT
  count(*) FILTER (WHERE sent_at >= now() - interval '1 hour')   AS enviados_hora,
  -- Dia no fuso da operação: é à meia-noite daqui que o cliente espera zerar.
  count(*) FILTER (
    WHERE (sent_at AT TIME ZONE 'America/Sao_Paulo')::date
        = (now()   AT TIME ZONE 'America/Sao_Paulo')::date
  )                                                              AS enviados_dia,
  count(*) FILTER (
    WHERE sent_at >= (date_trunc('month', now() AT TIME ZONE 'America/Sao_Paulo')
                      AT TIME ZONE 'America/Sao_Paulo')
  )                                                              AS enviados_mes,
  max(sent_at)                                                   AS ultimo_envio
FROM email.recipients
WHERE status = 'enviado' AND sent_at IS NOT NULL;

COMMENT ON VIEW email.vw_consumo IS
  'Consumo de envio nas três janelas. Qual manda depende do transporte: mês para '
  'provedor externo (plano comprado), dia para o disparador próprio (capacidade '
  'compartilhada).';

COMMIT;
