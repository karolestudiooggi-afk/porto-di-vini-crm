PERMISSOES = {
    "contatos:read",
    "contatos:write",
    "contatos:export",
    "contatos:import",
    "contatos:delete",
    "dashboard:read",
    "usuarios:read",
    "usuarios:manage",
    "auditoria:read",
    # Módulo de e-mail (sql/002 + sql/004). `send` é separado de `manage` de
    # propósito: montar campanha é reversível; disparar consome cota do plano e
    # não tem desfazer — por isso fica só com admin.
    "campanhas:manage",
    "campanhas:send",
    # módulo de avaliação/NPS (sql/008) — o QR na mesa e o painel de notas
    "avaliacoes:manage",
    # Integrações (sql/013): avaliações do iFood e do Google. `config` é separado
    # de `manage` pelo mesmo motivo de campanhas:send — responder é rotina;
    # ligar o modo automático do iFood muda o que sai em nome da casa.
    "integracoes:manage",
    "integracoes:config",
}
