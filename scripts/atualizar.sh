#!/usr/bin/env bash
# Atualiza o CRM nesta VPS depois de um push no GitHub: código novo, imagens
# novas, migrations e serviços reiniciados — nessa ordem (banco -> API -> front),
# como no docs/DEPLOY.md. Os dados ficam.
#
#   ./scripts/atualizar.sh
source "$(dirname "$0")/_comum.sh"

precisa_docker
[ -f .env ] || erro "Sem .env: a primeira vez é ./scripts/instalar.sh."

info "Código novo"
git pull --ff-only

info "Construindo as imagens"
docker compose build

info "Banco e Supabase"
docker compose up -d --wait db auth rest storage

migrar

info "API, front e agendador"
docker compose up -d --wait api
docker compose up -d
docker image prune -f >/dev/null
ok "atualizado"
docker compose ps
