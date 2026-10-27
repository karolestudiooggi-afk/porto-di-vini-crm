"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { Icon } from "@/components/ui/icon";
import { Select } from "@/components/ui/select";

/**
 * Base pública do CRM — é o que vai dentro do QR impresso.
 *
 * Sai de `window.location.origin`: o QR aponta para o mesmo domínio em que a
 * pessoa está gerando. Domínio fixo aqui faria um CRM clonado do template gerar
 * QR para o domínio de outro cliente — e um QR errado só é descoberto depois de
 * impresso e espalhado pela unidade.
 */
const APP_ORIGIN = typeof window !== "undefined" ? window.location.origin : "";

// Gerador de QR de avaliação. Usa a API pública qrserver (imagem PNG) — sem dependência nova.
export function QrGenerator() {
  // As unidades vêm de GET /avaliacao/contas — o seed é derivado dos dados, então
  // unidade nova entra aqui sozinha, sem deploy.
  const contas = useApi(() => api.avaliacao.contas(), []);
  const UNIDADES = (contas.data ?? []).map((c) => ({ slug: c.slug, nome: c.nome }));
  const [slug, setSlug] = useState("");
  useEffect(() => {
    if (!slug && UNIDADES.length) setSlug(UNIDADES[0].slug);
  }, [slug, UNIDADES]);
  const unidade = UNIDADES.find((u) => u.slug === slug) ?? { slug: "", nome: "—" };
  const url = `${APP_ORIGIN}/avaliar/${slug}`;
  const qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=520x520&margin=8&data=${encodeURIComponent(url)}`;

  async function baixarPng() {
    try {
      const res = await fetch(qrSrc);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `qr-avaliacao-${slug}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      window.open(qrSrc, "_blank");
    }
  }

  function imprimir() {
    const w = window.open("", "_blank", "width=600,height=800");
    if (!w) return;
    w.document.write(`
      <html><head><title>QR ${unidade.nome}</title>
      <style>
        body{font-family:system-ui,sans-serif;text-align:center;padding:48px 24px;color:#1D1D1F}
        h1{font-size:26px;margin:0 0 4px} .stars{color:#E56D23;font-size:26px;letter-spacing:4px}
        h2{font-size:30px;margin:18px 0 6px} p{color:#666;margin:0 0 20px}
        img{width:320px;height:320px} .foot{margin-top:16px;font-size:13px;color:#888;word-break:break-all}
      </style></head>
      <body>
        <h1>${unidade.nome}</h1>
        <div class="stars">★ ★ ★ ★ ★</div>
        <h2>Como foi sua experiência?</h2>
        <p>Aponte a câmera do celular no código</p>
        <img src="${qrSrc}" alt="QR" />
        <div class="foot">${url}</div>
        <script>window.onload=()=>setTimeout(()=>window.print(),400)</script>
      </body></html>`);
    w.document.close();
  }

  // Link direto — copiado para a área de transferência. Sugerido em reunião (Eva/Raphael):
  // no celular a leitura do QR muitas vezes não rola, então o link direto é a alternativa.
  const [copiado, setCopiado] = useState(false);
  async function copiarLink() {
    try {
      await navigator.clipboard.writeText(url);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 1800);
    } catch {
      // fallback: seleciona num prompt para copiar manualmente
      window.prompt("Copie o link de avaliação:", url);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
      {/* Controles */}
      <div className="rounded-2xl border border-line/12 bg-surface p-5 shadow-domani-lift">
        <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-domani-orange-600">Gerar QR de avaliação</p>

        <label className="mt-4 mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-ink/55">Unidade</label>
        <Select
          aria-label="Unidade"
          value={slug}
          onChange={setSlug}
          options={UNIDADES.map((u) => ({ value: u.slug, label: u.nome }))}
          triggerClassName="w-full rounded-xl border border-line/20 bg-app px-3 py-2.5 text-sm font-semibold text-ink"
        />

        <label className="mt-4 mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-ink/55">Endereço</label>
        <div className="break-all rounded-xl border border-line/15 bg-app px-3 py-2.5 text-xs text-ink/70">{url}</div>

        <button onClick={copiarLink} className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-line/25 px-4 py-2.5 text-sm font-semibold text-ink transition hover:bg-app">
          <Icon name={copiado ? "check" : "send"} className="h-4 w-4" strokeWidth={2} />
          {copiado ? "Link copiado!" : "Copiar link direto"}
        </button>
        <p className="mt-1.5 text-xs text-muted">Para enviar por WhatsApp/Instagram quando a câmera não lê o QR.</p>

        <div className="mt-4 flex gap-2">
          <button onClick={imprimir} className="flex-1 rounded-xl bg-domani-orange px-4 py-2.5 text-sm font-bold text-white transition hover:bg-domani-orange-600">Imprimir</button>
          <button onClick={baixarPng} className="flex-1 rounded-xl border border-line/25 px-4 py-2.5 text-sm font-semibold text-ink transition hover:bg-app">Baixar PNG</button>
        </div>
        <p className="mt-3 text-xs text-muted">Cada unidade tem seu QR. Ele aponta para a tela de avaliação daquela unidade.</p>
      </div>

      {/* Prévia do cartão */}
      <div className="grid place-items-center rounded-2xl border border-line/12 bg-surface p-8 shadow-domani-lift">
        <div className="w-full max-w-xs rounded-3xl border border-line/12 bg-app/40 p-7 text-center">
          <p className="font-display text-base font-bold text-ink">{unidade.nome}</p>
          <div className="mt-2 text-domani-orange" style={{ letterSpacing: "4px" }}>★ ★ ★ ★ ★</div>
          <h2 className="mt-3 font-display text-2xl font-extrabold tracking-tight text-ink">Como foi sua experiência?</h2>
          <p className="mt-1.5 text-sm text-muted">Aponte a câmera do celular no código</p>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={qrSrc} alt={`QR ${unidade.nome}`} className="mx-auto mt-4 h-56 w-56 rounded-2xl bg-white p-2" />
          <p className="mt-3 break-all text-[11px] text-muted">{url}</p>
          <p className="mt-1 text-xs font-semibold text-domani-orange-600">Leva 10 segundos</p>
        </div>
      </div>
    </div>
  );
}
