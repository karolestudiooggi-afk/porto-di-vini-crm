"use client";

import { useState } from "react";
import clsx from "clsx";
import { NpsPanel } from "./nps-panel";
import { QrGenerator } from "./qr-generator";

// Avaliações — duas abas: Visão geral (NPS) e QR Codes (gerador de QR de avaliação).
export default function AvaliacoesPage() {
  const [aba, setAba] = useState<"geral" | "qr">("geral");

  return (
    <div className="space-y-5 animate-rise">
      <section className="overflow-hidden rounded-3xl border border-line/12 shadow-domani-lift">
        <div className="flex flex-col gap-4 bg-domani-graphite px-5 py-6 text-white sm:flex-row sm:items-end sm:justify-between sm:px-7">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-domani-orange-300">Experiência do cliente</p>
            <h1 className="mt-1.5 font-display text-2xl font-extrabold tracking-tight sm:text-3xl">Avaliações</h1>
            <p className="mt-1.5 max-w-xl text-sm text-white/55">NPS de todas as unidades, alertas de insatisfação em tempo real e o QR de avaliação de cada unidade.</p>
          </div>
          <div className="flex shrink-0 rounded-2xl bg-white/10 p-1">
            <TabBtn on={aba === "geral"} onClick={() => setAba("geral")}>Visão geral</TabBtn>
            <TabBtn on={aba === "qr"} onClick={() => setAba("qr")}>QR Codes</TabBtn>
          </div>
        </div>
      </section>

      {aba === "geral" ? <NpsPanel /> : <QrGenerator />}
    </div>
  );
}

function TabBtn({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "rounded-xl px-4 py-2 text-sm font-bold transition",
        on ? "bg-domani-orange text-white" : "text-white/70 hover:text-white",
      )}
    >
      {children}
    </button>
  );
}
