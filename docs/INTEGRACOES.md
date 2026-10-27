# Integrações — avaliações do iFood e do Google Meu Negócio

A aba **Integrações** do CRM mostra as avaliações das duas plataformas e deixa a
equipe responder sem sair dele, com a IA sugerindo o texto. Cada plataforma tem
sua chave em `frontend/src/config/cliente.ts`: `modulos.integracoes.ifood` e
`modulos.integracoes.google` (Tripadvisor e Reclame Aqui estão em
[MONITOR-REPUTACAO.md](MONITOR-REPUTACAO.md)).

| | iFood | Google Meu Negócio |
|---|---|---|
| Como o CRM entra | credenciais do aplicativo no `.env` | **pelo NichoChat do cliente** (`DOMANI_API_KEY`, `WEBHOOK_GOOGLE_KEY` e `NICHOCHAT_*` no `.env`); a conexão direta com o Google é opcional |
| Unidades | seed do cliente, pelo merchant UUID | seed do cliente, pelo id da location no Google |
| Leitura das avaliações | agente a cada 15 min | **automática, pelo NichoChat, a cada 29 min** ([ver abaixo](#leitura-automática-do-google)) |
| Resposta manual | sim | sim — **publicada pelo NichoChat** ([ver abaixo](#resposta-do-google-pelo-nichochat)) |
| Resposta automática | sim, pelo agente (opcional) | não pelo CRM — ver [abaixo](#por-que-a-resposta-do-google-é-só-manual) |
| Editar depois de publicar | **não**: é definitiva | sim: publicar de novo substitui |
| Prazo para responder | 5 dias | não há |
| Limite do texto | 10 a 300 caracteres | 4.096 bytes |

O iFood aqui é uma **cópia do Domani Avaliações** para dentro do CRM, servindo só
a um cliente: mesma fila, mesma tela de responder, mesmo agente rodando sozinho,
mesmo aviso para o NichoChat. A lógica foi reescrita em Python (a linguagem do
CRM), com as mesmas regras. As poucas diferenças estão em
[Vindo do Domani Avaliações](#vindo-do-domani-avaliações).

## Colocar no ar

### 1. Banco

As migrations `013`, `014`, `017` a `021` fazem parte da sequência `001`→`021`
do [README](../README.md#migrations). As unidades **não** vêm das migrations:
entram pelo seed do cliente (`backend/sql/seeds/cliente.sql`, copiado de
`cliente.exemplo.sql`), em `integra.lojas`:

```sql
insert into integra.lojas (origem, loja_id, nome, cidade) values
  ('ifood',  '<merchant UUID>',            'Unidade Centro', '<cidade>'),
  ('google', '<id da location no Google>', 'Unidade Centro', '<cidade>'),
  ('google', '<id da location no Google>', 'Unidade Norte',  '<cidade>')
on conflict (origem, loja_id) do nothing;
```

- iFood: o **merchant UUID** (Developer Portal do iFood); o código numérico do
  Portal do Parceiro não serve.
- Google: o id numérico da location, sem o prefixo `locations/` — o mesmo que o
  subfluxo de busca do NichoChat manda em `idUnidade`.

A tela só lista as unidades. Para tirar uma da fila sem perder o histórico:
`update integra.lojas set ativo = false where origem = '…' and loja_id = '…';`.
As migrations podem ser reaplicadas: não mexem no que já foi configurado pela
tela.

### 2. Variáveis no `.env` da raiz

```bash
APP_URL=https://crmportodivino.estudiodomaniai.com.br
CLIENTE_NOME=Cliente Exemplo     # vai no campo "cliente" dos avisos

# iFood — credenciais do aplicativo no Developer Portal
IFOOD_CLIENT_ID=
IFOOD_CLIENT_SECRET=

# Google — tudo pelo NichoChat (ver passo 4). Todas vazias no template.
DOMANI_API_URL=https://app.estudiodomani.com/api
DOMANI_API_KEY=                       # a mesma da sincronização; precisa do escopo "Manage Flow"
WEBHOOK_GOOGLE_KEY=                   # gere uma; vai também nos POSTs do NichoChat (X-API-Key)
NICHOCHAT_CONTATO_USER_ID=            # contato da busca: <DDI+DDD+número, sem +>
NICHOCHAT_RESPOSTA_CONTATO_USER_ID=   # contato das respostas: <DDI+DDD+número, sem +>
NICHOCHAT_BUSCA_GOOGLE_SUBFLUXO=      # <ns do subfluxo de busca>
NICHOCHAT_RESPOSTA_GOOGLE_SUBFLUXO=   # <ns do subfluxo de resposta>

# IA que sugere a resposta. Chave e modelo ficam só aqui, nunca na tela.
OPENAI_API_KEY=
```

`APP_URL` precisa estar correto: é dele que sai o endereço de retorno do Google
e o link que vai no aviso do WhatsApp. As demais variáveis, todas opcionais,
estão comentadas no `.env.example`. Para gerar a `WEBHOOK_GOOGLE_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Depois, ligue as chaves em `cliente.ts`, **reinicie a API e só então** refaça o
build do frontend:

```bash
sudo systemctl restart crm-portodivino-api.service
cd frontend && npm ci && npm run build
sudo systemctl restart crm-portodivino-front.service
```

### 3. iFood

1. Entre no CRM como **admin** → Integrações → iFood → Configuração.
2. Confira em **Lojas** as unidades que vieram do seed.
3. Em **Como responder**, preencha assinatura, tom e o **webhook do NichoChat**
   (sem ele, vale `NICHOCHAT_WEBHOOK_URL` do `.env`, se houver).

Cada loja também precisa ter autorizado o aplicativo no Portal do Parceiro. Sem
isso a fila daquela loja mostra *"não autorizou este aplicativo"*.

### 4. Google (pelo NichoChat)

O CRM não precisa de conexão própria com o Google: o canal do cliente no
NichoChat já tem a dele, e as duas pontas passam por lá. O canal precisa ter:

1. **A conexão Google** com os perfis das unidades.
2. **Três campos de contato** (Campos personalizados do contato), com estes
   nomes exatos — o CRM procura pelo nome e recusa se faltar algum:
   `ID_localizacao_resposta`, `review_id_resposta` e `resposta_comentario`.
3. **Um subfluxo de busca** (`NICHOCHAT_BUSCA_GOOGLE_SUBFLUXO`): lê as
   avaliações das unidades, separa as **criadas nos últimos 30 minutos**, monta
   blocos de até 2.900 caracteres e faz um POST por bloco em
   `/api/webhooks/nichochat/avaliacoes-google` com `X-API-Key` =
   `WEBHOOK_GOOGLE_KEY` ([contrato](#contrato-da-entrega-para-o-fluxo-do-nichochat)).
   O envio pode ficar num subfluxo auxiliar chamado por ele.
4. **Um subfluxo de resposta** (`NICHOCHAT_RESPOSTA_GOOGLE_SUBFLUXO`): lê
   `ID_localizacao_resposta`, `review_id_resposta` e `resposta_comentario` do
   contato, publica a resposta no Google e confirma por POST em
   `/api/webhooks/nichochat/resposta-google`, com a mesma chave
   ([contrato](#resposta-do-google-pelo-nichochat)).

| Ponta | Quem chama quem | Subfluxo |
|---|---|---|
| Avaliações novas | o CRM dispara a busca a cada 29 min no contato `NICHOCHAT_CONTATO_USER_ID`; o NichoChat devolve por POST | `<ns do subfluxo de busca>` |
| Resposta | o CRM grava os três campos no contato `NICHOCHAT_RESPOSTA_CONTATO_USER_ID` e dispara; o NichoChat publica e confirma por POST | `<ns do subfluxo de resposta>` |

Os dois contatos são números de serviço (não use o de uma pessoa da equipe:
os campos e disparos aparecem na conversa dela). Contato que não existe no
NichoChat o CRM cria sozinho (`POST /subscriber/create`, nome "CRM Busca Google"
/ "CRM Respostas Google").

Para ligar:

1. No `.env`: as variáveis do passo 2. Reinicie a API.
2. No NichoChat: a mesma `WEBHOOK_GOOGLE_KEY` no cabeçalho `X-API-Key` dos dois
   POSTs (também aceita `Authorization: Bearer <chave>`).
3. Confira em Integrações → Google Meu Negócio → Configuração → **Ligação com o
   NichoChat**: as três linhas verdes, a hora do último pedido de busca e da
   última entrega. Em **Unidades**, cada uma mostra quando foi lida.

Sem `DOMANI_API_*`, contato e subfluxo da busca, a busca simplesmente não
dispara; sem os da resposta, publicar recusa com "a ligação com o NichoChat não
está configurada".

#### Conexão direta com o Google (opcional)

Só serve para, ao abrir uma avaliação, conferir na hora como ela está no Google.
Precisa de um projeto no Google Cloud com a **Business Profile API** aprovada
(até aprovar, toda chamada dá erro de cota), um **ID do cliente OAuth** do tipo
*Aplicativo da Web* com este URI de redirecionamento:

```
https://crmportodivino.estudiodomaniai.com.br/api/integracoes/google/callback
```

`GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `.env`, e um admin em
Configuração → **Conectar conta Google** com a conta dona dos perfis. Com a tela
de consentimento em modo *Teste*, o Google expira a conexão a cada 7 dias.

### 5. Agente do iFood

**Não há nada para instalar.** Como no Domani Avaliações, o agente roda sozinho
dentro da API: sobe junto com ela, faz a primeira passada 30 segundos depois e
repete a cada 15 minutos. Em cada passada ele consulta as lojas ativas, avisa o
NichoChat do que chegou e, no modo automático, responde.

A aba **Agente de IA** mostra cada passada, e a visão geral do iFood mostra há
quanto tempo foi a última. O botão **Rodar agora** dispara uma fora de hora.

Para subir a API **sem** o agente (por exemplo, nas gravações de homologação do
iFood, para sobrar avaliação pendente na fila), use a mesma variável do Domani
Avaliações e reinicie:

```bash
WORKER_DESLIGADO=1
```

Para uma passada avulsa pelo terminal (o equivalente ao `domani worker`):

```bash
cd backend && uv run python -m app.services.integracoes.agente
```

> Se as lojas do cliente também estiverem no Domani Avaliações, **tire-as de lá**
> (ou pause o cliente) ao ligar o iFood aqui. Com os dois agentes olhando as
> mesmas lojas, o aviso sai em dobro e, no automático, o segundo a responder
> recebe erro 422 do iFood.

## Como funciona

### Quem pode o quê

| Permissão | Quem tem | O que libera |
|---|---|---|
| `integracoes:manage` | admin e operador | ver a fila, pedir sugestão, responder, histórico, rodar o agente, "Ler agora" |
| `integracoes:config` | só admin | conectar o Google, mudar o modo e o prompt (lojas são cadastradas no servidor, por SQL) |

A divisão segue a de campanhas: responder é rotina; ligar o automático muda o
que é publicado em nome da casa sem ninguém olhar.

### Modos do iFood

- **Manual** (padrão): o agente só avisa. A equipe responde pela fila.
- **Automático**: o agente escreve e publica as avaliações com nota igual ou
  acima da **nota mínima**. As abaixo ficam na fila para uma pessoa.

Comece com nota mínima 4. Resposta de iFood não pode ser editada nem apagada.

### A sugestão da IA

Cada plataforma tem um prompt padrão:

- **iFood**: o do Domani Avaliações — até 300 caracteres, sem emoji, sem
  prometer cupom ou reembolso, sem pedir mudança de nota.
- **Google**: 2 a 4 frases. Para a sugestão daqui soar igual à resposta
  automática do NichoChat do cliente, use o mesmo texto da tarefa de IA de lá.

Preencher o campo **Prompt da IA** substitui o padrão **por inteiro**, inclusive
as proibições. A tela oferece "Começar pelo padrão" para editar em cima dele. É
ali que entra a voz da marca de cada cliente.

### Aviso para o NichoChat (só iFood)

O CRM envia **todas** as avaliações, sem filtro; o que é caso crítico e quem é
avisado é decisão do fluxo no NichoChat. Dois eventos:

| Evento | Quando |
|---|---|
| `avaliacao_nova` | na primeira vez que o agente vê a avaliação, em qualquer modo |
| `avaliacao_respondida` | depois da publicação, pelo agente ou pela tela |

```json
{
  "evento": "avaliacao_nova",
  "cliente": "Cliente Exemplo",
  "merchant_id": "<merchant UUID>", "loja": "Unidade Centro", "cidade": "<cidade>",
  "avaliacao_id": "<id da avaliação>", "pedido": "1234",
  "nota": 2, "comentario": "chegou fria",
  "criada_em": "2026-01-10T18:00:00+00:00",
  "nivel": "negativa",
  "prazo_horas": 18,
  "link": "https://crmportodivino.estudiodomaniai.com.br/integracoes?origem=ifood&loja=...&avaliacao=..."
}
```

`cliente` vem de `CLIENTE_NOME`. `avaliacao_respondida` leva também `resposta` e
`origem` (`manual` ou `agente`). `nivel` é `negativa` até nota 2, `neutra` na 3
e `positiva` de 4 para cima.

### Leitura automática do Google

O CRM recebe as avaliações novas do Google **pelo NichoChat**, que já tem a
conexão Google funcionando. A conexão Google do próprio CRM não é necessária.

1. A cada 29 minutos (`GOOGLE_LEITURA_INTERVALO_MIN`) o CRM dispara, no contato
   `NICHOCHAT_CONTATO_USER_ID`, o subfluxo de busca
   (`NICHOCHAT_BUSCA_GOOGLE_SUBFLUXO`) — `POST /subscriber/send-sub-flow-by-user-id`.
2. O subfluxo lê as unidades, separa as avaliações **criadas nos últimos 30
   minutos** e monta blocos de até 2.900 caracteres.
3. Para cada bloco, faz um POST ao CRM (contrato abaixo).
4. O CRM guarda em `integra.avaliacoes_google`, e as avaliações entram na fila.

**Por que 29.** O fluxo olha 30 minutos para trás: com o CRM disparando a cada
29, as janelas se encostam e cada avaliação cai numa busca só — o alerta de
negativa que o fluxo manda não sai dobrado. O CRM conta os 29 minutos a partir
do **último** disparo (o agendado, o "Ler agora" ou o de antes de a API
reiniciar), então a folga de 1 minuto não vai sendo comida. Disparo que falha
é repetido em 1 minuto. A mesma avaliação chegando de novo (`reviewId`) não
duplica. A rotina roda dentro da API, junto com o agente do iFood
(`WORKER_DESLIGADO` desliga as duas). O intervalo aceito vai de 5 a 30 minutos.

Limite conhecido: avaliação que o Google só libera **mais de 30 minutos depois**
de criada (a hora que conta é a de criação) fica fora da janela e não chega.

Na visão geral: o selo "leitura automática a cada 29 min", a hora da última
busca (e de quando chegou a última avaliação nova) e o botão **Ler agora**,
que pede a busca fora do horário. Se o NichoChat recusar o disparo, a mensagem
dele aparece no topo.

#### Contrato da entrega (para o fluxo do NichoChat)

```
POST https://crmportodivino.estudiodomaniai.com.br/api/webhooks/nichochat/avaliacoes-google
X-API-Key: <WEBHOOK_GOOGLE_KEY do .env>
Content-Type: application/json
```

Corpo: um bloco, como o fluxo monta — a lista de avaliações (`{{loop_item}}`):

```json
[
  {"unidade": "Unidade Centro", "idUnidade": "<id da location no Google>",
   "comentario": "(Translated by Google) …\n\n(Original)\nO atendimento demorou…",
   "notaReview": "ONE", "reviewId": "…", "displayName": "Ana",
   "dataHora": "2026-01-10T15:05:00.000000Z", "url": "https://business.google.com/…"}
]
```

- Também aceita `{"result": […]}`, `{"avaliacoes": […]}`, ou o mesmo corpo como
  texto JSON (variável serializada).
- Unidade: pelo `idUnidade`; vazio ou desconhecido, pelo nome em `unidade`,
  comparado com o `nome` de `integra.lojas` (sem acento e sem espaço também
  casa: `UnidadeCentro` = "Unidade Centro").
- Do comentário fica o original, sem a tradução automática.
- **Comentário em pedaços.** O que não cabe num bloco vem dividido, um POST por
  pedaço, com o mesmo `reviewId` e `parte` / `totalPartes`. O CRM guarda cada
  pedaço (`integra.avaliacoes_google_partes`) e grava a avaliação com o texto
  juntado até ali, marcado com "[…]" até chegar o último. A ordem dos POSTs não
  importa.
- Opcional por item: `resposta` — texto já publicado no Google; a avaliação
  sai da fila. Item sem `resposta` nunca apaga uma resposta já guardada.
- **Sem avaliação nova, o fluxo não precisa fazer POST.** Por isso o CRM dá as
  unidades como lidas quando o NichoChat **aceita o disparo** da busca (e também
  a cada entrega). Corpo vazio ou `[]` também é aceito, como "nada novo".

Respostas:

| HTTP | Quando | Corpo |
|---|---|---|
| 200 | gravou | `{"recebido": true, "processado": true, "recebidas": 4, "novas": 4, "unidades": 4, "confirmadas": 0, "ignoradas": []}` (e `"aguardando_partes": ["<reviewId>"]` enquanto falta pedaço de algum comentário) |
| 401 | chave errada ou `WEBHOOK_GOOGLE_KEY` vazia no servidor | `{"detail": "chave inválida"}` |
| 422 | corpo sem a lista | `{"detail": "formato não reconhecido: …"}` |

`ignoradas` lista o que não entrou e por quê (sem `reviewId`, unidade
desconhecida). Todo corpo recebido fica em `integra.webhook_eventos`
(origem `nichochat`).

**O subfluxo de resposta deve ler `ID_localizacao_resposta`**, e não um campo
que a busca também use: se a busca roda no mesmo contato e troca o id da
location a cada unidade, a resposta sairia na unidade errada.

Um disparo avulso pelo terminal:

```bash
cd backend && uv run python -m app.services.integracoes.leitor_google
```

### Resposta do Google pelo NichoChat

O CRM **não publica direto no Google**. Quando a atendente clica em publicar,
o backend:

1. acha o contato das respostas no NichoChat (`GET /subscriber/get-info-by-user-id`,
   `user_id` = `NICHOCHAT_RESPOSTA_CONTATO_USER_ID`). Se ele não existir, cria
   (`POST /subscriber/create` com
   `{"phone": "+<user_id>", "first_name": "CRM", "last_name": "Respostas Google"}`);
2. grava nele os três campos numa chamada só (`PUT /subscriber/set-user-fields` —
   é PUT: com POST o NichoChat responde 405). Se algum campo não voltar em
   `matched_items`, o fluxo **não** é disparado, para não publicar o valor da
   resposta anterior:

   | Campo | Valor |
   |---|---|
   | `ID_localizacao_resposta` | id da unidade no Google (`loja_id` em `integra.lojas`) |
   | `review_id_resposta` | `reviewId` da avaliação (campo só da resposta, para não colidir com outros fluxos) |
   | `resposta_comentario` | o texto da atendente |

3. dispara o subfluxo de resposta no contato:
   `POST /subscriber/send-sub-flow-by-user-id` com
   `{"user_id": "<NICHOCHAT_RESPOSTA_CONTATO_USER_ID>", "sub_flow_ns": "<ns do subfluxo de resposta>"}`.

Tudo com `DOMANI_API_URL` e `DOMANI_API_KEY` do `.env` — a chave precisa do
escopo **Manage Flow**. Nada disso passa pela tela.

O `user_id` vai **sem o "+"** (ex.: `5521999990000`): o NichoChat grava o
contato assim, e com o "+" a API responde *subscriber not found*.

**Um envio por vez.** O contato é o mesmo para todas as respostas; se duas
saíssem juntas, a segunda poderia trocar os campos antes de o fluxo ler a
primeira. Os envios fazem fila, com no mínimo 10 s entre um e outro
(`NICHOCHAT_RESPOSTA_INTERVALO_SEG`). Se o fluxo demorar mais que isso para
ler os campos, aumente o número.

**"Enviada ao NichoChat" não é "publicada".** O NichoChat responde `ok` quando o
fluxo disparou, não quando a resposta apareceu no Google. Quem confirma é o
próprio subfluxo de resposta: depois de publicar, ele avisa o CRM.

```
POST https://crmportodivino.estudiodomaniai.com.br/api/webhooks/nichochat/resposta-google
X-API-Key: <a mesma WEBHOOK_GOOGLE_KEY da entrega das avaliações>
Content-Type: application/json

{"reviewId": "{{review_id_resposta}}", "idUnidade": "{{ID_localizacao_resposta}}", "resposta": "{{resposta_comentario}}"}
```

Se não conseguiu publicar: `{"reviewId": "{{review_id_resposta}}", "status": "erro", "erro": "<motivo>"}`.

O fluxo cola a resposta entre aspas no corpo, então resposta com quebra de linha
ou aspas chega como JSON inválido. O CRM aceita assim mesmo: acha o `reviewId`
no texto e considera publicado o texto que ele próprio enviou.
Também aceita uma lista desses avisos, ou `{"result": …}`. Resposta:
`{"recebido": true, "processado": true, "avisos": [{"reviewId": "…", "resultado": "publicada"}]}`.

| No CRM | Quando |
|---|---|
| *aguardando o Google* (`encaminhada`) | o NichoChat aceitou o disparo; a avaliação sai da fila por até 15 min |
| *publicada* (`enviada`) | o subfluxo avisou que publicou esse texto |
| *falhou* (`erro`) | o NichoChat recusou o disparo, ou o subfluxo avisou que não publicou; volta para a fila com o motivo |
| *não confirmada, publique de novo* | passaram 15 min sem aviso nenhum: volta para a fila com o texto já no campo — o fluxo travou no caminho |

Aviso de resposta que o CRM não encaminhou (uma automação do NichoChat que
responde as notas altas, por exemplo) também serve: a avaliação sai da fila do
CRM como respondida.

Para conferir no NichoChat: o contato "CRM Respostas Google" mostra os três
campos com os valores da última resposta enviada.

### Por que a resposta do Google é só manual

É comum o canal do cliente no NichoChat já responder sozinho as avaliações de 4
e 5 estrelas. Um segundo robô aqui sobrescreveria as respostas dele. No CRM a
fila do Google serve para o que sobra — em geral as notas de 1 a 3, que pedem
uma pessoa.

### Regras do iFood que estão no código

| Regra | Onde | Se ignorar |
|---|---|---|
| Texto entre 10 e 300 caracteres | `ifood.responder`, prompt | erro na publicação |
| Só responder avaliação `NOT_REPLIED` | `ifood.pendente`, tabela de respostas | erro 422 |
| Máximo de 50 itens por página | `ifood.MAX_PAGE_SIZE` | erro 400 |
| Sem `dateFrom` a API devolve só 7 dias | `ifood.VALIDADE` (85 dias) | perde avaliação ainda no prazo |
| `score` vem como decimal | `ifood.nota` | nota errada na tela |
| Nunca prometer cupom ou reembolso | prompt | obrigação pública não autorizada |
| Erro passageiro é tentado de novo, até o limite | `agente.py`, coluna `tentativas` (014) | avaliação fora do alcance para sempre, ou laço infinito |

A tela **não bloqueia** entrada inválida no iFood (página acima de 50, texto fora
do limite): envia assim mesmo e mostra o erro que a API devolve. É o que a
homologação do iFood exige, e o client ID do aplicativo fica visível na
Configuração para aparecer nas gravações. O agente, onde não há ninguém para ler
o erro, valida antes de enviar.

## Vindo do Domani Avaliações

| No Domani Avaliações | No CRM |
|---|---|
| Vários clientes, cada um com lojas | um cliente só; as lojas ficam no seed |
| Chave da OpenAI do cliente, visível no formulário | só no `.env` do servidor (`OPENAI_API_KEY`, `OPENAI_MODEL`); a tela não tem campo de chave nem de modelo |
| Login único do painel | usuários e permissões do CRM; cada resposta guarda quem publicou |
| `cliente_id` no corpo do webhook | não existe; vai `cliente` (`CLIENTE_NOME`) e o resto do corpo é igual |
| `link` do aviso abre o painel | abre a avaliação dentro do CRM |
| Agente dentro do processo do painel | igual: dentro do processo da API, a cada 15 minutos, desligável por `WORKER_DESLIGADO` |
| Página Política de Avaliações | aba **Política** do iFood, mesmo texto |
| Deploy por Docker, com banco próprio | usa a API, o banco e o deploy do CRM (schema `integra`) |

Assinatura, tom e webhook do painel precisam ser copiados para a Configuração
do CRM. O histórico do painel **não é migrado**: o CRM começa a registrar a
partir da primeira resposta dada por ele.

## Onde está cada coisa

```
backend/sql/013_integracoes.sql                tabelas (schema integra) e permissões
backend/sql/014_tentativas.sql                 tentativas do agente do iFood
backend/sql/017_lojas_no_servidor.sql          chave da IA e lojas só no servidor
backend/sql/018_resposta_google_nichochat.sql  status 'encaminhada'
backend/sql/019_leitura_google.sql             avaliações do Google guardadas pela leitura automática
backend/sql/020_busca_google_nichochat.sql     resultado do último disparo da busca no NichoChat
backend/sql/021_partes_google.sql              pedaços de comentário longo, até o CRM juntar
backend/sql/seeds/cliente.exemplo.sql          modelo do seed: unidades/lojas do cliente
backend/app/routers/integracoes.py     as rotas /integracoes/*
backend/app/routers/webhooks.py        POST /webhooks/nichochat/avaliacoes-google e /resposta-google
backend/app/services/integracoes/
  ifood.py          Merchant API do iFood
  google.py         OAuth e Business Profile API
  redator.py        prompts e chamada da IA
  notificar.py      webhook para o NichoChat
  nichochat.py      resposta do Google entregue ao NichoChat (campos + subfluxo)
  leitor_google.py  busca do Google pelo NichoChat (disparo a cada 29 min + o que chega)
  agente.py         o agente do iFood (o laço é ligado em app/main.py)
  store.py          config, lojas, histórico, trava do agente
frontend/src/app/(app)/integracoes/    a página
frontend/src/components/integracoes/   fila, responder, histórico, agente, configuração
```

## Conferir no banco

```sql
-- unidades e quando cada uma do Google foi lida pelo NichoChat
select l.origem, l.nome, l.cidade, l.ativo, g.lida_em
  from integra.lojas l left join integra.google_leitura g using (loja_id)
 order by l.origem, l.nome;

-- o que foi publicado, por quem
select a.origem, l.nome, a.nota, a.status, a.via, u.email, a.atualizado_em
  from integra.avaliacao_respostas a
  left join integra.lojas l on l.origem = a.origem and l.loja_id = a.loja_id
  left join app.usuarios u on u.id = a.usuario_id
 where a.status <> 'pendente'
 order by a.atualizado_em desc limit 30;

-- o agente está rodando?
select iniciado_em, lojas, encontradas, respondidas, erros
  from integra.agente_execucoes order by iniciado_em desc limit 10;

-- busca do Google pelo NichoChat: último disparo e últimas entregas
select ultimo_disparo_em, ultimo_disparo_erro from integra.agente_estado where origem = 'google';
select iniciado_em as entregue_em, encontradas as novas, respondidas as confirmadas, erros as ignoradas
  from integra.agente_execucoes where origem = 'google' order by iniciado_em desc limit 5;
select recebido_em, status, erro from integra.webhook_eventos
 where origem = 'nichochat' order by recebido_em desc limit 5;

-- conexão DIRETA com o Google, se usada (nunca selecione as colunas de token em tela compartilhada)
select conta_email, conectado_em, refresh_token is not null as conectado
  from integra.tokens where origem = 'google';
```

## Pontos de atenção

- **A credencial do iFood é do aplicativo inteiro.** Com ela, quem cadastrar o
  merchant UUID de outra casa lê as avaliações dela. Por isso loja só entra por
  SQL, no servidor.
- **Se a conexão direta com o Google for usada, o token fica em `integra.tokens`,
  sem criptografia.** A API nunca o devolve, mas quem lê o banco lê o token.
- **A `WEBHOOK_GOOGLE_KEY` é a senha da entrega.** Quem a tiver consegue pôr
  avaliação na fila do CRM. Fica no `.env` e no fluxo do NichoChat, em mais
  lugar nenhum. Cada cliente tem a sua.
- **A busca traz só avaliação nova, sem resposta.** Uma avaliação respondida
  fora do CRM (por uma automação do NichoChat, por exemplo) continua na fila
  do CRM, a menos que o NichoChat avise pela confirmação da resposta.
