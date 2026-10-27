import clsx from "clsx";
import { Icon } from "@/components/ui/icon";

export interface KpiData {
  label: string;
  value: string;
  cur?: string;
  meta?: string;
  delta?: { dir: "up" | "down"; v: string };
  tag?: string;
  dark?: boolean;
}

export function KpiCard({ kpi }: { kpi: KpiData }) {
  return (
    <div
      className={clsx(
        "relative overflow-hidden rounded-2xl border px-5 py-4 shadow-domani-lift",
        kpi.dark ? "border-domani-graphite bg-domani-graphite text-white" : "border-line/12 bg-surface",
      )}
    >
      <div className={clsx("flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.16em]", kpi.dark ? "text-white/45" : "text-muted")}>
        {kpi.dark && <span className="h-1.5 w-1.5 rounded-full bg-domani-orange" />}
        <span>{kpi.label}</span>
        {kpi.tag && <span className="ml-auto rounded bg-domani-orange/15 px-1.5 py-0.5 text-[9px] font-bold tracking-[0.08em] text-domani-orange-600">{kpi.tag}</span>}
      </div>

      <p className={clsx("mt-3 font-display text-3xl font-extrabold tracking-tight [font-variant-numeric:tabular-nums]", kpi.dark ? "text-white" : "text-ink")}>
        {kpi.cur && <span className={clsx("mr-1 text-lg font-semibold", kpi.dark ? "text-white/55" : "text-muted")}>{kpi.cur}</span>}
        {kpi.value}
      </p>

      {(kpi.delta || kpi.meta) && (
        <div className={clsx("mt-2 flex items-center gap-1.5 text-[11.5px]", kpi.dark ? "text-white/45" : "text-muted")}>
          {kpi.delta && (
            <span className="inline-flex items-center gap-0.5 font-semibold text-domani-orange-600">
              <Icon name="arrowUp" className="h-3.5 w-3.5" strokeWidth={2.2} />
              {kpi.delta.v}
            </span>
          )}
          {kpi.meta}
        </div>
      )}
    </div>
  );
}
