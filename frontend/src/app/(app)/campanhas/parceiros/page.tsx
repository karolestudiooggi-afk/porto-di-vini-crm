"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import clsx from "clsx";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Icon } from "@/components/ui/icon";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { dataBR, num } from "@/lib/format";
import type { ImportacaoParceiros, Parceiro, ParceiroIn, SituacaoParceiro } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";

const CAMPO =
  "w-full rounded-xl border border-line/15 bg-app px-3 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted focus:border-domani-orange focus:bg-surface";
const BOTAO = "rounded-xl border border-line/20 px-4 py-2 text-sm font-bold text-ink transition hover:bg-app";
const BOTAO_PRINCIPAL = "rounded-xl bg-domani-orange px-4 py-2 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:opacity-50";
const POR_PAGINA = 50;

const SITUACAO: Record<SituacaoParceiro, { rotulo: string; tom: string; dica: string }> = {
  recebe: { rotulo: "recebe", tom: "bg-emerald-500/15 text-emerald-700", dica: "Entra nas campanhas de parceiros." },
  descadastrou: { rotulo: "descadastrou", tom: "bg-app text-ink/60", dica: "Pediu para sair da lista de parceiros. Não recebe mais, nem se for importado de novo." },
  bloqueado: { rotulo: "bloqueado", tom: "bg-red-500/10 text-red-600", dica: "O endereço deu erro definitivo, marcou spam ou se descadastrou como cliente." },
};

export default function ParceirosPage() {
  return (
    <Suspense fallback={<div className="skeleton h-40 rounded-3xl" />}>
      <Parceiros />
    </Suspense>
  );
}

/**
 * Base de parceiros. Separada da base de clientes de propósito: entra por
 * planilha, só é usada pelas campanhas da aba Parceiros e não aparece em Contatos.
 */
function Parceiros() {
  const params = useSearchParams();
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [tag, setTag] = useState("");
  const [situacao, setSituacao] = useState("");
  const [pagina, setPagina] = useState(1);

  const [importando, setImportando] = useState(params.get("importar") === "1");
  const [editando, setEditando] = useState<Parceiro | "novo" | null>(null);
  const [apagar, setApagar] = useState<Parceiro | null>(null);

  // Respiro na busca: não consultar a cada tecla.
  useEffect(() => {
    const t = setTimeout(() => { setBuscaAplicada(busca.trim()); setPagina(1); }, 350);
    return () => clearTimeout(t);
  }, [busca]);

  const lista = useApi(
    () => api.email.parceiros.list({ busca: buscaAplicada, tag, situacao, page: pagina, page_size: POR_PAGINA }),
    [buscaAplicada, tag, situacao, pagina],
  );
  const numeros = useApi(() => api.email.parceiros.numeros(), []);
  const tags = useApi(() => api.email.parceiros.tags(), []);
  const recarregar = () => { lista.reload(); numeros.reload(); tags.reload(); };

  const total = lista.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));
  const n = numeros.data;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3 rounded-3xl border border-line/10 bg-surface px-5 py-5 shadow-domani-lift sm:px-6">
        <div>
          <Link href="/campanhas?aba=parceiros" className="text-xs font-bold text-muted hover:text-domani-orange-600">
            ← E-mail · Parceiros
          </Link>
          <h1 className="mt-2 font-display text-2xl font-extrabold tracking-tight">Base de parceiros</h1>
          <p className="mt-1 text-sm text-muted">
            {n ? `${num(n.total)} na base · ${num(n.recebem)} recebem e-mail` : "Quem recebe as campanhas da aba Parceiros."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setEditando("novo")} className={BOTAO}>Adicionar parceiro</button>
          <button onClick={() => setImportando(true)} className={BOTAO_PRINCIPAL}>Importar planilha</button>
        </div>
      </header>

      <section className="grid gap-3 rounded-3xl border border-line/10 bg-surface p-4 shadow-domani-lift sm:grid-cols-3">
        <label className="relative block">
          <span className="sr-only">Buscar</span>
          <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/35" strokeWidth={2} />
          <input value={busca} onChange={(e) => setBusca(e.target.value)}
                 placeholder="Buscar empresa, nome ou e-mail" className={clsx(CAMPO, "pl-9")} />
        </label>
        <Select aria-label="Tag" value={tag} onChange={(v) => { setTag(v); setPagina(1); }}
                triggerClassName={CAMPO}
                options={[{ value: "", label: "Todas as tags" }, ...(tags.data ?? []).map((t) => ({ value: t, label: t }))]} />
        <Select aria-label="Situação" value={situacao} onChange={(v) => { setSituacao(v); setPagina(1); }}
                triggerClassName={CAMPO}
                options={[
                  { value: "", label: "Todas as situações" },
                  { value: "recebe", label: "Recebem e-mail" },
                  { value: "descadastrou", label: "Descadastraram" },
                  { value: "bloqueado", label: "Bloqueados" },
                ]} />
      </section>

      <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
        {lista.loading && !lista.data ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-10 rounded-lg" />)}
          </div>
        ) : lista.error ? (
          <p className="px-6 py-16 text-center text-sm text-red-500">{lista.error}</p>
        ) : !lista.data?.items.length ? (
          <div className="px-6 py-16 text-center">
            <p className="font-semibold text-ink">
              {buscaAplicada || tag || situacao ? "Ninguém com esses filtros" : "A base de parceiros está vazia"}
            </p>
            <p className="mt-1 text-sm text-muted">
              {buscaAplicada || tag || situacao
                ? "Limpe a busca ou troque o filtro."
                : "Importe a planilha (.csv ou .xlsx) com empresa, contato e e-mail."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line/10 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
                  <th className="px-5 py-3">Empresa</th>
                  <th className="px-5 py-3">Contato</th>
                  <th className="px-5 py-3">E-mail</th>
                  <th className="px-5 py-3">Tags</th>
                  <th className="px-5 py-3">Situação</th>
                  <th className="px-5 py-3">Último envio</th>
                  <th className="px-5 py-3"><span className="sr-only">Ações</span></th>
                </tr>
              </thead>
              <tbody>
                {lista.data.items.map((p) => (
                  <tr key={p.id} className="border-b border-line/[0.08] transition hover:bg-app">
                    <td className="px-5 py-3 font-semibold text-ink">{p.empresa ?? "—"}</td>
                    <td className="px-5 py-3">
                      <div className="text-ink/85">{p.nome ?? "—"}</div>
                      {p.cargo && <div className="text-xs text-muted">{p.cargo}</div>}
                    </td>
                    <td className="px-5 py-3 text-ink/80 [overflow-wrap:anywhere]">{p.email}</td>
                    <td className="px-5 py-3">
                      <div className="flex flex-wrap gap-1">
                        {p.tags.length ? p.tags.map((t) => (
                          <span key={t} className="rounded-full bg-app px-2 py-0.5 text-[11px] font-semibold text-ink/70">{t}</span>
                        )) : <span className="text-xs text-muted">—</span>}
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <span title={SITUACAO[p.situacao].dica}
                            className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase ${SITUACAO[p.situacao].tom}`}>
                        {SITUACAO[p.situacao].rotulo}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-ink/70">{p.ultimo_envio ? dataBR(p.ultimo_envio) : "nunca"}</td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1">
                        <button onClick={() => setEditando(p)}
                                className="rounded-lg border border-line/20 px-3 py-1.5 text-xs font-bold text-ink transition hover:bg-app">
                          Editar
                        </button>
                        <button onClick={() => setApagar(p)}
                                className="rounded-lg px-3 py-1.5 text-xs font-bold text-red-500 transition hover:bg-red-500/10">
                          Excluir
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {total > POR_PAGINA && (
          <div className="flex items-center justify-between gap-3 border-t border-line/10 px-5 py-3 text-sm">
            <span className="text-muted [font-variant-numeric:tabular-nums]">
              {num((pagina - 1) * POR_PAGINA + 1)}–{num(Math.min(pagina * POR_PAGINA, total))} de {num(total)}
            </span>
            <div className="flex gap-2">
              <button disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)} className={clsx(BOTAO, "disabled:opacity-40")}>Anterior</button>
              <button disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)} className={clsx(BOTAO, "disabled:opacity-40")}>Próxima</button>
            </div>
          </div>
        )}
      </section>

      <p className="px-1 text-xs text-muted">
        Quem pede para sair pelo link do e-mail sai só da lista de parceiros — e continua fora
        mesmo que a planilha seja importada de novo.
      </p>

      {importando && (
        <ModalImportar onClose={() => setImportando(false)} onImportado={recarregar} />
      )}
      {editando && (
        <ModalParceiro
          inicial={editando === "novo" ? null : editando}
          onClose={() => setEditando(null)}
          onSalvo={() => { setEditando(null); recarregar(); }}
        />
      )}
      <ConfirmDialog
        open={apagar !== null}
        variant="danger"
        title="Excluir este parceiro?"
        description={<>{apagar?.empresa ?? apagar?.nome ?? apagar?.email} sai da base. O histórico das campanhas que ele recebeu fica.</>}
        confirmLabel="Excluir"
        cancelLabel="Manter"
        onConfirm={async () => {
          if (apagar) await api.email.parceiros.excluir(apagar.id);
          setApagar(null);
          recarregar();
        }}
        onClose={() => setApagar(null)}
      />
    </div>
  );
}

function Modal({ titulo, onClose, children }: { titulo: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 animate-overlay-fade bg-domani-ink/45 backdrop-blur-sm" onClick={onClose} />
      <div className="relative max-h-[90vh] w-full max-w-lg animate-modal-panel overflow-y-auto rounded-2xl bg-surface shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-line/20 px-5 py-4">
          <h2 className="font-display text-lg font-extrabold text-ink">{titulo}</h2>
          <button onClick={onClose} aria-label="Fechar" className="rounded-lg p-2 text-ink/50 transition hover:bg-app hover:text-ink">
            <Icon name="close" className="h-4 w-4" strokeWidth={2} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ModalImportar({ onClose, onImportado }: { onClose: () => void; onImportado: () => void }) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [rel, setRel] = useState<ImportacaoParceiros | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function importar() {
    if (!arquivo) return;
    setEnviando(true);
    setErro(null);
    try {
      setRel(await api.email.parceiros.importar(arquivo));
      onImportado();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao importar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal titulo="Importar parceiros" onClose={onClose}>
      {rel ? (
        <div className="px-5 py-6">
          <dl className="grid grid-cols-3 gap-3 text-center">
            {[
              { k: "Novos", v: rel.criados },
              { k: "Atualizados", v: rel.atualizados },
              { k: "Ignorados", v: rel.ignorados },
            ].map((it) => (
              <div key={it.k} className="rounded-xl border border-line/20 bg-app/40 py-3">
                <dt className="text-xs text-ink/50">{it.k}</dt>
                <dd className="font-display text-xl font-extrabold text-ink">{num(it.v)}</dd>
              </div>
            ))}
          </dl>
          {rel.descadastrados > 0 && (
            <p className="mt-3 text-xs text-muted">
              {num(rel.descadastrados)} vieram marcados na planilha como “não aceita e-mail” e entraram já descadastrados.
            </p>
          )}
          {rel.erros.length > 0 && (
            <div className="mt-4 max-h-40 overflow-auto rounded-xl border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-xs text-amber-700">
              {rel.erros.slice(0, 50).map((e, i) => <p key={i}>{e}</p>)}
            </div>
          )}
          <div className="mt-5 flex gap-2">
            <button onClick={() => { setRel(null); setArquivo(null); }} className={BOTAO}>Importar outra</button>
            <button onClick={onClose} className="flex-1 rounded-xl bg-domani-graphite px-4 py-2.5 text-sm font-bold text-white transition hover:bg-domani-slate">Concluir</button>
          </div>
        </div>
      ) : (
        <div className="px-5 py-5">
          <p className="text-sm text-ink/70">
            Arquivo <strong>.csv</strong> ou <strong>.xlsx</strong> com a primeira linha de títulos.
          </p>
          <p className="mt-2 text-xs text-ink/50">
            Colunas reconhecidas: <span className="font-medium text-ink/70">empresa, nome (ou contato), e-mail, cargo, telefone, cidade, tags, observações</span>.
            O <strong>e-mail</strong> é a chave: subir a mesma planilha de novo atualiza em vez de duplicar.
          </p>
          <label className="mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line/35 bg-app/40 px-4 py-8 text-center transition hover:border-domani-orange/50 hover:bg-domani-orange/5">
            <Icon name="upload" className="h-8 w-8 text-ink/35" strokeWidth={1.6} />
            <span className="text-sm font-semibold text-ink">{arquivo?.name ?? "Clique para escolher o arquivo"}</span>
            <input type="file" accept=".csv,.xlsx" onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
                   className="block w-full text-xs text-ink/60 file:mr-3 file:rounded-lg file:border-0 file:bg-domani-graphite file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white" />
          </label>
          {erro && <p className="mt-3 rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-500">{erro}</p>}
          <div className="mt-5 flex items-center justify-end gap-2">
            {enviando && <span className="text-sm font-semibold text-domani-orange-600">Importando…</span>}
            <button onClick={importar} disabled={!arquivo || enviando} className={BOTAO_PRINCIPAL}>Importar</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function ModalParceiro({ inicial, onClose, onSalvo }: {
  inicial: Parceiro | null;
  onClose: () => void;
  onSalvo: () => void;
}) {
  const [f, setF] = useState({
    email: inicial?.email ?? "",
    empresa: inicial?.empresa ?? "",
    nome: inicial?.nome ?? "",
    cargo: inicial?.cargo ?? "",
    telefone: inicial?.telefone ?? "",
    cidade: inicial?.cidade ?? "",
    tags: (inicial?.tags ?? []).join(", "),
    observacoes: inicial?.observacoes ?? "",
  });
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const campo = (k: keyof typeof f) => ({
    value: f[k],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value }),
  });

  async function salvar() {
    if (!f.email.trim()) { setErro("Informe o e-mail."); return; }
    setSalvando(true);
    setErro(null);
    const body: ParceiroIn = {
      email: f.email.trim(),
      empresa: f.empresa.trim() || null,
      nome: f.nome.trim() || null,
      cargo: f.cargo.trim() || null,
      telefone: f.telefone.trim() || null,
      cidade: f.cidade.trim() || null,
      tags: f.tags.split(/[,;|]/).map((t) => t.trim()).filter(Boolean),
      observacoes: f.observacoes.trim() || null,
    };
    try {
      if (inicial) await api.email.parceiros.editar(inicial.id, body);
      else await api.email.parceiros.criar(body);
      onSalvo();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não deu para salvar.");
      setSalvando(false);
    }
  }

  return (
    <Modal titulo={inicial ? "Editar parceiro" : "Adicionar parceiro"} onClose={onClose}>
      <div className="grid gap-3 px-5 py-5 sm:grid-cols-2">
        <Campo rotulo="E-mail *" largo><input type="email" {...campo("email")} className={CAMPO} placeholder="contato@empresa.com.br" /></Campo>
        <Campo rotulo="Empresa"><input {...campo("empresa")} className={CAMPO} /></Campo>
        <Campo rotulo="Contato"><input {...campo("nome")} className={CAMPO} /></Campo>
        <Campo rotulo="Cargo"><input {...campo("cargo")} className={CAMPO} /></Campo>
        <Campo rotulo="Telefone"><input {...campo("telefone")} className={CAMPO} /></Campo>
        <Campo rotulo="Cidade"><input {...campo("cidade")} className={CAMPO} /></Campo>
        <Campo rotulo="Tags" largo>
          <input {...campo("tags")} className={CAMPO} placeholder="hotel, zona sul" />
          <span className="mt-1 block text-[11px] text-muted">Separe por vírgula. Servem para escolher o público da campanha.</span>
        </Campo>
        <Campo rotulo="Observações" largo><textarea rows={3} {...campo("observacoes")} className={CAMPO} /></Campo>
        {inicial && inicial.situacao !== "recebe" && (
          <p className="text-xs text-muted sm:col-span-2">{SITUACAO[inicial.situacao].dica}</p>
        )}
        {erro && <p className="rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-500 sm:col-span-2">{erro}</p>}
        <div className="flex justify-end gap-2 sm:col-span-2">
          <button onClick={onClose} className={BOTAO}>Cancelar</button>
          <button onClick={salvar} disabled={salvando} className={BOTAO_PRINCIPAL}>
            {salvando ? "Salvando…" : "Salvar"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Campo({ rotulo, largo, children }: { rotulo: string; largo?: boolean; children: React.ReactNode }) {
  return (
    <label className={clsx("block", largo && "sm:col-span-2")}>
      <span className="mb-1.5 block text-xs font-bold text-ink/70">{rotulo}</span>
      {children}
    </label>
  );
}
