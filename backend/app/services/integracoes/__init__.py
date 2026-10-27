"""Integrações com plataformas de avaliação: iFood e Google Meu Negócio.

Cada plataforma tem um módulo que só conversa com a API dela (`ifood`,
`google`). O que é comum às duas — configuração, lojas, histórico, a IA que
sugere a resposta — fica em `store` e `redator`. O `agente` é a rotina agendada
do iFood, e `notificar` é o aviso que sai para o NichoChat.
"""
