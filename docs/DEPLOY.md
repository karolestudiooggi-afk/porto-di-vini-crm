# Deploy — CRM Porto Di Vino

Passo a passo para pôr o CRM da Porto Di Vino no ar. Convenções usadas aqui e
nos arquivos de `docs/systemd/` e `docs/nginx/`:

| Peça | Valor |
|---|---|
| Pasta | `/home/domani/crm-portodivino` (usuário `domani`) |
| Domínio | `crmportodivino.estudiodomaniai.com.br` |
| API | `crm-portodivino-api.service`, `127.0.0.1:8081`, publicada em `/api/` |
| Front | `crm-portodivino-front.service`, `127.0.0.1:3000`, publicado em `/` |
| Sync Domani | `crm-portodivino-sync.service` + `crm-portodivino-sync.timer` (06:00, `America/Sao_Paulo`) |
| Continuação de campanhas | `crm-portodivino-agenda.service` + `crm-portodivino-agenda.timer` (de hora em hora) |
| nginx | `docs/nginx/crm-portodivino.conf` |

Agente do iFood, busca do Google pelo NichoChat e leitura da caixa do monitor
de reputação **não têm timer**: rodam dentro do processo da API.

> A Porto tem VPS própria: as portas do template (8081/3000) ficam como estão.

## 1. Pré-requisitos

- DNS: registro A de `crmportodivino.estudiodomaniai.com.br` apontando para o servidor.
- Pacotes: nginx, certbot, cliente `psql`, Node.js 20 LTS e
  [uv](https://docs.astral.sh/uv/) instalado para o usuário `domani`
  (`~/.local/bin/uv`). O Python (3.13, ver `.python-version`) o uv baixa.
- Supabase do cliente (nuvem ou self-hosted): `DATABASE_URL`, URL, JWT secret,
  service role e chave `anon`.

## 2. Código e `.env`

```bash
sudo -iu domani
git clone <repositório do cliente> ~/crm-portodivino
cd ~/crm-portodivino
cp .env.example .env                       # backend; fica fora do Git
cp frontend/.env.example frontend/.env     # front; idem
```

Preencha os dois conforme o [README](../README.md#novo-cliente-em-10-passos).
O `.env` da raiz é lido pelo `python-dotenv`: não use como `EnvironmentFile`
nem versione.

## 3. Banco

```bash
cd ~/crm-portodivino
for f in backend/sql/0*.sql; do
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f" || break
done

# seed da Porto: só o remetente das campanhas (confira o endereço antes)
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/sql/seeds/cliente.sql
```

As migrations podem ser reaplicadas, na ordem: não desfazem o que foi
configurado pela tela. O `cliente.sql` fica no repositório do cliente — nunca
volta para o template.

## 4. Backend e primeiro sync

```bash
cd ~/crm-portodivino/backend
uv sync
uv run pytest

DOMANI_SYNC_LIMIT=50 uv run python -m sync.main   # controlado
uv run python -m sync.main                        # completo
uv run python -m sync.main                        # de novo: nada deve mudar
```

A segunda rodada completa confirma a idempotência. O primeiro admin é criado
agora (ver [API.md](API.md#primeiro-usuário)).

## 5. Front

```bash
cd ~/crm-portodivino/frontend
npm ci
npm run build
```

`NEXT_PUBLIC_*` e `src/config/cliente.ts` entram **no build**: mudou um deles,
rode `npm run build` de novo.

## 6. systemd

```bash
sudo cp ~/crm-portodivino/docs/systemd/crm-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crm-portodivino-api.service crm-portodivino-front.service
sudo systemctl enable --now crm-portodivino-sync.timer crm-portodivino-agenda.timer
systemctl list-timers 'crm-*'
curl -s http://127.0.0.1:8081/health; echo
```

O `crm-portodivino-agenda.timer` só é necessário com o módulo de campanhas ligado. Os
timers usam `Persistent=true`: uma execução perdida com o servidor fora roda
assim que ele volta.

## 7. nginx e HTTPS

```bash
sudo cp ~/crm-portodivino/docs/nginx/crm-portodivino.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/crm-portodivino.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d crmportodivino.estudiodomaniai.com.br
```

O nginx encaminha `/api/` para `127.0.0.1:8081` **removendo o prefixo**; o
`--root-path /api` da API mantém Swagger e OpenAPI coerentes com a URL externa.
Com Supabase self-hosted, descomente o bloco `/supabase/` (gateway Kong). Sempre
`sudo nginx -t` antes de recarregar.

## Atualizar um cliente que já está no ar

Ordem fixa: **banco → API → front**. **Reinicie a API antes de refazer o build
do front**: o front novo chama rotas e campos que só a API nova tem; publicado
com a API antiga no ar, a tela abre e quebra.

```bash
cd ~/crm-portodivino && git pull
cd backend && uv sync
# migrations novas, se houver, na ordem
sudo systemctl restart crm-portodivino-api.service
curl -s http://127.0.0.1:8081/health; echo
cd ../frontend && npm ci && npm run build
sudo systemctl restart crm-portodivino-front.service
```

Mudança só de `.env` do backend (cota, chave, contato do NichoChat): basta
`sudo systemctl restart crm-portodivino-api.service`.

## Logs

```bash
sudo journalctl -u crm-portodivino-api -n 100 --no-pager
sudo journalctl -u crm-portodivino-sync -n 50 --no-pager
sudo journalctl -u crm-portodivino-agenda -n 30 --no-pager
```

O envio real de e-mail fica desligado (`EMAIL_DRY_RUN=true`) até o roteiro de
[DISPARADOR.md](DISPARADOR.md#antes-de-disparar-de-verdade).
