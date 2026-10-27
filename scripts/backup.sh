#!/usr/bin/env bash
# Backup do banco do CRM em ./backups (guarda os últimos 14).
#
#   ./scripts/backup.sh
#
# Todo dia às 03:00, pelo cron da VPS (crontab -e):
#   0 3 * * * cd /home/domani/crm-portodivino && ./scripts/backup.sh >> backups/backup.log 2>&1
#
# Gera dois arquivos por rodada:
#   crm-AAAAMMDD-HHMM.dump   dados do CRM (schemas crm, app, email, integra,
#                            avaliacao), formato do pg_restore
#   auth-AAAAMMDD-HHMM.sql   contas de login (só os dados do schema auth)
# As imagens dos templates de e-mail ficam no volume storage_data — entram no
# backup da VPS (snapshot do provedor), não aqui.
source "$(dirname "$0")/_comum.sh"

precisa_docker
mkdir -p backups
quando=$(date +%Y%m%d-%H%M)

docker compose exec -T db pg_dump -U postgres -d postgres -Fc \
  -n crm -n app -n email -n integra -n avaliacao \
  > "backups/crm-$quando.dump"

docker compose exec -T db pg_dump -U postgres -d postgres --data-only \
  -n auth --exclude-table-data=auth.schema_migrations \
  > "backups/auth-$quando.sql"

# Mantém os 14 mais recentes de cada tipo.
for tipo in crm auth; do
  # shellcheck disable=SC2012
  ls -1t backups/"$tipo"-* 2>/dev/null | tail -n +15 | xargs -r rm -f
done

ok "backups/crm-$quando.dump e backups/auth-$quando.sql"
