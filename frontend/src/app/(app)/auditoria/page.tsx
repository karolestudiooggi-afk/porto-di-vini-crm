"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { dataHoraBR } from "@/lib/format";

/**
 * Registro de alterações manuais.
 *
 * O que aparece aqui é o que foi feito por pessoas — edição de observação,
 * importação, exclusão de ficha. O sync do Domani não entra: ele roda todo dia e
 * afogaria o log, tornando inútil justamente a pergunta que esta tela responde
 * ("quem mexeu nisso?").
 */
export default function AuditoriaPage() {
  const { data, loading, error } = useApi(() => api.auditoria.list(), []);
  const [aberto, setAberto] = useState<number | null>(null);

  return (
    <div className="space-y-4">
      <header className="rounded-3xl border border-line/10 bg-surface px-5 py-5 shadow-domani-lift sm:px-6">
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-domani-orange-300">
          Rastreabilidade
        </p>
        <h1 className="mt-1 font-display text-2xl font-extrabold tracking-tight">Auditoria</h1>
        <p className="mt-1 text-sm text-muted">
          Alterações feitas por pessoas na base. A sincronização automática não entra aqui.
        </p>
      </header>

      <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
        {loading ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skeleton h-10 rounded-lg" />
            ))}
          </div>
        ) : error ? (
          <p className="px-6 py-16 text-center text-sm text-red-500">{error}</p>
        ) : !data?.length ? (
          <p className="px-6 py-16 text-center text-sm text-muted">
            Nenhuma alteração registrada ainda.
          </p>
        ) : (
          <ul className="divide-y divide-line/10">
            {data.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => setAberto(aberto === a.id ? null : a.id)}
                  className="flex w-full items-start gap-4 px-5 py-3.5 text-left transition hover:bg-app"
                  aria-expanded={aberto === a.id}
                >
                  <span className="w-36 shrink-0 text-xs text-muted [font-variant-numeric:tabular-nums]">
                    {dataHoraBR(a.created_at)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold text-ink">{a.acao}</span>
                    <span className="block truncate text-xs text-muted">{a.recurso}</span>
                  </span>
                  {a.detalhe && (
                    <span className="shrink-0 text-xs font-bold text-domani-orange-600">
                      {aberto === a.id ? "ocultar" : "detalhe"}
                    </span>
                  )}
                </button>

                {aberto === a.id && a.detalhe && (
                  <pre className="mx-5 mb-4 overflow-x-auto rounded-2xl bg-app px-4 py-3 text-xs text-ink/80">
                    {JSON.stringify(a.detalhe, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
