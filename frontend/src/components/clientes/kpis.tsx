"use client";

import type { ContatoStats } from "@/lib/api-types";
import { num } from "@/lib/format";

/**
 * Contadores do topo da lista. Respondem aos MESMOS filtros da tabela (o backend
 * aplica o mesmo recorte em /contatos/stats) — então o número muda junto com o
 * filtro, que é o comportamento que as pessoas esperam.
 */
export function ClientesKpis({
  stats,
  loading,
}: {
  stats?: ContatoStats;
  loading: boolean;
}) {
  const v = (n?: number) => (loading || n === undefined ? "—" : num(n));

  const cards = [
    { rotulo: "Total", valor: v(stats?.total), apoio: "no recorte atual", tag: "base" },
    { rotulo: "Com telefone", valor: v(stats?.com_telefone), apoio: "alcançáveis no WhatsApp", tag: "contato" },
    { rotulo: "Com e-mail", valor: v(stats?.com_email), apoio: "elegíveis a campanha", tag: "contato" },
    { rotulo: "Já interagiram", valor: v(stats?.com_interacao), apoio: "conversaram ao menos uma vez", tag: "domani" },
    { rotulo: "Opt-in de e-mail", valor: v(stats?.com_opt_in_email), apoio: "autorizaram receber", tag: "consentimento" },
  ];

  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {cards.map((c) => (
        <div key={c.rotulo} className="rounded-3xl border border-line/10 bg-surface p-5 shadow-domani-lift">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">{c.rotulo}</p>
            <span className="rounded-full bg-line/10 px-2 py-0.5 text-[10px] font-bold text-muted">{c.tag}</span>
          </div>
          <p className="mt-2 font-display text-3xl font-extrabold tracking-tight text-ink [font-variant-numeric:tabular-nums]">
            {c.valor}
          </p>
          <p className="mt-1 text-xs text-muted">{c.apoio}</p>
        </div>
      ))}
    </section>
  );
}
