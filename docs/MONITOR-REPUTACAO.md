# Tripadvisor e Reclame Aqui (monitor de reputação)

Módulos `integracoes.tripadvisor` e `integracoes.reclameaqui` em
`frontend/src/config/cliente.ts`. Os dois leem a mesma caixa de e-mail.

## Por que pelo e-mail

| Plataforma | API | Serve? |
|---|---|---|
| Tripadvisor | Content API: só as **5 avaliações mais recentes** de cada local, e os termos **proíbem guardar** o conteúdo | Não dá histórico, relatório nem alerta |
| Reclame Aqui | API paga, preço sob consulta | Só se o cliente contratar |

As duas, porém, **avisam a empresa por e-mail** a cada avaliação/reclamação nova.
O CRM lê esses e-mails. Responder continua sendo na própria plataforma — o link
de cada item leva direto até lá.

## Como ligar (uma vez)

1. **Caixa**: crie uma caixa só para isso, ex.: `avaliacoes@seucliente.com.br`.
   Gmail/Google Workspace: ative a verificação em 2 etapas e gere uma
   **senha de app** (a senha normal é recusada pelo IMAP).
2. **Fazer as notificações chegarem nela** (uma das duas):
   - cadastrar `avaliacoes@` como usuário no **Management Center do Tripadvisor**
     e no **painel da empresa no Reclame Aqui**, com as notificações ligadas; ou
   - na caixa que recebe hoje, criar uma **regra de encaminhamento automático**
     dos remetentes `tripadvisor` e `reclameaqui` para `avaliacoes@`.
     (Encaminhamento manual também funciona: o CRM reconhece pelo conteúdo.)
3. **Servidor** — no `.env` da raiz:
   ```
   MONITOR_IMAP_HOST=imap.gmail.com
   MONITOR_IMAP_USUARIO=avaliacoes@seucliente.com.br
   MONITOR_IMAP_SENHA=<senha de app>
   ```
   e `sudo systemctl restart crm-portodivino-api.service`.
4. Na **primeira leitura** o CRM busca os últimos 180 dias da caixa
   (`MONITOR_HISTORICO_DIAS`) — o histórico entra junto, **sem disparar aviso**.
   Depois lê a cada 10 minutos (`MONITOR_INTERVALO_MIN`).

A caixa é aberta **só para leitura** (EXAMINE): nada é marcado como lido,
movido ou apagado. Do que é novo, baixa só o cabeçalho; o e-mail inteiro só é
baixado quando o remetente/assunto parece ser das plataformas.

Antes de a caixa estar ligada dá para testar e trazer histórico pela tela:
**Integrações → Tripadvisor → Configuração → Importar e-mails** (`.eml`, `.mbox`
do Google Takeout ou `.zip` com `.eml`).

## Aviso no NichoChat

Por plataforma, em **Configuração**: o webhook do fluxo e quando avisar
(`negativos` = crise ou nota baixa/reclamação nova, padrão; `criticos`; `todos`;
`nenhum`). Só avisa o que aconteceu nas **últimas 48 h**.

Corpo enviado (POST JSON):

```json
{
  "evento": "reputacao_nova",
  "cliente": "Cliente Exemplo",
  "origem": "tripadvisor",
  "plataforma": "Tripadvisor",
  "tipo": "avaliacao",
  "unidade": "Unidade Centro",
  "nota": 2, "nota_maxima": 5,
  "nivel": "negativa",
  "critico": true,
  "palavras": ["vidro", "procon"],
  "titulo": "Demora no atendimento",
  "texto": "…",
  "autor": "Joana M.",
  "cidade": null,
  "link": "https://crmportodivino.estudiodomaniai.com.br/integracoes?origem=tripadvisor&item=123",
  "link_plataforma": "https://www.tripadvisor.com.br/ShowUserReviews-…",
  "ocorrido_em": "2026-01-10T21:14:00-03:00"
}
```

`cliente` vem de `CLIENTE_NOME`. No fluxo do NichoChat, o comum é rotear por
`critico` (crise: quem trata ocorrência) e por `nivel = negativa` (o gerente da
`unidade`).

## Palavras de crise

Lista única para as duas plataformas. A migration traz uma lista inicial; a de
cada cliente se ajusta na tela. Combinam **pelo começo da
palavra e sem acento** ("intoxica" pega "intoxicação"; "vidro" não acende em
"envidraçado"). Salvar a lista **recalcula o histórico inteiro**.

## Como a leitura funciona

`backend/app/services/integracoes/`:

- `email_bruto.py` — MIME → texto, links (com o `%XX` dos redirecionadores
  decodificado) e o `alt`/arquivo das imagens (é onde está a nota em bolhas).
  E-mail encaminhado como anexo: vale o original.
- `monitor_regras.py` — de qual plataforma é, e o leitor de cada uma: id da
  avaliação/reclamação, local do Tripadvisor (`d…`), unidade (comparada com as
  unidades cadastradas em Integrações), nota, título, texto, autor, cidade, link.
  Português e inglês.
- `monitor.py` — grava, deduplica (Message-ID; e a mesma avaliação avisada duas
  vezes vira um item só), completa com IA, avisa, lê o IMAP, monta o painel.

**IA como reserva**: quando o leitor não acha o texto, a nota ou a unidade — ou não
reconhece o e-mail —, e há chave da OpenAI (a mesma do iFood/Google), a IA lê o
mesmo e-mail. Ela **só completa campo vazio** e só é aceita se o trecho estiver
escrito no e-mail (conferido sem acento); texto inventado é descartado. O item
fica marcado `ia` (completado) ou `parcial` (faltou e não havia IA).

**O e-mail original fica guardado** (`integra.monitor_emails.bruto`). Quando
chegar o primeiro e-mail real de cada plataforma:

1. suba o `.eml` pela tela (ou espere a caixa ler);
2. confira o item — o detalhe mostra o e-mail original;
3. se algo saiu errado, ajuste a regra em `monitor_regras.py`, transforme o
   e-mail em caso de teste em `tests/amostras_monitor.py` (trocando nomes,
   contatos e unidades por dados fictícios) e use **Reler todos os e-mails** na
   Configuração.

Unidade errada no Tripadvisor se corrige no próprio item: vale para todas as
avaliações daquele local, inclusive as próximas (`integra.monitor_unidades`).

## Banco

`backend/sql/016_monitor_reputacao.sql`: `monitor_caixa` (onde parou e trava),
`monitor_emails` (cada e-mail lido, com o original), `monitor_itens`,
`monitor_config` (por plataforma), `monitor_ajustes` (palavras),
`monitor_unidades` (de-para do local do Tripadvisor).

## API

| Rota | Permissão | O quê |
|---|---|---|
| `GET /monitor` | manage | caixa, números, config, palavras |
| `GET /monitor/{origem}/painel?dias=` | manage | números, semanas, unidades, notas, palavras |
| `GET /monitor/{origem}/itens` | manage | lista com filtros |
| `GET/PATCH /monitor/itens/{id}` | manage | detalhe; tratado, observação, unidade |
| `POST /monitor/importar` | manage | `.eml`/`.mbox`/`.zip` (até 50 arquivos, 60 MB) |
| `GET /monitor/emails` | manage | e-mails não aproveitados e por quê |
| `PATCH /monitor/{origem}/config` | config | ligado, aviso, webhook |
| `PUT /monitor/palavras` | config | palavras de crise (recalcula o histórico) |
| `POST /monitor/ler` | config | lê a caixa agora |
| `POST /monitor/reprocessar` | config | relê todos os e-mails guardados |

`WORKER_DESLIGADO` desliga a leitura automática junto com o agente do iFood.
