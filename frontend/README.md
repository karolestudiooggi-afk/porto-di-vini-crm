# CRM Domani — front-end

Next.js 14 (App Router) + Tailwind, no design system Domani. Fala com a API
FastAPI do template (`docs/API.md`) e usa o Supabase só para o login.

## O que muda por cliente

Só dois lugares — as telas acompanham sem reescrita:

- **`.env`** (copiado de `.env.example`): `NEXT_PUBLIC_CLIENT_NAME`,
  `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
- **`src/config/cliente.ts`**: nome exibido, vocabulário do negócio e `modulos`
  (`campanhas`, `parceiros`, `avaliacoes`, `rankings`, `agente`, `auditoria`,
  `integracoes: { ifood, google, tripadvisor, reclameaqui }`).

Módulo desligado some do menu e a rota mostra "módulo desligado" em vez da tela.
Só ligue um módulo quando o backend do cliente tiver as variáveis dele (ver o
README da raiz). Os dois entram **no build**: mudou, rode `npm run build` de novo.

Tela que só um cliente tem: item em `src/lib/nav.ts` e rota em `src/app/(app)/`,
com um comentário dizendo de quem é — para o próximo não achar que é do template.

## O que a base tem — e o que não tem

Por padrão o **Domani é a única fonte** de dados. Sem PDV, bilheteria nem agenda
ligados, **não existe** visita, compra, ticket, faturamento nem aniversário — nem
na API, nem aqui. O `docs/API.md` é explícito: *"não existem respostas simuladas
para esses campos"*. A interface segue essa regra: nada de cartão com `R$ 0,00`
para fingir que há receita.

O que a base sabe, e o CRM mostra: identificação, canal, status da conversa,
idioma, origem, tags (Domani e manuais separadas), consentimento de e-mail e
histórico de interações.

| Rota | Fonte |
|---|---|
| `/dashboards` | `/dashboard/resumo`, `/distribuicoes`, `/atividade`, `/consumo` |
| `/clientes` | `/contatos`, `/stats`, `/filtros`, `/{id}`, `/{id}/timeline` |
| `/campanhas` | `/email/*` (módulos `campanhas` e `parceiros`) |
| `/avaliacoes`, `/avaliar/{slug}` | `/avaliacao/*` (módulo `avaliacoes`) |
| `/integracoes` | `/integracoes/*`, `/monitor/*` (módulo `integracoes`) |
| `/agente` | sem backend: tela de apresentação (módulo `agente`) |
| `/usuarios` | `/usuarios`, `/usuarios/convites` |
| `/auditoria` | `/auditoria` (módulo `auditoria`) |

## Decisões que valem saber

**Só `observacoes` é editável.** Todo o resto vem do Domani e seria sobrescrito na
sincronização seguinte. O backend recusa qualquer outro campo, então o formulário
não oferece — input que não salva é pior que campo ausente.

**A exclusão é lógica.** A ficha some das listas, do dashboard e das exportações,
mas continua no banco. Uma interação nova no Domani, ou uma importação, restaura.
O texto do diálogo diz isso; não prometa exclusão definitiva.

**Tags Domani e manuais ficam separadas na ficha.** O sync sobrescreve as
primeiras e nunca toca nas segundas — juntar as duas na tela esconderia qual
sobrevive à próxima rodada. Na lista elas aparecem unificadas (é o backend que
faz isso), o que é adequado para varredura rápida.

**Os filtros vêm de `/contatos/filtros`.** Canal, status, idioma e origem não são
listas fixas no código: saem dos dados. Valor novo no Domani aparece sem deploy.

## Rodar

```bash
cp .env.example .env    # preencher
npm install && npm run dev
```

Sem `NEXT_PUBLIC_SUPABASE_*` o login não bloqueia, e sem `NEXT_PUBLIC_API_URL`
as telas usam dados fictícios ou pedem a API (**modo demo**) — útil para
trabalhar no visual antes do backend estar disponível.

Produção: `npm ci && npm run build`, servido pelo `crm-portodivino-front.service`
(`docs/systemd/`, `next start` em `127.0.0.1:3000`). Reinicie a API antes de
refazer o build (ver `docs/DEPLOY.md`).

## Design system

Tokens em `tailwind.config.ts` e `src/app/globals.css`: laranja `#E56D23`, Sora +
Hanken Grotesk, tema claro/escuro. Fontes servidas de `public/fonts`, sem CDN.
Cor solta em hex não entra — use `bg-surface`, `text-ink`, `text-muted`,
`border-line/10`, `bg-domani-orange`.
