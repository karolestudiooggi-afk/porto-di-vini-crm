import type { Metadata } from "next";
import { Icon } from "@/components/ui/icon";

export const metadata: Metadata = { title: "Agente IA" };

const SUGESTOES = [
  "Quem são os 50 clientes com maior ticket que não vêm há 90 dias?",
  "Monte uma lista de aniversariantes da semana com telefone.",
  "Compare o faturamento entre as unidades no último mês.",
];

export default function AgentePage() {
  return (
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)] lg:items-start">
      <aside className="rounded-3xl border border-domani-graphite bg-domani-graphite p-6 text-white shadow-domani-card lg:sticky lg:top-20">
        <span className="inline-flex items-center gap-2 rounded-full bg-domani-orange px-3 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-white">Beta fechado</span>
        <h1 className="mt-4 font-display text-2xl font-extrabold tracking-tight">Agente IA</h1>
        <p className="mt-2 text-sm text-white/55">
          Converse com a base em linguagem natural. Peça listas, segmentações e comparativos — e exporte direto pro WhatsApp.
        </p>
        <ul className="mt-5 space-y-2.5 text-sm text-white/70">
          {["Segmentação por linguagem natural", "Listas prontas para campanha", "Insights de reativação"].map((f) => (
            <li key={f} className="flex items-start gap-2">
              <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-domani-orange" strokeWidth={2} />
              {f}
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex min-h-[calc(100vh-7rem)] flex-col rounded-3xl border border-line/12 bg-surface shadow-domani-lift">
        <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-domani-orange/10 text-domani-orange-600">
            <Icon name="agente" className="h-8 w-8" />
          </div>
          <h2 className="mt-4 font-display text-xl font-extrabold tracking-tight text-ink">Em construção</h2>
          <p className="mt-2 max-w-md text-sm text-muted">
            O agente está sendo treinado com os dados da base. Enquanto isso, dá uma olhada no que vai dar pra perguntar:
          </p>
          <div className="mt-5 grid w-full max-w-lg gap-2">
            {SUGESTOES.map((s) => (
              <div key={s} className="rounded-xl border border-line/12 bg-app px-4 py-3 text-left text-sm text-ink/70">{s}</div>
            ))}
          </div>
        </div>

        <div className="border-t border-line/10 p-4">
          <div className="flex items-center gap-2 rounded-2xl border border-line/15 bg-app px-4 py-3 opacity-60">
            <input disabled placeholder="O agente estará disponível em breve…" className="w-full cursor-not-allowed bg-transparent text-sm text-ink placeholder:text-muted focus:outline-none" />
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-domani-graphite text-white/40">
              <Icon name="send" className="h-4 w-4" strokeWidth={2} />
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
