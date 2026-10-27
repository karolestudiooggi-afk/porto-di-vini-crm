# Funções compartilhadas pelos scripts da VPS. Não rode direto: é `source`.
# shellcheck shell=bash

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

info() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    ok:\033[0m %s\n' "$*"; }
aviso(){ printf '\033[1;35m    atenção:\033[0m %s\n' "$*"; }
erro() { printf '\n\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

precisa_docker() {
  command -v docker >/dev/null 2>&1 \
    || erro "Docker não está instalado. Na VPS (Ubuntu/Debian): curl -fsSL https://get.docker.com | sh"
  docker compose version >/dev/null 2>&1 \
    || erro "Falta o plugin 'docker compose' (vem com o get.docker.com)."
  docker info >/dev/null 2>&1 \
    || erro "Sem acesso ao Docker. Rode com sudo, ou entre no grupo: sudo usermod -aG docker \$USER (e saia/entre de novo)."
}

# Valor de uma variável no .env (sem aspas em volta). Vazio se não existir.
ler_env() {
  local linha
  linha=$(grep -E "^$1=" .env 2>/dev/null | tail -n 1 || true)
  linha=${linha#*=}
  linha=${linha%\"}; linha=${linha#\"}
  printf '%s' "$linha"
}

# Grava (substitui ou acrescenta) uma variável no .env.
gravar_env() {
  local chave=$1 valor=$2
  if grep -qE "^$chave=" .env; then
    # Os valores gerados são hex/base64/JWT: nunca têm '|' nem '&'.
    sed -i "s|^$chave=.*|$chave=$valor|" .env
  else
    printf '%s=%s\n' "$chave" "$valor" >> .env
  fi
}

# psql no banco do CRM, dentro do container `db` (backend/sql montado em /crm-sql).
psql_db() {
  docker compose exec -T db psql -v ON_ERROR_STOP=1 -q -U postgres -d postgres "$@"
}

# Aplica as migrations 0*.sql que ainda não rodaram, na ordem, e o seed.
#
# Cada migration roda UMA vez só: o registro fica em controle.migracoes.
# Reaplicar a sequência inteira não é seguro — a 004 recria a view de consumo
# com colunas que a 010/011 mudaram depois, e o Postgres recusa.
# O seed é ON CONFLICT DO NOTHING e roda sempre.
migrar() {
  info "Migrations do banco"
  psql_db -c "SET client_min_messages = warning;
              CREATE SCHEMA IF NOT EXISTS controle;
              CREATE TABLE IF NOT EXISTS controle.migracoes (
                arquivo text PRIMARY KEY,
                aplicada_em timestamptz NOT NULL DEFAULT now());" >/dev/null
  local aplicadas f nome novas=0
  aplicadas=$(psql_db -tA -c "SELECT arquivo FROM controle.migracoes")
  for f in backend/sql/0*.sql; do
    nome=$(basename "$f")
    if grep -qxF "$nome" <<<"$aplicadas"; then
      continue
    fi
    psql_db -f "/crm-sql/$nome" >/dev/null \
      || erro "a migration $nome falhou (mensagem acima). Nada depois dela foi aplicado."
    psql_db -c "INSERT INTO controle.migracoes (arquivo) VALUES ('$nome')" >/dev/null
    ok "$nome"
    novas=$((novas + 1))
  done
  [ "$novas" -gt 0 ] || ok "nenhuma migration nova"
  psql_db -f /crm-sql/seeds/cliente.sql >/dev/null \
    || erro "o seed backend/sql/seeds/cliente.sql falhou."
  ok "seed da Porto (remetente)"
}
