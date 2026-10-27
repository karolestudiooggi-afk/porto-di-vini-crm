import { supabase } from "./supabase";
import type {
  AuditoriaItem, Campanha, Convite, CampanhaStats, ContatoDetail, ContatoFiltro,
  ContatoFiltros, ContatoListItem, ContatoPatch, ContatoStats, Cota,
  DashboardAtividade, DashboardConsumo, DashboardDistribuicoes, DashboardResumo, Destinatario, DisparoIniciado,
  EmailTemplate, ImportReport, Me, Page, PreviaSegmento, ResultadoEnvio,
  ImportacaoParceiros, ListaEmail, PaginaParceiros, Parceiro, ParceiroIn, ParceirosNumeros,
  AvisoMonitor, ConfigMonitor, DetalheMonitor, EmailMonitor, ImportacaoMonitor, OrigemMonitor,
  PaginaMonitor, PainelMonitor, SituacaoMonitor,
  NpsResumoApi, ContaAvaliacaoApi,
  ConfigIntegracao, ConfigIntegracaoPatch, DetalheAvaliacao, EstadoAgente, FilaGoogle,
  FilaIfood, HistoricoAvaliacao, LojaIntegracao, Origem, ResumoIntegracao,
  SincronizacaoGoogle, SituacaoIntegracoes,
  SegmentoIn, TimelineItem, Usuario,
} from "./api-types";


const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

/** true quando NEXT_PUBLIC_API_URL está definido. */
export const isApiConfigured = Boolean(BASE);

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function token(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

type Query = Record<string, string | number | boolean | string[] | null | undefined>;

function qs(params?: Query): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function request<T>(method: string, path: string, opts: { query?: Query; body?: unknown; form?: FormData } = {}): Promise<T> {
  if (!BASE) throw new ApiError(0, "API não configurada (defina NEXT_PUBLIC_API_URL).");
  const headers: Record<string, string> = {};
  const jwt = await token();
  if (jwt) headers.Authorization = `Bearer ${jwt}`;

  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form; // o browser define o Content-Type com boundary
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  const res = await fetch(`${BASE}${path}${qs(opts.query)}`, { method, headers, body });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      const bruto = j.detail ?? j.message ?? detail;
      // Erro de validação (422) vem como lista de objetos: sem isto a tela
      // mostrava "[object Object]".
      detail = typeof bruto === "string" ? bruto
        : Array.isArray(bruto) ? bruto.map((e) => e?.msg ?? JSON.stringify(e)).join(" · ")
        : JSON.stringify(bruto);
    } catch { /* corpo não-JSON */ }
    throw new ApiError(res.status, detail);
  }
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? await res.json() : (await res.blob())) as T;
}

/** URL absoluta (para downloads diretos via <a> — export). */
export function apiUrl(path: string, query?: Query): string {
  return `${BASE}${path}${qs(query)}`;
}

export type { ContatoFiltro };

export const api = {
  usuarios: {
    me: () => request<Me>("GET", "/usuarios/me"),
    list: () => request<Usuario[]>("GET", "/usuarios"),
    /** Muda papel ou desativa. Nome e e-mail vêm do Auth e não se editam aqui. */
    patch: (id: string, body: { papel?: string; status?: string }) =>
      request<Usuario>("PATCH", `/usuarios/${id}`, { body }),

    convites: {
      list: () => request<Convite[]>("GET", "/usuarios/convites"),
      criar: (body: { email: string; papel: string }) =>
        request<Convite>("POST", "/usuarios/convites", { body }),
      cancelar: (id: number) => request<void>("DELETE", `/usuarios/convites/${id}`),
    },
  },

  auditoria: {
    list: () => request<AuditoriaItem[]>("GET", "/auditoria"),
  },

  contatos: {
    list: (f: ContatoFiltro) => request<Page<ContatoListItem>>("GET", "/contatos", { query: f as never }),
    stats: (f: ContatoFiltro) => request<ContatoStats>("GET", "/contatos/stats", { query: f as never }),
    /** Opções reais dos filtros — derivadas dos dados, não fixas no código. */
    filtros: () => request<ContatoFiltros>("GET", "/contatos/filtros"),
    detalhe: (id: number) => request<ContatoDetail>("GET", `/contatos/${id}`),
    timeline: (id: number, q: { limit?: number; offset?: number } = {}) =>
      request<Page<TimelineItem>>("GET", `/contatos/${id}/timeline`, { query: q }),
    /** Só `observacoes`: o resto é autoridade do sync do Domani. */
    patch: (id: number, body: ContatoPatch) =>
      request<ContatoDetail>("PATCH", `/contatos/${id}`, { body }),
    /** Exclusão lógica e auditada — some das listas, mas a ficha permanece. */
    remover: (id: number) => request<void>("DELETE", `/contatos/${id}`),
    /** Exportação do recorte filtrado. Volta como Blob (a rota exige o JWT). */
    exportarBlob: (f: ContatoFiltro, formato: "csv" | "xlsx") =>
      request<Blob>("GET", "/contatos/export", { query: { ...f, formato } as never }),
    importar: (arquivo: File) => {
      const form = new FormData();
      form.append("arquivo", arquivo);
      return request<ImportReport>("POST", "/contatos/import", { form });
    },
  },

  email: {
    /** Consumo do plano. Consultar ANTES de habilitar o disparo. */
    cota: () => request<Cota>("GET", "/email/cota"),

    templates: {
      /** Sem `lista`, todos; com ela, só os da aba. */
      list: (lista?: ListaEmail) =>
        request<EmailTemplate[]>("GET", "/email/templates", { query: { lista } }),
      criar: (body: { nome: string; assunto: string; html: string; design?: unknown; lista?: ListaEmail }) =>
        request<EmailTemplate>("POST", "/email/templates", { body }),
      atualizar: (id: string, body: { nome: string; assunto: string; html: string; design?: unknown }) =>
        request<EmailTemplate>("PUT", `/email/templates/${id}`, { body }),
      apagar: (id: string) => request<void>("DELETE", `/email/templates/${id}`),
    },

    /** Upload de imagem do editor. Devolve a URL pública. */
    upload: (file: File) => {
      const form = new FormData();
      form.append("arquivo", file);
      return request<{ url: string }>("POST", "/email/uploads", { form });
    },

    /** Prévia do público — devolve também quem foi barrado e por quê. */
    previa: (seg: SegmentoIn, lista: ListaEmail = "clientes") =>
      request<PreviaSegmento>("POST", "/email/segmentos/previa", { body: seg, query: { lista } }),

    campanhas: {
      /** Sem `lista` é a visão geral (todas); com ela, só as da aba. */
      list: (lista?: ListaEmail) =>
        request<Campanha[]>("GET", "/email/campanhas", { query: { lista } }),
      criar: (body: {
        nome: string; template_id: string; assunto: string;
        segmento: SegmentoIn; agendada_para?: string | null; lista?: ListaEmail;
      }) => request<Campanha>("POST", "/email/campanhas", { body }),
      relatorio: (id: string) =>
        request<{ campanha: Campanha; stats: CampanhaStats }>("GET", `/email/campanhas/${id}`),
      destinatarios: (id: string) =>
        request<Destinatario[]>("GET", `/email/campanhas/${id}/destinatarios`),
      /** Dispara o que couber na cota. Chamar de novo continua de onde parou. */
      /** Inicia o disparo. Responde na hora; o envio segue em segundo plano. */
      enviar: (id: string) =>
        request<DisparoIniciado>("POST", `/email/campanhas/${id}/enviar`),
      cancelar: (id: string) =>
        request<Campanha>("POST", `/email/campanhas/${id}/cancelar`),
    },

    /** Base da aba Parceiros — separada da base de Contatos. */
    parceiros: {
      list: (q: { busca?: string; tag?: string; situacao?: string; page?: number; page_size?: number }) =>
        request<PaginaParceiros>("GET", "/email/parceiros", { query: q }),
      numeros: () => request<ParceirosNumeros>("GET", "/email/parceiros/numeros"),
      tags: () => request<string[]>("GET", "/email/parceiros/tags"),
      criar: (body: ParceiroIn) => request<Parceiro>("POST", "/email/parceiros", { body }),
      editar: (id: number, body: Partial<ParceiroIn>) =>
        request<Parceiro>("PATCH", `/email/parceiros/${id}`, { body }),
      excluir: (id: number) => request<void>("DELETE", `/email/parceiros/${id}`),
      importar: (arquivo: File) => {
        const form = new FormData();
        form.append("arquivo", arquivo);
        return request<ImportacaoParceiros>("POST", "/email/parceiros/import", { form });
      },
    },
  },

  avaliacao: {
    /** Painel de NPS. `janela` em dias limita o período. */
    nps: (janela?: number) =>
      request<NpsResumoApi>("GET", "/avaliacao/nps", { query: { janela } }),
    /** Unidades com QR — o seed cria uma; outras entram pela tela. */
    contas: () => request<ContaAvaliacaoApi[]>("GET", "/avaliacao/contas"),
    editarConta: (slug: string, patch: {
      google_url?: string | null; webhook_url?: string | null;
      limite_promotor?: number; ativo?: boolean;
    }) => request<ContaAvaliacaoApi>("PATCH", `/avaliacao/contas/${slug}`, { body: patch }),
  },

  integracoes: {
    situacao: () => request<SituacaoIntegracoes>("GET", "/integracoes"),

    config: (o: Origem) => request<ConfigIntegracao>("GET", `/integracoes/${o}/config`),
    salvarConfig: (o: Origem, patch: ConfigIntegracaoPatch) =>
      request<ConfigIntegracao>("PATCH", `/integracoes/${o}/config`, { body: patch }),

    lojas: (o: Origem) => request<LojaIntegracao[]>("GET", `/integracoes/${o}/lojas`),
    // Sem criar/editar/excluir: as lojas são cadastradas no servidor (SQL).

    /** iFood: consulta ao vivo, loja por loja. Google: lê o que a leitura automática guardou. */
    resumo: (o: Origem) => request<ResumoIntegracao>("GET", `/integracoes/${o}/resumo`),
    /** Pede ao NichoChat a busca do Google agora. As avaliações chegam em seguida. */
    lerGoogle: () => request<{ iniciada: boolean }>("POST", "/integracoes/google/ler"),
    historico: (o: Origem, q: { loja?: string; status?: string } = {}) =>
      request<HistoricoAvaliacao[]>("GET", `/integracoes/${o}/historico`, { query: q }),

    filaIfood: (loja: string, q: { de?: string; ate?: string; tamanho?: number; pagina?: number }) =>
      request<FilaIfood>("GET", `/integracoes/ifood/lojas/${loja}/avaliacoes`, { query: q }),
    filaGoogle: (loja: string, q: { filtro?: "pendentes" | "todas"; page_token?: string | null }) =>
      request<FilaGoogle>("GET", `/integracoes/google/lojas/${loja}/avaliacoes`, { query: q }),

    detalhe: (o: Origem, loja: string, id: string) =>
      request<DetalheAvaliacao>("GET", `/integracoes/${o}/lojas/${loja}/avaliacoes/${encodeURIComponent(id)}`),
    /** Pede uma sugestão à IA. Não publica nada. */
    sugerir: (o: Origem, loja: string, id: string) =>
      request<{ texto: string }>("POST", `/integracoes/${o}/lojas/${loja}/avaliacoes/${encodeURIComponent(id)}/sugerir`),
    /** Publica. No iFood é definitivo; no Google substitui a resposta anterior. */
    responder: (o: Origem, loja: string, id: string, texto: string) =>
      /** No Google, `encaminhada`: foi para o NichoChat, que publica. */
      request<{ ok: boolean; encaminhada?: boolean }>("POST", `/integracoes/${o}/lojas/${loja}/avaliacoes/${encodeURIComponent(id)}/responder`, { body: { texto } }),

    agente: () => request<EstadoAgente>("GET", "/integracoes/ifood/agente"),
    rodarAgente: () => request<{ iniciado: boolean }>("POST", "/integracoes/ifood/agente/rodar"),

    google: {
      /** Endereço de consentimento; a tela redireciona o navegador para ele. */
      urlConexao: () => request<{ url: string }>("GET", "/integracoes/google/oauth/url"),
      desconectar: () => request<void>("POST", "/integracoes/google/desconectar"),
      sincronizar: () => request<SincronizacaoGoogle>("POST", "/integracoes/google/sincronizar"),
    },
  },

  /** Tripadvisor e Reclame Aqui, lidos pelos e-mails de notificação. */
  monitor: {
    situacao: () => request<SituacaoMonitor>("GET", "/monitor"),
    emails: () => request<EmailMonitor[]>("GET", "/monitor/emails"),
    salvarPalavras: (palavras: string[]) =>
      request<{ palavras: string[]; itens_recalculados: number }>("PUT", "/monitor/palavras", { body: { palavras } }),
    salvarConfig: (o: OrigemMonitor, patch: { ativo?: boolean; aviso?: AvisoMonitor; webhook_url?: string | null }) =>
      request<ConfigMonitor>("PATCH", `/monitor/${o}/config`, { body: patch }),
    /** Lê a caixa agora, em segundo plano. */
    ler: () => request<{ iniciado: boolean }>("POST", "/monitor/ler"),
    reprocessar: () =>
      request<{ emails: number; atualizados: number; novos: number; ignorados: number }>("POST", "/monitor/reprocessar"),
    importar: (arquivos: File[]) => {
      const form = new FormData();
      arquivos.forEach((a) => form.append("arquivos", a));
      return request<ImportacaoMonitor>("POST", "/monitor/importar", { form });
    },
    painel: (o: OrigemMonitor, dias: number) =>
      request<PainelMonitor>("GET", `/monitor/${o}/painel`, { query: { dias } }),
    itens: (o: OrigemMonitor, q: {
      tipo?: string; unidade?: string; nivel?: string; critico?: boolean; pendente?: boolean;
      busca?: string; dias?: number; page?: number; page_size?: number;
    }) => request<PaginaMonitor>("GET", `/monitor/${o}/itens`, { query: q }),
    detalhe: (id: number) => request<DetalheMonitor>("GET", `/monitor/itens/${id}`),
    marcar: (id: number, patch: { tratado?: boolean; observacao?: string | null; unidade?: string | null }) =>
      request<DetalheMonitor>("PATCH", `/monitor/itens/${id}`, { body: patch }),
  },

  dashboard: {
    resumo: () => request<DashboardResumo>("GET", "/dashboard/resumo"),
    distribuicoes: () => request<DashboardDistribuicoes>("GET", "/dashboard/distribuicoes"),
    /** Faturamento, pedidos por dia e itens mais vendidos (Alpha Code). */
    consumo: (dias = 30) =>
      request<DashboardConsumo>("GET", "/dashboard/consumo", { query: { dias } }),
    atividade: (dias = 30) =>
      request<DashboardAtividade>("GET", "/dashboard/atividade", { query: { dias } }),
  },
};
