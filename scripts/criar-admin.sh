#!/usr/bin/env bash
# Cria o primeiro admin do CRM (ou promove uma conta a admin). Pede a senha.
#
#   ./scripts/criar-admin.sh email@dominio "Nome da pessoa"
source "$(dirname "$0")/_comum.sh"

[ $# -ge 1 ] || erro "uso: ./scripts/criar-admin.sh email@dominio \"Nome\""
precisa_docker
docker compose exec api python /app/docker/criar_admin.py "$@"
