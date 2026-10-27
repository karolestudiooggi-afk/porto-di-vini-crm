/**
 * Contrato da API — espelho dos schemas Pydantic do backend
 * (`backend/app/schemas/`). Mantenha os nomes em snake_case iguais aos de lá: o
 * front não renomeia campo, senão a próxima mudança no backend passa despercebida.
 *
 * O que NÃO existe aqui, e é proposital: visita, compra, ticket, faturamento,
 * aniversário. O Domani é a única fonte ativa e não fornece nada disso. O
 * `docs/API.md` é explícito: "não existem respostas simuladas para esses campos".
 */

export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface CountByValue {
  valor: string;
  total: number;
}

/* --------------------------------- Sessão --------------------------------- */

export interface Me {
  id: string;
  email: string;
  papel: string;
  permissoes: string[];
}

export interface Usuario {
  id: string;
  nome: string | null;
  email: string;
  papel: string;
  status: string;
  ultimo_acesso: string | null;
}

export interface AuditoriaItem {
  id: number;
  usuario_id: string | null;
  acao: string;
  recurso: string;
  detalhe: Record<string, unknown> | null;
  created_at: string;
}

/* -------------------------------- Contatos -------------------------------- */

export interface ContatoListItem {
  id: number;
  nome: string | null;
  telefone: string | null;
  email: string | null;
  canal: string | null;
  status: string | null;
  origem: string | null;
  /** Tags Domani + manuais, já unificadas pelo backend. */
  tags: string[];
  etiquetas: string[];
  last_interaction: string | null;
  url_foto_perfil: string | null;
}

/** A ficha completa estende a linha da lista (é assim no backend também). */
export interface ContatoDetail extends ContatoListItem {
  telefone_norm: string | null;
  email_norm: string | null;
  user_ns: string | null;
  domani_user_id: string | null;
  origens: string[];
  /** Separadas de propósito: o sync sobrescreve as Domani, nunca as manuais. */
  tags_domani: string[];
  tags_manuais: string[];
  primeiro_nome: string | null;
  sobrenome: string | null;
  genero: string | null;
  locale: string | null;
  idioma: string | null;
  subscribed: string | null;
  last_message_at: string | null;
  last_message_type: string | null;
  opt_in_email: boolean | null;
  opted_in_email: boolean | null;
  opted_in_through: string | null;
  /** Único campo editável: o sync não toca nele. */
  observacoes: string | null;
  domani_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContatoStats {
  total: number;
  com_telefone: number;
  com_email: number;
  com_interacao: number;
  com_opt_in_email: number;
}

/** Opções reais dos filtros, derivadas dos dados (GET /contatos/filtros). */
export interface ContatoFiltros {
  canais: string[];
  status: string[];
  origens: string[];
  idiomas: string[];
  tags: string[];
  etiquetas: string[];
}

export interface ContatoPatch {
  observacoes?: string | null;
}

export interface TimelineItem {
  quando: string;
  fonte: string;
  tipo: string;
  descricao: string;
}

export interface ImportReport {
  total_linhas: number;
  criados: number;
  atualizados: number;
  /** Fichas que estavam excluídas logicamente e voltaram pela importação. */
  restaurados: number;
  ignorados: number;
  erros: string[];
}

export interface ContatoFiltro {
  busca?: string;
  ordenar?: string;
  canal?: string;
  status?: string;
  idioma?: string;
  origem?: string;
  tags?: string[];
  etiquetas?: string[];
  com_email?: boolean;
  com_telefone?: boolean;
  /** Recebe campanha? Usa a mesma regra do disparo: tem e-mail, não recusou e
   *  não está na lista de descadastro. */
  recebe_email?: boolean;
  /** Já recebeu alguma campanha? Para montar o próximo envio sem repetir quem
   *  já foi alcançado. Conta só o que saiu de fato. */
  ja_recebeu?: boolean;
  limit?: number;
  offset?: number;
}

/* -------------------------------- Dashboard ------------------------------- */

export interface ConsumoPonto {
  data: string;
  pedidos: number;
  faturamento: string | null;
}

export interface ItemVendido {
  nome: string;
  quantidade: string | null;
  faturamento: string | null;
}

export interface DashboardConsumo {
  dias: number;
  serie: ConsumoPonto[];
  itens: ItemVendido[];
}

export interface DashboardResumo {
  total_contatos: number;
  contatos_com_telefone: number;
  contatos_com_email: number;
  contatos_com_interacao: number;
  contatos_com_opt_in_email: number;
  interacoes_ultimos_30_dias: number;
  domani_ultima_sincronizacao: string | null;
  /** Quais fontes alimentam a base — cresce quando um PDV é ligado. */
  fontes_ativas: string[];

  /** Consumo (Alpha Code). Nulo enquanto o PDV não enviar nada: null é ausência
   *  de dado, e zero afirmaria que não houve faturamento. */
  pedidos_total: number;
  pedidos_30_dias: number;
  faturamento_total: string | null;
  faturamento_30_dias: string | null;
  ticket_medio: string | null;
  clientes_com_pedido: number;
  ultimo_pedido: string | null;
}

export interface DashboardDistribuicoes {
  por_canal: CountByValue[];
  por_status: CountByValue[];
  por_origem: CountByValue[];
  por_idioma: CountByValue[];
}

export interface AtividadePonto {
  data: string;
  total: number;
}

export interface DashboardAtividade {
  dias: number;
  serie: AtividadePonto[];
}

/* --------------------------------- E-mail --------------------------------- */

export interface EmailTemplateApi {
  id: string;
  nome: string;
  assunto: string;
  html: string;
  design: Record<string, unknown> | null;
  updated_at: string;
}

export interface SegmentoInApi {
  kind: "filtro" | "selecao";
  canal?: string;
  status?: string;
  idioma?: string;
  origem?: string;
  tags?: string[];
  etiquetas?: string[];
  interagiu_dias?: number;
  /** Exclui quem recebeu campanha nos últimos N dias. Quem nunca recebeu entra. */
  sem_email_dias?: number;
  ids?: number[];
}

export interface SegmentoPreviewApi {
  /** Já é o número REAL de envios: as guardas são aplicadas antes de contar. */
  total: number;
  label: string;
  amostra: { id: number; nome: string | null; email: string }[];
  /** Explica a diferença para o filtro cru — sem isso parece que sumiu gente. */
  excluidos: { sem_email: number; recusaram: number; suprimidos: number };
}

export interface CampanhaStatsApi {
  enviados: number;
  falhas: number;
  suprimidos: number;
  pendentes: number;
  aberturas: number;
  cliques: number;
  descadastros: number;
}

export interface CampanhaApi {
  id: string;
  nome: string;
  assunto: string;
  template_id: string | null;
  template_nome: string | null;
  segmento_label: string | null;
  remetente: string | null;
  status: string;
  publico: number;
  agendada_para: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  ultimo_erro: string | null;
  stats: CampanhaStatsApi;
}

export interface DestinatarioApi {
  id: string;
  email: string;
  nome: string | null;
  status: string;
  erro: string | null;
  sent_at: string | null;
}

export interface EnvioResultadoApi {
  enviados: number;
  falhas: number;
  suprimidos: number;
  /** > 0 significa que a cota da hora acabou: chamar de novo continua de onde parou. */
  restantes: number;
  concluida: boolean;
  dry_run: boolean;
}

/** Consumo do plano do provedor. A tela mostra antes de habilitar o disparo. */
export interface CotaApi {
  disponivel: number;
  enviados_hora: number;
  limite_hora: number;
  enviados_mes: number;
  limite_mes: number;
  bloqueio: string | null;
}

export interface RemetenteApi {
  email: string;
  nome: string;
  padrao: boolean;
  ativo: boolean;
}

export interface SupressaoApi {
  email: string;
  motivo: string;
  detalhe: string | null;
  created_at: string;
}

/* ------------------------------ E-mail ------------------------------------ */

/** Cada aba do e-mail. "clientes" é a base de Contatos; "parceiros" é a base de
 *  parceiros, com remetente próprio (parcerias@). */
export type ListaEmail = "clientes" | "parceiros";

export interface EmailTemplate {
  id: string;
  nome: string;
  assunto: string;
  html: string;
  design: Record<string, unknown> | null;
  lista: ListaEmail;
  created_at: string;
  updated_at: string;
}

/** Filtros do público. As regras de consentimento e supressão são sempre
 *  aplicadas pelo backend e NÃO são parâmetro. */
export interface SegmentoIn {
  canal?: string;
  status?: string;
  idioma?: string;
  origem?: string;
  tags?: string[];
  etiquetas?: string[];
  interagiu_dias?: number;
  /** Exclui quem recebeu campanha nos últimos N dias. Quem nunca recebeu entra. */
  sem_email_dias?: number;
  ids?: number[];
}

export interface PreviaSegmento {
  total: number;
  com_email: number;
  label: string;
  amostra: { id: number; nome: string | null; email: string | null }[];
  /** Quem o filtro pegaria mas as regras barraram — a tela explica a diferença. */
  excluidos: {
    sem_email: number;
    recusou: number;
    excluido: number;
    suprimido: number;
  };
}

export interface CampanhaStats {
  enviados: number;
  publico: number;
  pendentes: number;
  /** Reservados por um disparo em curso. > 0 significa "tem processo rodando". */
  processando: number;
  suprimidos: number;
  falhas: number;
  aberturas: number;
  cliques: number;
  /** Caixa inexistente — definitivo, o endereço sai da base. */
  bounce_hard: number;
  /** Falha temporária (caixa cheia, servidor fora) — volta para a fila. */
  bounce_soft: number;
  descadastros: number;

  /** Taxas sobre ENVIADOS. Nulas sem envio: a tela mostra "—" em vez de 0%,
   *  que afirmaria que ninguém abriu. */
  taxa_abertura: string | null;
  taxa_clique: string | null;
  taxa_bounce_hard: string | null;
  taxa_bounce_soft: string | null;
  taxa_descadastro: string | null;
}

export interface Campanha {
  id: string;
  nome: string;
  assunto: string;
  status: "rascunho" | "agendada" | "enviando" | "enviada" | "falhou" | "cancelada";
  /** De qual aba é. A visão geral mostra as duas e marca as de parceiro. */
  lista: ListaEmail;
  /** Por onde sai ("Nome <email>"), gravado ao criar. */
  remetente: string | null;
  segmento_label: string | null;
  template_nome: string | null;
  publico: number;
  com_email: number;
  enviados: number;
  agendada_para: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  stats?: CampanhaStats;
}

/** Resposta do disparo. O envio roda em segundo plano, então isto diz o que foi
 *  colocado em marcha — não o que já saiu. O progresso vem do relatório. */
export interface DisparoIniciado {
  iniciado: boolean;
  /** Quantos estão na fila desta campanha agora. */
  na_fila: number;
  /** Quantos cabem na janela de cota atual. O resto sai quando ela abrir. */
  cabe_agora: number;
  /** true = EMAIL_DRY_RUN ligado; nada sai de verdade. */
  simulado: boolean;
}

export interface ResultadoEnvio {
  enviados: number;
  falhas_temporarias: number;
  suprimidos: number;
  restantes: number;
  concluida: boolean;
  /** true = EMAIL_DRY_RUN ligado; nada saiu de verdade. */
  simulado: boolean;
  aviso: string | null;
}

/** Consumo do plano do provedor. Com o disparador próprio a janela vira o dia
 *  (ver docs/DISPARADOR-PROPRIO.md). */
export interface Cota {
  enviados_hora: number;
  /** Enviados HOJE. Durante o aquecimento é a janela que manda. */
  enviados_dia: number;
  enviados_mes: number;
  limite_hora: number;
  limite_dia: number;
  limite_mes: number;
  resta_hora: number;
  resta_dia: number;
  resta_mes: number;
  disponivel: number;
  bloqueio: "hora" | "dia" | "mes" | null;
}

export interface Destinatario {
  id: string;
  email: string;
  nome: string | null;
  status: "pendente" | "enviado" | "falhou" | "suprimido";
  erro: string | null;
  sent_at: string | null;
  aberturas: number;
  cliques: number;
  /** Caixa inexistente — definitivo, o endereço sai da base. */
  bounce_hard: number;
  /** Falha temporária (caixa cheia, servidor fora) — volta para a fila. */
  bounce_soft: number;
  descadastros: number;

  /** Taxas sobre ENVIADOS. Nulas sem envio: a tela mostra "—" em vez de 0%,
   *  que afirmaria que ninguém abriu. */
  taxa_abertura: string | null;
  taxa_clique: string | null;
  taxa_bounce_hard: string | null;
  taxa_bounce_soft: string | null;
  taxa_descadastro: string | null;
}

export interface Convite {
  id: number;
  email: string;
  papel: string;
  status: string;
  created_at: string;
  expira_em: string;
}


/* ----------------------------- Avaliação / NPS ---------------------------- */

export interface ContaAvaliacaoApi {
  slug: string;
  nome: string;
  google_url: string | null;
  webhook_url: string | null;
  limite_promotor: number;
  ativo: boolean;
}

export interface UnidadeNpsApi {
  slug: string;
  nome: string;
  nps: number;
  total: number;
  promotores: number;
  neutros: number;
  detratores: number;
}

export interface RespostaAvaliacaoApi {
  id: string;
  slug: string;
  nota: number;
  categoria: string;
  comentario: string;
  nome: string | null;
  whatsapp: string | null;
  created_at: string;
}

export interface NpsResumoApi {
  nps: number;
  total: number;
  promotores: number;
  neutros: number;
  detratores: number;
  por_unidade: UnidadeNpsApi[];
  ultimas: RespostaAvaliacaoApi[];
}


/* ------------------------------- Integrações ------------------------------ */

export type Origem = "ifood" | "google";

/** Estado de cada integração — GET /integracoes. */
export interface SituacaoIntegracoes {
  ifood: {
    /** IFOOD_CLIENT_ID e IFOOD_CLIENT_SECRET presentes no .env. */
    configurado: boolean;
    client_id: string | null;
    ativo: boolean;
    modo: "manual" | "automatico";
    lojas: number;
    /** O agente roda dentro da API. False = ela subiu com WORKER_DESLIGADO. */
    agente_agendado: boolean;
  };
  google: {
    /** O caminho de verdade: as avaliações chegam e as respostas saem pelo NichoChat. */
    nichochat?: LigacaoNichoChat;
    /** Conexão DIRETA com o Google (opcional): GOOGLE_CLIENT_ID e _SECRET no .env. */
    configurado: boolean;
    /** Um admin já passou pelo "Conectar Google". */
    conectado: boolean;
    conta_email: string | null;
    conectado_em: string | null;
    lojas: number;
    /** Unidades ativas que a conta conectada ainda não vinculou. */
    lojas_sem_conta: number;
    /** O endereço que precisa estar cadastrado no Google Cloud. */
    callback_url: string;
  };
  /** Chave e modelo da IA ficam só no .env do servidor; aqui só "tem ou não". */
  ia: { configurada: boolean; modelo: string };
}

export interface LigacaoNichoChat {
  /** DOMANI_API_URL e DOMANI_API_KEY no .env: o CRM consegue disparar os subfluxos. */
  api_configurada: boolean;
  /** WEBHOOK_GOOGLE_KEY no .env: o CRM aceita o que o NichoChat entrega. */
  entrega_configurada: boolean;
  /** Contato do NichoChat em que o CRM dispara a busca (definido no servidor). */
  contato_user_id: string;
  /** Contato em que o CRM grava e dispara a resposta. Ausente em API antiga. */
  contato_resposta_user_id?: string;
  subfluxo_busca: string;
  subfluxo_resposta: string;
  intervalo_min: number;
  /** False = a API subiu com WORKER_DESLIGADO. */
  busca_agendada: boolean;
  ultimo_disparo_em: string | null;
  ultimo_disparo_erro: string | null;
  ultima_entrega_em: string | null;
  url_entrega: string;
  url_confirmacao: string;
}

export interface ConfigIntegracao {
  origem: Origem;
  ativo: boolean;
  modo: "manual" | "automatico";
  tom: string | null;
  assinatura: string | null;
  /** Vazio = prompt padrão do sistema (ver `prompt_padrao`). */
  prompt: string | null;
  nota_minima: number;
  webhook_url: string | null;
  /** Anotações internas; não entram em lugar nenhum da resposta. */
  observacoes: string | null;
  atualizado_em: string | null;
  prompt_padrao: string;
}

/** Chave e modelo da IA não existem aqui de propósito: ficam só no servidor. */
export type ConfigIntegracaoPatch = Partial<Pick<ConfigIntegracao,
  "ativo" | "modo" | "tom" | "assinatura" | "prompt" | "nota_minima" | "webhook_url"
  | "observacoes">>;

/** Unidade: merchant no iFood, location no Google. */
export interface LojaIntegracao {
  origem: Origem;
  loja_id: string;
  nome: string;
  cidade: string | null;
  ativo: boolean;
  assinatura: string | null;
  /** Só Google, conexão direta (opcional): a conta dona da unidade. */
  conta_id: string | null;
  /** Só Google: última leitura da unidade pelo NichoChat. Nulo = ainda não chegou. */
  lida_em?: string | null;
  criado_em: string;
}

export interface ReplicaAvaliacao {
  texto: string;
  de: string;
  criada_em: string | null;
}

/** O que o CRM registrou sobre uma avaliação (integra.avaliacao_respostas). */
export interface RegistroAvaliacao {
  review_id: string;
  /** `encaminhada`: Google — entregue ao NichoChat, ainda não vista no Google. */
  status: "pendente" | "enviada" | "encaminhada" | "ignorada" | "erro";
  resposta: string | null;
  erro: string | null;
  via: "manual" | "agente" | null;
  atualizado_em: string;
}

/**
 * Avaliação no formato comum às duas plataformas.
 *
 * Os campos de prazo só existem no iFood (5 dias para responder); no Google vêm
 * nulos. `autor` é o inverso: o iFood não identifica quem avaliou.
 */
export interface AvaliacaoExterna {
  id: string;
  nota: number;
  score: number | null;
  comentario: string;
  autor: string | null;
  criada_em: string | null;
  atualizada_em: string | null;
  /** Status cru do iFood (NOT_REPLIED, REPLIED…). Nulo no Google. */
  status: string | null;
  pendente: boolean;
  /** Considera também o registro do CRM: o iFood demora a propagar o status. */
  respondida: boolean;
  respostas: ReplicaAvaliacao[];
  prazo_seg: number | null;
  prazo_perc: number | null;
  urgencia: "" | "quente" | "morno" | "frio";
  pedido: string | null;
  campos: Record<string, string | boolean | null>;
  registro: RegistroAvaliacao | null;
  /**
   * Só no Google, quando a resposta foi entregue ao NichoChat: `aguardando`
   * (ainda no prazo de publicar) ou `sem_confirmacao` (passou o prazo e o texto
   * enviado não está no Google). Nulo no resto.
   */
  encaminhamento: "aguardando" | "publicada" | "sem_confirmacao" | null;
}

export interface FilaIfood {
  loja: LojaIntegracao;
  filtro: { de: string; ate: string; tamanho: number; pagina: number };
  pagina: { page: number; size: number; total: number; page_count: number };
  avaliacoes: AvaliacaoExterna[];
  max_por_pagina: number;
  /** Erro da plataforma, como veio. A tela mostra e continua de pé. */
  erro: string | null;
}

export interface FilaGoogle {
  loja: LojaIntegracao;
  filtro: string;
  media: number | null;
  total: number;
  avaliacoes: AvaliacaoExterna[];
  /** Token da próxima página; nulo quando acabou. */
  proxima: string | null;
  /** Quantas avaliações desta unidade a leitura automática já guardou. */
  varridas: number;
  /** Última leitura automática bem-sucedida desta unidade. */
  lida_em?: string | null;
  erro: string | null;
}

export interface DetalheAvaliacao {
  loja: LojaIntegracao;
  review_id: string;
  avaliacao: AvaliacaoExterna | null;
  /** As que ainda esperam resposta nesta loja — a coluna lateral. */
  fila: AvaliacaoExterna[];
  erro: string | null;
}

export interface LinhaResumoIntegracao {
  loja_id: string;
  nome: string;
  cidade: string | null;
  pendentes: number | null;
  media: number | null;
  total: number | null;
  /** O número é "pelo menos" (não contou tudo). Hoje sempre false: o Google vem do banco. */
  parcial: boolean;
  erro: string | null;
}

export interface ResumoIntegracao {
  respondidas_hoje: number;
  respondidas_7d: number;
  erros_7d: number;
  lojas: LinhaResumoIntegracao[];
  erro: string | null;
  /**
   * iFood: a passada mais recente do agente. Google: a leitura automática mais
   * recente (`encontradas` = avaliações novas; `respondidas` = respostas
   * confirmadas no Google).
   */
  ultima_execucao: ExecucaoAgente | null;
  /** Só Google: a busca no NichoChat que alimenta a fila. */
  leitura?: {
    intervalo_min: number;
    lendo: boolean;
    agendada: boolean;
    /** Último pedido de busca ao NichoChat (as avaliações chegam logo depois). */
    ultimo_disparo_em?: string | null;
  };
}

export interface HistoricoAvaliacao {
  review_id: string;
  loja_id: string;
  loja: string;
  nota: number | null;
  comentario: string | null;
  autor: string | null;
  resposta: string | null;
  status: "enviada" | "encaminhada" | "ignorada" | "erro";
  erro: string | null;
  via: "manual" | "agente" | null;
  usuario: string | null;
  atualizado_em: string;
}

export interface ExecucaoAgente {
  iniciado_em: string;
  lojas: number;
  encontradas: number;
  respondidas: number;
  erros: number;
  duracao_ms: number;
}

export interface EstadoAgente {
  rodando: boolean;
  /** O laço de 15 em 15 minutos está ligado nesta API. */
  agendado: boolean;
  intervalo_min: number;
  execucoes: ExecucaoAgente[];
}

export interface UnidadeGoogleAchada {
  loja_id: string;
  conta_id: string;
  conta_nome: string | null;
  nome: string;
  cidade: string | null;
  cadastrada: boolean;
}

export interface SincronizacaoGoogle {
  vinculadas: number;
  achadas: UnidadeGoogleAchada[];
  /** Cadastradas no CRM mas invisíveis para a conta conectada. */
  nao_encontradas: string[];
}


/* ----------------------------- Parceiros ---------------------------------- */

/** recebe | descadastrou (saiu da lista de parceiros) | bloqueado (bounce,
 *  spam ou descadastro como cliente — vale para o endereço inteiro). */
export type SituacaoParceiro = "recebe" | "descadastrou" | "bloqueado";

export interface Parceiro {
  id: number;
  nome: string | null;
  empresa: string | null;
  email: string;
  telefone: string | null;
  cargo: string | null;
  cidade: string | null;
  tags: string[];
  observacoes: string | null;
  origem: string | null;
  situacao: SituacaoParceiro;
  ultimo_envio: string | null;
  created_at: string;
  updated_at: string;
}

export interface ParceiroIn {
  email: string;
  nome?: string | null;
  empresa?: string | null;
  telefone?: string | null;
  cargo?: string | null;
  cidade?: string | null;
  tags?: string[];
  observacoes?: string | null;
}

export interface PaginaParceiros {
  items: Parceiro[];
  total: number;
  page: number;
  page_size: number;
}

export interface ParceirosNumeros {
  total: number;
  recebem: number;
  descadastrados: number;
  bloqueados: number;
}

export interface ImportacaoParceiros {
  total_linhas: number;
  criados: number;
  atualizados: number;
  ignorados: number;
  descadastrados: number;
  erros: string[];
}


/* ------------------- Tripadvisor e Reclame Aqui (monitor) ------------------- */

/** Plataformas lidas pelos e-mails de notificação (não têm API utilizável). */
export type OrigemMonitor = "tripadvisor" | "reclameaqui";

export type TipoMonitor = "avaliacao" | "reclamacao" | "interacao" | "resultado";
export type NivelMonitor = "negativa" | "neutra" | "positiva";
/** nenhum | criticos (só palavra de crise) | negativos (crise ou nota baixa) | todos */
export type AvisoMonitor = "nenhum" | "criticos" | "negativos" | "todos";

export interface ConfigMonitor {
  origem: OrigemMonitor;
  ativo: boolean;
  aviso: AvisoMonitor;
  webhook_url: string | null;
  atualizado_em: string | null;
}

export interface SituacaoMonitor {
  caixa: {
    configurada: boolean;
    endereco: string | null;
    servidor: string | null;
    pasta: string;
    intervalo_min: number;
    /** false com caixa configurada = WORKER_DESLIGADO no servidor. */
    agendada: boolean;
    ultima_leitura: string | null;
    ultimo_erro: string | null;
    ultimo_erro_em: string | null;
    lendo: boolean;
  };
  emails: { processados: number; ignorados: number; erros: number };
  /** Há chave da OpenAI para completar o que o leitor não achou. */
  ia: boolean;
  origens: Record<OrigemMonitor, {
    itens: number;
    ultimos_7d: number;
    /** Críticos ou negativos ainda não tratados. */
    pendentes: number;
    ultimo_em: string | null;
    config: ConfigMonitor;
  }>;
  palavras: string[];
}

export interface PainelMonitor {
  numeros: {
    total: number;
    negativas: number;
    positivas: number;
    criticos: number;
    pendentes: number;
    media: string | null;
    ultimos_7d: number;
    reclamacoes: number;
    avaliadas: number;
    parciais: number;
  };
  semanas: { semana: string; total: number; negativas: number; positivas: number; criticos: number; media: string | null }[];
  unidades: { unidade: string; total: number; negativas: number; criticos: number; media: string | null }[];
  palavras: { palavra: string; total: number }[];
  notas: { nota: number; total: number }[];
}

export interface ItemMonitor {
  id: number;
  origem: OrigemMonitor;
  tipo: TipoMonitor;
  externo_id: string | null;
  unidade: string | null;
  nota: string | null;
  nota_maxima: number | null;
  titulo: string | null;
  texto: string | null;
  autor: string | null;
  cidade: string | null;
  /** Onde se responde, na própria plataforma. */
  link: string | null;
  ocorrido_em: string;
  nivel: NivelMonitor | null;
  critico: boolean;
  palavras: string[];
  /** regra | ia (completado pela IA) | parcial (faltou campo; o e-mail está guardado) */
  extraido_por: "regra" | "ia" | "parcial";
  tratado_em: string | null;
  tratado_por: string | null;
  observacao: string | null;
  avisado_em: string | null;
}

export interface DetalheMonitor extends ItemMonitor {
  loja_id: string | null;
  email_assunto: string | null;
  email_remetente: string | null;
  email_via: "imap" | "upload" | null;
  /** Texto do e-mail original, para conferir o que foi extraído. */
  email_texto: string | null;
}

export interface PaginaMonitor {
  items: ItemMonitor[];
  total: number;
  page: number;
  page_size: number;
}

export interface EmailMonitor {
  id: number;
  origem: OrigemMonitor | null;
  remetente: string | null;
  assunto: string | null;
  enviado_em: string | null;
  lido_em: string;
  via: "imap" | "upload";
  situacao: "processado" | "ignorado" | "erro";
  motivo: string | null;
}

export interface ImportacaoMonitor {
  lidos: number;
  novos: number;
  repetidos: number;
  ignorados: number;
  criticos: number;
  erros: string[];
}
