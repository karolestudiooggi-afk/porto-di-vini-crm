/**
 * ============================================================================
 * CONFIGURAÇÃO DO CLIENTE — CRM Porto Di Vino
 * ============================================================================
 *
 * Gerado a partir do template CRM Domani. Tudo o que muda de um cliente para
 * outro no front-end mora aqui e no `.env` — as telas acompanham sem reescrita.
 *
 * Foco deste CRM: o DISPARADOR DE E-MAIL (módulo `campanhas`, envio pelo
 * SendPulse). Por isso só a base (Dashboard, Contatos, Usuários), E-mail,
 * Agente e Auditoria estão ligados. NPS, Parceiros e Integrações ficam
 * desligados até a Porto pedir — ligar sem as variáveis do backend mostraria
 * tela que responde erro.
 *
 * Fonte dos dados: o Domani (WhatsApp da Porto) mais as importações de
 * planilha. O Domani raramente traz e-mail; o público das campanhas vem
 * sobretudo da base do e-commerce/clube importada em Contatos (CSV/XLSX, com a
 * coluna de consentimento). Sem PDV ligado não existe compra, ticket nem
 * faturamento aqui — e o CRM não inventa nenhum deles.
 */

export const CLIENTE = {
  nome: process.env.NEXT_PUBLIC_CLIENT_NAME ?? "Porto Di Vino",

  vocab: {
    /** O que a base registra: a conversa no WhatsApp, não a compra. */
    interacao: { um: "interação", muitos: "interações" },
    /** Corte principal da base. Sem unidades, o equivalente é o canal. */
    local: { um: "canal", muitos: "canais" },
    /** Quem atende. Vazio: a base não registra executor. */
    executor: { um: "", muitos: "" },
    pessoa: { um: "contato", muitos: "contatos" },
  },

  modulos: {
    /** E-mail: templates, campanhas e disparo pelo SendPulse (routers /email/*). */
    campanhas: true,
    /** Aba "Parceiros" do E-mail. Desligada: a Porto não tem lista de parcerias. */
    parceiros: false,
    /** NPS por QR. Desligado. */
    avaliacoes: false,
    /** Rankings de clientes. O template ainda não traz a tela. */
    rankings: false,
    /** Aba do Agente IA (beta) — presente em todos os CRMs Domani. */
    agente: true,
    /** Registro de alterações manuais (GET /auditoria), só para a equipe. */
    auditoria: true,
    /** Avaliações externas. Todas desligadas neste CRM. */
    integracoes: {
      ifood: false,
      google: false,
      tripadvisor: false,
      reclameaqui: false,
    },
  },
} as const;

export type PlataformaIntegracao = keyof typeof CLIENTE.modulos.integracoes;

/** Plataformas de integração ligadas, na ordem em que aparecem acima. */
export const integracoesLigadas: PlataformaIntegracao[] =
  (Object.keys(CLIENTE.modulos.integracoes) as PlataformaIntegracao[])
    .filter((p) => CLIENTE.modulos.integracoes[p]);

/** Atalho: primeira letra maiúscula, para começar frase. */
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
