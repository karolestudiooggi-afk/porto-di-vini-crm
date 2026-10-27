-- 006 — Convites de acesso ao CRM.
--
-- Até aqui, dar acesso a alguém exigia criar o usuário no Supabase Studio e
-- inserir a linha em `app.usuarios` por SQL — ou seja, dependia de quem tem
-- acesso ao servidor. Esta migration permite que um administrador convide pela
-- própria tela.
--
-- COMO FUNCIONA
--
-- 1. O admin convida um e-mail e escolhe o papel → nasce uma linha 'pendente'
--    com um token de uso único.
-- 2. A pessoa recebe o link, define a senha (a conta é criada no Supabase Auth
--    pela service role) e o token é zerado.
-- 3. No primeiro request autenticado, o convite é consumido e o usuário passa a
--    existir em `app.usuarios` com o papel escolhido.
--
-- O passo 3 é o que fecha o cerco: quem tem login válido no Supabase mas nunca
-- foi convidado continua recebendo 403. Criar conta no Auth, sozinho, não dá
-- acesso a nada.
BEGIN;

CREATE TABLE IF NOT EXISTS app.convites (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email         text NOT NULL,
  papel_id      smallint NOT NULL REFERENCES app.papeis(id),
  status        text NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente', 'aceito', 'expirado', 'cancelado')),
  -- Uso único: vai no link e é zerado assim que a senha é criada. Guardar o
  -- token depois disso só aumentaria a superfície de ataque sem serventia.
  token         text,
  convidado_por uuid,
  created_at    timestamptz NOT NULL DEFAULT now(),
  expira_em     timestamptz NOT NULL DEFAULT now() + interval '7 days'
);

-- Um convite pendente por e-mail. Reconvidar substitui o anterior em vez de
-- acumular dois links válidos para a mesma pessoa.
CREATE UNIQUE INDEX IF NOT EXISTS ux_convites_email_pendente
  ON app.convites (lower(email)) WHERE status = 'pendente';

CREATE INDEX IF NOT EXISTS ix_convites_token
  ON app.convites (token) WHERE token IS NOT NULL;

COMMENT ON TABLE app.convites IS
  'Convites de acesso. O acesso ao CRM é fechado: sem convite aceito, mesmo um '
  'login válido no Supabase Auth recebe 403.';

-- O admin precisa poder disparar campanha. Faltava no seed do 003 — sem isso,
-- ninguém no sistema conseguia enviar e-mail.
INSERT INTO app.papel_permissoes (papel_id, permissao)
SELECT id, 'campanhas:send' FROM app.papeis WHERE nome = 'admin'
ON CONFLICT DO NOTHING;

COMMIT;
