#!/usr/bin/env bash
# Cria o admin do CRM (ou promove uma conta a admin). Pede a senha.
#
#   ./scripts/criar-admin.sh                 -> ai@estudiooggi.com (o admin de sempre)
#   ./scripts/criar-admin.sh outro@email "Nome"
#
# O acesso de admin dos CRMs Domani é sempre o ai@estudiooggi.com. Os demais
# entram por convite, na tela Usuários.
source "$(dirname "$0")/_comum.sh"

precisa_docker
if [ $# -eq 0 ]; then
  set -- ai@estudiooggi.com "Domani"
fi
docker compose exec api python /app/docker/criar_admin.py "$@"
