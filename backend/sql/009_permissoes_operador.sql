-- 009 — Permissões do operador: tudo, menos gestão de usuários e auditoria.
--
-- O seed original dava ao operador só leitura, escrita e exportação de contatos,
-- mais o dashboard e a montagem de campanha. Na prática isso travava a operação
-- do dia a dia: quem opera o CRM precisa importar planilha, disparar campanha e
-- cuidar das avaliações. Só a gestão de ACESSOS e o log de auditoria são
-- exclusivos de quem administra.
--
-- A regra, em uma frase: operador faz tudo com os DADOS; admin também cuida de
-- QUEM entra e do que foi feito.
BEGIN;

INSERT INTO app.papel_permissoes (papel_id, permissao)
SELECT p.id, permissao
FROM app.papeis p
CROSS JOIN (VALUES
  ('contatos:import'),      -- importar planilha é rotina, não exceção
  ('contatos:delete'),      -- limpar ficha duplicada ou lixo de importação
  ('campanhas:send'),       -- quem monta a campanha é quem dispara
  ('avaliacoes:manage')     -- configurar QR e acompanhar as notas
) AS permissoes(permissao)
WHERE p.nome = 'operador'
ON CONFLICT DO NOTHING;

-- O que o operador NÃO tem, e é deliberado:
--   usuarios:read / usuarios:manage  -> quem entra no CRM é decisão do admin
--   auditoria:read                   -> o log existe para auditar a operação;
--                                       quem é auditado não controla o registro
DELETE FROM app.papel_permissoes
 WHERE papel_id = (SELECT id FROM app.papeis WHERE nome = 'operador')
   AND permissao IN ('usuarios:read', 'usuarios:manage', 'auditoria:read');

COMMIT;
