"use client";

import { useState } from "react";

import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { brl, brlCompact, num, lerData } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const ACCENT = "#E56D23";
// Área de plotagem. O viewBox vai até 812 para sobrar margem à direita e o rótulo
// do último valor caber sem ser cortado.
const X0 = 60, X1 = 720, Y0 = 40, Y1 = 250;

const JANELAS = [
  { value: "7", label: "7 dias" },
  { value: "30", label: "30 dias" },
  { value: "90", label: "90 dias" },
];

/** Mantém o rótulo dentro da área do gráfico, sem escapar por cima ou por baixo. */
const clampY = (y: number) => Math.max(Y0 + 8, Math.min(Y1 - 4, y));

function fmtDia(iso: string) {
  // lerData: "2026-10-07" puro viraria 06/10 no fuso do Brasil.
  const d = lerData(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

/**
 * Faturamento por dia e itens mais vendidos.
 *
 * Vem do PDV (Alpha Code) via webhook. Enquanto ele não enviar nada, mostra o
 * estado real — "aguardando o PDV" — em vez de um gráfico zerado, que daria a
 * impressão errada de que não houve venda.
 *
 * Mesmo desenho da curva de interações, para as duas lerem igual.
 */
export function ConsumoCurva() {
  const [dias, setDias] = useState("30");
  const { data, loading, error } = useApi(
    () => api.dashboard.consumo(Number(dias)),
    [dias],
  );

  const serie = data?.serie ?? [];
  const itens = data?.itens ?? [];
  const valores = serie.map((p) => Number(p.faturamento ?? 0));
  const max = Math.max(1, ...valores);
  const total = valores.reduce((s, v) => s + v, 0);
  const pedidos = serie.reduce((s, p) => s + p.pedidos, 0);
  const ticket = pedidos ? total / pedidos : 0;

  const X = (i: number) =>
    serie.length <= 1 ? X0 : X0 + (i / (serie.length - 1)) * (X1 - X0);
  const Y = (v: number) => Y1 - (v / max) * (Y1 - Y0);

  const pts = serie.map((p, i) => `${X(i).toFixed(1)},${Y(Number(p.faturamento ?? 0)).toFixed(1)}`).join(" ");
  const area = serie.length ? `${X0},${Y1} ${pts} ${X(serie.length - 1)},${Y1}` : "";
  const last = serie.length ? [X(serie.length - 1), Y(Number(serie[serie.length - 1].faturamento ?? 0))] : null;

  // Rótulo do último valor: vai para a margem direita, e sobe ou desce conforme o
  // ponto esteja na metade de baixo ou de cima — nunca encosta na curva.
  const lastLabel = last ? brlCompact(Number(serie[serie.length - 1].faturamento ?? 0)) : "";
  const labelAcima = last ? last[1] > (Y0 + Y1) / 2 : true;
  const labelY = last ? clampY(labelAcima ? last[1] - 12 : last[1] + 18) : 0;
  const labelX = last ? last[0] + 10 : 0;
  const labelW = Math.max(46, lastLabel.length * 8);

  return (
    <div className="grid gap-px overflow-hidden rounded-2xl border border-line/10 bg-line/10 shadow-domani-lift lg:grid-cols-[minmax(0,1fr)_240px]">
      <div className="bg-surface">
        <div className="flex items-start justify-between gap-3 border-b border-line/10 px-5 py-4">
          <div>
            <h3 className="font-display text-[15px] font-extrabold tracking-tight text-ink">
              Faturamento por dia
            </h3>
            <p className="mt-0.5 text-[11.5px] text-muted">
              Pedidos registrados no PDV
            </p>
          </div>
          <span className="flex items-center gap-1.5 text-[11px] text-muted">
            <i className="inline-block h-0 w-4 border-t-2" style={{ borderColor: ACCENT }} />
            faturamento
          </span>
        </div>

        <div className="px-3 py-3">
          {loading ? (
            <div className="skeleton m-3 h-64 rounded-xl" />
          ) : error ? (
            <p className="px-5 py-16 text-center text-sm text-red-500">{error}</p>
          ) : serie.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <p className="font-semibold text-ink">Aguardando o PDV</p>
              <p className="mt-1 text-sm text-muted">
                Assim que o PDV enviar os primeiros pedidos, o faturamento
                aparece aqui.
              </p>
            </div>
          ) : (
            <svg viewBox="0 0 812 290" preserveAspectRatio="xMidYMid meet"
                 className="h-auto w-full" role="img"
                 aria-label={`Faturamento por dia nos últimos ${dias} dias`}>
              <defs>
                <linearGradient id="fillConsumo" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={ACCENT} stopOpacity="0.34" />
                  <stop offset="100%" stopColor={ACCENT} stopOpacity="0" />
                </linearGradient>
              </defs>

              <g className="text-ink/10" stroke="currentColor" strokeWidth="1">
                {[40, 92.5, 145, 197.5, 250].map((y) => (
                  <line key={y} x1={X0} y1={y} x2={X1} y2={y} />
                ))}
              </g>

              <g className="fill-muted font-display text-[9px]" textAnchor="end">
                {[0, 1, 2, 3, 4].map((k) => (
                  <text key={k} x={X0 - 8} y={44 + k * 52.5}>
                    {brlCompact(max * (1 - k / 4))}
                  </text>
                ))}
              </g>

              <polygon fill="url(#fillConsumo)" points={area} />
              <polyline fill="none" stroke={ACCENT} strokeWidth="2.6"
                        strokeLinejoin="round" strokeLinecap="round" points={pts} />

              {last && (
                <>
                  <circle cx={last[0]} cy={last[1]} r="5" fill={ACCENT}
                          strokeWidth="2.5" style={{ stroke: "rgb(var(--surface))" }} />
                  <rect x={labelX - 4} y={labelY - 11} width={labelW} height="16" rx="8"
                        fill="rgb(var(--surface))" fillOpacity="0.9" />
                  <text x={labelX} y={labelY} textAnchor="start" fill={ACCENT}
                        className="font-display text-[11.5px] font-bold">
                    {lastLabel}
                  </text>
                </>
              )}

              {/* Eixo de datas: só as pontas e o meio — com 30 pontos, todas as
                  datas viram borrão ilegível. */}
              <g className="fill-muted font-display text-[9px]" textAnchor="middle">
                <text x={X0} y="268">{fmtDia(serie[0].data)}</text>
                {serie.length > 2 && (
                  <text x={(X0 + X1) / 2} y="268">
                    {fmtDia(serie[Math.floor(serie.length / 2)].data)}
                  </text>
                )}
                {serie.length > 1 && (
                  <text x={X1} y="268">{fmtDia(serie[serie.length - 1].data)}</text>
                )}
              </g>
            </svg>
          )}
        </div>
      </div>

      <div className="space-y-4 bg-surface px-5 py-5">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-domani-orange-600">
          Período
        </p>

        <Select aria-label="Janela" value={dias} onChange={setDias} options={JANELAS}
                triggerClassName="rounded-xl border border-line/15 bg-app px-3 py-2.5 text-sm font-semibold text-ink" />

        <div className="h-px bg-line/10" />

        <dl className="space-y-2.5 text-sm">
          <Linha termo="Faturamento" valor={total ? brl(total) : "—"} destaque />
          <Linha termo="Pedidos" valor={num(pedidos)} />
          <Linha termo="Ticket médio" valor={ticket ? brl(ticket) : "—"} />
        </dl>

        {itens.length > 0 && (
          <>
            <div className="h-px bg-line/10" />
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
                Mais vendidos
              </p>
              <ul className="mt-2 space-y-1.5">
                {itens.slice(0, 5).map((i) => (
                  <li key={i.nome} className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="truncate text-ink/80" title={i.nome}>{i.nome}</span>
                    <span className="shrink-0 font-semibold text-ink [font-variant-numeric:tabular-nums]">
                      {num(Number(i.quantidade ?? 0))}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Linha({
  termo, valor, destaque,
}: {
  termo: string;
  valor: string;
  destaque?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs text-muted">{termo}</dt>
      <dd className={`font-display text-sm font-bold [font-variant-numeric:tabular-nums] ${
        destaque ? "text-domani-orange-600" : "text-ink"
      }`}>
        {valor}
      </dd>
    </div>
  );
}
