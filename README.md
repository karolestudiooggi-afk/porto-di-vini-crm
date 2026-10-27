# CRM Porto Di Vino

CRM da Porto Di Vino, gerado a partir do template CRM Domani. O foco é o
**disparador de e-mail**: montar a base, segmentar e disparar campanhas pelo
**SendPulse** — o mesmo provedor e o mesmo código de envio do CRM da Mamma Jamma
(cota por hora/dia/mês, retomada automática, supressão de bounce e descadastro,
`List-Unsubscribe` de um clique).

| | |
|---|---|
| Endereço do CRM | `https://crmportodivino.estudiodomaniai.com.br` |
| Provedor de envio | SendPulse, SMTP `smtp-pulse.com:587` (TLS) — conta da Domani, a mesma de todos os CRMs |
| Remetente | `Porto Di Vino <contato@portodivino.com.br>` — **a confirmar com a Porto** |
| Domínio que precisa de autenticação | `portodivino.com.br` ([DNS-PORTODIVINO.md](docs/DNS-PORTODIVINO.md)) |
| Servidor | VPS própria da Porto, com Docker ([DOCKER.md](docs/DOCKER.md)), pasta `~/crm-portodivino` |

## O que falta antes do primeiro envio real

O código está pronto; o que segura o disparo está fora dele.

| # | Item | Situação | Com quem |
|---|---|---|---|
| 1 | Saber onde está o DNS do `portodivino.com.br` e quem tem acesso | pedido à Porto | Porto |
| 2 | Definir a caixa que assina as campanhas (hoje `contato@`, provisório) | pedido à Porto | Porto |
| 3 | SPF + DKIM do SendPulse no DNS; DMARC já existe (`p=none`), manter | depois do 1 | quem cuida do DNS |
| 4 | Remetente `@portodivino.com.br` verificado na conta SendPulse da Domani | depois do 2 | Domani |
| 5 | Base de e-mails: exportação do e-commerce/clube **com o consentimento** | pedir à Porto | Porto |
| 6 | Registro A de `crmportodivino.estudiodomaniai.com.br` → IP da VPS, e `./scripts/instalar.sh` | a fazer | Domani |
| 7 | Aquecimento do domínio: ~2 semanas subindo `SMTP_LIMITE_DIA` | depois do 3 | Domani |

A conta SendPulse é uma só para todos os CRMs: a cota do mês e o limite de
2.500/h são divididos. A Porto começa com 5.000/mês (`SMTP_LIMITE_MES`); a soma
de todos os CRMs não pode passar do plano. Ver
[DISPARADOR.md](docs/DISPARADOR.md#conta-sendpulse-compartilhada).

Sobre o item 5: o Domani (WhatsApp) quase nunca traz e-mail. Só recebe campanha
quem tem e-mail na ficha, então o público vem da importação em **Contatos**
(CSV/XLSX, [planilha modelo](docs/modelos/modelo-importacao-contatos.csv)). Uma
coluna `opt_in_email` (ou `aceita_email`) com "não" barra a pessoa para sempre.

## Módulos ligados

Em `frontend/src/config/cliente.ts`. Desligado, o módulo some do menu e a rota
mostra "módulo desligado".

| Módulo | Estado | Por quê |
|---|---|---|
| Base: Dashboard, Contatos, Usuários | ligado | sempre |
| `campanhas` (E-mail) | **ligado** | o foco deste CRM |
| `agente` | ligado | aba do Agente IA, presente em todos os CRMs Domani |
| `auditoria` | ligado | alterações manuais, só admin |
| `parceiros`, `avaliacoes`, `rankings` | desligado | a Porto não pediu |
| `integracoes.*` (iFood, Google, Tripadvisor, Reclame Aqui) | desligado | idem |

Para ligar um módulo depois: variáveis no `.env` (bloco do `.env.example` do
template), chave em `cliente.ts`, API reiniciada e build do front.

## Onde mora a configuração da Porto

| Onde | O quê |
|---|---|
| `.env` (raiz, de `.env.example`) | segredos, SMTP do SendPulse, remetente, limites de envio, `CLIENTE_NOME` |
| `frontend/src/config/cliente.ts` | vocabulário e módulos (no Docker, nome, API e Supabase do front vêm do `.env` da raiz) |
| `backend/sql/seeds/cliente.sql` | remetente das campanhas em `email.remetentes` |

## Subir do zero (Docker na VPS)

Um `docker compose` sobe tudo na VPS da Porto: banco do cliente (Postgres do
Supabase), login, API, front, o sync diário com a Domani, a continuação das
campanhas e o HTTPS. Passo a passo completo em [DOCKER.md](docs/DOCKER.md).

```bash
curl -fsSL https://get.docker.com | sh
git clone https://github.com/karolestudiooggi-afk/porto-di-vini-crm.git ~/crm-portodivino
cd ~/crm-portodivino
cp .env.example .env && nano .env     # DOMANI_API_KEY, senha SMTP do SendPulse, SMTP de convites
./scripts/instalar.sh                 # gera segredos, sobe, migra, seed e primeiro sync
./scripts/criar-admin.sh rick@estudiooggi.com "Rick"
```

Antes: registro A de `crmportodivino.estudiodomaniai.com.br` apontando para a
VPS (o Caddy tira o certificado HTTPS sozinho). Depois:

1. **Base de e-mails.** Importe a planilha da Porto em Contatos.
2. **Primeiro envio.** Só depois do DNS do `portodivino.com.br` autenticado e
   do roteiro de [DISPARADOR.md](docs/DISPARADOR.md#antes-de-disparar-de-verdade):
   dry-run, teste com 2 ou 3 e-mails da equipe, depois a campanha real.

Atualizar depois de um push: `./scripts/atualizar.sh` (código, imagens,
migrations novas e serviços, nessa ordem).

O caminho manual do template (systemd + nginx + Supabase à parte) continua em
[DEPLOY.md](docs/DEPLOY.md), para quem não quiser Docker.

## Stack

- **Backend**: FastAPI + psycopg (async), Python 3.13 com [uv](https://docs.astral.sh/uv/).
- **Front**: Next.js 14 (App Router) + Tailwind, no design system Domani.
- **Banco e login**: Supabase — Postgres e Auth. O Supabase emite o JWT; o
  FastAPI é a porta de acesso ao banco, e a service role nunca sai do backend.
- **Produção**: Docker Compose na VPS — Caddy (HTTPS), front, API, agendador e o
  recorte do Supabase (Postgres, Auth, Storage). Ver [DOCKER.md](docs/DOCKER.md).

```text
Domani (WhatsApp da Porto) -> sync diário -> crm.contatos <- importação CSV/XLSX
                                                  |            (base do e-commerce/clube)
                                                  v
          FastAPI (/api) <---- segmentos -> email.* -> SMTP SendPulse -> caixa do cliente
                |                                         (From: @portodivino.com.br,
            Next.js (/)                                    DKIM assinado pelo SendPulse)
```

## Estrutura

```text
backend/
├── app/                  # FastAPI: auth, RBAC, rotas e serviços
├── sql/
│   ├── 001_…sql … 021_…sql   # migrations, na ordem
│   └── seeds/
│       └── cliente.sql       # remetente da Porto
├── sync/                 # sync diário Domani -> crm.contatos
└── tests/
frontend/
└── src/config/cliente.ts # nome, vocabulário e módulos da Porto
docs/
├── DNS-PORTODIVINO.md    # o que configurar no DNS do portodivino.com.br
├── DISPARADOR.md         # campanhas: cota, público, entregabilidade, aquecimento
├── DOCKER.md             # subir na VPS com Docker
├── systemd/, nginx/      # caminho manual, sem Docker (DEPLOY.md)
└── modelos/              # planilha modelo de importação
docker/                   # Dockerfiles, Caddyfile, init do banco, agendador
scripts/                  # instalar, atualizar, criar-admin, backup
docker-compose.yml
```

## Migrations

No Docker, o `instalar.sh`/`atualizar.sh` aplica cada migration **uma vez só**
e registra em `controle.migracoes`. Reaplicar a sequência inteira não é
seguro: a `004` recria a view de consumo com colunas que a `010`/`011` mudaram,
e o Postgres recusa. Nenhuma migration traz dado de cliente: isso é papel do seed.

| # | O quê |
|---|---|
| `001` | ficha unificada (`crm.contatos`), com o Domani como fonte |
| `002` | schema do e-mail: templates, campanhas, destinatários, eventos, supressões |
| `003` | API: papéis, permissões (RBAC), usuários, auditoria e notas manuais |
| `004` | envio real: consumo do provedor, supressão por bounce, remetentes autorizados |
| `005` | reserva atômica do lote de envio (estado `processando`) |
| `006` | convites de acesso |
| `007` | PDV Alpha Code: cadastro e consumo por webhook |
| `008` | avaliação/NPS (`avaliacao.*`) |
| `009` | permissões do operador: tudo, menos usuários e auditoria |
| `010` | cota diária de envio |
| `011` | cota mensal de envio |
| `012` | métricas de campanha: bounce, descadastro e taxas |
| `013` | integrações iFood e Google (`integra.*`) |
| `014` | tentativas do agente do iFood: erro passageiro não é definitivo |
| `015` | e-mail para parceiros |
| `016` | monitor de reputação: Tripadvisor e Reclame Aqui |
| `017` | chave da IA e lojas só no servidor |
| `018` | resposta do Google pelo NichoChat (status `encaminhada`) |
| `019` | leitura automática das avaliações do Google |
| `020` | busca do Google pelo NichoChat |
| `021` | comentário do Google em partes |

## Desenvolvimento

```bash
cd backend
uv sync
uv run pytest
uv run uvicorn app.main:app --reload     # Swagger em http://127.0.0.1:8000/docs

cd frontend
cp .env.example .env
npm install && npm run dev               # sem API/Supabase roda em modo demo
```

O contrato completo da API está em [`docs/API.md`](docs/API.md).

## Contatos

A API importa e exporta contatos em CSV/XLSX. Importações fazem merge por
telefone ou e-mail; o sync Domani posterior complementa a mesma ficha.
Exclusões ficam ocultas até uma nova atividade Domani ou reimportação explícita.

## Sync Domani

```bash
cd backend
uv run python -m sync.main
```

| variável | papel |
|---|---|
| `DATABASE_URL` | Postgres/Supabase |
| `DOMANI_API_URL` | base da API Domani |
| `DOMANI_API_KEY` | conta da Porto no Domani |
| `DOMANI_SYNC_LIMIT` | teto opcional para teste controlado |
| `DOMANI_INCLUDE_LABELS` | default `true` |
| `DOMANI_RESET_STATE` | default `true`; reconciliação completa diária |

Quando `DOMANI_SYNC_LIMIT` está definido, etiquetas são puladas para impedir um
reset global seguido de reconciliação parcial.

A reconciliação de etiquetas é atômica: todas as páginas são lidas antes de o
banco ser alterado. Depois, o reset e a reaplicação acontecem na mesma transação;
uma falha de API ou banco preserva o estado anterior.

O sync faz upsert por `user_ns`, depois por telefone canônico e, por último, pela
identidade social `(canal, domani_user_id)`. Em Instagram, Facebook e TikTok o
`user_id` nunca é interpretado como telefone.

Em produção roda pelo serviço `agendador` do Docker, todo dia às 06:00
(`America/Sao_Paulo`; outros horários em `SYNC_HORARIOS`). Na mão:
`docker compose exec api python -m sync.main`.

## Documentação

| Doc | O quê |
|---|---|
| [DNS-PORTODIVINO.md](docs/DNS-PORTODIVINO.md) | registros SPF/DKIM/DMARC do `portodivino.com.br` para o SendPulse |
| [DISPARADOR.md](docs/DISPARADOR.md) | campanhas: cota, regras de público, entregabilidade, aquecimento, timer |
| [API.md](docs/API.md) | contrato da API, permissões e primeiro usuário |
| [DOCKER.md](docs/DOCKER.md) | **subir na VPS com Docker**: instalar, sync, atualizar, backup |
| [DEPLOY.md](docs/DEPLOY.md) | caminho manual (systemd + nginx), sem Docker |
| [DISPARADOR-PROPRIO.md](docs/DISPARADOR-PROPRIO.md) | transporte alternativo pelo disparador HTTP da Domani |
| [frontend/README.md](frontend/README.md) | front-end: módulos, decisões, design system |

Docs dos módulos desligados (vêm do template, para quando forem ligados):
[PARCEIROS.md](docs/PARCEIROS.md), [AVALIACAO.md](docs/AVALIACAO.md),
[INTEGRACOES.md](docs/INTEGRACOES.md),
[MONITOR-REPUTACAO.md](docs/MONITOR-REPUTACAO.md),
[INTEGRACAO-ALPHACODE.md](docs/INTEGRACAO-ALPHACODE.md).
