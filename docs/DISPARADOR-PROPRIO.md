# Disparador próprio (HTTP) — transporte alternativo

> **No template, o envio sai pelo SMTP do provedor de campanha** (ver
> [DISPARADOR.md](DISPARADOR.md)). Este documento descreve como trocar o
> transporte pelo **disparador da Domani**, por HTTP — por exemplo, quando o
> cliente não tem conta em provedor ou enquanto ela é liberada.

## Para ativar

1. **Código** — em `app/services/sender.py`, a classe `Conexao` passa a fazer
   `POST /v1/send` no disparador em vez de abrir SMTP (classificação de erro
   abaixo).
2. **`.env`** — preencher `DISPARADOR_URL` e `DISPARADOR_API_KEY` (as variáveis
   já existem no `config.py`, sem uso enquanto o transporte é SMTP).
3. **Limites** — trocar para os do disparador:
   ```
   SMTP_LIMITE_DIA=800      # a janela que manda passa a ser o dia
   SMTP_INTERVALO_SEG=15    # ele entrega ~4/min no total
   ```
4. **Cota** — a view `email.vw_consumo` já expõe `enviados_dia` e `enviados_mes`.
   Só o `cota.py` muda de coluna; não precisa de migration.
5. **Front** — `painel-cota.tsx` e o tipo `Cota` trocam `mes` por `dia`.
6. **Schema** — `CotaOut` acompanha. Há teste amarrando os dois: se esquecer,
   a suíte quebra em vez de dar 500 em produção.

## O que NÃO esquecer

A classificação de erro HTTP é o ponto crítico — está descrita abaixo. Mapear
429 para supressão permanente, com ~4/min de teto, queimaria a base inteira em
minutos.

## O que muda no CRM

| | SMTP do provedor | Disparador próprio |
|---|---|---|
| Transporte | SMTP direto | POST `/v1/send` no disparador |
| Quem assina DKIM | provedor | disparador |
| Quem monta o MIME | CRM | **CRM** (não muda) |
| Cota | mensal, do plano | **diária** (`SMTP_LIMITE_DIA`) |
| Ritmo | 1 a cada 1,5s | **1 a cada 15s** |

O CRM continua montando o e-mail inteiro — From, List-Unsubscribe, texto + HTML,
rodapé de descadastro e pixel de abertura. O disparador recebe pronto, assina e
envia. Por isso tracking, supressão e idempotência seguem funcionando iguais.

## Configuração

```bash
cd ~/crm-portodivino
cat >> .env <<'EOF'
DISPARADOR_URL=https://disparador.estudiodomaniai.com.br
DISPARADOR_API_KEY=dsp_live_...
SMTP_LIMITE_DIA=800
EOF
sudo systemctl restart crm-portodivino-api.service
```

Sem a `DISPARADOR_API_KEY` o envio **nem começa** — falha na abertura da conexão,
em vez de errar mensagem por mensagem.

## ⚠️ Classificação de erro

Neste CRM, `SMTPRecipientsRefused` vira `ErroPermanente`, que **suprime o
endereço para sempre**. Por isso o **429 (ritmo cheio)** não pode ser mapeado
para ela: com o disparador entregando ~4 e-mails/minuto no total, o 429 é
rotina — não exceção — e a base inteira do cliente seria suprimida em poucos
minutos, por uma falha que não era de ninguém. Vale o mesmo para qualquer
recusa por cota (`554 quota exceeded` no SMTP).

| HTTP | Significado | Tratamento |
|---|---|---|
| 202 | aceito | enviado |
| **400** | destinatário inválido | **ErroPermanente** → suprime |
| 429 | ritmo cheio | ErroTemporario → volta para a fila |
| 401 / 403 / 422 | credencial, cliente não liberado, remetente errado | ErroTemporario + log de erro |
| 5xx / rede | serviço fora | ErroTemporario |

**Só o 400 suprime.** Todo o resto é problema nosso, e o endereço da pessoa está
perfeito.

## Cota: por que vira diária

O teto não é um plano comprado — é a **capacidade da infraestrutura da Domani**,
compartilhada entre todos os clientes: ~4/min, ~5.760/dia para todo mundo.

A soma das cotas diárias de todos os clientes não pode passar disso, senão forma
fila e a campanha de um atrasa a do outro:

| Clientes ativos | Cota sugerida por cliente |
|---|---|
| 7 | 800/dia |
| 15 | 380/dia |
| 30 | 190/dia |

Por isso `SMTP_LIMITE_DIA` vem do `.env`: entrando cliente novo, as cotas de
todos caem — e isso não pode exigir deploy. Com infraestrutura maior, só estes
números mudam; a integração continua igual.

## Atenção: dois módulos de envio

Existem **duas implementações** no repositório:

```
app/services/           ← ATIVA. É o que app/routers/email.py importa.
app/services/email/     ← ninguém importa. Só tests/test_email_regras.py a usa (em skip).
```

Qualquer troca de transporte vai no módulo **ativo**. Editar
`app/services/email/envio.py` não tem efeito: o disparo continua tentando SMTP.

## Testar sem enviar

`EMAIL_DRY_RUN=true` continua funcionando: a campanha percorre todo o fluxo —
reserva o lote, monta o MIME, marca "enviado" — sem chamar o disparador.

Para verificar que o disparador está no ar:

```bash
curl -s https://disparador.estudiodomaniai.com.br/healthz; echo
```
