"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";

import { BarList, toBars } from "@/components/dashboards/bar-list";
import { Icon } from "@/components/ui/icon";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import type {
  AvisoMonitor, DetalheMonitor, ImportacaoMonitor, ItemMonitor, OrigemMonitor, PainelMonitor,
  SituacaoMonitor,
} from "@/lib/api-types";
import { lerData, num } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import {
  Aviso, BOTAO_PRINCIPAL, BOTAO_SECUNDARIO, CAMPO, Carregando, Cartao, Selo, Vazio, desde,
  mensagemDe, quando, quandoCompleto,
} from "./partes";

/**
 * Tripadvisor e Reclame Aqui: o que chega pelos e-mails de notificação.
 *
 * Diferente de iFood e Google, aqui não se responde — a resposta continua na
 * própria plataforma (o link de cada item leva até lá). O CRM lê, guarda,
 * avisa a crise e mostra a evolução. A regra de cor é a do módulo: laranja é
 * atenção (crise, nota baixa, reclamação), o resto é neutro.
 */

export const NOME_MONITOR: Record<OrigemMonitor, string> = {
  tripadvisor: "Tripadvisor",
  reclameaqui: "Reclame Aqui",
};

const TIPO: Record<string, string> = {
  avaliacao: "Avaliação",
  reclamacao: "Reclamação",
  interacao: "Réplica",
  resultado: "Avaliada pelo consumidor",
};

const NEUTRO = "rgb(var(--line) / 0.45)";
const LARANJA = "#E56D23";

function semanaBR(iso: string): string {
  const d = lerData(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function nota(n: string | number | null | undefined, max?: number | null): string {
  if (n == null || n === "") return "—";
  const v = Number(n);
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}${max ? ` de ${max}` : ""}`;
}

// ---------------------------------------------------------------------------
// Painel
// ---------------------------------------------------------------------------

const PERIODOS = [
  { value: "30", label: "30 dias" },
  { value: "90", label: "90 dias" },
  { value: "180", label: "6 meses" },
  { value: "365", label: "12 meses" },
];

export function MonitorPainel({ origem, situacao, onLista, onConfig }: {
  origem: OrigemMonitor;
  situacao: SituacaoMonitor;
  /** Abre a lista já filtrada (clique num número ou numa unidade). */
  onLista: (filtro: { pendente?: boolean; critico?: boolean; unidade?: string; nivel?: string }) => void;
  onConfig: () => void;
}) {
  const [dias, setDias] = useState("90");
  const q = useApi(() => api.monitor.painel(origem, Number(dias)), [origem, dias]);
  const d = q.data;
  const ta = origem === "tripadvisor";

  if (q.loading && !d) return <Carregando />;
  if (q.error || !d) return <Aviso tipo="erro">{q.error ?? "Não foi possível carregar o painel."}</Aviso>;

  const n = d.numeros;
  const nada = situacao.origens[origem].itens === 0;

  if (nada) {
    return (
      <Vazio titulo={`Nenhum${ta ? "a avaliação do Tripadvisor" : "a reclamação do Reclame Aqui"} ainda`}>
        <p>
          Tudo aqui chega pelos e-mails de notificação da plataforma.{" "}
          {situacao.caixa.configurada
            ? `A caixa ${situacao.caixa.endereco} é lida a cada ${situacao.caixa.intervalo_min} min — falta as notificações chegarem nela.`
            : "Falta ligar a caixa de leitura no servidor — ou subir e-mails antigos (.eml) para trazer o histórico."}
        </p>
        <button onClick={onConfig} className={clsx(BOTAO_PRINCIPAL, "mt-4")}>Ver como ligar</button>
      </Vazio>
    );
  }

  const pctNeg = n.total ? Math.round((n.negativas / n.total) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <p className="text-sm text-muted">
          {situacao.caixa.ultima_leitura
            ? <>Caixa lida {desde(situacao.caixa.ultima_leitura)}.</>
            : situacao.caixa.configurada ? "A caixa ainda não foi lida." : "Caixa de leitura não ligada — só e-mails enviados à mão."}
          {n.parciais > 0 && <> {num(n.parciais)} {n.parciais === 1 ? "item veio" : "itens vieram"} incompleto{n.parciais === 1 ? "" : "s"} do e-mail.</>}
        </p>
        <div className="w-36">
          <Select aria-label="Período" value={dias} onChange={setDias} options={PERIODOS}
                  triggerClassName={clsx(CAMPO, "py-2")} />
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {ta ? (
          <>
            <Numero rotulo="Avaliações" valor={num(n.total)} apoio={`${num(n.ultimos_7d)} nos últimos 7 dias`} />
            <Numero rotulo="Nota média" valor={nota(n.media)} apoio="de 5 bolhas" />
            <Numero rotulo="Negativas (1 e 2)" valor={num(n.negativas)} apoio={`${pctNeg}% do período`}
                    destaque={n.negativas > 0} onClick={() => onLista({ nivel: "negativa" })} />
          </>
        ) : (
          <>
            <Numero rotulo="Reclamações novas" valor={num(n.reclamacoes)} apoio={`${num(n.ultimos_7d)} movimentos em 7 dias`}
                    destaque={n.reclamacoes > 0} onClick={() => onLista({ nivel: "negativa" })} />
            <Numero rotulo="Avaliadas pelo consumidor" valor={num(n.avaliadas)}
                    apoio={n.avaliadas ? `nota média ${nota(n.media)} de 10` : "ninguém avaliou no período"} />
            <Numero rotulo="Movimentos no período" valor={num(n.total)} apoio="reclamações, réplicas e avaliações" />
          </>
        )}
        <Numero rotulo="Sem tratamento" valor={num(n.pendentes)}
                apoio={`negativas e crises em aberto · ${num(n.criticos)} com palavra de crise`}
                destaque={n.pendentes > 0} onClick={() => onLista({ pendente: true })} />
      </dl>

      <div className="grid gap-3 xl:grid-cols-2">
        <Cartao titulo={ta ? "Avaliações por semana" : "Movimentos por semana"}
                descricao={ta ? "Em laranja, as negativas (nota 1 e 2)." : "Em laranja, as reclamações novas e notas baixas."}>
          <BarrasSemana semanas={d.semanas} rotulo={ta ? "avaliações" : "movimentos"} />
        </Cartao>
        {ta ? (
          <Cartao titulo="Nota média por semana" descricao="Semanas sem avaliação ficam sem ponto.">
            <LinhaMedia semanas={d.semanas} maximo={5} />
          </Cartao>
        ) : (
          <BarList
            title="Palavras de crise mais citadas"
            caption="Nas reclamações e réplicas do período."
            items={toBars(d.palavras.map((p) => ({ label: p.palavra, total: p.total })))}
            format={(i) => num(i.value)}
            accent="orange"
          />
        )}
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        <Cartao titulo={ta ? "Por unidade" : "Unidades citadas"}
                descricao={ta ? "Clique para ver as avaliações da unidade." : "Quando a reclamação cita a unidade."}>
          {d.unidades.length ? (
            <ul className="divide-y divide-line/[0.08]">
              {d.unidades.map((u) => (
                <li key={u.unidade}>
                  <button onClick={() => onLista({ unidade: u.unidade })}
                          className="flex w-full items-center gap-3 px-5 py-2.5 text-left text-sm transition hover:bg-app/70">
                    <span className="min-w-0 flex-1 truncate text-ink">{u.unidade}</span>
                    {ta && u.media != null && (
                      <span className="w-14 shrink-0 text-right text-xs text-muted [font-variant-numeric:tabular-nums]">
                        {nota(u.media)}
                      </span>
                    )}
                    <span className={clsx("w-20 shrink-0 text-right text-xs [font-variant-numeric:tabular-nums]",
                      u.negativas > 0 ? "font-bold text-domani-orange-600" : "text-muted")}>
                      {num(u.negativas)} {u.negativas === 1 ? (ta ? "negativa" : "negativo") : (ta ? "negativas" : "negativos")}
                    </span>
                    <span className="w-10 shrink-0 text-right font-semibold text-ink [font-variant-numeric:tabular-nums]">
                      {num(u.total)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="px-5 py-8 text-center text-sm text-muted">Sem dados no período.</p>}
        </Cartao>
        {ta ? (
          <div className="grid gap-3">
            <BarList
              title="Distribuição das notas"
              caption="Quantas avaliações em cada nota, no período."
              items={toBars([5, 4, 3, 2, 1].map((v) => ({
                label: `${v} ${v === 1 ? "bolha" : "bolhas"}`,
                total: d.notas.find((x) => x.nota === v)?.total ?? 0,
              })))}
              format={(i) => num(i.value)}
              accent="graphite"
            />
            {d.palavras.length > 0 && (
              <BarList
                title="Palavras de crise citadas"
                items={toBars(d.palavras.map((p) => ({ label: p.palavra, total: p.total })))}
                format={(i) => num(i.value)}
                accent="orange"
              />
            )}
          </div>
        ) : (
          <BarList
            title="Notas dadas pelo consumidor"
            caption="De 0 a 10, quando a reclamação é avaliada."
            items={toBars(d.notas.slice().reverse().map((x) => ({ label: `nota ${x.nota}`, total: x.total })))}
            format={(i) => num(i.value)}
            accent="graphite"
          />
        )}
      </div>
    </div>
  );
}

function Numero({ rotulo, valor, apoio, destaque, onClick }: {
  rotulo: string; valor: string; apoio?: React.ReactNode; destaque?: boolean; onClick?: () => void;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick}
         className={clsx("rounded-2xl border border-line/12 bg-surface px-5 py-4 text-left shadow-domani-lift",
           onClick && "transition hover:border-line/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-domani-orange")}>
      <dt className="text-xs font-semibold text-muted">{rotulo}</dt>
      <dd className={clsx("mt-1 font-display text-3xl font-extrabold tracking-tight [font-variant-numeric:tabular-nums]",
        destaque ? "text-domani-orange-600" : "text-ink")}>{valor}</dd>
      {apoio && <dd className="mt-1 text-xs text-muted">{apoio}</dd>}
    </Tag>
  );
}

// --------------------------------- gráficos ---------------------------------

const H = 220, PX0 = 34, PY0 = 16, PY1 = 188;

/**
 * Largura real do gráfico, em pixels. O SVG é desenhado na largura em que
 * aparece (e não esticado de um tamanho fixo), para o texto dos eixos ficar
 * sempre com 11px — esticado, ele virava 7px no celular.
 */
function useLargura(): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const medir = () => {
      const cs = getComputedStyle(el);
      const util = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      setW(Math.max(240, Math.floor(util)));
    };
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** Barras empilhadas por semana: laranja = negativas, neutro = o resto. */
function BarrasSemana({ semanas, rotulo }: { semanas: PainelMonitor["semanas"]; rotulo: string }) {
  const [foco, setFoco] = useState<number | null>(null);
  const [caixa, W] = useLargura();
  const PX1 = W - 10;
  if (!semanas.length) return <p className="px-5 py-10 text-center text-sm text-muted">Sem dados no período.</p>;
  const max = Math.max(1, ...semanas.map((s) => s.total));
  const passo = (PX1 - PX0) / semanas.length;
  const largura = Math.max(4, Math.min(28, passo - 6));
  const Y = (v: number) => PY1 - (v / max) * (PY1 - PY0);
  const marcas = [0, Math.ceil(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);
  const cadaRotulo = Math.max(1, Math.ceil(semanas.length / Math.max(2, Math.floor(W / 64))));
  const s = foco != null ? semanas[foco] : null;

  return (
    <div ref={caixa} className="relative px-3 pb-3 pt-2">
      <div className="flex gap-4 px-2 pb-1 text-[11px] text-muted">
        <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: LARANJA }} />negativas</span>
        <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: NEUTRO }} />demais</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="block max-w-full" role="img"
           aria-label={`${rotulo} por semana`} onMouseLeave={() => setFoco(null)}>
        {marcas.map((v) => (
          <g key={v}>
            <line x1={PX0} x2={PX1} y1={Y(v)} y2={Y(v)} stroke="rgb(var(--line) / 0.10)" />
            <text x={PX0 - 8} y={Y(v) + 4} textAnchor="end" className="fill-muted text-[11px]">{v}</text>
          </g>
        ))}
        {semanas.map((sem, i) => {
          const x = PX0 + i * passo + (passo - largura) / 2;
          const yNeg = Y(sem.negativas);
          const yTot = Y(sem.total);
          const temResto = sem.total > sem.negativas;
          return (
            <g key={sem.semana} opacity={foco == null || foco === i ? 1 : 0.55}>
              {sem.negativas > 0 && (
                <rect x={x} y={yNeg} width={largura} height={PY1 - yNeg} rx={temResto ? 0 : 3} fill={LARANJA} />
              )}
              {temResto && (
                <rect x={x} y={yTot} width={largura}
                      height={Math.max(1, (sem.negativas > 0 ? yNeg - 2 : PY1) - yTot)} rx={3} fill={NEUTRO} />
              )}
              {i % cadaRotulo === 0 && (
                <text x={x + largura / 2} y={H - 10} textAnchor="middle" className="fill-muted text-[11px]">
                  {semanaBR(sem.semana)}
                </text>
              )}
              {/* Alvo do hover maior que a barra: a semana inteira. */}
              <rect x={PX0 + i * passo} y={PY0} width={passo} height={PY1 - PY0 + 20} fill="transparent"
                    onMouseEnter={() => setFoco(i)} />
            </g>
          );
        })}
        <line x1={PX0} x2={PX1} y1={PY1} y2={PY1} stroke="rgb(var(--line) / 0.25)" />
      </svg>
      {s && foco != null && (
        <Dica x={(PX0 + foco * passo + passo / 2) / W}>
          <strong className="block">Semana de {semanaBR(s.semana)}</strong>
          {num(s.total)} {rotulo} · {num(s.negativas)} negativas
          {s.criticos > 0 && <> · {num(s.criticos)} com crise</>}
        </Dica>
      )}
    </div>
  );
}

/** Nota média por semana. Uma série só: o título diz o que é, sem legenda. */
function LinhaMedia({ semanas, maximo }: { semanas: PainelMonitor["semanas"]; maximo: number }) {
  const [foco, setFoco] = useState<number | null>(null);
  const [caixa, W] = useLargura();
  const PX1 = W - 10;
  const passo = (PX1 - PX0) / Math.max(1, semanas.length);
  const X = (i: number) => PX0 + i * passo + passo / 2;
  const Y = (v: number) => PY1 - ((v - 1) / (maximo - 1)) * (PY1 - PY0);
  const pontos = semanas.map((s, i) => (s.media != null ? { i, v: Number(s.media) } : null));
  // Segmentos só entre semanas seguidas com dado: semana vazia é buraco, não ponte.
  const trechos: { i: number; v: number }[][] = [];
  pontos.forEach((p) => {
    if (!p) { trechos.push([]); return; }
    if (!trechos.length) trechos.push([]);
    trechos[trechos.length - 1].push(p);
  });
  const cadaRotulo = Math.max(1, Math.ceil(semanas.length / Math.max(2, Math.floor(W / 64))));
  const s = foco != null ? semanas[foco] : null;

  return (
    <div ref={caixa} className="relative px-3 pb-3 pt-2">
      {!pontos.some(Boolean) ? (
        <p className="px-2 py-10 text-center text-sm text-muted">Sem notas no período.</p>
      ) : (
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="block max-w-full" role="img" aria-label="nota média por semana"
           onMouseLeave={() => setFoco(null)}>
        {Array.from({ length: maximo }, (_, k) => k + 1).map((v) => (
          <g key={v}>
            <line x1={PX0} x2={PX1} y1={Y(v)} y2={Y(v)} stroke="rgb(var(--line) / 0.10)" />
            <text x={PX0 - 8} y={Y(v) + 4} textAnchor="end" className="fill-muted text-[11px]">{v}</text>
          </g>
        ))}
        {trechos.filter((t) => t.length > 1).map((t, k) => (
          <polyline key={k} fill="none" stroke="rgb(var(--ink))" strokeWidth={2} strokeLinejoin="round"
                    points={t.map((p) => `${X(p.i)},${Y(p.v)}`).join(" ")} />
        ))}
        {pontos.map((p) => p && (
          <circle key={p.i} cx={X(p.i)} cy={Y(p.v)} r={foco === p.i ? 5 : 4}
                  fill={p.v <= 2 ? LARANJA : "rgb(var(--ink))"} stroke="rgb(var(--surface))" strokeWidth={2} />
        ))}
        {semanas.map((sem, i) => (
          <g key={sem.semana}>
            {i % cadaRotulo === 0 && (
              <text x={X(i)} y={H - 10} textAnchor="middle" className="fill-muted text-[11px]">{semanaBR(sem.semana)}</text>
            )}
            <rect x={PX0 + i * passo} y={PY0} width={passo} height={PY1 - PY0 + 20} fill="transparent"
                  onMouseEnter={() => setFoco(i)} />
          </g>
        ))}
        {foco != null && <line x1={X(foco)} x2={X(foco)} y1={PY0} y2={PY1} stroke="rgb(var(--line) / 0.25)" />}
      </svg>
      )}
      {s && foco != null && (
        <Dica x={X(foco) / W}>
          <strong className="block">Semana de {semanaBR(s.semana)}</strong>
          {s.media != null ? `média ${nota(s.media)} · ${num(s.total)} avaliações` : "sem avaliação nesta semana"}
        </Dica>
      )}
    </div>
  );
}

function Dica({ x, children }: { x: number; children: React.ReactNode }) {
  return (
    <div className="pointer-events-none absolute top-8 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg bg-domani-graphite px-3 py-2 text-xs text-white shadow-lg dark:bg-white dark:text-domani-graphite"
         style={{ left: `${Math.min(85, Math.max(15, x * 100))}%` }}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lista
// ---------------------------------------------------------------------------

export interface FiltroMonitor {
  pendente?: boolean;
  critico?: boolean;
  unidade?: string;
  nivel?: string;
}

const POR_PAGINA = 30;

export function MonitorLista({ origem, itemId, filtroInicial, onAbrir }: {
  origem: OrigemMonitor;
  itemId: number | null;
  filtroInicial: FiltroMonitor;
  onAbrir: (id: number | null) => void;
}) {
  const ta = origem === "tripadvisor";
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [unidade, setUnidade] = useState(filtroInicial.unidade ?? "");
  const [nivel, setNivel] = useState(filtroInicial.nivel ?? "");
  const [tipo, setTipo] = useState("");
  const [soCrise, setSoCrise] = useState(!!filtroInicial.critico);
  const [soPendente, setSoPendente] = useState(!!filtroInicial.pendente);
  const [pagina, setPagina] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => { setBuscaAplicada(busca.trim()); setPagina(1); }, 350);
    return () => clearTimeout(t);
  }, [busca]);

  const unidades = useApi(() => api.monitor.painel(origem, 365), [origem]);
  const lista = useApi(() => api.monitor.itens(origem, {
    busca: buscaAplicada, unidade, nivel, tipo,
    critico: soCrise || undefined, pendente: soPendente || undefined,
    page: pagina, page_size: POR_PAGINA,
  }), [origem, buscaAplicada, unidade, nivel, tipo, soCrise, soPendente, pagina]);

  const total = lista.data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / POR_PAGINA));
  const mudou = (f: () => void) => { f(); setPagina(1); };

  return (
    <div className="space-y-3">
      <section className="grid gap-2 rounded-2xl border border-line/12 bg-surface p-3 shadow-domani-lift sm:grid-cols-2 lg:grid-cols-4">
        <label className="relative block">
          <span className="sr-only">Buscar</span>
          <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/35" strokeWidth={2} />
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar no texto ou autor"
                 className={clsx(CAMPO, "pl-9")} />
        </label>
        <Select aria-label="Unidade" value={unidade} onChange={(v) => mudou(() => setUnidade(v))} triggerClassName={CAMPO}
                options={[{ value: "", label: "Todas as unidades" },
                  ...(unidades.data?.unidades ?? []).map((u) => ({ value: u.unidade, label: u.unidade }))]} />
        {ta ? (
          <Select aria-label="Nota" value={nivel} onChange={(v) => mudou(() => setNivel(v))} triggerClassName={CAMPO}
                  options={[{ value: "", label: "Todas as notas" }, { value: "negativa", label: "Negativas (1 e 2)" },
                    { value: "neutra", label: "Neutras (3)" }, { value: "positiva", label: "Positivas (4 e 5)" }]} />
        ) : (
          <Select aria-label="Tipo" value={tipo} onChange={(v) => mudou(() => setTipo(v))} triggerClassName={CAMPO}
                  options={[{ value: "", label: "Todos os movimentos" }, { value: "reclamacao", label: "Reclamações novas" },
                    { value: "interacao", label: "Réplicas do consumidor" }, { value: "resultado", label: "Avaliadas pelo consumidor" }]} />
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Alternar ativo={soCrise} onClick={() => mudou(() => setSoCrise(!soCrise))}>Só crises</Alternar>
          <Alternar ativo={soPendente} onClick={() => mudou(() => setSoPendente(!soPendente))}>Sem tratamento</Alternar>
        </div>
      </section>

      {lista.loading && !lista.data ? <Carregando /> : lista.error ? (
        <Aviso tipo="erro">{lista.error}</Aviso>
      ) : !lista.data?.items.length ? (
        <Vazio titulo="Nada com esses filtros">Limpe a busca ou troque o filtro.</Vazio>
      ) : (
        <Cartao titulo={`${num(total)} ${ta ? (total === 1 ? "avaliação" : "avaliações") : (total === 1 ? "movimento" : "movimentos")}`}
                descricao="Do mais recente para o mais antigo. Responder é na própria plataforma.">
          <ul className="divide-y divide-line/[0.08]">
            {lista.data.items.map((it) => (
              <li key={it.id}>
                <LinhaItem item={it} onAbrir={() => onAbrir(it.id)} />
              </li>
            ))}
          </ul>
          {total > POR_PAGINA && (
            <div className="flex items-center justify-between gap-3 border-t border-line/10 px-5 py-3 text-sm">
              <span className="text-muted [font-variant-numeric:tabular-nums]">página {pagina} de {paginas}</span>
              <div className="flex gap-2">
                <button disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)} className={clsx(BOTAO_SECUNDARIO, "px-3 py-1.5")}>Anterior</button>
                <button disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)} className={clsx(BOTAO_SECUNDARIO, "px-3 py-1.5")}>Próxima</button>
              </div>
            </div>
          )}
        </Cartao>
      )}

      {itemId != null && (
        <DetalheItem id={itemId} unidades={(unidades.data?.unidades ?? []).map((u) => u.unidade)}
                     onFechar={() => onAbrir(null)} onMudou={lista.reload} />
      )}
    </div>
  );
}

function Alternar({ ativo, onClick, children }: { ativo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={ativo}
            className={clsx("rounded-full px-3 py-1.5 text-xs font-bold transition",
              ativo ? "bg-domani-graphite text-white dark:bg-white dark:text-domani-graphite" : "border border-line/20 text-ink/75 hover:bg-app")}>
      {children}
    </button>
  );
}

function SeloNota({ item }: { item: ItemMonitor }) {
  if (item.nota == null) {
    return (
      <span className={clsx("inline-flex h-[30px] shrink-0 items-center justify-center rounded-lg px-2 text-[10px] font-bold uppercase",
        item.nivel === "negativa" ? "bg-domani-orange text-domani-graphite" : "bg-line/[0.08] text-ink/70")}>
        {item.tipo === "reclamacao" ? "RA" : item.tipo === "interacao" ? "Réplica" : "—"}
      </span>
    );
  }
  const baixa = item.nivel === "negativa";
  return (
    <span aria-label={`Nota ${nota(item.nota, item.nota_maxima)}`}
          className={clsx("inline-flex h-[30px] min-w-[30px] shrink-0 items-center justify-center rounded-lg px-1 font-display text-sm font-extrabold [font-variant-numeric:tabular-nums]",
            baixa ? "bg-domani-orange text-domani-graphite" : "bg-line/[0.08] text-ink")}>
      {Number(item.nota).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}
    </span>
  );
}

function LinhaItem({ item, onAbrir }: { item: ItemMonitor; onAbrir: () => void }) {
  return (
    <button onClick={onAbrir}
            className="group relative flex w-full items-start gap-3 px-5 py-3.5 text-left transition hover:bg-app/70 focus:outline-none focus-visible:bg-app">
      {item.critico && !item.tratado_em && (
        <i aria-hidden="true" className="absolute inset-y-0 left-0 w-1 bg-domani-orange" />
      )}
      <SeloNota item={item} />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-semibold text-ink">{item.titulo || TIPO[item.tipo]}</span>
          {item.critico && (
            <span className="rounded-full bg-domani-orange/15 px-2 py-0.5 text-[10px] font-bold uppercase text-domani-orange-600">
              crise · {item.palavras.join(", ")}
            </span>
          )}
          {item.tratado_em && <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-700 dark:text-emerald-400">tratado</span>}
          {item.extraido_por === "parcial" && <span className="rounded-full bg-line/10 px-2 py-0.5 text-[10px] font-bold uppercase text-ink/60">incompleto</span>}
        </span>
        <span className="mt-0.5 line-clamp-2 block text-sm text-ink/75">{item.texto || "Sem texto no e-mail."}</span>
        <span className="mt-1 block text-xs text-muted">
          {[TIPO[item.tipo], item.unidade, item.autor, item.cidade, quando(item.ocorrido_em)].filter(Boolean).join(" · ")}
        </span>
      </span>
      <Icon name="chevronRight" className="mt-1 h-4 w-4 shrink-0 text-ink/30 transition group-hover:text-ink/70" strokeWidth={2} />
    </button>
  );
}

function DetalheItem({ id, unidades, onFechar, onMudou }: {
  id: number; unidades: string[]; onFechar: () => void; onMudou: () => void;
}) {
  const q = useApi(() => api.monitor.detalhe(id), [id]);
  const [obs, setObs] = useState("");
  const [unidade, setUnidade] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [verEmail, setVerEmail] = useState(false);
  const d = q.data;

  useEffect(() => {
    if (d) { setObs(d.observacao ?? ""); setUnidade(d.unidade ?? ""); }
  }, [d]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onFechar(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onFechar]);

  async function salvar(patch: { tratado?: boolean; observacao?: string | null; unidade?: string | null }) {
    setSalvando(true);
    setErro(null);
    try {
      await api.monitor.marcar(id, patch);
      q.reload();
      onMudou();
    } catch (e) {
      setErro(mensagemDe(e, "Não deu para salvar."));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 animate-overlay-fade bg-domani-ink/45 backdrop-blur-sm" onClick={onFechar} />
      <aside className="relative flex h-full w-full max-w-xl flex-col overflow-y-auto bg-surface shadow-2xl" role="dialog" aria-label="Detalhe">
        <div className="flex items-center justify-between gap-3 border-b border-line/15 px-5 py-4">
          <h2 className="font-display text-lg font-extrabold text-ink">{d ? TIPO[d.tipo] : "Carregando"}</h2>
          <button onClick={onFechar} aria-label="Fechar" className="rounded-lg p-2 text-ink/50 transition hover:bg-app hover:text-ink">
            <Icon name="close" className="h-4 w-4" strokeWidth={2} />
          </button>
        </div>

        {q.loading && !d ? <div className="p-5"><Carregando /></div> : q.error || !d ? (
          <div className="p-5"><Aviso tipo="erro">{q.error ?? "Não encontrado."}</Aviso></div>
        ) : (
          <div className="space-y-4 px-5 py-5">
            <div className="flex items-start gap-3">
              <SeloNota item={d} />
              <div className="min-w-0">
                <p className="font-display text-base font-extrabold text-ink">{d.titulo || "Sem título"}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {[d.autor, d.cidade, quandoCompleto(d.ocorrido_em)].filter(Boolean).join(" · ")}
                </p>
              </div>
            </div>

            {d.critico && (
              <Aviso tipo="atencao">
                <strong>Palavra de crise:</strong> {d.palavras.join(", ")}.
                {d.avisado_em && <> Aviso enviado ao NichoChat {quando(d.avisado_em)}.</>}
              </Aviso>
            )}

            <p className="whitespace-pre-line text-sm leading-relaxed text-ink">{d.texto || "O e-mail não trouxe o texto. Veja o e-mail original abaixo ou abra na plataforma."}</p>

            {d.extraido_por !== "regra" && (
              <p className="text-xs text-muted">
                {d.extraido_por === "ia"
                  ? "Parte destes dados foi completada pela IA a partir do próprio e-mail."
                  : "O e-mail não trouxe todos os campos. O original está guardado logo abaixo."}
              </p>
            )}

            {d.link && (
              <a href={d.link} target="_blank" rel="noreferrer" className={clsx(BOTAO_PRINCIPAL, "w-full")}>
                Abrir no {NOME_MONITOR[d.origem]} para responder
              </a>
            )}

            <section className="space-y-3 rounded-2xl bg-app p-4">
              <label className="block">
                <span className="mb-1.5 block text-xs font-bold text-ink/70">Unidade</span>
                <div className="flex gap-2">
                  <input list={`unidades-${id}`} value={unidade} onChange={(e) => setUnidade(e.target.value)}
                         placeholder="Qual unidade" className={CAMPO} />
                  <datalist id={`unidades-${id}`}>
                    {unidades.map((u) => <option key={u} value={u} />)}
                  </datalist>
                  <button disabled={salvando || unidade === (d.unidade ?? "")}
                          onClick={() => salvar({ unidade: unidade || null })} className={BOTAO_SECUNDARIO}>
                    Salvar
                  </button>
                </div>
                {d.loja_id && (
                  <span className="mt-1 block text-[11px] text-muted">
                    Corrigir aqui vale para todas as avaliações deste local do Tripadvisor, inclusive as próximas.
                  </span>
                )}
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-bold text-ink/70">Observação interna</span>
                <textarea rows={3} value={obs} onChange={(e) => setObs(e.target.value)}
                          placeholder="O que foi feito, com quem falou…" className={CAMPO} />
              </label>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-muted">
                  {d.tratado_em ? `Tratado ${quando(d.tratado_em)}${d.tratado_por ? ` por ${d.tratado_por}` : ""}.` : "Ainda não tratado."}
                </span>
                <div className="flex gap-2">
                  {obs !== (d.observacao ?? "") && (
                    <button disabled={salvando} onClick={() => salvar({ observacao: obs })} className={BOTAO_SECUNDARIO}>
                      Salvar observação
                    </button>
                  )}
                  <button disabled={salvando}
                          onClick={() => salvar({ tratado: !d.tratado_em, ...(obs !== (d.observacao ?? "") ? { observacao: obs } : {}) })}
                          className={d.tratado_em ? BOTAO_SECUNDARIO : BOTAO_PRINCIPAL}>
                    {d.tratado_em ? "Reabrir" : "Marcar como tratado"}
                  </button>
                </div>
              </div>
              {erro && <Aviso tipo="erro">{erro}</Aviso>}
            </section>

            {d.email_texto && (
              <section>
                <button onClick={() => setVerEmail(!verEmail)} className="text-xs font-bold text-ink/60 hover:text-ink">
                  {verEmail ? "Esconder" : "Ver"} o e-mail original
                </button>
                {verEmail && (
                  <div className="mt-2 rounded-2xl border border-line/12 p-4">
                    <p className="text-xs text-muted">{d.email_remetente} · {d.email_assunto}</p>
                    <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap font-sans text-xs text-ink/75">{d.email_texto}</pre>
                  </div>
                )}
              </section>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Configuração
// ---------------------------------------------------------------------------

const AVISOS: { value: AvisoMonitor; label: string }[] = [
  { value: "negativos", label: "Crise e nota baixa / reclamação nova" },
  { value: "criticos", label: "Só quando tiver palavra de crise" },
  { value: "todos", label: "Tudo o que chegar" },
  { value: "nenhum", label: "Não avisar" },
];

export function MonitorConfig({ origem, situacao, podeConfigurar, onMudou }: {
  origem: OrigemMonitor;
  situacao: SituacaoMonitor;
  podeConfigurar: boolean;
  onMudou: () => void;
}) {
  return (
    <div className="space-y-3">
      <Caixa situacao={situacao} podeConfigurar={podeConfigurar} onMudou={onMudou} />
      <AvisoNichoChat key={origem} origem={origem} situacao={situacao} podeConfigurar={podeConfigurar} onMudou={onMudou} />
      <Palavras situacao={situacao} podeConfigurar={podeConfigurar} onMudou={onMudou} />
      <ImportarEmails onMudou={onMudou} />
      <EmailsNaoAproveitados podeConfigurar={podeConfigurar} onMudou={onMudou} />
    </div>
  );
}

function Caixa({ situacao, podeConfigurar, onMudou }: {
  situacao: SituacaoMonitor; podeConfigurar: boolean; onMudou: () => void;
}) {
  const c = situacao.caixa;
  const [lendo, setLendo] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);

  async function ler() {
    setLendo(true);
    setMsg(null);
    try {
      await api.monitor.ler();
      setMsg({ tipo: "ok", texto: "Leitura iniciada. Os números atualizam em alguns segundos." });
      setTimeout(onMudou, 6000);
    } catch (e) {
      setMsg({ tipo: "erro", texto: mensagemDe(e, "Não deu para iniciar a leitura.") });
    } finally {
      setLendo(false);
    }
  }

  return (
    <Cartao titulo="Caixa de leitura"
            descricao="O CRM lê os e-mails de notificação que o Tripadvisor e o Reclame Aqui mandam para a empresa."
            acoes={c.configurada && podeConfigurar ? (
              <button onClick={ler} disabled={lendo || c.lendo} className={clsx(BOTAO_SECUNDARIO, "px-3 py-1.5 text-xs")}>
                <Icon name="refresh" className="h-3.5 w-3.5" strokeWidth={2} />
                {c.lendo ? "Lendo…" : "Ler agora"}
              </button>
            ) : undefined}>
      <div className="space-y-3 px-5 py-4 text-sm">
        <p className="flex flex-wrap gap-2">
          <Selo ok={c.configurada}>{c.configurada ? `lendo ${c.endereco}` : "caixa não configurada"}</Selo>
          {c.configurada && <Selo ok={c.agendada}>{c.agendada ? `a cada ${c.intervalo_min} min` : "leitura automática desligada"}</Selo>}
          <Selo ok={situacao.ia}>{situacao.ia ? "IA completa o que faltar" : "sem IA para completar"}</Selo>
        </p>
        {c.configurada && (
          <p className="text-muted">
            Servidor {c.servidor}, pasta {c.pasta}. Última leitura: {c.ultima_leitura ? `${quandoCompleto(c.ultima_leitura)} (${desde(c.ultima_leitura)})` : "nunca"}.
            {" "}{num(situacao.emails.processados)} e-mails aproveitados até agora.
          </p>
        )}
        {c.ultimo_erro && <Aviso tipo="erro">Última tentativa ({quando(c.ultimo_erro_em)}): {c.ultimo_erro}</Aviso>}
        {msg && <Aviso tipo={msg.tipo}>{msg.texto}</Aviso>}
        {!c.configurada && (
          <ol className="list-decimal space-y-1.5 pl-5 text-ink/80">
            <li>Crie uma caixa só para isso (ex.: <strong>avaliacoes@seucliente.com.br</strong>) e gere uma <strong>senha de app</strong> para ela.</li>
            <li>Faça as notificações chegarem nela: cadastre esse e-mail como usuário no Management Center do Tripadvisor e no painel do Reclame Aqui, <em>ou</em> crie uma regra de encaminhamento automático na caixa que recebe hoje.</li>
            <li>No servidor, preencha <code className="rounded bg-app px-1">MONITOR_IMAP_HOST</code>, <code className="rounded bg-app px-1">MONITOR_IMAP_USUARIO</code> e <code className="rounded bg-app px-1">MONITOR_IMAP_SENHA</code> no .env e reinicie a API.</li>
            <li>Na primeira leitura o CRM busca os últimos 180 dias da caixa — o histórico entra junto, sem disparar aviso.</li>
          </ol>
        )}
      </div>
    </Cartao>
  );
}

function AvisoNichoChat({ origem, situacao, podeConfigurar, onMudou }: {
  origem: OrigemMonitor; situacao: SituacaoMonitor; podeConfigurar: boolean; onMudou: () => void;
}) {
  const cfg = situacao.origens[origem].config;
  const [ativo, setAtivo] = useState(cfg.ativo);
  const [aviso, setAviso] = useState<AvisoMonitor>(cfg.aviso);
  const [url, setUrl] = useState(cfg.webhook_url ?? "");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const mudou = ativo !== cfg.ativo || aviso !== cfg.aviso || url !== (cfg.webhook_url ?? "");

  async function salvar() {
    setSalvando(true);
    setMsg(null);
    try {
      await api.monitor.salvarConfig(origem, { ativo, aviso, webhook_url: url.trim() || null });
      setMsg({ tipo: "ok", texto: "Salvo." });
      onMudou();
    } catch (e) {
      setMsg({ tipo: "erro", texto: mensagemDe(e, "Não deu para salvar.") });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Cartao titulo={`Aviso no NichoChat · ${NOME_MONITOR[origem]}`}
            descricao="O que chega aqui pode disparar um fluxo no NichoChat (WhatsApp para a gestão). O aviso leva unidade, nota, texto, se é crise e o link.">
      <div className="grid gap-3 px-5 py-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-xs font-bold text-ink/70">Quando avisar</span>
          <Select aria-label="Quando avisar" value={aviso} onChange={(v) => setAviso(v as AvisoMonitor)}
                  options={AVISOS} triggerClassName={CAMPO} />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-xs font-bold text-ink/70">Webhook do fluxo (NichoChat)</span>
          <input value={url} onChange={(e) => setUrl(e.target.value)} disabled={!podeConfigurar}
                 placeholder="https://app.estudiodomani.com/api/iwh/…" className={CAMPO} />
        </label>
        <label className="flex items-center gap-2 text-sm text-ink sm:col-span-2">
          <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} disabled={!podeConfigurar} />
          Monitorar o {NOME_MONITOR[origem]} (desligado, os e-mails continuam guardados mas ninguém é avisado)
        </label>
        <p className="text-xs text-muted sm:col-span-2">
          Só avisa o que aconteceu nas últimas 48 horas: histórico importado não dispara alarme. No fluxo,
          use <code>critico</code> para mandar à diretoria e <code>nivel</code> = negativa para o atendimento.
        </p>
        {msg && <Aviso tipo={msg.tipo} className="sm:col-span-2">{msg.texto}</Aviso>}
        {podeConfigurar && (
          <div className="flex justify-end sm:col-span-2">
            <button onClick={salvar} disabled={!mudou || salvando} className={BOTAO_PRINCIPAL}>
              {salvando ? "Salvando…" : "Salvar"}
            </button>
          </div>
        )}
      </div>
    </Cartao>
  );
}

function Palavras({ situacao, podeConfigurar, onMudou }: {
  situacao: SituacaoMonitor; podeConfigurar: boolean; onMudou: () => void;
}) {
  const [lista, setLista] = useState<string[]>(situacao.palavras);
  const [nova, setNova] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const original = useRef(situacao.palavras.join("|"));
  const mudou = lista.join("|") !== original.current;

  function adicionar() {
    const partes = nova.split(",").map((p) => p.trim()).filter(Boolean);
    if (!partes.length) return;
    setLista([...lista, ...partes.filter((p) => !lista.some((x) => x.toLowerCase() === p.toLowerCase()))]);
    setNova("");
  }

  async function salvar() {
    setSalvando(true);
    setMsg(null);
    try {
      const r = await api.monitor.salvarPalavras(lista);
      original.current = r.palavras.join("|");
      setLista(r.palavras);
      setMsg({ tipo: "ok", texto: `Salvo. ${num(r.itens_recalculados)} itens do histórico foram reclassificados.` });
      onMudou();
    } catch (e) {
      setMsg({ tipo: "erro", texto: mensagemDe(e, "Não deu para salvar.") });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Cartao titulo="Palavras de crise"
            descricao="Valem para as duas plataformas. Pegam pelo começo da palavra e sem acento: “intoxica” pega “intoxicação”.">
      <div className="space-y-3 px-5 py-4">
        <div className="flex flex-wrap gap-1.5">
          {lista.map((p) => (
            <span key={p} className="inline-flex items-center gap-1 rounded-full bg-domani-orange/10 px-2.5 py-1 text-xs font-semibold text-ink">
              {p}
              {podeConfigurar && (
                <button onClick={() => setLista(lista.filter((x) => x !== p))} aria-label={`Tirar ${p}`}
                        className="text-ink/45 hover:text-ink">
                  <Icon name="close" className="h-3 w-3" strokeWidth={2.4} />
                </button>
              )}
            </span>
          ))}
        </div>
        {podeConfigurar && (
          <div className="flex gap-2">
            <input value={nova} onChange={(e) => setNova(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); adicionar(); } }}
                   placeholder="Nova palavra (separe várias por vírgula)" className={CAMPO} />
            <button onClick={adicionar} className={BOTAO_SECUNDARIO}>Adicionar</button>
          </div>
        )}
        {msg && <Aviso tipo={msg.tipo}>{msg.texto}</Aviso>}
        {podeConfigurar && (
          <div className="flex justify-end">
            <button onClick={salvar} disabled={!mudou || salvando} className={BOTAO_PRINCIPAL}>
              {salvando ? "Salvando…" : "Salvar palavras"}
            </button>
          </div>
        )}
      </div>
    </Cartao>
  );
}

function ImportarEmails({ onMudou }: { onMudou: () => void }) {
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [rel, setRel] = useState<ImportacaoMonitor | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar() {
    setEnviando(true);
    setErro(null);
    try {
      setRel(await api.monitor.importar(arquivos));
      setArquivos([]);
      onMudou();
    } catch (e) {
      setErro(mensagemDe(e, "Não deu para importar."));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Cartao titulo="Importar e-mails"
            descricao="Para trazer o histórico ou testar com um e-mail real: .eml (no Gmail, ⋮ → Fazer download da mensagem), .mbox ou .zip com vários .eml. Não dispara aviso.">
      <div className="space-y-3 px-5 py-4">
        <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line/30 bg-app/40 px-4 py-6 text-center transition hover:border-domani-orange/50">
          <Icon name="upload" className="h-7 w-7 text-ink/35" strokeWidth={1.6} />
          <span className="text-sm font-semibold text-ink">
            {arquivos.length ? `${arquivos.length} arquivo(s) escolhido(s)` : "Clique para escolher os arquivos"}
          </span>
          <input type="file" multiple accept=".eml,.mbox,.zip,message/rfc822" className="sr-only"
                 onChange={(e) => setArquivos(Array.from(e.target.files ?? []))} />
        </label>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {rel && (
          <Aviso tipo={rel.novos ? "ok" : "info"}>
            {num(rel.lidos)} e-mails lidos: {num(rel.novos)} novos ({num(rel.criticos)} com crise),{" "}
            {num(rel.repetidos)} já estavam aqui, {num(rel.ignorados)} não eram avaliação nem reclamação.
            {rel.erros.length > 0 && <span className="mt-1 block">{rel.erros.slice(0, 5).join(" · ")}</span>}
          </Aviso>
        )}
        <div className="flex justify-end">
          <button onClick={enviar} disabled={!arquivos.length || enviando} className={BOTAO_PRINCIPAL}>
            {enviando ? "Importando…" : "Importar"}
          </button>
        </div>
      </div>
    </Cartao>
  );
}

function EmailsNaoAproveitados({ podeConfigurar, onMudou }: { podeConfigurar: boolean; onMudou: () => void }) {
  const q = useApi(() => api.monitor.emails(), []);
  const [rodando, setRodando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const linhas = useMemo(() => q.data ?? [], [q.data]);

  async function reprocessar() {
    setRodando(true);
    setMsg(null);
    try {
      const r = await api.monitor.reprocessar();
      setMsg(`${num(r.emails)} e-mails relidos: ${num(r.atualizados)} atualizados, ${num(r.novos)} novos.`);
      q.reload();
      onMudou();
    } catch (e) {
      setMsg(mensagemDe(e, "Não deu para reprocessar."));
    } finally {
      setRodando(false);
    }
  }

  return (
    <Cartao titulo="E-mails não aproveitados"
            descricao="Chegaram na caixa mas não viraram avaliação nem reclamação — e por quê. Se aparecer aqui algo que deveria ter entrado, mande o .eml para ajustarmos a leitura."
            acoes={podeConfigurar ? (
              <button onClick={reprocessar} disabled={rodando} className={clsx(BOTAO_SECUNDARIO, "px-3 py-1.5 text-xs")}>
                {rodando ? "Relendo…" : "Reler todos os e-mails"}
              </button>
            ) : undefined}>
      {msg && <div className="px-5 pt-3"><Aviso>{msg}</Aviso></div>}
      {q.loading && !q.data ? <div className="p-5"><Carregando /></div> : !linhas.length ? (
        <p className="px-5 py-8 text-center text-sm text-muted">Nenhum até agora.</p>
      ) : (
        <ul className="divide-y divide-line/[0.08]">
          {linhas.map((e) => (
            <li key={e.id} className="px-5 py-3 text-sm">
              <p className="truncate font-semibold text-ink">{e.assunto || "(sem assunto)"}</p>
              <p className="truncate text-xs text-muted">
                {[e.remetente, quando(e.enviado_em ?? e.lido_em), e.via === "upload" ? "enviado à mão" : null].filter(Boolean).join(" · ")}
              </p>
              {e.motivo && <p className="mt-0.5 text-xs text-ink/70">{e.motivo}</p>}
            </li>
          ))}
        </ul>
      )}
    </Cartao>
  );
}
