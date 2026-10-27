export type Origem = "Domani" | "zigpay" | "brevo" | "importacao" | "whatsapp";

export interface Customer {
  id: string;
  nome: string | null;
  telefone: string | null;
  email: string | null;
  cpf: string | null;
  dataNascimento: string | null; // ISO
  origem: Origem;
  origens: Origem[];
  casaMaisVisitada: string | null;
  visitas: number;
  ticketMedio: number;
  totalGasto: number;
  dataPrimeiraVisita: string | null;
  dataUltimaVisita: string | null;
  dataUltimaReserva: string | null;
  unidadeUltimaReserva: string | null;
  pessoasUltimaReserva: number | null;
  nps: number | null;
  perfilConsumo: string | null;
  tags: string[];
  etiquetas: string[];
}

export interface Kpis {
  total: number;
  comTelefone: number;
  comAniversario: number;
  comVisitas: number;
  ticketMedio: number;
  reativacao: number;
}

export interface BarItem {
  label: string;
  value: number;
  percent: number;      // largura da barra (proporção do MAIOR valor)
  share?: number;       // % do total (soma) — rótulo "quanto representa"
}

export interface DonutItem extends BarItem {
  total: number;
  color: string;
}

export type RankingMode = "ticket" | "frequencia" | "valor" | "reativacao";

export interface UserRow {
  id: string;
  nome: string;
  email: string;
  papel: "Superadmin" | "Administrador" | "Membro";
  status: "Ativo" | "Convite pendente" | "Inativo";
  ultimoAcesso: string | null;
}

export interface CurvePoint {
  x: number; // dia relativo ao evento (-120 .. 0)
  cur: number; // 2027 acumulado
  prev: number; // 2026 fechado
  ads: number; // investimento em ads acumulado (proporção)
}
