#!/usr/bin/env bash
# Sobe o CRM Porto Di Vino inteiro nesta VPS: banco, login, API, front,
# agendador (sync Domani + campanhas) e HTTPS. Ver docs/DOCKER.md.
#
#   ./scripts/instalar.sh
#
# Pode rodar de novo sem perder nada: não recria o banco nem troca segredos
# que já existem. Para só atualizar o código depois, use ./scripts/atualizar.sh.
source "$(dirname "$0")/_comum.sh"

precisa_docker
command -v openssl >/dev/null 2>&1 || erro "Falta o openssl: sudo apt install -y openssl"

# -----------------------------------------------------------------------------
info "Configuração (.env)"
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  ok "criei o .env a partir do .env.example"
fi

dominio=$(ler_env CRM_DOMINIO)
[ -n "$dominio" ] || erro "Preencha CRM_DOMINIO no .env (ex.: crmportodivino.estudiodomaniai.com.br)."
ok "domínio: $dominio"

# Segredos: só gera o que está vazio. Mesma receita do utils/generate-keys.sh
# do Supabase (JWT HS256 com role anon / service_role).
b64url() { openssl enc -base64 -A | tr '+/' '-_' | tr -d '='; }
jwt() {
  local cabecalho payload assinatura
  cabecalho=$(printf '%s' '{"alg":"HS256","typ":"JWT"}' | b64url)
  payload=$(printf '%s' "$1" | b64url)
  assinatura=$(printf '%s' "$cabecalho.$payload" | openssl dgst -binary -sha256 -hmac "$2" | b64url)
  printf '%s' "$cabecalho.$payload.$assinatura"
}

if [ -z "$(ler_env POSTGRES_PASSWORD)" ]; then
  gravar_env POSTGRES_PASSWORD "$(openssl rand -hex 24)"
  ok "POSTGRES_PASSWORD gerada"
fi
if [ -z "$(ler_env JWT_SECRET)" ]; then
  gravar_env JWT_SECRET "$(openssl rand -base64 30 | tr -d '\n')"
  gravar_env ANON_KEY ""
  gravar_env SERVICE_ROLE_KEY ""
  ok "JWT_SECRET gerado"
fi
segredo=$(ler_env JWT_SECRET)
agora=$(date +%s)
validade=$((agora + 10 * 365 * 24 * 3600))
if [ -z "$(ler_env ANON_KEY)" ]; then
  gravar_env ANON_KEY "$(jwt "{\"role\":\"anon\",\"iss\":\"supabase\",\"iat\":$agora,\"exp\":$validade}" "$segredo")"
  ok "ANON_KEY gerada"
fi
if [ -z "$(ler_env SERVICE_ROLE_KEY)" ]; then
  gravar_env SERVICE_ROLE_KEY "$(jwt "{\"role\":\"service_role\",\"iss\":\"supabase\",\"iat\":$agora,\"exp\":$validade}" "$segredo")"
  ok "SERVICE_ROLE_KEY gerada"
fi
chmod 600 .env

[ -n "$(ler_env DOMANI_API_KEY)" ] || aviso "DOMANI_API_KEY vazia: o sync com a Domani fica parado até preencher."
[ -n "$(ler_env CAMPANHA_SMTP_PASSWORD)" ] || aviso "CAMPANHA_SMTP_PASSWORD vazia: sem ela o SendPulse recusa (o dry-run funciona)."
[ -n "$(ler_env EMAIL_HOST_USER)" ] || aviso "EMAIL_HOST_USER vazio: convites e 'redefinir senha' não saem até preencher o SMTP transacional."

if command -v getent >/dev/null 2>&1 && ! getent hosts "$dominio" >/dev/null 2>&1; then
  aviso "$dominio ainda não resolve no DNS. O CRM sobe, mas o HTTPS só sai quando o registro A apontar para esta VPS."
fi

# -----------------------------------------------------------------------------
info "Construindo as imagens (a primeira vez leva alguns minutos)"
docker compose build

info "Subindo banco e Supabase (db, auth, rest, storage)"
docker compose up -d --wait db auth rest storage
ok "banco e login no ar"

migrar

info "Subindo API, front, agendador e HTTPS"
docker compose up -d --wait api
docker compose up -d
ok "tudo no ar"

# -----------------------------------------------------------------------------
if [ -n "$(ler_env DOMANI_API_KEY)" ]; then
  info "Primeiro sync com a Domani"
  echo "    teste controlado (50 contatos)…"
  docker compose exec -T -e DOMANI_SYNC_LIMIT=50 api python -m sync.main \
    || erro "o sync de teste falhou. Confira DOMANI_API_KEY e DOMANI_API_URL no .env e rode de novo."
  echo "    sync completo…"
  docker compose exec -T api python -m sync.main || erro "o sync completo falhou (mensagem acima)."
  ok "contatos da Domani no banco"
fi

# -----------------------------------------------------------------------------
cat <<EOF

$(printf '\033[1;32m')CRM no ar.$(printf '\033[0m')

  Endereço:     https://$dominio
  Primeiro admin (uma vez só):
                ./scripts/criar-admin.sh email@dominio "Nome"

  Ver o que está rodando:   docker compose ps
  Logs:                     docker compose logs -f api agendador
  Sync manual:              docker compose exec api python -m sync.main
  Banco (psql):             docker compose exec db psql -U postgres
  Backup:                   ./scripts/backup.sh

EOF
