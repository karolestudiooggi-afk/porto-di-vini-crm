# Contrato da API

Supabase Auth emite o JWT e o FastAPI é a superfície principal de acesso ao
banco. O frontend envia o token em `Authorization: Bearer <jwt>`. Em produção a
API fica atrás do nginx em `https://crmportodivino.estudiodomaniai.com.br/api`.

Em desenvolvimento:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`

## Rotas da base

| método | rota | permissão | finalidade |
|---|---|---|---|
| `GET` | `/health` | pública | disponibilidade da API |
| `GET` | `/usuarios/me` | autenticado | sessão, papel e permissões |
| `GET` | `/usuarios` | `usuarios:read` | usuários autorizados |
| `GET` | `/auditoria` | `auditoria:read` | alterações manuais auditadas |
| `GET` | `/contatos` | `contatos:read` | lista paginada e filtrada |
| `GET` | `/contatos/stats` | `contatos:read` | contadores do mesmo recorte |
| `GET` | `/contatos/filtros` | `contatos:read` | opções reais para os filtros |
| `POST` | `/contatos/import` | `contatos:import` | importação CSV/XLSX por telefone/e-mail |
| `GET` | `/contatos/export` | `contatos:export` | CSV/XLSX do recorte filtrado |
| `GET` | `/contatos/{id}` | `contatos:read` | ficha nativa completa |
| `GET` | `/contatos/{id}/timeline` | `contatos:read` | eventos Domani disponíveis |
| `PATCH` | `/contatos/{id}` | `contatos:write` | somente `observacoes` |
| `DELETE` | `/contatos/{id}` | `contatos:delete` | exclusão lógica auditada |
| `GET` | `/dashboard/resumo` | `dashboard:read` | KPIs reais da base atual |
| `GET` | `/dashboard/distribuicoes` | `dashboard:read` | canal, status, origem e idioma |
| `GET` | `/dashboard/atividade` | `dashboard:read` | interações por dia |
| `GET` | `/dashboard/consumo` | `dashboard:read` | consumo por período (com PDV ligado) |
| `GET` | `/usuarios/convites` | `usuarios:read` | convites pendentes |
| `POST` | `/usuarios/convites` | `usuarios:manage` | convidar por e-mail |
| `DELETE` | `/usuarios/convites/{id}` | `usuarios:manage` | cancelar convite |
| `PATCH` | `/usuarios/{id}` | `usuarios:manage` | papel e situação do usuário |
| `GET` · `POST` | `/definir-senha` | pública (token do convite) | aceite do convite |

Filtros de `/contatos`: `busca`, `ordenar`, `canal`, `status`, `idioma`,
`origem`, `tags`, `etiquetas`, `com_email`, `com_telefone`, `limit` e `offset`.
`tags` e `etiquetas` podem ser repetidos na query string; o contato precisa ter
ao menos um dos valores enviados.

As rotas dos módulos estão nos documentos de cada um:

| prefixo | módulo | documento |
|---|---|---|
| `/email/*`, `/track/*`, `/unsubscribe` | campanhas e parceiros | [DISPARADOR.md](DISPARADOR.md), [PARCEIROS.md](PARCEIROS.md) |
| `/avaliacao/*` | NPS | [AVALIACAO.md](AVALIACAO.md) |
| `/integracoes/*` | iFood e Google | abaixo e [INTEGRACOES.md](INTEGRACOES.md) |
| `/monitor/*` | Tripadvisor e Reclame Aqui | [MONITOR-REPUTACAO.md](MONITOR-REPUTACAO.md) |
| `/webhooks/*` | PDV e NichoChat | [INTEGRACAO-ALPHACODE.md](INTEGRACAO-ALPHACODE.md), [INTEGRACOES.md](INTEGRACOES.md) |

## Limites

Por padrão o Domani é a única fonte. Sem PDV ligado, dados de compra, visita,
faturamento, ticket, aniversário e preferências comerciais não fazem parte do
contrato. Não existem respostas simuladas para esses campos.

Os campos sincronizados do Domani são somente leitura. A edição pontual altera
`observacoes`, campo editorial que o sync não toca.

A importação aceita `.csv` e `.xlsx` de até 10 MB. Telefone e e-mail localizam a
ficha existente; quando ambos apontam para pessoas diferentes, a linha é rejeitada
para impedir uma fusão incorreta. Dados importados preenchem campos vazios, e tags
manuais permanecem separadas das tags Domani. O modelo está em
[`docs/modelos/modelo-importacao-contatos.csv`](modelos/modelo-importacao-contatos.csv).

A exclusão é lógica: a ficha deixa imediatamente de aparecer nas listas,
dashboard e exportações. Um sync comum não a restaura. Se o Domani registrar uma
nova interação posterior à exclusão, a mesma ficha é reativada e complementada;
uma nova importação explícita também a restaura.

Cada fonte futura deve ter schema, pipeline e router próprios. O enriquecimento
da ficha acontece em `crm.contatos`, preservando as rotas acima e acrescentando
novos campos de forma compatível.

## Integrações

Avaliações do iFood e do Google Meu Negócio. Exigem `integracoes:manage`; as
marcadas com **(config)** exigem `integracoes:config`, que só o admin tem.
`{origem}` é `ifood` ou `google`. Detalhes em [`INTEGRACOES.md`](INTEGRACOES.md).

| Rota | O que faz |
|---|---|
| `GET /integracoes` | situação de cada integração (configurada, conectada, quantas lojas) |
| `GET /integracoes/{origem}/config` · `PATCH` **(config)** | modo, tom, assinatura, prompt, webhook |
| `GET /integracoes/{origem}/lojas` | unidades cadastradas (o cadastro é por SQL, no seed do cliente) |
| `GET /integracoes/{origem}/resumo` | pendentes por loja, consultando a plataforma ao vivo |
| `GET /integracoes/{origem}/historico` | o que o CRM publicou, ignorou ou não conseguiu publicar |
| `GET /integracoes/{origem}/lojas/{loja_id}/avaliacoes` | fila da loja |
| `GET /integracoes/{origem}/lojas/{loja_id}/avaliacoes/{id}` | detalhe + as que ainda esperam resposta |
| `POST …/avaliacoes/{id}/sugerir` | texto sugerido pela IA; não publica |
| `POST …/avaliacoes/{id}/responder` | publica (`{"texto": "…"}`) |
| `GET /integracoes/ifood/agente` · `POST …/agente/rodar` | passadas do agente; disparar uma agora |
| `POST /integracoes/google/ler` | pede ao NichoChat a busca das avaliações novas agora |
| `GET /integracoes/google/oauth/url` **(config)** | endereço de consentimento do Google |
| `POST /integracoes/google/sincronizar` **(config)** | lê as unidades da conta e vincula as cadastradas |
| `POST /integracoes/google/desconectar` **(config)** | apaga a conexão |

As rotas de fila e detalhe devolvem o erro da plataforma no campo `erro`, com
status 200: a tela mostra a mensagem como veio e continua de pé. As que publicam
devolvem 400 com a mensagem em `detail`.

`GET /integracoes/google/callback` é pública e não aparece no Swagger: é para
onde o Google devolve o navegador, validada pelo `state` assinado.

## Primeiro usuário

O JWT só é aceito quando o mesmo `auth.users.id` existe em `app.usuarios`. Após
criar o primeiro usuário pelo Supabase Auth (Studio → Authentication → Add user,
com e-mail confirmado), um administrador do banco deve vinculá-lo ao papel
`admin`:

```sql
INSERT INTO app.usuarios (id, nome, email, papel_id)
SELECT '<auth.users.id>', '<nome>', '<email>', id
FROM app.papeis
WHERE nome = 'admin';
```

Daí em diante, os acessos saem pela tela **Usuários** (convite por e-mail, que usa
o SMTP transacional e a `SUPABASE_SERVICE_ROLE_KEY`). Não use a service role no
frontend. Ela permanece exclusiva do backend.
