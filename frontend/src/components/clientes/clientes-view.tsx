"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import clsx from "clsx";
import { api, isApiConfigured, type ContatoFiltro } from "@/lib/api";
import type { ContatoListItem } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { guardarSelecao } from "@/lib/selecao";
import { CLIENTE, cap } from "@/config/cliente";
import { useAuth } from "@/providers/auth";
import { dataBR, num, pluralize } from "@/lib/format";
import { Icon } from "@/components/ui/icon";
import { Select } from "@/components/ui/select";
import { ClientesKpis } from "./kpis";
import { DetailDrawer } from "./detail-drawer";
import { ImportModal } from "./import-modal";

const PAGE = 25;
const FIELD = "w-full rounded-2xl border border-line/15 bg-app px-3 py-3 text-sm text-ink outline-none transition placeholder:text-muted focus:border-domani-orange focus:bg-surface";

const { vocab } = CLIENTE;

// Ordenações aceitas pelo backend (app/routers/contatos.py::_ORDER).
const ORDENAR = [
  { value: "interacao_recente", label: "Interação recente" },
  { value: "mensagem_recente", label: "Mensagem recente" },
  { value: "cadastro_recente", label: "Cadastro recente" },
  { value: "az", label: "A–Z" },
  { value: "za", label: "Z–A" },
];

// Canal, status, idioma e origem NÃO são listas fixas: vêm de /contatos/filtros,
// derivadas dos dados. Valor novo no Domani aparece aqui sem deploy.
const SIM_NAO = [
  { value: "", label: "Todos" },
  { value: "true", label: "Só com" },
  { value: "false", label: "Só sem" },
];

/**
 * Filtro de e-mail, num seletor só.
 *
 * "Tem e-mail" e "recebe campanha" são coisas diferentes: alguém pode ter e-mail
 * cadastrado e ainda assim não receber, se recusou ou se descadastrou. Manter os
 * dois no mesmo lugar evita a pergunta "então qual eu uso?".
 *
 * "Recebem campanha" usa EXATAMENTE a regra do disparo — o número que aparece
 * aqui é o que vai sair de verdade.
 */
/**
 * Histórico de campanha.
 *
 * Existe porque "selecionar os primeiros N" traz sempre as mesmas pessoas: a
 * ordem não muda entre um disparo e outro. Com este filtro, cada envio pega
 * gente nova sem ninguém precisar controlar isso numa planilha.
 */
const HISTORICO = [
  { value: "", label: "Todos" },
  { value: "nunca", label: "Nunca receberam" },
  { value: "ja", label: "Já receberam" },
];

const EMAIL = [
  { value: "", label: "Todos" },
  { value: "recebem", label: "Recebem campanha" },
  { value: "nao_recebem", label: "Não recebem" },
  { value: "com", label: "Têm e-mail" },
  { value: "sem", label: "Sem e-mail" },
];

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function ClientesView() {
  const params = useSearchParams();
  const router = useRouter();
  const { can } = useAuth();

  const [buscaInput, setBuscaInput] = useState(params.get("q") ?? "");
  // Aba ativa: "todos" (lista com filtros) ou "rankings" (listas estratégicas).
  const busca = useDebounced(buscaInput, 350);
  const [ordenar, setOrdenar] = useState("interacao_recente");
  const [canal, setCanal] = useState("");
  const [status, setStatus] = useState("");
  const [idioma, setIdioma] = useState("");
  const [origem, setOrigem] = useState("");
  const [email, setEmail] = useState("");
  const [historico, setHistorico] = useState("");
  const [comTelefone, setComTelefone] = useState("");
  const [tags, setTags] = useState("");
  const [etiquetas, setEtiquetas] = useState("");

  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Map<number, string>>(new Map());
  const [selecionandoLote, setSelecionandoLote] = useState(false);
  const [tamanhoLote, setTamanhoLote] = useState("500");
  const [erroLote, setErroLote] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const tagsArr = tags.split(",").map((s) => s.trim()).filter(Boolean);
  const etiquetasArr = etiquetas.split(",").map((s) => s.trim()).filter(Boolean);

  const filtro: ContatoFiltro = useMemo(() => ({
    busca: busca || undefined,
    ordenar,
    canal: canal || undefined,
    status: status || undefined,
    idioma: idioma || undefined,
    origem: origem || undefined,
    // "" = indiferente; "true"/"false" viram booleano de verdade na query.
    // Um seletor, dois parâmetros: "recebem" olha consentimento e supressão,
    // "têm e-mail" olha só o campo preenchido.
    com_email: email === "com" ? true : email === "sem" ? false : undefined,
    recebe_email:
      email === "recebem" ? true : email === "nao_recebem" ? false : undefined,
    ja_recebeu:
      historico === "ja" ? true : historico === "nunca" ? false : undefined,
    com_telefone: comTelefone === "" ? undefined : comTelefone === "true",
    tags: tagsArr.length ? tagsArr : undefined,
    etiquetas: etiquetasArr.length ? etiquetasArr : undefined,
  }), [busca, ordenar, canal, status, idioma, origem, email, historico, comTelefone, tags, etiquetas]);

  const filtroKey = JSON.stringify(filtro);

  // Volta pra primeira página quando o filtro muda.
  useEffect(() => setOffset(0), [filtroKey]);

  const list = useApi(() => api.contatos.list({ ...filtro, limit: PAGE, offset }), [filtroKey, offset]);
  const stats = useApi(() => api.contatos.stats(filtro), [filtroKey]);
  // Opções reais dos filtros (GET /contatos/filtros) — nada fixo no código.
  const filtros = useApi(() => api.contatos.filtros(), []);
  const opts = (vs?: string[]) => [{ value: "", label: "Todos" }, ...(vs ?? []).map((v) => ({ value: v, label: v }))];

  const rows: ContatoListItem[] = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const from = total ? offset + 1 : 0;
  const to = offset + rows.length;

  const activeFilters =
    (busca ? 1 : 0) + (canal ? 1 : 0) + (status ? 1 : 0) + (idioma ? 1 : 0) +
    (origem ? 1 : 0) + (email ? 1 : 0) + (historico ? 1 : 0) + (comTelefone ? 1 : 0) +
    tagsArr.length + etiquetasArr.length;

  function toggle(id: number, nome: string) {
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(id)) next.delete(id);
      else next.set(id, nome);
      return next;
    });
  }
  const allOnPage = rows.length > 0 && rows.every((r) => selected.has(r.id));
  function toggleAll() {
    setSelected((prev) => {
      const next = new Map(prev);
      if (allOnPage) rows.forEach((r) => next.delete(r.id));
      else rows.forEach((r) => next.set(r.id, r.nome ?? "—"));
      return next;
    });
  }

  /**
   * Seleciona os N primeiros do recorte atual, sem paginar.
   *
   * Existe por uma necessidade concreta: disparar para um lote controlado
   * (aquecimento de domínio, teste com parte da base) sem clicar página por
   * página. Respeita os filtros da tela — se há busca ou filtro ativo, seleciona
   * os N primeiros DAQUELE recorte, não da base inteira.
   */
  /**
   * Seleciona os N primeiros COM E-MAIL do recorte atual.
   *
   * O `com_email: true` é fixo, não opcional: esta seleção existe para alimentar
   * campanha, e contato sem e-mail não recebe. Sem esse filtro, pedir 500 traria
   * os primeiros 500 da lista — boa parte deles sem e-mail — e a campanha sairia
   * para bem menos gente do que a pessoa pediu, sem aviso nenhum.
   */
  async function selecionarPrimeiros(quantos: number) {
    setSelecionandoLote(true);
    setErroLote(null);
    try {
      const pagina = await api.contatos.list({
        // `recebe_email` em vez de só `com_email`: esta seleção alimenta
        // campanha, e quem recusou ou descadastrou não recebe. Selecionar essas
        // pessoas só faria o número da campanha vir menor que o esperado.
        ...filtro, recebe_email: true, limit: quantos, offset: 0,
      });
      setSelected(new Map(pagina.items.map((c) => [c.id, c.nome ?? "—"])));
      // Se o recorte tinha menos gente com e-mail do que o pedido, é melhor dizer
      // do que deixar a pessoa achar que selecionou 500 e ter 180.
      if (pagina.items.length < quantos) {
        setErroLote(
          `Só ${pagina.items.length} recebem campanha neste recorte — todos selecionados.`,
        );
      }
    } catch (e) {
      // Falha aqui PRECISA aparecer. Engolir o erro fazia o botão parecer
      // quebrado — a pessoa clicava, nada mudava, e não havia como saber por quê.
      setErroLote(e instanceof Error ? e.message : "Não deu para selecionar.");
    } finally {
      setSelecionandoLote(false);
    }
  }

  /**
   * Leva os contatos marcados para a criação de campanha.
   *
   * É o caminho de quem importou uma planilha: marca quem deve receber e dispara,
   * sem precisar inventar um filtro que descreva exatamente aquele grupo.
   */
  function paraCampanha() {
    guardarSelecao({
      ids: [...selected.keys()],
      nomes: [...selected.values()],
    });
    router.push("/campanhas/nova");
  }

  async function exportar(formato: "csv" | "xlsx") {
    setExporting(true);
    try {
      // Baixa via fetch (e não <a href>) porque a rota exige o header Authorization,
      // que um link comum não carrega.
      const blob = await api.contatos.exportarBlob(filtro, formato);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `contatos.${formato}`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  function limparFiltros() {
    setBuscaInput(""); setOrdenar("interacao_recente"); setCanal(""); setStatus("");
    setIdioma(""); setOrigem(""); setEmail(""); setHistorico(""); setComTelefone("");
    setTags(""); setEtiquetas("");
  }

  if (!isApiConfigured) {
    return <Aviso title="Conecte a API para carregar os clientes" sub="Defina NEXT_PUBLIC_API_URL e o Supabase no .env." />;
  }

  return (
    <div className="space-y-5">
      {/* Filtros */}
      <section className="overflow-hidden rounded-3xl border border-line/12 bg-surface shadow-domani-lift">
        <div className="bg-domani-graphite px-5 py-5 text-white sm:px-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-domani-orange-300">Base unificada</p>
              <h1 className="mt-1 font-display text-2xl font-extrabold tracking-tight">{cap(vocab.pessoa.muitos)}</h1>
            </div>
            {activeFilters > 0 && (
              <span className="w-fit rounded-full bg-domani-orange px-3 py-1 text-xs font-bold text-white">
                {activeFilters} filtro{pluralize(activeFilters)} ativo{pluralize(activeFilters)}
              </span>
            )}
          </div>
        </div>

        <div className="space-y-4 px-5 py-5 sm:px-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
            <label className="block sm:col-span-2">
              <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Busca</span>
              <input value={buscaInput} onChange={(e) => setBuscaInput(e.target.value)} placeholder="Nome, telefone ou email" className={FIELD} />
            </label>
            <Campo label="Ordenar"><Select aria-label="Ordenar" value={ordenar} onChange={setOrdenar} options={ORDENAR} triggerClassName={FIELD} /></Campo>
            <Campo label={cap(vocab.local.um)}><Select aria-label="Canal" value={canal} onChange={setCanal} options={opts(filtros.data?.canais)} triggerClassName={FIELD} /></Campo>
            <Campo label="Status"><Select aria-label="Status" value={status} onChange={setStatus} options={opts(filtros.data?.status)} triggerClassName={FIELD} /></Campo>
            <Campo label="Origem"><Select aria-label="Origem" value={origem} onChange={setOrigem} options={opts(filtros.data?.origens)} triggerClassName={FIELD} /></Campo>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Campo label="Idioma"><Select aria-label="Idioma" value={idioma} onChange={setIdioma} options={opts(filtros.data?.idiomas)} triggerClassName={FIELD} /></Campo>
            <Campo label="E-mail">
              <Select aria-label="E-mail" value={email} onChange={setEmail}
                      options={EMAIL} triggerClassName={FIELD} />
            </Campo>
            <Campo label="Campanha">
              <Select aria-label="Histórico de campanha" value={historico}
                      onChange={setHistorico} options={HISTORICO} triggerClassName={FIELD} />
            </Campo>
            <Campo label="Telefone"><Select aria-label="Com telefone" value={comTelefone} onChange={setComTelefone} options={SIM_NAO} triggerClassName={FIELD} /></Campo>
            <Campo label="Tags (vírgula)"><input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Cliente, Fidelidade" className={FIELD} /></Campo>
            <Campo label="Etiquetas (vírgula)"><input value={etiquetas} onChange={(e) => setEtiquetas(e.target.value)} placeholder="Reativar" className={FIELD} /></Campo>
          </div>

          <div className="flex justify-end border-t border-line/10 pt-4">
            <button onClick={limparFiltros} className="text-xs font-bold text-domani-orange-600 transition hover:text-domani-orange">Limpar filtros</button>
          </div>
        </div>
      </section>

      <ClientesKpis stats={stats.data ?? undefined} loading={stats.loading} />

      {/* Tabela */}
      <section className="overflow-hidden rounded-3xl border border-line/12 bg-surface shadow-domani-lift">
        <div className="flex flex-col gap-3 border-b border-line/10 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-domani-orange px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-white">Grid</span>
            <h2 className="font-display text-lg font-extrabold text-ink">Clientes</h2>
            <span className="text-xs text-muted">
              {total ? <>{from}–{to} de <span className="font-semibold text-ink/75">{num(total)}</span></> : list.loading ? "Carregando…" : "Nenhum resultado"}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Seleção em lote: disparar para um recorte controlado sem clicar
                página por página. Respeita os filtros ativos da tela. */}
            {total > 0 && (
              <div className="flex items-center gap-1.5 rounded-xl border border-line/25 bg-surface px-2 py-1">
                <label htmlFor="lote" className="text-xs text-muted" title="Seleciona os primeiros do recorte atual, na ordem escolhida acima. Só quem tem e-mail.">
                  Selecionar
                </label>
                <input
                  id="lote"
                  type="number"
                  min={1}
                  max={total}
                  value={tamanhoLote}
                  onChange={(e) => setTamanhoLote(e.target.value)}
                  className="w-20 rounded-lg border border-line/20 bg-app px-2 py-1 text-sm font-semibold text-ink [font-variant-numeric:tabular-nums]"
                />
                <button
                  onClick={() => selecionarPrimeiros(Math.min(Number(tamanhoLote) || 0, total))}
                  disabled={selecionandoLote || !Number(tamanhoLote)}
                  className="rounded-lg bg-domani-graphite px-2.5 py-1 text-xs font-bold text-white transition hover:bg-domani-ink disabled:opacity-40"
                >
                  {selecionandoLote ? "…" : "que recebem"}
                </button>
              </div>
            )}
            {erroLote && (
              <span className="text-xs font-semibold text-amber-600">{erroLote}</span>
            )}
            {can("contatos:import") && (
              <button onClick={() => setImporting(true)} className="inline-flex items-center gap-1.5 rounded-xl border border-line/25 bg-surface px-3 py-2 text-sm font-semibold text-ink transition hover:bg-app">
                <Icon name="upload" className="h-4 w-4" /> Importar
              </button>
            )}
            {can("contatos:export") && (
              <>
                <button onClick={() => exportar("csv")} disabled={exporting} className="rounded-xl border border-line/25 bg-surface px-3 py-2 text-sm font-semibold text-ink transition hover:bg-app disabled:opacity-50">CSV</button>
                <button onClick={() => exportar("xlsx")} disabled={exporting} className="rounded-xl bg-domani-orange px-3 py-2 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:opacity-50">Excel</button>
              </>
            )}
          </div>
        </div>

        {selected.size > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-domani-orange/20 bg-domani-orange/10 px-5 py-2.5">
            {/* Deixar explícito que a seleção atravessa páginas: sem isso ninguém
                confia e refaz tudo ao paginar. */}
            <span className="text-sm font-semibold text-ink">
              {num(selected.size)} selecionado{pluralize(selected.size)}
              <span className="ml-1.5 font-normal text-ink/60">· a seleção continua ao mudar de página</span>
            </span>
            <div className="flex flex-wrap items-center gap-2">
              {/* Só com o módulo de E-mail ligado: sem ele não há para onde levar. */}
              {CLIENTE.modulos.campanhas && (
                <button onClick={paraCampanha}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-domani-orange px-3 py-1.5 text-xs font-bold text-white transition hover:bg-domani-orange-600">
                  <Icon name="campanhas" className="h-3.5 w-3.5" strokeWidth={2} />
                  Enviar campanha para estes
                </button>
              )}
              <button onClick={() => setSelected(new Map())} className="rounded-lg px-2 py-1.5 text-xs font-semibold text-muted transition hover:text-ink">Limpar</button>
            </div>
          </div>
        )}

        <div className="scroll-area max-h-[calc(100vh-20rem)] overflow-auto">
          <table className="w-full min-w-[980px] border-collapse text-sm [font-variant-numeric:tabular-nums]">
            <thead>
              <tr className="sticky top-0 z-10 border-b border-line/15 bg-panel text-left text-[11px] uppercase tracking-[0.12em] text-muted">
                <th className="cell-pad w-10 pl-4 pr-2"><input type="checkbox" checked={allOnPage} onChange={toggleAll} aria-label="Selecionar todos" className="accent-domani-orange" /></th>
                <th className="cell-pad px-4 font-bold">{cap(vocab.pessoa.um)}</th>
                <th className="cell-pad px-4 font-bold">Telefone</th>
                <th className="cell-pad px-4 font-bold">E-mail</th>
                <th className="cell-pad px-4 font-bold">{cap(vocab.local.um)}</th>
                <th className="cell-pad px-4 font-bold">Status</th>
                <th className="cell-pad px-4 font-bold">Tags</th>
                <th className="cell-pad px-4 font-bold">Última {vocab.interacao.um}</th>
              </tr>
            </thead>
            <tbody>
              {list.loading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i} className="border-b border-line/[0.06]"><td colSpan={8} className="px-4 py-2"><div className="skeleton h-6 rounded-lg" /></td></tr>
                ))
              ) : list.error ? (
                <tr><td colSpan={8} className="px-6 py-16 text-center text-sm text-red-500">{list.error}</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={8} className="px-6 py-16 text-center text-sm text-muted">Nenhum {vocab.pessoa.um} encontrado com os filtros atuais.</td></tr>
              ) : rows.map((c) => (
                <tr key={c.id} onClick={() => setOpenId(c.id)} className="group cursor-pointer border-b border-line/[0.08] bg-surface transition hover:bg-domani-orange/5">
                  <td className="cell-pad pl-4 pr-2" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id, c.nome ?? "—")} className="accent-domani-orange" aria-label={`Selecionar ${c.nome ?? c.telefone}`} />
                  </td>
                  <td className="cell-pad max-w-[280px] px-4">
                    <div className="flex items-center gap-2">
                      <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", c.origem === "Domani" ? "bg-domani-orange" : c.origem === "zigpay" ? "bg-ink/30" : "bg-ink/15")} title={c.origem ?? ""} />
                      <span className="truncate font-semibold text-ink group-hover:text-domani-orange-600">{c.nome ?? "—"}</span>
                    </div>
                  </td>
                  <td className="cell-pad whitespace-nowrap px-4 text-ink/80">{c.telefone ?? "—"}</td>
                  <td className="cell-pad max-w-[220px] px-4"><span className="block truncate text-ink/80">{c.email ?? "—"}</span></td>
                  <td className="cell-pad max-w-[130px] px-4"><span className="block truncate text-ink/80">{c.canal ?? "—"}</span></td>
                  <td className="cell-pad max-w-[130px] px-4"><span className="block truncate text-ink/80">{c.status ?? "—"}</span></td>
                  <td className="cell-pad max-w-[200px] px-4">
                    {c.tags.length === 0 ? <span className="text-ink/80">—</span> : (
                      <span className="flex flex-wrap gap-1">
                        {c.tags.slice(0, 2).map((t) => (
                          <span key={t} className="rounded-full bg-app px-2 py-0.5 text-[11px] font-semibold text-ink/70">{t}</span>
                        ))}
                        {c.tags.length > 2 && <span className="text-[11px] text-muted">+{c.tags.length - 2}</span>}
                      </span>
                    )}
                  </td>
                  <td className="cell-pad whitespace-nowrap px-4 text-ink/80">{dataBR(c.last_interaction)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {total > PAGE && (
          <div className="flex items-center justify-between gap-3 border-t border-line/12 px-5 py-3 text-sm">
            <button disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE))} className="rounded-xl border border-line/25 px-4 py-1.5 font-semibold text-ink transition hover:bg-app disabled:border-line/15 disabled:text-ink/30">Anterior</button>
            <span className="text-xs text-muted">Página {Math.floor(offset / PAGE) + 1} de {Math.max(1, Math.ceil(total / PAGE))}</span>
            <button disabled={to >= total} onClick={() => setOffset((o) => o + PAGE)} className="rounded-xl border border-line/25 px-4 py-1.5 font-semibold text-ink transition hover:bg-app disabled:border-line/15 disabled:text-ink/30">Próxima</button>
          </div>
        )}
      </section>

      {openId !== null && (
        <DetailDrawer
          id={openId}
          canWrite={can("contatos:write")}
          canDelete={can("contatos:delete")}
          onClose={() => setOpenId(null)}
          onChanged={() => { list.reload(); stats.reload(); }}
        />
      )}
      {importing && <ImportModal onClose={() => setImporting(false)} onImported={() => { list.reload(); stats.reload(); }} />}
    </div>
  );
}

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.14em] text-muted">{label}</span>
      {children}
    </label>
  );
}

function Aviso({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="rounded-3xl border border-line/12 bg-surface px-6 py-16 text-center shadow-domani-lift">
      <p className="font-display text-base font-extrabold text-ink">{title}</p>
      <p className="mx-auto mt-1.5 max-w-md text-sm text-muted">{sub}</p>
    </div>
  );
}
