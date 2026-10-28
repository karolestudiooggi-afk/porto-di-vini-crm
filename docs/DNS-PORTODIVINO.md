# DNS do portodivino.com.br — autenticação para o SendPulse

Guia para quem administra o DNS do `portodivino.com.br`. São **dois registros
novos** (SPF ajustado e DKIM) e um que já existe e fica como está (DMARC).
Nada sai do ar: caixas de e-mail, site e e-mails automáticos da loja continuam
funcionando igual.

## Por que isso é necessário

As campanhas do CRM saem pelo SendPulse com o remetente
`@portodivino.com.br`. Para o Gmail, o Outlook e o Yahoo aceitarem esse e-mail
na caixa de entrada — e não no spam —, o próprio domínio precisa declarar no
DNS que o SendPulse está autorizado a enviar em nome dele. Desde 2024 isso é
exigência para quem envia em volume: sem a autenticação, a mensagem é desviada
para o spam ou recusada, por mais que o conteúdo esteja certo.

Só o dono do domínio pode publicar esses registros. Por isso precisamos saber
onde o DNS é administrado e de alguém com acesso.

## Onde costuma estar

Todo domínio `.com.br` é registrado no **Registro.br**, mas a zona de DNS (onde
os registros moram) pode estar no próprio Registro.br ou num provedor apontado
por ele: a hospedagem do site, a Cloudflare, a Locaweb, a GoDaddy etc. No
Registro.br, em *Domínios > portodivino.com.br > DNS*, aparece qual é.

**O que já observamos** (cabeçalho de um e-mail da loja, 20/10/2026):

- os e-mails automáticos do site saem de `site@s.portodivino.com.br`, pelo
  servidor `smtp1.interneteua.net` — a hospedagem do site é a **InternetEUA**,
  que pode ser também quem administra o DNS;
- o subdomínio `s.portodivino.com.br` tem SPF autorizando esse servidor —
  **não mexer nele**;
- o domínio principal já tem um **DMARC com `p=none`** — manter.

## Os registros

Os valores do DKIM são gerados no painel do SendPulse e enviados pela Domani no
momento da configuração. O SPF é fixo.

### 1. SPF — TXT na raiz (`@`)

**Se ainda não existe** um TXT começando com `v=spf1` na raiz:

| Tipo | Nome | Valor |
|---|---|---|
| TXT | `@` (ou `portodivino.com.br`) | `v=spf1 include:mxsspf.sendpulse.com +a +mx ~all` |

**Se já existe** (por exemplo, do Google Workspace ou da hospedagem): **não crie
um segundo**. Acrescente `include:mxsspf.sendpulse.com` dentro do registro que
já está lá, antes do `~all`/`-all`. Exemplo:

```
antes:  v=spf1 include:_spf.google.com ~all
depois: v=spf1 include:_spf.google.com include:mxsspf.sendpulse.com ~all
```

Dois registros SPF no mesmo nome invalidam os dois — e aí até o e-mail do dia a
dia da equipe passa a falhar na verificação.

### 2. DKIM — TXT em `sign._domainkey`

| Tipo | Nome | Valor |
|---|---|---|
| TXT | `sign._domainkey` (em alguns painéis: `sign._domainkey.portodivino.com.br`) | `v=DKIM1; k=rsa; p=…` (chave enviada pela Domani, colada **sem aspas**) |

É o registro que mais importa: é a assinatura do DKIM que faz o DMARC passar
para o `@portodivino.com.br`.

### 3. DMARC — TXT em `_dmarc` (já existe)

Manter o registro atual (`p=none`). Se quiserem receber os relatórios
agregados, dá para acrescentar `rua=mailto:<uma caixa da Porto>` no mesmo
registro. Endurecer a política (`p=quarantine`) só depois de algumas semanas de
envio sem falhas — não é necessário para começar.

## Remetente

As campanhas saem como `Porto Di Vino <borabrindar@portodivino.com.br>`. A caixa
`borabrindar@` já existe na Porto: é para ela que vão as respostas dos clientes e o
e-mail de confirmação do SendPulse.

## Como conferir

1. Depois de publicar, a Domani clica em **Verificar registros DNS** no
   SendPulse; o status muda de "Aguardando confirmação" para "Conectado". A
   propagação pode levar até 24 horas.
2. Pelo terminal, de qualquer máquina:
   ```bash
   dig +short TXT portodivino.com.br                 # SPF com mxsspf.sendpulse.com
   dig +short TXT sign._domainkey.portodivino.com.br # v=DKIM1; k=rsa; p=…
   dig +short TXT _dmarc.portodivino.com.br          # v=DMARC1; p=none…
   ```
3. No primeiro e-mail de teste, no Gmail: *Mostrar original* deve trazer
   `SPF: PASS`, `DKIM: PASS` e `DMARC: PASS`.

## Duas formas de fazer

- **Acesso para a Domani**: um usuário com permissão de editar DNS no painel
  onde a zona está (Registro.br, hospedagem, Cloudflare…). A Domani publica e
  confere na hora.
- **A Domani manda os registros prontos** e quem já cuida do DNS publica. Leva
  uns 10 minutos para quem tem acesso.
