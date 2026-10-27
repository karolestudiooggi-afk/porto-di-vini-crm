"use client";

import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { useApi } from "@/lib/use-api";

/**
 * Consumo do plano do provedor.
 *
 * Fica visível em toda tela de campanha de propósito: o limite de 2.500/hora é a
 * causa nº 1 de campanha parada pela metade, e quem dispara precisa saber quanto
 * cabe ANTES de clicar, não depois.
 */
export function PainelCota({ compacto = false }: { compacto?: boolean }) {
  const { data: c, loading, error } = useApi(() => api.email.cota(), []);

  if (loading) {
    return <div className="skeleton h-20 rounded-2xl" />;
  }

  // Falha aqui PRECISA aparecer. Ficar no esqueleto para sempre deixa a tela com
  // um retângulo vazio e ninguém sabe se está carregando ou quebrado — foi
  // exatamente o que aconteceu quando a view do banco mudou.
  if (error || !c) {
    return (
      <section className="rounded-3xl border border-red-500/20 bg-red-500/5 px-5 py-4">
        <p className="text-sm font-bold text-red-600">
          Não foi possível ler a capacidade de envio
        </p>
        <p className="mt-0.5 text-xs text-red-600/90">
          {error ?? "resposta vazia"} — o disparo fica bloqueado até isso voltar.
        </p>
      </section>
    );
  }

  const pctHora = Math.min(100, (c.enviados_hora / c.limite_hora) * 100);
  const pctDia = Math.min(100, (c.enviados_dia / c.limite_dia) * 100);
  const pctMes = Math.min(100, (c.enviados_mes / c.limite_mes) * 100);

  if (compacto) {
    return (
      <span className="text-xs text-muted">
        Cabem <strong className="text-ink">{num(c.disponivel)}</strong> e-mails agora
        {c.bloqueio && (
          <span className="ml-1 font-bold text-red-500">
            · limite {c.bloqueio === "mes" ? "mensal" : c.bloqueio === "dia" ? "de hoje" : "por hora"} atingido
          </span>
        )}
      </span>
    );
  }

  return (
    <section className="rounded-3xl border border-line/10 bg-surface p-5 shadow-domani-lift">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
          Plano do provedor
        </h2>
        <span className="text-sm font-bold text-ink [font-variant-numeric:tabular-nums]">
          {num(c.disponivel)} disponíveis agora
        </span>
      </div>

      <div className="mt-4 space-y-3">
        <Barra
          rotulo="Nesta hora"
          usado={c.enviados_hora}
          total={c.limite_hora}
          pct={pctHora}
          alerta={c.bloqueio === "hora"}
        />
        <Barra
          rotulo="Hoje"
          usado={c.enviados_dia}
          total={c.limite_dia}
          pct={pctDia}
          alerta={c.bloqueio === "dia"}
        />
        <Barra
          rotulo="Neste mês"
          usado={c.enviados_mes}
          total={c.limite_mes}
          pct={pctMes}
          alerta={c.bloqueio === "mes"}
        />
      </div>

      {c.bloqueio === "hora" && (
        <p className="mt-3 rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-700">
          Limite por hora atingido. A campanha continua sozinha quando a janela
          abrir — nada se perde.
        </p>
      )}
      {c.bloqueio === "dia" && (
        <p className="mt-3 rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-700">
          Cota de hoje atingida. A contagem zera à meia-noite e a campanha
          continua sozinha com o que ficou na fila.
        </p>
      )}
      {c.bloqueio === "mes" && (
        <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-600">
          Cota mensal esgotada. O envio recomeça no ciclo seguinte, ou após
          recarga no provedor.
        </p>
      )}
    </section>
  );
}

function Barra({
  rotulo, usado, total, pct, alerta,
}: {
  rotulo: string;
  usado: number;
  total: number;
  pct: number;
  alerta: boolean;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-muted">{rotulo}</span>
        <span className="text-ink/70 [font-variant-numeric:tabular-nums]">
          {num(usado)} / {num(total)}
        </span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-app">
        <div
          className={`h-full rounded-full transition-all ${
            alerta ? "bg-red-500" : pct > 80 ? "bg-amber-500" : "bg-domani-orange"
          }`}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Aviso de modo simulação.
 *
 * É o alerta mais importante da tela: com EMAIL_DRY_RUN=true o disparo percorre
 * todo o fluxo e marca "enviado" — mas NENHUM e-mail sai. Sem este aviso, alguém
 * dispara a campanha do mês, vê o relatório verdinho e só descobre dias depois
 * que ninguém recebeu.
 */
export function AvisoSimulacao({ simulado }: { simulado: boolean }) {
  if (!simulado) return null;
  return (
    <div className="rounded-2xl border-2 border-amber-500/40 bg-amber-500/10 px-4 py-3">
      <p className="text-sm font-bold text-amber-700">Modo simulação ligado</p>
      <p className="mt-0.5 text-xs text-amber-700/90">
        A campanha percorre todo o fluxo e o relatório mostra “enviado”, mas
        <strong> nenhum e-mail sai de verdade</strong>. Para disparar, mude
        <code className="mx-1 rounded bg-amber-500/20 px-1">EMAIL_DRY_RUN=false</code>
        no .env do servidor e reinicie a API.
      </p>
    </div>
  );
}
