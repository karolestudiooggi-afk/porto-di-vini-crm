-- 010 — Cota DIÁRIA, para o disparador próprio.
--
-- O envio deixou de passar pelo SendPulse e passou a usar o disparador da casa.
-- Isso muda a natureza do limite:
--
--   ANTES  o teto era um PLANO mensal comprado de um provedor externo.
--   AGORA  o teto é a CAPACIDADE da nossa infraestrutura, compartilhada entre
--          todos os clientes: ~4 e-mails por minuto no total, ~5.760/dia.
--
-- Por isso a janela relevante virou o DIA: a soma das cotas diárias de todos os
-- clientes não pode passar do teto compartilhado, senão um cliente atrasa a
-- campanha do outro.
--
-- O dia é o de São Paulo, não UTC — é o fuso da operação, e é à meia-noite daqui
-- que o cliente espera a contagem zerar.
BEGIN;

-- DROP antes de recriar: `CREATE OR REPLACE VIEW` não permite RENOMEAR coluna
-- existente (só acrescentar no fim), e aqui a 2ª coluna deixa de ser
-- `enviados_mes` e passa a ser `enviados_dia`. O Postgres recusa com
-- "cannot change name of view column".
--
-- Dropar é seguro: a view não guarda dado, só lê `email.recipients`.
DROP VIEW IF EXISTS email.vw_consumo;

CREATE VIEW email.vw_consumo AS
SELECT
  count(*) FILTER (WHERE sent_at >= now() - interval '1 hour')   AS enviados_hora,
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
  'Consumo de envio nas três janelas. A que manda hoje é `enviados_dia`: o teto '
  'é a capacidade da infraestrutura, compartilhada entre os clientes.';

COMMIT;
