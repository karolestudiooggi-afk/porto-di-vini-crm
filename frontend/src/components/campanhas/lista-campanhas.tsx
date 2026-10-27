"use client";

import Link from "next/link";

import { dataHoraBR, num } from "@/lib/format";
import type { Campanha } from "@/lib/api-types";

const TOM: Record<string, string> = {
  rascunho: "bg-app text-ink/70",
  agendada: "bg-amber-500/15 text-amber-700",
  enviando: "bg-domani-orange/15 text-domani-orange-600",
  enviada: "bg-emerald-500/15 text-emerald-700",
  falhou: "bg-red-500/10 text-red-600",
  cancelada: "bg-app text-muted",
};

/** Selo da aba Parceiros. Grafite, e não laranja: laranja aqui é status. */
export function SeloParceiro({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full bg-domani-graphite px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white dark:bg-white dark:text-domani-graphite ${className}`}>
      Parceiro
    </span>
  );
}

/**
 * Tabela de campanhas. A mesma nas três abas: na visão geral aparecem as duas
 * listas, e as de parceiro levam o selo ao lado do nome.
 */
export function ListaCampanhas({
  campanhas, loading, error, vazio, marcarParceiro = true,
}: {
  campanhas: Campanha[] | null;
  loading: boolean;
  error: string | null;
  vazio: { titulo: string; texto: string };
  /** Na aba Parceiros todas são de parceiro; o selo em cada linha seria ruído. */
  marcarParceiro?: boolean;
}) {
  return (
    <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
      {loading ? (
        <div className="space-y-2 p-5">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-10 rounded-lg" />)}
        </div>
      ) : error ? (
        <p className="px-6 py-16 text-center text-sm text-red-500">{error}</p>
      ) : !campanhas?.length ? (
        <div className="px-6 py-16 text-center">
          <p className="font-semibold text-ink">{vazio.titulo}</p>
          <p className="mt-1 text-sm text-muted">{vazio.texto}</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line/10 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
                <th className="px-5 py-3">Campanha</th>
                <th className="px-5 py-3">Público</th>
                <th className="px-5 py-3">Situação</th>
                <th className="px-5 py-3 text-right">Enviados</th>
                <th className="px-5 py-3">Criada</th>
              </tr>
            </thead>
            <tbody>
              {campanhas.map((c) => (
                <tr key={c.id} className="border-b border-line/[0.08] transition hover:bg-app">
                  <td className="px-5 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link href={`/campanhas/${c.id}`}
                            className="font-semibold text-ink hover:text-domani-orange-600">
                        {c.nome}
                      </Link>
                      {marcarParceiro && c.lista === "parceiros" && <SeloParceiro />}
                    </div>
                    <div className="text-xs text-muted">{c.template_nome ?? "—"}</div>
                  </td>
                  <td className="px-5 py-3">
                    <div className="text-ink/80">{c.segmento_label ?? "—"}</div>
                    <div className="text-xs text-muted [font-variant-numeric:tabular-nums]">
                      {num(c.com_email)} destinatários
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase ${TOM[c.status] ?? TOM.rascunho}`}>
                      {c.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-right font-semibold text-ink [font-variant-numeric:tabular-nums]">
                    {num(c.enviados)}
                  </td>
                  <td className="px-5 py-3 text-ink/70">{dataHoraBR(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** "Nome <email>" → "email". Para mostrar por onde a campanha sai. */
export function enderecoDe(remetente: string | null | undefined): string {
  if (!remetente) return "";
  const m = /<([^>]+)>/.exec(remetente);
  return (m ? m[1] : remetente).trim();
}
