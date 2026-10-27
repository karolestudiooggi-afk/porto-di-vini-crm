"use client";

import { api, isApiConfigured } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { num, dataBR } from "@/lib/format";
import { Icon } from "@/components/ui/icon";


// Painel de NPS (aba "Visão geral") — GET /avaliacao/nps.
export function NpsPanel() {
  const q = useApi(() => api.avaliacao.nps(), []);
  const d = q.data;
  // O nome legível de cada unidade vem no próprio payload (por_unidade), em vez de
  // um de-para fixo no código — as unidades mudam de cliente para cliente.
  const NOMES: Record<string, string> = Object.fromEntries(
    (d?.por_unidade ?? []).map((u) => [u.slug, u.nome]),
  );

  if (!isApiConfigured) return <Estado titulo="Conecte a API" sub="Defina NEXT_PUBLIC_API_URL no .env.local." />;
  if (q.loading) return (
    <div className="grid place-items-center rounded-3xl border border-line/12 bg-surface py-16 shadow-domani-lift">
      <div className="h-7 w-7 animate-spin rounded-full border-2 border-line/20 border-t-domani-orange" />
    </div>
  );
  if (q.error || !d) return <Estado titulo="Não foi possível carregar" sub={q.error ?? "Sem dados."} danger />;

  return (
    <div className="space-y-3">
      <section className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-2xl border border-line/12 bg-surface p-6 shadow-domani-lift">
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">NPS geral</p>
          <div className="mt-2 flex items-end gap-3">
            <span className="font-display text-5xl font-extrabold tracking-tight text-domani-orange-600 [font-variant-numeric:tabular-nums]">{d.nps}</span>
            <span className="mb-1.5 text-sm text-muted">de {num(d.total)} avaliações</span>
          </div>
          <p className="mt-2 text-xs text-muted">NPS = % promotores − % detratores. Acima de 50 é ótimo; acima de 70, excelente.</p>
        </div>
        <div className="rounded-2xl border border-line/12 bg-surface p-6 shadow-domani-lift">
          <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Distribuição</p>
          <DistRow label="Promotores" valor={d.promotores} total={d.total} cor="#16a34a" />
          <DistRow label="Neutros" valor={d.neutros} total={d.total} cor="#F0A050" />
          <DistRow label="Detratores" valor={d.detratores} total={d.total} cor="#dc2626" />
        </div>
      </section>

      <section className="rounded-2xl border border-line/12 bg-surface shadow-domani-lift">
        <div className="border-b border-line/10 px-5 py-4">
          <h3 className="font-display text-[15px] font-extrabold tracking-tight text-ink">NPS por unidade</h3>
          <p className="mt-0.5 text-[11.5px] text-muted">Notas 4-5 = promotor · 3 = neutro · 1-2 = detrator</p>
        </div>
        <div className="space-y-3.5 px-5 py-4">
          {d.por_unidade.map((u) => (
            <div key={u.slug} className="flex items-center gap-3 text-sm">
              <span className="w-28 shrink-0 truncate text-ink/80">{u.nome}</span>
              <span className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-line/10">
                <span className="block h-full rounded-full bg-domani-orange transition-all duration-500" style={{ width: `${Math.max((u.nps + 100) / 2, 1)}%` }} />
              </span>
              <span className="w-10 shrink-0 text-right font-display font-extrabold text-ink [font-variant-numeric:tabular-nums]">{u.nps}</span>
              <span className="w-16 shrink-0 text-right text-xs text-muted [font-variant-numeric:tabular-nums]">{num(u.total)} aval.</span>
            </div>
          ))}
        </div>
      </section>

      <section className="overflow-hidden rounded-2xl border border-line/12 bg-surface shadow-domani-lift">
        <div className="border-b border-line/10 px-5 py-4">
          <h3 className="font-display text-[15px] font-extrabold tracking-tight text-ink">Últimas avaliações</h3>
        </div>
        {d.ultimas.length === 0 ? (
          <p className="px-6 py-10 text-center text-sm text-muted">Nenhuma avaliação ainda. Gere os QR codes na aba ao lado!</p>
        ) : (
          <div className="scroll-area max-h-[50vh] overflow-auto">
            <table className="w-full min-w-[680px] border-collapse text-sm">
              <thead>
                <tr className="sticky top-0 border-b border-line/12 bg-panel text-left text-[11px] uppercase tracking-[0.12em] text-muted">
                  <th className="px-5 py-3 font-bold">Nota</th><th className="px-4 py-3 font-bold">Unidade</th>
                  <th className="px-4 py-3 font-bold">Comentário</th><th className="px-4 py-3 font-bold">Cliente</th>
                  <th className="px-4 py-3 font-bold">Quando</th>
                </tr>
              </thead>
              <tbody>
                {d.ultimas.map((r) => (
                  <tr key={r.id} className="border-b border-line/[0.08]">
                    <td className="px-5 py-3"><span className="inline-flex items-center gap-1 font-bold text-domani-orange-600">{r.nota} <Icon name="rankings" className="h-3.5 w-3.5" /></span></td>
                    <td className="px-4 py-3 text-ink/80">{NOMES[r.slug] ?? r.slug}</td>
                    <td className="max-w-[280px] truncate px-4 py-3 text-ink/70">{r.comentario || "—"}</td>
                    <td className="px-4 py-3 text-ink/70">{r.nome || "anônimo"}</td>
                    <td className="px-4 py-3 text-ink/60">{dataBR(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function DistRow({ label, valor, total, cor }: { label: string; valor: number; total: number; cor: string }) {
  const pct = total > 0 ? (valor / total) * 100 : 0;
  return (
    <div className="mb-2.5 flex items-center gap-3 text-sm">
      <span className="w-24 shrink-0 text-ink/80">{label}</span>
      <span className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-line/10">
        <span className="block h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(pct, 1)}%`, backgroundColor: cor }} />
      </span>
      <span className="w-12 shrink-0 text-right font-semibold text-ink [font-variant-numeric:tabular-nums]">{pct.toFixed(0)}%</span>
    </div>
  );
}

function Estado({ titulo, sub, danger }: { titulo: string; sub: string; danger?: boolean }) {
  return (
    <div className="rounded-3xl border border-line/12 bg-surface px-6 py-14 text-center shadow-domani-lift">
      <p className={danger ? "font-display text-base font-extrabold text-red-500" : "font-display text-base font-extrabold text-ink"}>{titulo}</p>
      <p className="mx-auto mt-1.5 max-w-md text-sm text-muted">{sub}</p>
    </div>
  );
}
