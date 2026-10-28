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

/** Situação da campanha, na tabela e no topo do relatório. */
export function SeloSituacao({ status, className = "" }: { status: string; className?: string }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${TOM[status] ?? TOM.rascunho} ${className}`}>
      {status}
    </span>
  );
}

/** Selo da aba Parceiros. Grafite, e não laranja: laranja aqui é status. */
export function SeloParceiro({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full bg-domani-graphite px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white dark:bg-white dark:text-domani-graphite ${className}`}>
      Parceiro
    </span>
  );
}

/** Percentual vindo da API. Nulo vira "—": sem envio, 0% afirmaria que ninguém abriu. */
export function pct(valor: string | number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return `${Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

/** Quanto da fila já saiu: enviados sobre enviados + na fila + saindo agora. */
function progresso(c: Campanha): number {
  const s = c.stats;
  if (!s) return 0;
  const total = s.enviados + s.pendentes + s.processando;
  return total ? Math.round((s.enviados / total) * 100) : 0;
}

/**
 * Tabela de campanhas. A mesma nas abas: na visão geral aparecem todas as
 * listas, e as de parceiro levam o selo ao lado do nome.
 *
 * Abertura e cliques vêm da mesma view do relatório da campanha; sem envio, a
 * célula mostra "—".
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
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-12 rounded-lg" />)}
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
          <table className="w-full min-w-[980px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line/10 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
                <th className="px-5 py-3.5">Campanha</th>
                <th className="px-5 py-3.5">Público</th>
                <th className="px-5 py-3.5">Situação</th>
                <th className="px-5 py-3.5 text-right">Enviados</th>
                <th className="px-5 py-3.5 text-right">Abertura</th>
                <th className="px-5 py-3.5 text-right">Cliques</th>
                <th className="px-5 py-3.5">Criada</th>
              </tr>
            </thead>
            <tbody>
              {campanhas.map((c) => {
                const enviou = (c.stats?.enviados ?? c.enviados) > 0;
                return (
                  <tr key={c.id} className="border-b border-line/[0.08] align-middle transition last:border-0 hover:bg-app">
                    <td className="max-w-[260px] px-5 py-4">
                      <Link href={`/campanhas/${c.id}`}
                            className="font-semibold leading-snug text-ink hover:text-domani-orange-600">
                        {c.nome}
                      </Link>
                      {marcarParceiro && c.lista === "parceiros" && (
                        <div className="mt-1"><SeloParceiro /></div>
                      )}
                      <div className="mt-0.5 truncate text-xs text-muted">{c.template_nome ?? "—"}</div>
                    </td>
                    <td className="max-w-[300px] px-5 py-4">
                      <div className="truncate text-ink/80" title={c.segmento_label ?? undefined}>
                        {c.segmento_label ?? "—"}
                      </div>
                      <div className="text-xs text-muted [font-variant-numeric:tabular-nums]">
                        {num(c.com_email)} destinatários
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <SeloSituacao status={c.status} />
                      {c.status === "enviando" && (
                        <div className="mt-1.5 h-1 w-24 overflow-hidden rounded-full bg-app"
                             title={`${progresso(c)}% enviado`}>
                          <div className="h-full rounded-full bg-domani-orange"
                               style={{ width: `${Math.max(3, progresso(c))}%` }} />
                        </div>
                      )}
                      {c.status === "agendada" && c.agendada_para && (
                        <div className="mt-1 text-[11px] text-muted [font-variant-numeric:tabular-nums]">
                          {dataHoraBR(c.agendada_para)}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-4 text-right font-semibold text-ink [font-variant-numeric:tabular-nums]">
                      {num(c.enviados)}
                    </td>
                    <td className="px-5 py-4 text-right text-ink/75 [font-variant-numeric:tabular-nums]">
                      {enviou ? pct(c.stats?.taxa_abertura) : "—"}
                    </td>
                    <td className="px-5 py-4 text-right text-ink/75 [font-variant-numeric:tabular-nums]">
                      {enviou ? pct(c.stats?.taxa_clique) : "—"}
                    </td>
                    <td className="px-5 py-4 text-ink/70 [font-variant-numeric:tabular-nums]">
                      {dataHoraBR(c.created_at)}
                    </td>
                  </tr>
                );
              })}
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
