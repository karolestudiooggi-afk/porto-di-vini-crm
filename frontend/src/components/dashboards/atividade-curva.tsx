"use client";

import { useState } from "react";

import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { num, lerData } from "@/lib/format";
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
 * Interações por dia.
 *
 * Mesmo desenho da curva do dashboard dos outros CRMs: área com gradiente, grade
 * de referência, rótulo do último ponto numa pill (para não sumir atrás da linha)
 * e painel lateral com os totais.
 */
export function AtividadeCurva() {
  const [dias, setDias] = useState("30");
  const { data, loading, error } = useApi(
    () => api.dashboard.atividade(Number(dias)),
    [dias],
  );

  const serie = data?.serie ?? [];
  const max = Math.max(1, ...serie.map((p) => p.total));
  const acumulado = serie.reduce((s, p) => s + p.total, 0);
  const media = serie.length ? Math.round(acumulado / serie.length) : 0;
  const pico = serie.reduce(
    (melhor, p) => (p.total > (melhor?.total ?? -1) ? p : melhor),
    serie[0],
  );

  const X = (i: number) =>
    serie.length <= 1 ? X0 : X0 + (i / (serie.length - 1)) * (X1 - X0);
  const Y = (v: number) => Y1 - (v / max) * (Y1 - Y0);

  const pts = serie.map((p, i) => `${X(i).toFixed(1)},${Y(p.total).toFixed(1)}`).join(" ");
  const area = serie.length ? `${X0},${Y1} ${pts} ${X(serie.length - 1)},${Y1}` : "";
  const last = serie.length ? [X(serie.length - 1), Y(serie[serie.length - 1].total)] : null;

  // Rótulo do último valor: vai para a margem direita, e sobe ou desce conforme o
  // ponto esteja na metade de baixo ou de cima — nunca encosta na curva.
  const lastLabel = last ? num(serie[serie.length - 1].total) : "";
  const labelAcima = last ? last[1] > (Y0 + Y1) / 2 : true;
  const labelY = last ? clampY(labelAcima ? last[1] - 12 : last[1] + 18) : 0;
  const labelX = last ? last[0] + 10 : 0;
  const labelW = Math.max(38, lastLabel.length * 8);

  return (
    <div className="grid gap-px overflow-hidden rounded-2xl border border-line/10 bg-line/10 shadow-domani-lift lg:grid-cols-[minmax(0,1fr)_240px]">
      <div className="bg-surface">
        <div className="flex items-start justify-between gap-3 border-b border-line/10 px-5 py-4">
          <div>
            <h3 className="font-display text-[15px] font-extrabold tracking-tight text-ink">
              Interações por dia
            </h3>
            <p className="mt-0.5 text-[11.5px] text-muted">
              Conversas registradas pelo Domani
            </p>
          </div>
          <span className="flex items-center gap-1.5 text-[11px] text-muted">
            <i className="inline-block h-0 w-4 border-t-2" style={{ borderColor: ACCENT }} />
            interações
          </span>
        </div>

        <div className="px-3 py-3">
          {loading ? (
            <div className="skeleton m-3 h-64 rounded-xl" />
          ) : error ? (
            <p className="px-5 py-16 text-center text-sm text-red-500">{error}</p>
          ) : serie.length === 0 ? (
            <p className="px-5 py-16 text-center text-sm text-muted">
              Nenhuma interação no período.
            </p>
          ) : (
            <svg viewBox="0 0 812 290" preserveAspectRatio="xMidYMid meet"
                 className="h-auto w-full" role="img"
                 aria-label={`Interações por dia nos últimos ${dias} dias`}>
              <defs>
                <linearGradient id="fillAtividade" x1="0" y1="0" x2="0" y2="1">
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
                    {num(Math.round(max * (1 - k / 4)))}
                  </text>
                ))}
              </g>

              <polygon fill="url(#fillAtividade)" points={area} />
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
          <Linha termo="Total" valor={num(acumulado)} destaque />
          <Linha termo="Média por dia" valor={num(media)} />
          <Linha termo="Pico" valor={pico ? num(pico.total) : "—"} />
          {pico && (
            <p className="text-[11px] text-muted">em {fmtDia(pico.data)}</p>
          )}
        </dl>
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
