"use client";

import { useMemo } from "react";

import { KpiCard, type KpiData } from "@/components/dashboards/kpi-card";
import { BarList, toBars } from "@/components/dashboards/bar-list";
import { AtividadeCurva } from "@/components/dashboards/atividade-curva";
import { ConsumoCurva } from "@/components/dashboards/consumo-curva";
import { CLIENTE, cap } from "@/config/cliente";
import { api } from "@/lib/api";
import { brl, brlCompact, dataHoraBR, num } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const { vocab } = CLIENTE;

/**
 * Painel do CRM.
 *
 * Todos os números vêm de /dashboard/*. Não há faturamento, ticket nem visita
 * porque o Domani é a única fonte e não fornece isso — o `docs/API.md` do backend
 * é explícito ao dizer que não existem respostas simuladas para esses campos.
 * Quando uma fonte nova entrar, os cartões correspondentes aparecem aqui.
 */
export default function DashboardsPage() {
  const resumo = useApi(() => api.dashboard.resumo(), []);
  const dist = useApi(() => api.dashboard.distribuicoes(), []);

  const r = resumo.data;

  // Com PDV ligado, os cartões passam a ser de negócio (faturamento, ticket) em
  // vez de só volume de base. Sem PDV, nem aparecem — melhor do que mostrar
  // "R$ 0,00", que afirmaria que não houve venda.
  const temConsumo = (r?.pedidos_total ?? 0) > 0;

  const kpisConsumo: KpiData[] = temConsumo ? [
    {
      label: "Faturamento (30 dias)",
      value: r?.faturamento_30_dias ? brlCompact(Number(r.faturamento_30_dias)) : "—",
      meta: `${num(r?.pedidos_30_dias ?? 0)} pedidos`,
      dark: true,
    },
    {
      label: "Ticket médio",
      value: r?.ticket_medio ? brl(Number(r.ticket_medio)) : "—",
      meta: "por pedido",
    },
    {
      label: "Clientes que compraram",
      value: num(r?.clientes_com_pedido ?? 0),
      meta: `de ${num(r?.total_contatos ?? 0)} na base`,
    },
  ] : [];

  const kpis: KpiData[] = [
    {
      label: `${cap(vocab.pessoa.muitos)} na base`,
      value: r ? num(r.total_contatos) : "—",
      meta: r ? `${num(r.contatos_com_interacao)} já interagiram` : "",
      dark: true,
    },
    {
      label: `${cap(vocab.interacao.muitos)} (30 dias)`,
      value: r ? num(r.interacoes_ultimos_30_dias) : "—",
      meta: "conversas no período",
    },
    {
      label: "Com telefone",
      value: r ? num(r.contatos_com_telefone) : "—",
      meta: "alcançáveis no WhatsApp",
    },
    {
      label: "Opt-in de e-mail",
      value: r ? num(r.contatos_com_opt_in_email) : "—",
      meta: r ? `de ${num(r.contatos_com_email)} com e-mail` : "",
    },
  ];

  const porCanal = useMemo(
    () => toBars((dist.data?.por_canal ?? []).map((d) => ({ label: d.valor, total: d.total }))),
    [dist.data],
  );
  const porStatus = useMemo(
    () => toBars((dist.data?.por_status ?? []).map((d) => ({ label: d.valor, total: d.total }))),
    [dist.data],
  );
  const porOrigem = useMemo(
    () => toBars((dist.data?.por_origem ?? []).map((d) => ({ label: d.valor, total: d.total }))),
    [dist.data],
  );
  const porIdioma = useMemo(
    () => toBars((dist.data?.por_idioma ?? []).map((d) => ({ label: d.valor, total: d.total }))),
    [dist.data],
  );

  return (
    <div className="space-y-4">
      <header className="rounded-3xl border border-line/10 bg-surface px-5 py-5 shadow-domani-lift sm:px-6">
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-domani-orange-300">
          Visão geral
        </p>
        <h1 className="mt-1 font-display text-2xl font-extrabold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-muted">
          {r?.domani_ultima_sincronizacao
            ? `Última sincronização com o Domani: ${dataHoraBR(r.domani_ultima_sincronizacao)}.`
            : "Aguardando a primeira sincronização com o Domani."}
          {r?.fontes_ativas?.length ? ` Fontes ativas: ${r.fontes_ativas.join(", ")}.` : ""}
        </p>
      </header>

      {resumo.error ? (
        <p className="rounded-3xl border border-line/10 bg-surface px-5 py-10 text-center text-sm text-red-500">
          {resumo.error}
        </p>
      ) : (
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[...kpisConsumo, ...kpis].map((k) => <KpiCard key={k.label} kpi={k} />)}
        </section>
      )}

      {/* Faturamento primeiro: com PDV ligado, é o número que o dono do
          negócio abre o CRM para ver. */}
      <ConsumoCurva />

      <AtividadeCurva />

      <section className="grid gap-3 lg:grid-cols-2">
        <BarList
          title={`${cap(vocab.pessoa.muitos)} por ${vocab.local.um}`}
          caption="Por onde a conversa chega"
          items={porCanal}
          format={(i) => num(i.value)}
          limite={8}
        />
        <BarList
          title="Situação da conversa"
          caption="Status registrado no Domani"
          items={porStatus}
          accent="palette"
          format={(i) => num(i.value)}
          limite={8}
        />
      </section>

      <section className="grid gap-3 lg:grid-cols-2">
        <BarList
          title="Origem da ficha"
          caption="De onde veio o cadastro"
          items={porOrigem}
          accent="palette"
          format={(i) => num(i.value)}
          limite={8}
        />
        <BarList
          title="Idioma"
          caption="Preferência declarada"
          items={porIdioma}
          accent="highlight"
          format={(i) => num(i.value)}
          limite={8}
        />
      </section>

      <p className="px-1 text-xs text-muted">
        Domani · {CLIENTE.nome} · Dashboard
      </p>
    </div>
  );
}
