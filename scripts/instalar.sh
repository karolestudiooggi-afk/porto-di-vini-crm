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
# Portas 80/443: livres -> o Caddy do CRM cuida do HTTPS. Ocupadas pelo nginx
# da VPS (outros sites) -> modo "atrás do nginx" (docker-compose.nginx.yml).
porta_ocupada() { ss -ltnH "( sport = :$1 )" 2>/dev/null | grep -q .; }

modo=$(ler_env COMPOSE_FILE)
if [ -z "$modo" ]; then
  if porta_ocupada 80 || porta_ocupada 443; then
    pgrep -x nginx >/dev/null 2>&1 \
      || erro "As portas 80/443 estão ocupadas por outro programa (não é o nginx). Veja com: sudo ss -ltnp | grep -E ':(80|443) '"
    porta=8085
    while porta_ocupada "$porta"; do porta=$((porta + 1)); done
    gravar_env COMPOSE_FILE "docker-compose.yml:docker-compose.nginx.yml"
    gravar_env CRM_PORTA_LOCAL "$porta"
    ok "nginx já usa as portas 80/443: o CRM fica atrás dele, em 127.0.0.1:$porta"
  else
    gravar_env COMPOSE_FILE "docker-compose.yml"
    ok "portas 80/443 livres: o Caddy do CRM cuida do HTTPS"
  fi
fi
atras_do_nginx=false
case "$(ler_env COMPOSE_FILE)" in *nginx*) atras_do_nginx=true ;; esac

# Memória: o build do front passa de 1 GB. Pouca folga = build morto no meio
# (e, num servidor com outros sites, o kernel mata processo dos outros).
folga_mb=$(awk '/MemAvailable|SwapFree/ {s += $2} END {print int(s / 1024)}' /proc/meminfo)
if [ "$folga_mb" -lt 2500 ]; then
  aviso "só ${folga_mb} MB livres (memória + swap). Crie 2 GB de swap antes, para o build não derrubar nada:"
  echo "      sudo fallocate -l 2G /swapfile-crm && sudo chmod 600 /swapfile-crm && sudo mkswap /swapfile-crm && sudo swapon /swapfile-crm"
  echo "      echo '/swapfile-crm none swap sw 0 0' | sudo tee -a /etc/fstab"
  printf '    Seguir mesmo assim? [s/N] '
  read -r resposta || resposta=""
  case "$resposta" in [sS]*) ;; *) erro "parado para criar o swap. Depois, rode ./scripts/instalar.sh de novo." ;; esac
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
if $atras_do_nginx; then
  info "nginx da VPS: site do CRM"
  porta=$(ler_env CRM_PORTA_LOCAL)
  if [ -d /etc/nginx/sites-available ]; then
    destino=/etc/nginx/sites-available/crm-portodivino.conf
    ativo=/etc/nginx/sites-enabled/crm-portodivino.conf
  else
    destino=/etc/nginx/conf.d/crm-portodivino.conf
    ativo=
  fi
  if [ -f "$destino" ]; then
    ok "já existe $destino (não mexi; o certbot pode ter acrescentado o HTTPS nele)"
  else
    sed -e "s/__DOMINIO__/$dominio/g" -e "s/__PORTA__/$porta/g" docker/nginx-site.conf.modelo \
      | sudo tee "$destino" >/dev/null
    [ -z "$ativo" ] || sudo ln -sf "$destino" "$ativo"
    if ! sudo nginx -t >/dev/null 2>&1; then
      sudo rm -f "$destino" ${ativo:+"$ativo"}
      sudo nginx -t || true
      erro "o nginx recusou a configuração (acima). Tirei o arquivo do CRM; os outros sites não foram tocados."
    fi
    sudo systemctl reload nginx
    ok "site $dominio -> 127.0.0.1:$porta"
  fi

  if ! command -v certbot >/dev/null 2>&1; then
    aviso "certbot não instalado. Para o HTTPS: sudo apt-get install -y certbot python3-certbot-nginx"
    aviso "depois: sudo certbot --nginx -d $dominio --redirect"
  elif sudo certbot certificates 2>/dev/null | grep -q "Domains:.*$dominio"; then
    ok "certificado HTTPS de $dominio já existe"
  elif sudo certbot --nginx -d "$dominio" --redirect --non-interactive --agree-tos \
         --register-unsafely-without-email >/dev/null 2>&1; then
    ok "HTTPS ativo em $dominio"
  else
    aviso "o certbot não conseguiu o certificado (o DNS de $dominio já aponta para esta VPS?)."
    aviso "quando apontar: sudo certbot --nginx -d $dominio --redirect"
  fi
fi

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
                ./scripts/criar-admin.sh     (ai@estudiooggi.com)

  Ver o que está rodando:   docker compose ps
  Logs:                     docker compose logs -f api agendador
  Sync manual:              docker compose exec api python -m sync.main
  Banco (psql):             docker compose exec db psql -U postgres
  Backup:                   ./scripts/backup.sh

EOF
