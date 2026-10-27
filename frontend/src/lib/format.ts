const BRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 2,
});

const NUM = new Intl.NumberFormat("pt-BR");

/** R$ 1.234,56 — equivalente ao filtro |brl do Django. */
export function brl(value: number | null | undefined): string {
  if (value == null) return "—";
  return BRL.format(value);
}

/** Abrevia valores grandes: 8.900.000 → R$ 8,9M */
export function brlCompact(value: number): string {
  if (value >= 1_000_000) return `R$ ${(value / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}M`;
  if (value >= 1_000) return `R$ ${(value / 1_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}k`;
  return brl(value);
}

/** 208363 → 208.363 */
export function num(value: number | null | undefined): string {
  if (value == null) return "—";
  return NUM.format(value);
}

/**
 * Lê uma data vinda da API.
 *
 * "2026-10-07" (só o dia, sem hora) o navegador interpreta como meia-noite em
 * UTC — que no Brasil ainda é 21h do dia ANTERIOR. Era por isso que o pedido do
 * dia 7 aparecia no gráfico como "06 de out.": todos os pontos ficavam um dia
 * atrás. Data sem hora é lida como dia local; com hora, segue o fuso que vier.
 */
export function lerData(iso: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
}

/** ISO → dd/mm/aaaa — equivalente ao filtro |data_br. */
export function dataBR(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = lerData(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function pluralize(n: number, singular = "", plural = "s"): string {
  return n === 1 ? singular : plural;
}

/** Data e hora em pt-BR — usado no "última sincronização" do dashboard. */
export function dataHoraBR(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
