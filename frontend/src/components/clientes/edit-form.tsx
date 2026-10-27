"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { ContatoDetail } from "@/lib/api-types";

/**
 * Edição da ficha.
 *
 * Só `observacoes` é editável — e isso não é limitação da tela, é o contrato: todo
 * o resto vem do Domani e seria sobrescrito na próxima sincronização. O backend
 * recusa qualquer outro campo (`ContatoPatch` tem um campo só), então oferecer
 * mais inputs aqui daria uma falsa sensação de que a mudança foi salva.
 */
export function EditForm({
  contato,
  onCancel,
  onSaved,
}: {
  contato: ContatoDetail;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [observacoes, setObservacoes] = useState(contato.observacoes ?? "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      await api.contatos.patch(contato.id, { observacoes: observacoes || null });
      onSaved();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível salvar.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="flex max-h-[92vh] flex-col">
      <div className="border-b border-line/10 bg-domani-graphite px-7 py-5 text-white">
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-domani-orange-300">
          Editar ficha
        </p>
        <h2 className="mt-1 font-display text-xl font-extrabold tracking-tight">
          {contato.nome ?? "Sem nome"}
        </h2>
      </div>

      <div className="scroll-area flex-1 overflow-y-auto bg-app/40 px-7 py-7">
        <label className="block">
          <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
            Observações
          </span>
          <textarea
            value={observacoes}
            onChange={(e) => setObservacoes(e.target.value)}
            rows={8}
            maxLength={10_000}
            placeholder="Preferências, combinados, contexto do atendimento…"
            className="w-full resize-y rounded-2xl border border-line/15 bg-surface px-4 py-3 text-sm text-ink outline-none transition placeholder:text-muted focus:border-domani-orange"
          />
          <span className="mt-1 block text-right text-[11px] text-muted">
            {observacoes.length}/10.000
          </span>
        </label>

        <p className="mt-4 rounded-2xl border border-line/10 bg-surface px-4 py-3 text-xs text-muted">
          Os demais campos vêm do Domani e são somente leitura: a sincronização
          diária os sobrescreveria.
        </p>

        {erro && (
          <p className="mt-3 rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-500">
            {erro}
          </p>
        )}
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-line/10 bg-surface px-7 py-4">
        <button
          onClick={onCancel}
          className="rounded-xl border border-line/20 px-4 py-2 text-sm font-bold text-ink transition hover:bg-app"
        >
          Cancelar
        </button>
        <button
          onClick={salvar}
          disabled={salvando}
          className="rounded-xl bg-domani-orange px-4 py-2 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:opacity-50"
        >
          {salvando ? "Salvando…" : "Salvar"}
        </button>
      </div>
    </div>
  );
}
