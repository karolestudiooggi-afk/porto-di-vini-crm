"use client";

import { useState } from "react";
import clsx from "clsx";
import type { BarItem } from "@/lib/types";

// Paleta Domani para barras "coloridas" (composição por categoria).
// Tons quentes ancorados no laranja da marca + neutros de apoio — legíveis nos 2 temas.
const PALETTE = ["#E56D23", "#F0A050", "#C9852F", "#8A6D4F", "#6B7280", "#9CA3AF"];

type Variant = "orange" | "graphite" | "palette" | "highlight";

/**
 * Converte contagens simples em barras com percentual.
 *
 * Mora aqui (e não em cada página) porque é o pré-processamento que TODA lista de
 * barra precisa — deixá-lo solto nas telas fazia cada uma calcular percentual do
 * seu jeito, e duas telas discordarem do mesmo total.
 */
export function toBars(rows: { label: string; total: number }[]): BarItem[] {
  const max = Math.max(1, ...rows.map((r) => r.total));
  const soma = Math.max(1, rows.reduce((s, r) => s + r.total, 0));
  return rows.map((r) => ({
    label: r.label,
    value: r.total,
    percent: Math.round((r.total / max) * 100), // largura da barra (relativa à maior)
    share: (r.total / soma) * 100,              // fatia do total (rótulo)
  }));
}

export function BarList({
  title,
  caption,
  items,
  format,
  accent = "orange",
  limite,
}: {
  title: string;
  caption?: string;
  items: BarItem[];
  format: (i: BarItem) => React.ReactNode;
  // "orange": tudo laranja. "palette": cor por item (composição).
  // "highlight": maior em laranja forte, resto suave (histogramas).
  accent?: Variant;
  /**
   * Mostra só os N primeiros, com botão para expandir. Sem isto, uma lista longa
   * (30 profissionais, 40 produtos) estica o card e desalinha a grade.
   */
  limite?: number;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const [expandido, setExpandido] = useState(false);
  const maxPct = Math.max(...items.map((i) => i.percent), 1);

  const cortar = limite != null && items.length > limite && !expandido;
  const visiveis = cortar ? items.slice(0, limite) : items;
  const ocultos = items.length - visiveis.length;

  const colorFor = (it: BarItem, idx: number): string => {
    if (accent === "palette") return PALETTE[idx % PALETTE.length];
    if (accent === "highlight") return it.percent >= maxPct ? "#E56D23" : "rgb(var(--line) / 0.28)";
    if (accent === "graphite") return "rgb(var(--line) / 0.45)"; // neutro visível nos 2 temas
    return "#E56D23";
  };

  return (
    <div className="rounded-2xl border border-line/12 bg-surface shadow-domani-lift">
      <div className="border-b border-line/10 px-5 py-4">
        <h3 className="font-display text-[15px] font-extrabold tracking-tight text-ink">{title}</h3>
        {caption && <p className="mt-0.5 text-[11.5px] text-muted">{caption}</p>}
      </div>
      <div className="space-y-3.5 px-5 py-4">
        {visiveis.map((it, idx) => {
          const cor = colorFor(it, idx);
          const on = hover === it.label;
          return (
            <div
              key={it.label}
              className="group flex items-center gap-3 text-sm"
              onMouseEnter={() => setHover(it.label)}
              onMouseLeave={() => setHover(null)}
            >
              <span className="flex w-28 shrink-0 items-center gap-2 truncate text-ink/80 sm:w-40">
                {(accent === "palette" || accent === "highlight") && (
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: cor }} />
                )}
                <span className="truncate">{it.label}</span>
              </span>

              {/* trilho sempre visível (bg-line/10 inverte entre temas) */}
              <span className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-line/10">
                <span
                  className="block h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.max(it.percent, 1.5)}%`, backgroundColor: cor, opacity: on ? 1 : 0.92 }}
                />
              </span>

              {/* % do total */}
              <span className="w-11 shrink-0 text-right text-[11px] font-semibold text-muted [font-variant-numeric:tabular-nums]">
                {it.share != null ? `${it.share.toFixed(it.share < 10 ? 1 : 0)}%` : ""}
              </span>

              {/* valor — realça no hover */}
              <span className={clsx(
                "w-16 shrink-0 text-right font-semibold [font-variant-numeric:tabular-nums] transition-colors",
                on ? "text-domani-orange-600" : "text-ink",
              )}>
                {format(it)}
              </span>
            </div>
          );
        })}

        {(cortar || expandido) && (
          <button
            type="button"
            onClick={() => setExpandido((e) => !e)}
            className="mt-1 w-full rounded-lg py-2 text-xs font-bold text-domani-orange-600 transition hover:bg-app"
          >
            {cortar ? `Ver todos (${ocultos} a mais)` : "Ver menos"}
          </button>
        )}
      </div>
    </div>
  );
}
