# Disparador de e-mail — Porto Di Vino

Módulo `campanhas` em `frontend/src/config/cliente.ts` — o foco deste CRM. O
envio sai pelo **SMTP do SendPulse** (`smtp-pulse.com:587`, TLS), como no CRM da
Mamma Jamma, configurado em `CAMPANHA_SMTP_*`. O que está construído e o que
precisa estar certo fora do código para o e-mail não cair em spam.

| | Porto Di Vino |
|---|---|
| Provedor | SendPulse (SMTP) |
| Remetente | `Porto Di Vino <site@portodivino.com.br>` |
| Domínio a autenticar | `portodivino.com.br` — ver [DNS-PORTODIVINO.md](DNS-PORTODIVINO.md) |
| Aquecimento | começa em 300/dia e 150/hora (`.env.example`) |
| Público | base importada do e-commerce/clube + contatos do Domani que tenham e-mail |

## O que existe

| Peça | Onde |
|---|---|
| Schema (`email.*`) | migrations `002`, `004`, `005`, `010`–`012` |
| Regras de público (consentimento, supressão) | `app/services/segmentos.py` |
| Renderização (variáveis, tracking, descadastro) | `app/services/render.py` |
| Envio SMTP com cota e retomada | `app/services/sender.py`, `campanhas.py`, `cota.py` |
| Rotas `/email/*`, `/track/*`, `/unsubscribe` | `app/routers/email.py`, `tracking.py` |
| Telas (templates, campanhas, relatório) | `frontend/src/app/(app)/campanhas/` |
| Continuação automática | `crm-portodivino-agenda.timer` (ver abaixo) |

## Variáveis do `.env`

| Variável | Para quê |
|---|---|
| `CAMPANHA_SMTP_HOST`, `_PORT`, `_USE_TLS`, `_USER`, `_PASSWORD` | conta SMTP do provedor |
| `CAMPANHA_FROM_EMAIL` | remetente: `"Porto Di Vino <site@portodivino.com.br>"` |
| `EMAIL_DRY_RUN` | `true` (padrão) não abre conexão SMTP |
| `SMTP_LIMITE_MES`, `SMTP_LIMITE_DIA`, `SMTP_LIMITE_HORA` | as três janelas de cota (abaixo) |
| `SMTP_MARGEM`, `SMTP_INTERVALO_SEG` | folga da janela e pausa entre mensagens |
| `APP_URL` | base dos links de abertura, clique e descadastro |

O remetente também é registrado em `email.remetentes` pelo seed do cliente
(`backend/sql/seeds/cliente.sql`).

## Limites do plano — e por que eles mandam no código

Estourar o limite do provedor não é "fica mais lento": ele recusa a conexão, e a
campanha para no meio — parte do público recebe, parte não.

Por isso a cota é verificada **antes de cada mensagem**, não uma vez no começo:
outro disparo pode estar correndo em paralelo, e a janela de 60 minutos é móvel.

A contagem vem de `email.vw_consumo`, derivada de `recipients.sent_at`. Não há
contador em memória de propósito — contador desanda quando o processo cai no meio
do envio, e passa a mentir justamente quando a informação importa.

**Retomada automática.** Campanha maior que a cota fica em `enviando` e
continua na janela seguinte. Ninguém recebe duas vezes: o `status` de cada
destinatário é o controle, e o commit é por mensagem.

**Margem de segurança** (`SMTP_MARGEM`, padrão 50): o CRM nunca usa as últimas 50
vagas da janela. Protege contra envio manual ou transacional que ele não
contabiliza.

## As regras que nunca são opcionais

Aplicadas a **toda** campanha, independente do filtro (ver
`app/services/segmentos.py`):

1. **Sem e-mail não entra.**
2. **`opt_in_email = false` é recusa explícita** — nunca recebe. Quem tem `null`
   (nunca foi perguntado) entra: o cadastro na plataforma é a base do
   relacionamento. Um clique no descadastro vira supressão permanente.
3. **Supressão é definitiva** — descadastro, bounce permanente ou reclamação de
   spam saem da base de envio para sempre. Insistir em endereço morto derruba a
   reputação do domínio e leva as campanhas seguintes para o spam de todo mundo.
4. **Ficha excluída não recebe** — a exclusão é lógica; a pessoa sumiu das listas
   de propósito e não pode reaparecer numa campanha.

A prévia do segmento (`POST /email/segmentos/previa`) devolve **quantos foram
barrados e por quê**, para a tela explicar a diferença entre "300 contatos" e
"271 destinatários" em vez de deixar parecer que o sistema perdeu gente.

## Envio duplicado: quatro camadas

Uma só sempre falha em algum canto.

1. Índice único `(campaign_id, email_norm)` — o mesmo e-mail não entra duas vezes
   na campanha, nem que o segmento traga a pessoa duplicada.
2. `status` do destinatário — o loop só olha `pendente`.
3. `status` da campanha — `enviada` não dispara de novo. Reenvio legítimo é
   campanha nova.
4. **Reserva atômica do lote.** As três camadas acima não cobrem disparos
   SIMULTÂNEOS: dois processos leriam a mesma lista de pendentes antes de
   qualquer um marcar "enviado". Por isso o lote é reservado no mesmo comando que
   o seleciona (`UPDATE ... RETURNING` com `FOR UPDATE SKIP LOCKED`), passando
   para o estado `processando`. O segundo processo pula o que já foi reservado.

   Quem for reservado e não chegar a ser enviado volta para `pendente` no fim do
   disparo. Se um processo morrer antes disso, `email.liberar_reservas_orfas()`
   devolve à fila o que ficou preso há mais de uma hora — o timer chama essa
   função a cada rodada.

**Como verificar:** dispare a mesma campanha duas vezes seguidas. O relatório
deve mostrar o mesmo número de enviados, e ninguém recebe de novo.

## Entregabilidade

**`List-Unsubscribe` + `List-Unsubscribe-Post`** (RFC 8058) vão em toda mensagem.
Gmail e Outlook exigem de quem envia em volume desde 2024; sem eles a campanha
perde entregabilidade mesmo com SPF e DKIM corretos.

**Rodapé de descadastro visível.** Sem uma saída fácil, o destinatário usa o botão
"marcar como spam" — que é muito pior, porque conta contra o domínio inteiro.

**Alternativa em texto puro** antes do HTML, exigência de qualquer filtro
anti-spam sério.

## O que precisa estar certo FORA do código

Isto não é opcional e não dá para resolver programando.

O remetente é `@portodivino.com.br`, mas o login SMTP é a conta SendPulse da
Domani. **São domínios diferentes**, e é aí que a maioria dos disparos vai para
o spam. Antes do primeiro envio real:

1. **Verificar o remetente no painel do SendPulse** (SMTP > Endereços de
   remetente). Sem isso ele recusa o envio. A verificação chega por e-mail na
   própria caixa — por isso ela precisa existir.
2. **SPF e DKIM do SendPulse no DNS do `portodivino.com.br`** — não no domínio
   da conta SendPulse. DMARC já existe (`p=none`): manter. Os registros exatos e
   os cuidados (SPF que já existe, subdomínio `s.` do site) estão em
   [DNS-PORTODIVINO.md](DNS-PORTODIVINO.md).
3. **Aquecer o domínio.** O `portodivino.com.br` nunca disparou volume pelo
   SendPulse. Disparar milhares no primeiro dia é tratado como spam. Ver
   [Aquecimento da Porto](#aquecimento-da-porto), abaixo.

Sem os três, o código funciona e o e-mail não chega.

### Por que o DKIM é o que mais pesa

Desde 2024, Gmail, Outlook e Yahoo exigem de quem envia em volume que o domínio
do `From:` passe no DMARC. O DMARC passa se o SPF **ou** o DKIM passarem
alinhados com esse domínio. No SendPulse, o endereço de retorno (o que o SPF
confere) é do próprio SendPulse — então o alinhamento vem do **DKIM**, assinado
com a chave publicada em `sign._domainkey.portodivino.com.br`. Sem ele, o
DMARC falha e a campanha cai no spam (ou é recusada) mesmo com tudo certo no
código.

## Aquecimento da Porto

O `.env.example` já vem com o ritmo inicial. Suba o diário a cada 2–3 dias, só
se o relatório da última leva estiver limpo (bounce definitivo < 2%,
descadastro < 0,5%):

| Fase | `SMTP_LIMITE_DIA` | `SMTP_LIMITE_HORA` | Para quem mandar primeiro |
|---|---|---|---|
| Dias 1–3 | 300 | 150 | quem mais interage: sócios do clube, compraram nos últimos 90 dias |
| Dias 4–6 | 600 | 300 | compradores dos últimos 12 meses |
| Dias 7–10 | 1.200 | 600 | restante da base com consentimento |
| Dia 11 em diante | 2.500 | 1.250 | ritmo normal, dentro do teto do mês |

Comece pelos mais engajados de propósito: abertura e clique nas primeiras levas
é o que ensina o Gmail que o domínio é legítimo. Base antiga, nunca contactada,
fica para o fim — é de onde vem o bounce.

## Conta SendPulse compartilhada

A Porto usa a **conta SendPulse da Domani** (`ai@estudiooggi.com`), a mesma de
todos os CRMs. O que isso implica:

- **Cota do mês dividida.** Cada CRM conta só o que ele mesmo enviou. A soma do
  `SMTP_LIMITE_MES` de todos os CRMs precisa ficar abaixo do plano, com folga.
  A Porto começa com 5.000; a Mamma Jamma usa 10.000. Mudou a divisão: ajuste
  o `.env` de cada um e reinicie a API dele.
- **Limite de 2.500/h dividido.** É da conta, não do CRM. Se dois CRMs
  dispararem na mesma hora e passarem disso, o SendPulse recusa; o
  `sender.py` trata a recusa como temporária e a campanha retoma na janela
  seguinte, sem perder ninguém.
- **Problema na conta vale para todos.** Bloqueio, plano vencido ou excesso de
  reclamação de spam param o envio de todos os CRMs ao mesmo tempo. É mais um
  motivo para a Porto só sair do dry-run com o DNS autenticado e aquecendo
  devagar: um domínio novo queimando a reputação afeta a conta inteira.
- **Remetente próprio.** Cada CRM verifica o próprio remetente no painel; o da
  Porto é o `@portodivino.com.br`, com o DKIM do domínio dela.

## Antes de disparar de verdade

`EMAIL_DRY_RUN=true` é o padrão: a campanha percorre todo o fluxo — materializa o
público, renderiza, contabiliza — **sem abrir conexão SMTP**. É assim que se testa
sem gastar cota nem incomodar cliente.

Roteiro do primeiro envio real:

1. Confirme SPF/DKIM/DMARC e a verificação do remetente (acima).
2. Monte a campanha e veja a prévia do público.
3. Dispare em dry-run e confira o relatório.
4. Crie uma campanha de teste com `ids` de 2 ou 3 e-mails da equipe.
5. `EMAIL_DRY_RUN=false`, reinicie a API, dispare essa, e **abra o e-mail
   recebido**: veja o rodapé, clique no link (deve passar por `/track/click`),
   teste o descadastro.
6. Só então a campanha real.

## Permissões

- `campanhas:manage` — montar template, criar campanha, ver relatório (admin e operador)
- `campanhas:send` — **disparar** (admin; o operador recebe pela migration `009`)

Separadas de propósito: o disparo consome cota e não tem desfazer. Para um
cliente em que só o admin dispara, tire `campanhas:send` do operador em
`app.papel_permissoes`.

## Rotas

```
GET    /email/cota                              consumo do plano
GET    /email/templates                         lista
POST   /email/templates                         cria
PUT    /email/templates/{id}                    edita
DELETE /email/templates/{id}                    apaga
POST   /email/uploads                           imagem para o editor de template
POST   /email/segmentos/previa                  prévia do público + barrados
GET    /email/campanhas                         lista
POST   /email/campanhas                         cria
GET    /email/campanhas/{id}                    relatório
GET    /email/campanhas/{id}/destinatarios      quem recebeu, com motivo
POST   /email/campanhas/{id}/enviar             dispara (campanhas:send)
POST   /email/campanhas/{id}/cancelar           cancela o restante da fila
```

## Continuação automática (timer)

> **No Docker** quem faz isso é o serviço `agendador` (toda hora cheia); não
> há timer do systemd para instalar. Logs: `docker compose logs -f agendador`.

Uma campanha maior que a cota sai em levas. **A continuação é automática** —
`crm-portodivino-agenda.timer` roda de hora em hora e:

- continua campanhas em `enviando` que ainda têm destinatário pendente;
- dispara campanhas `agendada` cuja hora chegou.

Sem esse timer, uma base de 5.000 com cota horária de 2.500 receberia a primeira
leva e o resto ficaria parado até alguém lembrar de clicar de novo.

### Instalar

Os arquivos estão em `docs/systemd/crm-portodivino-agenda.service` e `crm-portodivino-agenda.timer`
(ver [DEPLOY.md](DEPLOY.md#6-systemd)):

```bash
sudo cp ~/crm-portodivino/docs/systemd/crm-portodivino-agenda.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crm-portodivino-agenda.timer
systemctl list-timers crm-portodivino-agenda.timer
```

Testar sem esperar a hora:

```bash
sudo systemctl start crm-portodivino-agenda.service
sudo journalctl -u crm-portodivino-agenda -n 30 --no-pager
```

### Por que é seguro rodar quantas vezes for

O controle de quem já recebeu está no `status` de cada destinatário, não neste
processo. Rodar duas vezes seguidas não reenvia nada: o loop só olha `pendente`.
Campanha em `rascunho` nunca é tocada — rascunho é o que ninguém mandou disparar.

## Migration 005

`backend/sql/005_reserva_lote.sql` acrescenta o estado `processando` ao
destinatário e a função de liberar reservas órfãs. **Aplicar antes de reiniciar a
API** — sem ela, o disparo falha na primeira linha (o CHECK do status recusa o
valor novo).

## Aumentar o limite mensal

O teto mensal é **comercial**, não técnico: é o que o cliente contratou com o
provedor. Para mudar, sem deploy:

```bash
cd ~/crm-portodivino
sed -i 's/^SMTP_LIMITE_MES=.*/SMTP_LIMITE_MES=25000/' .env
sudo systemctl restart crm-portodivino-api.service
```

Se a variável não existir no `.env`, vale o padrão do código (`app/config.py`).
O teto **por hora** é imposto pelo provedor — só muda se o plano dele mudar de
verdade.

## Disparo em segundo plano

O clique em "Disparar" responde **na hora**; o envio continua no servidor.

Antes de responder, a rota valida o que é previsível — campanha já enviada, sem
cota, sem ninguém na fila, envio já em andamento. Esses viram erro imediato na
tela. Se fossem descobertos só no background, a pessoa veria "envio iniciado" e
nada aconteceria, sem pista do motivo.

O relatório se atualiza sozinho a cada 8 segundos enquanto a campanha está
`enviando`, então dá para acompanhar o número subindo — ou fechar a tela e voltar
depois.

**Por que não podia ser síncrono:** com pausa entre mensagens para proteger a
reputação, 10 mil destinatários levam horas. Além de prender o navegador,
qualquer timeout de proxy derrubaria a conexão no meio — e quem estava olhando
não saberia se o envio saiu ou não.

Se o processo da API reiniciar durante um envio, a campanha fica em `enviando`
com os pendentes intactos e o `crm-portodivino-agenda.timer` retoma na hora cheia.

## As três janelas de cota

O envio é limitado por **hora**, **dia** e **mês**, e vale sempre o mais apertado.

| Janela | Variável | Para quê |
|---|---|---|
| Hora | `SMTP_LIMITE_HORA` | evitar rajada que o provedor trate como abuso |
| **Dia** | `SMTP_LIMITE_DIA` | **controlar o ritmo do aquecimento** |
| Mês | `SMTP_LIMITE_MES` | teto do plano contratado |

**Por que o diário importa.** A janela horária é MÓVEL: uma hora depois de
disparar, ela zera. Sem teto diário, dá para mandar o limite da hora repetidas
vezes e queimar a cota do mês inteiro em algumas horas — o oposto de aquecer um
domínio, onde a regra é subir o volume dia a dia. Exemplo: 50 enviados às 18h;
às 19h a janela horária já liberaria mais 50, com o mês ainda folgado.

**Ordem do bloqueio.** Quando mais de um estoura, a mensagem cita o pior: mês só
abre no ciclo seguinte, dia à meia-noite, hora em minutos. Dizer "espere uma
hora" quando na verdade acabou o mês seria falsa esperança.

### Ajustar durante o aquecimento

```bash
cd ~/crm-portodivino
sed -i 's/^SMTP_LIMITE_DIA=.*/SMTP_LIMITE_DIA=100/' .env   # dobrou o volume
sudo systemctl restart crm-portodivino-api.service
```

Se a variável não existir no `.env`, acrescente. Uma referência para o horário:
metade do diário, para o volume do dia sair espalhado em pelo menos duas horas.

## Métricas do relatório

| Métrica | O que mede | Base do percentual |
|---|---|---|
| Aberturas | quem abriu ao menos uma vez | enviados |
| Cliques | quem clicou em algum link | enviados |
| Bounce definitivo | caixa inexistente — sai da base | enviados |
| Bounce temporário | caixa cheia, servidor fora — volta à fila | enviados |
| Descadastros | pediram para sair | enviados |

**As taxas usam ENVIADOS, não o público.** Quem não recebeu não pode abrir;
dividir pelo público inflaria o denominador e faria a campanha parecer pior do
que foi — principalmente as que ainda têm gente na fila.

**Aberturas contam pessoas, não eventos.** A mesma pessoa abrindo três vezes
conta uma. Sem isso, a taxa passaria de 100%.

**Sem envio, a taxa vem nula** e a tela mostra "—". Zero afirmaria que ninguém
abriu, o que é diferente de "ainda não há o que medir".

### Quando o número exige ação

O relatório destaca em vermelho:

- **Bounce definitivo acima de 2%** — a base tem endereços velhos demais; cada
  campanha nesse estado derruba a reputação do domínio.
- **Descadastro acima de 0,5%** — o conteúdo ou a frequência incomodaram.

### Hard × soft

Exigem reações opostas, por isso são separados:

- **hard** — a caixa não existe. Suprime, senão toda campanha futura insiste no
  mesmo endereço morto.
- **soft** — falha temporária. Volta para a fila; suprimir perderia um contato
  válido que só estava com a caixa cheia.

## Filtro de exclusão por período

Na criação da campanha: *"excluir quem já recebeu nos últimos N dias"*.

Evita mandar duas campanhas seguidas para a mesma pessoa — que é como uma base se
cansa e começa a marcar como spam.

**Quem nunca recebeu entra sempre.** A regra é `NOT EXISTS`, então ausência de
registro passa.

## Transporte alternativo

Para trocar o SMTP do provedor pelo disparador HTTP da Domani, ver
[DISPARADOR-PROPRIO.md](DISPARADOR-PROPRIO.md).
