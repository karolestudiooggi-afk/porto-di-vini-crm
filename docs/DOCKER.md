# Docker na VPS — CRM Porto Di Vino

Um `docker compose` sobe o CRM inteiro na VPS da Porto: o banco do cliente, o
login, a API, o front, o sync com a Domani e o HTTPS. Substitui o caminho
manual do [DEPLOY.md](DEPLOY.md) (systemd + nginx + Supabase à parte).

## O que sobe

| Serviço | O que é | Aparece no domínio |
|---|---|---|
| `caddy` | HTTPS automático (Let's Encrypt) e rotas | portas 80/443 |
| `front` | Next.js | `/` |
| `api` | FastAPI | `/api` |
| `agendador` | sync Domani → banco e continuação de campanhas | — |
| `db` | Postgres do Supabase — **o banco do cliente** | — (só interno) |
| `auth` | login (Supabase Auth) | `/auth/v1` |
| `storage` | imagens dos templates de e-mail | `/storage/v1` |
| `rest` | PostgREST, usado pelo storage | — (só interno) |

As peças do Supabase são um recorte do compose oficial
(`supabase/supabase`, pasta `docker/`, versões de 16/10/2026): só o que este
CRM usa. Não há Studio, Realtime, Edge Functions nem Analytics. O banco não
fica exposto na internet; para mexer nele, `docker compose exec db psql -U postgres`.

Dados ficam em volumes do Docker (`db_data`, `storage_data`, `estado`,
`caddy_data`): sobrevivem a `restart`, `down` e atualização. Só
`docker compose down -v` apaga — não use.

## Antes de começar

- **VPS** Ubuntu 22.04/24.04, 2 vCPU e 4 GB de RAM (com 2 GB, crie swap — o
  build do front passa de 1 GB). Portas 80 e 443 livres.
- **DNS**: registro A de `crmportodivino.estudiodomaniai.com.br` apontando
  para o IP da VPS (na zona do `estudiodomaniai.com.br`). Sem isso o CRM sobe,
  mas o HTTPS não sai.
- **Chaves** à mão: `DOMANI_API_KEY` da Porto, senha SMTP do SendPulse (a
  mesma do `.env` da Mamma Jamma) e o SMTP de convites (`EMAIL_HOST_USER` e
  senha de app do Gmail).

Swap, se a VPS tiver 2 GB:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Passo a passo

```bash
# 1. Docker
curl -fsSL https://get.docker.com | sh

# 2. Código (repositório privado: ver "Acesso ao GitHub" abaixo)
git clone https://github.com/karolestudiooggi-afk/porto-di-vini-crm.git ~/crm-portodivino
cd ~/crm-portodivino

# 3. Configuração: preencha DOMANI_API_KEY, CAMPANHA_SMTP_PASSWORD,
#    EMAIL_HOST_USER e EMAIL_HOST_PASSWORD. Os segredos do banco e do login
#    o instalar.sh gera sozinho.
cp .env.example .env
nano .env

# 4. Sobe tudo: imagens, banco, migrations, seed, serviços e o primeiro sync
./scripts/instalar.sh

# 5. Primeiro admin (pede a senha)
./scripts/criar-admin.sh              # admin: ai@estudiooggi.com (pede a senha)
```

Depois, `https://crmportodivino.estudiodomaniai.com.br` e login com
`ai@estudiooggi.com` (o admin de sempre dos CRMs Domani). Os demais acessos
entram por convite, na tela Usuários.

O `instalar.sh` pode rodar de novo: não recria o banco nem troca segredo que já
existe, e só aplica migration que ainda não rodou.

### Acesso ao GitHub

Enquanto o repositório for público, o `git clone` acima funciona direto.
Privado, use uma deploy key (só leitura, só este repositório):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/crm_portodivino -N "" -C "vps-porto"
cat ~/.ssh/crm_portodivino.pub
# GitHub > porto-di-vini-crm > Settings > Deploy keys > Add deploy key (colar)
GIT_SSH_COMMAND="ssh -i ~/.ssh/crm_portodivino" \
  git clone git@github.com:karolestudiooggi-afk/porto-di-vini-crm.git ~/crm-portodivino
cd ~/crm-portodivino && git config core.sshCommand "ssh -i ~/.ssh/crm_portodivino"
```

## VPS que já tem nginx (caso da Porto)

Se as portas 80/443 já estão com o nginx da VPS (outros sites no mesmo
servidor), o `instalar.sh` percebe sozinho e:

1. grava no `.env` `COMPOSE_FILE=docker-compose.yml:docker-compose.nginx.yml`
   e `CRM_PORTA_LOCAL` (8085, ou a próxima livre): o Caddy do CRM passa a
   escutar só em `127.0.0.1:<porta>`, sem HTTPS próprio;
2. cria o site do CRM no nginx (`/etc/nginx/sites-available/crm-portodivino.conf`,
   a partir de `docker/nginx-site.conf.modelo`), confere com `nginx -t` e
   recarrega — se o nginx recusar, o arquivo sai e os outros sites ficam como
   estavam;
3. pede o certificado com o certbot (`--nginx --redirect`). Se o DNS ainda não
   aponta para a VPS, avisa e você roda depois:
   `sudo certbot --nginx -d crmportodivino.estudiodomaniai.com.br --redirect`

Ele pede `sudo` para mexer no nginx. Os comandos `docker compose` do dia a dia
continuam iguais: o `COMPOSE_FILE` do `.env` já inclui o arquivo do nginx.

Com pouca memória livre (memória + swap abaixo de 2,5 GB), o `instalar.sh`
para antes do build e mostra como criar 2 GB de swap: num servidor com outros
sites, um build sem folga faz o kernel matar processos dos vizinhos.

## O sync Domani → banco

É o que traz os contatos do WhatsApp da Porto (canal no Domani) para o banco
do CRM: identificação, canal, status, etiquetas, histórico. Roda
`python -m sync.main` com a `DOMANI_API_KEY` do `.env`.

- **Quando**: todo dia às 06:00 (São Paulo), pelo serviço `agendador`. Para
  mais horários, `SYNC_HORARIOS=06:00,13:00` no `.env` e
  `docker compose up -d agendador`.
- **Se a VPS estava desligada** na hora, roda assim que o agendador volta.
- **Primeira vez**: o `instalar.sh` já roda um sync de teste (50 contatos) e
  o completo.
- **Na mão**: `docker compose exec api python -m sync.main`
- **Acompanhar**: `docker compose logs -f agendador`

O mesmo agendador, a cada 5 minutos (`AGENDA_INTERVALO_MIN`), continua as campanhas maiores que a cota
e dispara as agendadas — o que no template era o `crm-agenda.timer`.

## Dia a dia

| Para | Comando (na pasta `~/crm-portodivino`) |
|---|---|
| Ver o que está rodando | `docker compose ps` |
| Logs | `docker compose logs -f api agendador` |
| Atualizar depois de um push | `./scripts/atualizar.sh` |
| Mudou algo no `.env` | `docker compose up -d` (recria só o que mudou) |
| Mudou `CLIENTE_NOME` ou `CRM_DOMINIO` | `./scripts/atualizar.sh` (o front precisa de build novo) |
| Sync manual | `docker compose exec api python -m sync.main` |
| Banco | `docker compose exec db psql -U postgres` |
| Backup | `./scripts/backup.sh` |
| Reiniciar um serviço | `docker compose restart api` |

## Backup

`./scripts/backup.sh` grava em `backups/` os dados do CRM (`crm-*.dump`) e as
contas de login (`auth-*.sql`), guardando os 14 mais recentes. Para todo dia
às 03:00, no `crontab -e` da VPS:

```
0 3 * * * cd /home/<usuário>/crm-portodivino && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Copie a pasta `backups/` para fora da VPS de tempos em tempos (ou use o
snapshot do provedor, que pega também as imagens do `storage_data`).

Restaurar, numa instalação nova (depois do `instalar.sh`, antes de usar):

```bash
docker compose exec -T db psql -U postgres -c "DROP SCHEMA crm, app, email, integra, avaliacao CASCADE"
docker compose exec -T db pg_restore -U postgres -d postgres < backups/crm-AAAAMMDD-HHMM.dump
docker compose exec -T db psql -U postgres -d postgres < backups/auth-AAAAMMDD-HHMM.sql
```

## Cuidados

- **Não troque `POSTGRES_PASSWORD` nem `JWT_SECRET`** depois do primeiro
  `instalar.sh`. A senha fica gravada no volume do banco; o JWT assina as
  chaves que estão no front. Se precisar mesmo trocar, é reinstalar.
- O `.env` fica com permissão 600 e fora do Git (`.gitignore`). Não suba.
- Cadastro público no login está desligado: conta só nasce por convite ou
  pelo `criar-admin.sh`.
- Migrations: cada arquivo `backend/sql/0*.sql` roda uma vez só; o registro
  fica em `controle.migracoes`. Migration nova entra no próximo
  `atualizar.sh`.

## Quando algo não funciona

| Sintoma | Onde olhar |
|---|---|
| Site não abre em HTTPS | DNS apontando para a VPS? Portas 80/443 livres? `docker compose logs caddy` |
| Build do front morre no meio | memória: crie swap (acima) e rode de novo |
| Login responde erro | `docker compose logs auth`; se o `ANON_KEY` mudou, `./scripts/atualizar.sh` |
| Contatos não chegam | `docker compose logs agendador` e `DOMANI_API_KEY` no `.env` |
| Upload de imagem no template falha | `docker compose logs storage` |
| Campanha parada em "enviando" | normal se bateu a cota: o agendador continua na hora cheia seguinte |
