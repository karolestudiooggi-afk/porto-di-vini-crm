# Avaliação / NPS

QR na mesa (ou no balcão), o cliente dá a nota, a casa age na hora quando a nota
é baixa. Módulo `avaliacoes` em `frontend/src/config/cliente.ts`.

## Como funciona

1. O cliente escaneia o QR e cai em `/avaliar/{slug}` — página **pública**, sem
   login, feita para o celular.
2. Dá a nota de 1 a 5, comenta e (opcionalmente) diz quem atendeu.
3. **Nota 5** leva ao Google, onde a avaliação vale para a casa.
   **Nota baixa** dispara alerta interno na hora, para alguém falar com o cliente
   enquanto ele ainda está lá.

## As duas regras que costumam confundir

**Promotor ≠ vai para o Google.** A classificação de NPS usa `limite_promotor`
(padrão 4), mas **só nota 5** é encaminhada ao Google. Um cliente que deu 4 conta
como promotor no painel e cai na tela de agradecimento. São decisões separadas de
propósito: uma mede satisfação, a outra protege a nota pública.

**Falha de webhook não atrapalha o cliente.** Se o alerta não subir, o erro é
logado e engolido — a pessoa já respondeu, e não faz sentido mostrar erro a ela
porque um sistema interno falhou.

## Unidades

Cada unidade tem um QR próprio (`avaliacao.contas`). A migration não cria
nenhuma: as contas vêm do seed do cliente (`backend/sql/seeds/cliente.sql`,
copiado de `cliente.exemplo.sql`). Para acrescentar uma depois:

```sql
insert into avaliacao.contas (slug, nome)
values ('unidade_centro', 'Unidade Centro')
on conflict (slug) do nothing;
```

O `slug` vai na URL do QR — use `crm.fn_slug('Unidade Centro')` para gerar no
mesmo padrão. O QR aponta para `https://crmportodivino.estudiodomaniai.com.br/avaliar/{slug}`.

## Configurar (tela de Avaliações)

- **Link do Google** — para onde a nota 5 é encaminhada
- **Webhook de alerta** — recebe nota baixa (NichoChat)
- **Limite de promotor** — padrão 4
- **Ativo** — unidade inativa não recebe respostas

## "Quem te atendeu"

Lista fechada, montada a partir de quem já foi citado em avaliações anteriores.
Começa vazia — e o campo nem aparece na tela — e vai se formando com o uso.

É lista em vez de campo livre porque nome digitado vem sujo ("joao", "João",
"Joao P") e o NPS por pessoa não agruparia.

## Conferir

```sql
-- respostas recentes
select nota, categoria, comentario, colaborador, created_at
  from avaliacao.respostas order by created_at desc limit 20;

-- unidades e configuração
select slug, nome, google_url is not null as tem_google,
       webhook_url is not null as tem_alerta, ativo
  from avaliacao.contas;
```

## Migration

`backend/sql/008_avaliacao_schema.sql` — aplicar antes de reiniciar a API. As
contas entram depois, pelo seed.
