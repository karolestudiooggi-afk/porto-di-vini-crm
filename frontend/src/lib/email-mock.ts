import type { Customer } from "./types";
import { CUSTOMERS, RANKING_MODES, ranking, CASAS, TAGS, ETIQUETAS } from "./mock";

/* ============================================================================
 *  MOCK do módulo de E-mail / Campanhas — dados fictícios do template
 *  Substituível por chamadas ao backend (FastAPI) sem mexer nas telas.
 * ========================================================================== */

export type CampaignStatus = "rascunho" | "agendada" | "enviando" | "enviada";

export interface EmailTemplate {
  id: string;
  nome: string;
  assunto: string;
  html: string;
  design: unknown | null; // JSON do editor de blocos (re-editável)
  atualizadoEm: string; // ISO
}

export interface CampaignStats {
  enviados: number;
  recebidos: number; // entregas comprovadas (via abertura) — comprovação ao cliente
  aberturas: number;
  cliques: number;
  bounces: number;
  descadastros: number;
}

export interface EmailCampaign {
  id: string;
  nome: string;
  segmentoLabel: string; // de onde saiu o público
  templateNome: string;
  status: CampaignStatus;
  publico: number; // total de contatos
  comEmail: number; // quantos têm e-mail (só esses recebem)
  agendadaPara: string | null; // ISO
  criadaEm: string; // ISO
  stats: CampaignStats;
}

/* ----------------------------- Variáveis ----------------------------- */
/** Variáveis que o editor disponibiliza, vindas da base do CRM. */
export const TEMPLATE_VARS: { tag: string; label: string }[] = [
  { tag: "{{nome}}", label: "Nome" },
  { tag: "{{unidade_mais_visitada}}", label: "Unidade mais visitada" },
  { tag: "{{ultima_visita}}", label: "Última visita" },
  { tag: "{{ticket_medio}}", label: "Ticket médio" },
  { tag: "{{etiquetas}}", label: "Etiquetas" },
];

/* ----------------------------- Segmentos ----------------------------- */
/**
 * O público SAI da base do CRM — nunca de planilha avulsa.
 * Três origens: ranking (pronto), filtro (unidade/tag/etiqueta) e seleção manual.
 */
export type SegmentSourceKind = "ranking" | "filtro" | "selecao";

export interface SegmentSource {
  id: string;
  kind: SegmentSourceKind;
  label: string;
  hint: string;
}

export const RANKING_SEGMENTS: SegmentSource[] = Object.entries(RANKING_MODES).map(
  ([id, m]) => ({ id: `ranking:${id}`, kind: "ranking", label: m.label, hint: m.description }),
);

export const FILTRO_CASAS: string[] = [...CASAS];
export const FILTRO_TAGS: string[] = TAGS;
export const FILTRO_ETIQUETAS: string[] = ETIQUETAS;

/** Resolve o público de um segmento a partir da base (mock = CUSTOMERS). */
export function resolveSegment(opts: {
  kind: SegmentSourceKind;
  rankingMode?: string;
  casa?: string | null;
  tag?: string | null;
  etiqueta?: string | null;
  somenteComEmail?: boolean;
}): { customers: Customer[]; label: string } {
  let list: Customer[] = [];
  let label = "Base completa";

  if (opts.kind === "ranking" && opts.rankingMode) {
    list = ranking(opts.rankingMode);
    label = `Ranking · ${RANKING_MODES[opts.rankingMode]?.label ?? opts.rankingMode}`;
  } else {
    list = [...CUSTOMERS];
    const partes: string[] = [];
    if (opts.casa) { list = list.filter((c) => c.casaMaisVisitada === opts.casa); partes.push(opts.casa); }
    if (opts.tag) { list = list.filter((c) => c.tags.includes(opts.tag!)); partes.push(`#${opts.tag}`); }
    if (opts.etiqueta) { list = list.filter((c) => c.etiquetas.includes(opts.etiqueta!)); partes.push(opts.etiqueta); }
    label = partes.length ? `Filtro · ${partes.join(" · ")}` : "Base completa";
  }

  if (opts.somenteComEmail) list = list.filter((c) => !!c.email);
  return { customers: list, label };
}

/** Prévia de um segmento: total e quantos têm e-mail (só esses recebem). */
export function segmentPreview(opts: Parameters<typeof resolveSegment>[0]): {
  total: number;
  comEmail: number;
  sample: Customer[];
  label: string;
} {
  const { customers, label } = resolveSegment({ ...opts, somenteComEmail: false });
  const comEmail = customers.filter((c) => !!c.email).length;
  return { total: customers.length, comEmail, sample: customers.slice(0, 6), label };
}

/* ----------------------------- Templates ----------------------------- */
const HTML_BOAS_VINDAS = `<div style="font-family:Arial,sans-serif;color:#1D1D1F">
  <h2 style="color:#E56D23">Olá, {{nome}}!</h2>
  <p>Que saudade de te ver na {{unidade_mais_visitada}}. Preparamos novidades pra você.</p>
  <p><a href="https://seucliente.com.br" style="color:#E56D23">Ver as novidades</a></p>
</div>`;

export const TEMPLATES: EmailTemplate[] = [
  { id: "t1", nome: "Boas-vindas", assunto: "Novidades da {{unidade_mais_visitada}}", html: HTML_BOAS_VINDAS, design: null, atualizadoEm: "2026-06-22T14:00:00" },
  { id: "t2", nome: "Reativação 90 dias", assunto: "{{nome}}, sentimos sua falta", html: HTML_BOAS_VINDAS, design: null, atualizadoEm: "2026-06-20T10:30:00" },
  { id: "t3", nome: "Lista VIP — pré-venda", assunto: "Sua pré-venda exclusiva", html: HTML_BOAS_VINDAS, design: null, atualizadoEm: "2026-06-18T16:45:00" },
];

/* ----------------------------- Campanhas ----------------------------- */
export const CAMPAIGNS: EmailCampaign[] = [
  {
    id: "c1", nome: "Pré-venda VIP", segmentoLabel: "Ranking · Maior ticket médio",
    templateNome: "Lista VIP — pré-venda", status: "enviada", publico: 4200, comEmail: 3180,
    agendadaPara: null, criadaEm: "2026-06-21T09:00:00",
    stats: { enviados: 3180, recebidos: 2890, aberturas: 1422, cliques: 388, bounces: 41, descadastros: 12 },
  },
  {
    id: "c2", nome: "Reativação inverno", segmentoLabel: "Ranking · Reativação (90+ dias)",
    templateNome: "Reativação 90 dias", status: "enviando", publico: 12760, comEmail: 8910,
    agendadaPara: null, criadaEm: "2026-06-24T11:20:00",
    stats: { enviados: 5200, recebidos: 4760, aberturas: 1980, cliques: 410, bounces: 73, descadastros: 22 },
  },
  {
    id: "c3", nome: "Aniversariantes de julho", segmentoLabel: "Filtro · Aniversariante",
    templateNome: "Boas-vindas", status: "agendada", publico: 1840, comEmail: 1290,
    agendadaPara: "2026-07-01T09:00:00", criadaEm: "2026-06-25T15:00:00",
    stats: { enviados: 0, recebidos: 0, aberturas: 0, cliques: 0, bounces: 0, descadastros: 0 },
  },
  {
    id: "c4", nome: "Aniversário da unidade — save the date", segmentoLabel: "Filtro · Unidade Norte",
    templateNome: "Boas-vindas", status: "rascunho", publico: 4900, comEmail: 3200,
    agendadaPara: null, criadaEm: "2026-06-25T17:10:00",
    stats: { enviados: 0, recebidos: 0, aberturas: 0, cliques: 0, bounces: 0, descadastros: 0 },
  },
];

export function getCampaign(id: string): EmailCampaign | undefined {
  return CAMPAIGNS.find((c) => c.id === id);
}

export const CAMPAIGN_STATUS_LABEL: Record<CampaignStatus, string> = {
  rascunho: "Rascunho",
  agendada: "Agendada",
  enviando: "Enviando",
  enviada: "Enviada",
};

/* -------------------- Seleção manual (Clientes → Campanha) -------------------- */
/**
 * Ponte entre a tela de Clientes e o público "Seleção manual" da campanha.
 * Guarda um resumo da seleção (não os IDs), pra funcionar com os dados reais
 * da API mesmo com o módulo de Campanhas ainda em mock.
 */
const MANUAL_KEY = "domani-campanha-selecao";

export interface ManualSelection {
  total: number;
  comEmail: number;
  sampleNames: string[];
  ids?: number[]; // ids reais dos contatos marcados (para o segmento kind='selecao')
}

export function getManualSelection(): ManualSelection | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(MANUAL_KEY);
    return raw ? (JSON.parse(raw) as ManualSelection) : null;
  } catch {
    return null;
  }
}

export function setManualSelection(sel: ManualSelection): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(MANUAL_KEY, JSON.stringify(sel));
  } catch {
    /* ignora */
  }
}

export function clearManualSelection(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(MANUAL_KEY);
  } catch {
    /* ignora */
  }
}

/** Ids reais dos contatos marcados (para o segmento kind='selecao'). */
export function getManualIds(): number[] {
  return getManualSelection()?.ids ?? [];
}
