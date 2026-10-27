"use client";

import { useState } from "react";
import type { ImportReport } from "@/lib/api-types";
import { api, ApiError } from "@/lib/api";
import { Icon } from "@/components/ui/icon";

export function ImportModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [tagCampanha, setTagCampanha] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function importar() {
    if (!file) return;
    setLoading(true);
    setErro(null);
    try {
      const r = await api.contatos.importar(file); void (tagCampanha);
      setReport(r);
      onImported();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao importar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 animate-overlay-fade bg-domani-ink/45 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-lg animate-modal-panel overflow-hidden rounded-2xl bg-surface shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-line/20 px-5 py-4">
          <h2 className="font-display text-lg font-extrabold text-ink">Importar contatos</h2>
          <button onClick={onClose} className="rounded-lg p-2 text-ink/50 transition hover:bg-app hover:text-ink">
            <Icon name="close" className="h-4 w-4" strokeWidth={2} />
          </button>
        </div>

        {report ? (
          <div className="px-5 py-6">
            <div className="mb-4 flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
              <Icon name="check" className="h-6 w-6 text-emerald-600" strokeWidth={2} />
              <p className="text-sm font-semibold text-emerald-700">Importação concluída.</p>
            </div>
            {tagCampanha.trim() && (
              <div className="mb-4 rounded-xl border border-domani-orange/25 bg-domani-orange/5 px-4 py-3 text-sm text-ink/80">
                Contatos marcados com a tag <span className="font-bold text-domani-orange-600">{tagCampanha.trim()}</span>. Em <strong>Campanhas → Nova → Público → Por filtro</strong>, escolha essa tag para disparar só para eles.
              </div>
            )}
            <dl className="grid grid-cols-3 gap-3 text-center">
              {[
                { k: "Criados", v: report.criados, strong: true },
                { k: "Atualizados", v: report.atualizados, strong: true },
                { k: "Ignorados", v: report.ignorados, strong: false },
              ].map((it) => (
                <div key={it.k} className="rounded-xl border border-line/20 bg-app/40 py-3">
                  <dt className="text-xs text-ink/50">{it.k}</dt>
                  <dd className={`font-display text-xl font-extrabold ${it.strong ? "text-ink" : "text-ink/60"}`}>{it.v}</dd>
                </div>
              ))}
            </dl>
            {report.erros.length > 0 && (
              <div className="mt-4 max-h-40 overflow-auto rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                {report.erros.slice(0, 50).map((e, i) => <p key={i}>{e}</p>)}
              </div>
            )}
            <div className="mt-5 flex items-center gap-2">
              <button onClick={() => { setReport(null); setFile(null); }} className="rounded-xl border border-line/30 px-4 py-2.5 text-sm font-semibold text-ink transition hover:bg-app">Importar outro</button>
              <button onClick={onClose} className="flex-1 rounded-xl bg-domani-graphite px-4 py-2.5 text-sm font-bold text-white transition hover:bg-domani-slate">Concluir</button>
            </div>
          </div>
        ) : (
          <div className="px-5 py-5">
            <p className="text-sm text-ink/70">Envie um arquivo <strong>.csv</strong> ou <strong>.xlsx</strong> com a primeira linha de títulos.</p>
            <p className="mt-2 text-xs text-ink/50">Colunas: <span className="font-medium text-ink/70">telefone, nome, email, cpf, data_nascimento, tags</span>. O <strong>telefone</strong> é a chave (merge por telefone canônico).</p>

            <label className="mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line/35 bg-app/40 px-4 py-8 text-center transition hover:border-domani-orange/50 hover:bg-domani-orange/5">
              <Icon name="upload" className="h-8 w-8 text-ink/35" strokeWidth={1.6} />
              <span className="text-sm font-semibold text-ink">{file?.name ?? "Clique para escolher o arquivo"}</span>
              <input type="file" accept=".csv,.xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-xs text-ink/60 file:mr-3 file:rounded-lg file:border-0 file:bg-domani-graphite file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white" />
            </label>

            {/* Tag opcional p/ campanha (Opção A): marca todos os importados com a mesma
                tag, para depois selecioná-los no público de uma campanha de e-mail. */}
            <div className="mt-4">
              <label className="mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-ink/55">
                Tag da campanha <span className="font-normal normal-case text-ink/40">(opcional)</span>
              </label>
              <input
                type="text"
                value={tagCampanha}
                onChange={(e) => setTagCampanha(e.target.value)}
                placeholder="ex.: campanha-verao-2026"
                className="w-full rounded-xl border border-line/20 bg-app px-3 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted focus:border-domani-orange focus:bg-surface"
              />
              <p className="mt-1 text-xs text-muted">
                Se preencher, todos os contatos importados recebem esta tag — depois é só escolher a tag no público da campanha.
              </p>
            </div>

            {erro && <p className="mt-3 rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-500">{erro}</p>}

            <div className="mt-5 flex items-center gap-2">
              {loading && <span className="text-sm font-semibold text-domani-orange-600">Importando…</span>}
              <button onClick={importar} disabled={!file || loading} className="ml-auto rounded-xl bg-domani-orange px-5 py-2.5 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:cursor-not-allowed disabled:opacity-50">Importar</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
