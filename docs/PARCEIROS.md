# E-mail para parceiros

A base de parceiros (empresas que a equipe comercial levantou) é **fria**: nunca
recebeu nada do cliente. Por isso ela não se mistura com a base de clientes.
Módulo `parceiros` em `frontend/src/config/cliente.ts` (depende de `campanhas`).

## O que muda na tela

**E-mail** passa a ter três abas:

| Aba | O que mostra |
|---|---|
| Visão geral | Todas as campanhas, das duas listas. As de parceiro têm o selo **PARCEIRO**. |
| Clientes | As campanhas e templates de clientes. |
| Parceiros | Números da base, campanhas de parceiros e os botões *Base de parceiros*, *Templates* e *Nova campanha*. |

Com o módulo desligado, o E-mail tem uma lista só (clientes).

- **Base de parceiros** (`/campanhas/parceiros`): importa `.csv`/`.xlsx`, busca,
  filtra por tag e situação, edita e exclui. O **e-mail é a chave**: subir a mesma
  planilha de novo atualiza em vez de duplicar. Colunas reconhecidas: empresa
  (razão social, nome fantasia…), nome/contato, e-mail (qualquer coluna com
  "e-mail" no nome), cargo, telefone, cidade, tags, observações e as colunas de
  consentimento ("aceita e-mail" = não → entra já descadastrado).
- **Templates** de cada aba são separados. O de parceiro tem a variável
  `{{empresa}}` (além de `{{nome}}` e `{{primeiro_nome}}`).
- **Nova campanha de parceiros**: toda a base ou só algumas tags, com a opção de
  excluir quem recebeu nos últimos N dias. Não aceita template de cliente.

## Regras

- **Remetente**: `CAMPANHA_FROM_EMAIL_PARCEIROS` no `.env`, ex.:
  `"Cliente Exemplo Parcerias <parcerias@seucliente.com.br>"`. Gravado na
  campanha ao criar. Registre o mesmo endereço em `email.remetentes` pelo seed
  do cliente.
- **Rodapé**: "Você recebeu este e-mail porque sua empresa está na lista de
  parceiros de <nome do cliente>" — nunca "está cadastrado", que o parceiro não
  está.
- **Descadastro**: o link do parceiro grava em `email.supressoes_lista`
  (lista `parceiros`). Ele para de receber proposta, mas se também for cliente
  continua recebendo as novidades de cliente. Apagar a ficha e importar de novo
  **não** reinscreve.
- **Bloqueio global continua valendo**: bounce, spam e descadastro de cliente
  (`email.suppressions`) também tiram o endereço da lista de parceiros — o
  domínio costuma ser o mesmo dos dois remetentes.
- **Cota**: uma só para as duas listas (mesma conta SMTP). Os limites
  `SMTP_LIMITE_*` valem para a soma.

> Se o endereço de parcerias usar o mesmo domínio do remetente de clientes
> (`contato@seucliente.com.br`), a reputação é uma só. Para isolar de verdade a
> base fria, use um subdomínio próprio (ex.: `parcerias@parceiros.seucliente.com.br`)
> com SPF/DKIM no provedor — basta trocar `CAMPANHA_FROM_EMAIL_PARCEIROS`.

## Banco

`backend/sql/015_parceiros.sql`:

- `email.templates.lista` e `email.campaigns.lista` (`clientes` | `parceiros`,
  padrão `clientes` — nada muda no que já existe). O nome não é `publico` porque
  essa coluna já existe na campanha e guarda a contagem de destinatários.
- `email.parceiros` (único por e-mail), `email.supressoes_lista`,
  `email.recipients.parceiro_id`.

O remetente de parcerias em `email.remetentes` vem do seed do cliente
(`backend/sql/seeds/cliente.sql`), não da migration.

## API

| Rota | O quê |
|---|---|
| `GET /email/campanhas?lista=` | sem filtro = visão geral |
| `GET /email/templates?lista=` | templates da aba |
| `POST /email/segmentos/previa?lista=parceiros` | prévia do público de parceiros |
| `GET/POST /email/parceiros`, `PATCH/DELETE /email/parceiros/{id}` | base |
| `GET /email/parceiros/numeros`, `/tags` | números e tags da base |
| `POST /email/parceiros/import` | planilha |
