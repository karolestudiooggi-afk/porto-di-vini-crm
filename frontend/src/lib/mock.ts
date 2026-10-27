import type {
  BarItem,
  Customer,
  DonutItem,
  Kpis,
  Origem,
  UserRow,
} from "./types";

export const CASAS = [
  "Unidade Centro",
  "Unidade Norte",
] as const;

export const TAGS = [
  "VIP",
  "Aniversariante",
  "Indicação",
  "Corporativo",
  "Primeira compra",
  "Imprensa",
  "Influencer",
  "Recorrente",
];

export const ETIQUETAS = [
  "Reativar",
  "Alto valor",
  "Risco churn",
  "Embaixador",
  "Novo contato",
  "Sem retorno",
];

const NOMES = [
  "Ana Beatriz Mendes", "Carlos Eduardo Lima", "Mariana Figueiredo", "Roberta Coutinho",
  "Juliana Castro", "Bruno Tavares", "Fernanda Albuquerque", "Thiago Nogueira",
  "Patrícia Vasconcelos", "GustavoPereira", "Larissa Monteiro", "Diego Ramalho",
  "Camila Siqueira", "Vinícius Barros", "Renata Cardoso", "Felipe Andrade",
  "Beatriz Rocha", "André Luiz Moraes", "Tatiana Brandão", "Marcelo Queiroz",
  "Isabela Carvalho", "Rodrigo Sales", "Natália Furtado", "Leonardo Pacheco",
  "Vanessa Drummond", "Henrique Sampaio", "Priscila Goulart", "Eduardo Bittencourt",
  "Aline Bezerra", "Luana Maia", "Daniela Vargas", "Otávio Bastos",
  "Sofia Magalhães", "Pedro Henrique Reis", "Carolina Teixeira", "Gabriel Antunes",
  "Letícia Carneiro", "Matheus Pontes", "Bianca Lemos", "Caio Verissimo",
];

const PERFIS = [
  "Compra com frequência, prefere atendimento pelo WhatsApp.",
  "Vem em grupo e costuma reservar com antecedência.",
  "Responde bem a campanhas de e-mail.",
  "Aparece em datas especiais e aniversários.",
  "Consumo moderado, fiel à Unidade Centro.",
];

function rng(seed: number) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

function phone(r: () => number) {
  const ddd = [21, 22, 24, 11, 31, 32][Math.floor(r() * 6)];
  const a = 90000 + Math.floor(r() * 9999);
  const b = 1000 + Math.floor(r() * 8999);
  return `(${ddd}) 9${a.toString().slice(0, 4)}-${b}`;
}

function dateBack(r: () => number, maxDays: number) {
  const d = new Date(2026, 5, 20);
  d.setDate(d.getDate() - Math.floor(r() * maxDays));
  return d.toISOString();
}

function pick<T>(arr: readonly T[], r: () => number): T {
  return arr[Math.floor(r() * arr.length)];
}

function sample<T>(arr: readonly T[], n: number, r: () => number): T[] {
  const pool = [...arr];
  const out: T[] = [];
  for (let i = 0; i < n && pool.length; i++) {
    out.push(pool.splice(Math.floor(r() * pool.length), 1)[0]);
  }
  return out;
}

const ORIGENS: Origem[] = ["Domani", "zigpay", "brevo", "importacao", "whatsapp"];

function buildCustomers(): Customer[] {
  return NOMES.map((nome, i) => {
    const r = rng(i * 7 + 13);
    const visitas = Math.floor(r() * 22);
    const ticket = Math.round((40 + r() * 760) * 100) / 100;
    const origem = pick(ORIGENS, r);
    const hasBday = r() > 0.25;
    return {
      id: String(i + 1),
      nome,
      telefone: r() > 0.08 ? phone(r) : null,
      email: r() > 0.3 ? `${nome.toLowerCase().split(" ")[0]}.${i}@email.com` : null,
      cpf: r() > 0.5 ? `${100 + i}.${200 + i}.${300 + i}-0${i % 10}` : null,
      dataNascimento: hasBday ? dateBack(r, 16000) : null,
      origem,
      origens: sample(ORIGENS, 1 + Math.floor(r() * 3), r),
      casaMaisVisitada: visitas > 0 ? pick(CASAS, r) : null,
      visitas,
      ticketMedio: ticket,
      totalGasto: Math.round(ticket * Math.max(1, visitas) * 100) / 100,
      dataPrimeiraVisita: visitas > 0 ? dateBack(r, 1400) : null,
      dataUltimaVisita: visitas > 0 ? dateBack(r, 320) : null,
      dataUltimaReserva: r() > 0.45 ? dateBack(r, 200) : null,
      unidadeUltimaReserva: r() > 0.45 ? pick(CASAS, r) : null,
      pessoasUltimaReserva: r() > 0.45 ? 2 + Math.floor(r() * 10) : null,
      nps: r() > 0.4 ? Math.floor(r() * 11) : null,
      perfilConsumo: r() > 0.4 ? pick(PERFIS, r) : null,
      tags: sample(TAGS, Math.floor(r() * 3), r),
      etiquetas: sample(ETIQUETAS, Math.floor(r() * 2), r),
    };
  });
}

export const CUSTOMERS: Customer[] = buildCustomers();

export function getCustomer(id: string): Customer | undefined {
  return CUSTOMERS.find((c) => c.id === id);
}

export const KPIS: Kpis = {
  total: 48200,
  comTelefone: 43100,
  comAniversario: 16400,
  comVisitas: 9800,
  ticketMedio: 96,
  reativacao: 3150,
};

/* ----------------------------- Dashboard ----------------------------- */

export interface DashKpi {
  label: string;
  value: string;
  cur?: string;
  meta: string;
  delta?: { dir: "up" | "down"; v: string };
  tag?: string;
  dark?: boolean;
}

export const DASH_KPIS: DashKpi[] = [
  { label: "Faturamento · mês", cur: "R$", value: "1,2M", meta: "vs. dez/2025", delta: { dir: "up", v: "8%" }, dark: true },
  { label: "Pedidos", value: "12.480", meta: "vs. dez/2025", delta: { dir: "up", v: "5%" } },
  { label: "Ticket médio real", value: "96", cur: "R$", meta: "por pedido", tag: "real" },
  { label: "Base ativa", value: "11.300", meta: "de 48 mil contatos" },
];

export const FAT_POR_CASA: BarItem[] = [
  { label: "Unidade Centro", value: 0.7, percent: 100 },
  { label: "Unidade Norte", value: 0.5, percent: 71 },
];

export const ORIGEM_LEAD: BarItem[] = [
  { label: "Instagram", value: 44, percent: 100 },
  { label: "WhatsApp", value: 27, percent: 61 },
  { label: "Indicação", value: 14, percent: 32 },
  { label: "Google", value: 9, percent: 20 },
  { label: "Site / outros", value: 6, percent: 14 },
];

export const FAIXAS_TICKET: BarItem[] = [
  { label: "R$ 0 – 100", value: 38, percent: 100 },
  { label: "R$ 100 – 300", value: 31, percent: 82 },
  { label: "R$ 300 – 600", value: 19, percent: 50 },
  { label: "R$ 600+", value: 12, percent: 32 },
];

export const FAIXAS_VISITA: BarItem[] = [
  { label: "1 visita", value: 46, percent: 100 },
  { label: "2 – 3 visitas", value: 29, percent: 63 },
  { label: "4 – 6 visitas", value: 16, percent: 35 },
  { label: "7+ visitas", value: 9, percent: 20 },
];

export const POR_UNIDADE: DonutItem[] = [
  { label: "Unidade Centro", value: 6400, total: 6400, percent: 57, color: "#E56D23" },
  { label: "Unidade Norte", value: 4900, total: 4900, percent: 43, color: "#1D1D1F" },
];

export const MINI_BASE = [
  { label: "Contatos com telefone", value: "43.100", sub: "aptos para contato direto" },
  { label: "Contatos com visita", value: "9.800", sub: "já passaram por uma unidade" },
  { label: "Ticket médio", value: "96", cur: "R$", sub: "por pedido" },
  { label: "Clientes 90 dias+", value: "3.150", sub: "sem visita há 90 dias" },
];

/** Cenários da curva de venda — por unidade, com escala relativa. */
export interface CurveScenario {
  label: string;
  cap: string;
  curScale: number; // pico 2027 (em milhares de pedidos)
  prevScale: number; // pico 2026
  adsTotal: string;
  events: string[];
}

export const CURVE_SCENARIOS: Record<string, CurveScenario> = {
  todas: {
    label: "Todas as unidades",
    cap: "Pedidos acumulados · 2027 vs 2026",
    curScale: 12.48,
    prevScale: 11.9,
    adsTotal: "R$ 48k",
    events: ["Todas as campanhas", "Unidade Centro", "Unidade Norte"],
  },
  centro: {
    label: "Unidade Centro",
    cap: "Pedidos acumulados · 2027 vs 2026",
    curScale: 7.2,
    prevScale: 6.8,
    adsTotal: "R$ 28k",
    events: ["Todas as campanhas", "Dia das Mães", "Black Friday"],
  },
  norte: {
    label: "Unidade Norte",
    cap: "Pedidos acumulados · 2027 vs 2026",
    curScale: 5.3,
    prevScale: 5.1,
    adsTotal: "R$ 20k",
    events: ["Todas as campanhas", "Aniversário da unidade"],
  },
};

/* ------------------------------ Rankings ------------------------------ */

export function ranking(mode: string): Customer[] {
  const list = [...CUSTOMERS].filter((c) => c.visitas > 0);
  switch (mode) {
    case "frequencia":
      return list.sort((a, b) => b.visitas - a.visitas);
    case "valor":
      return list.sort((a, b) => b.totalGasto - a.totalGasto);
    case "reativacao":
      return list
        .filter((c) => c.dataUltimaVisita)
        .sort((a, b) => (a.dataUltimaVisita! < b.dataUltimaVisita! ? -1 : 1));
    case "ticket":
    default:
      return list.sort((a, b) => b.ticketMedio - a.ticketMedio);
  }
}

export const RANKING_MODES: Record<string, { label: string; title: string; description: string }> = {
  ticket: { label: "Maior ticket médio", title: "Maiores tickets médios", description: "Clientes que mais gastam por visita — lista pronta para campanha premium." },
  frequencia: { label: "Mais frequentes", title: "Clientes mais frequentes", description: "Quem mais aparece nas unidades." },
  valor: { label: "Maior valor total", title: "Maior valor acumulado", description: "Soma de tudo que cada cliente já consumiu." },
  reativacao: { label: "Reativação (90+ dias)", title: "Prontos para reativar", description: "Clientes valiosos sem visita recente." },
};

/* ------------------------------ Usuários ------------------------------ */

export const USERS: UserRow[] = [
  { id: "1", nome: "Admin Exemplo", email: "admin@seucliente.com.br", papel: "Superadmin", status: "Ativo", ultimoAcesso: "2026-06-24T20:10:00" },
  { id: "2", nome: "Gestão Exemplo", email: "gestao@seucliente.com.br", papel: "Administrador", status: "Ativo", ultimoAcesso: "2026-06-25T09:32:00" },
  { id: "3", nome: "Atendimento Exemplo", email: "atendimento@seucliente.com.br", papel: "Membro", status: "Ativo", ultimoAcesso: "2026-06-23T18:05:00" },
  { id: "4", nome: "Marketing Exemplo", email: "marketing@seucliente.com.br", papel: "Membro", status: "Convite pendente", ultimoAcesso: null },
  { id: "5", nome: "Financeiro Exemplo", email: "financeiro@seucliente.com.br", papel: "Membro", status: "Inativo", ultimoAcesso: "2026-02-11T11:40:00" },
];

export const CURRENT_USER = { nome: "Admin Exemplo", email: "admin@seucliente.com.br", papel: "Administrador", isStaff: true };
