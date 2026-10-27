"use client";

import clsx from "clsx";
import type { AvaliacaoExterna, Origem } from "@/lib/api-types";

/**
 * Peças pequenas compartilhadas pelas telas de Integrações.
 *
 * Uma regra de cor vale para o módulo inteiro, herdada do painel antigo do
 * iFood: o laranja carrega UM significado — atenção. Aparece em prazo curto, em
 * nota 1 ou 2 e na ação principal da tela, e em nenhum outro lugar. Por isso uma
 * fila com vinte avaliações continua legível e o que precisa de alguém salta
 * sozinho.
 */

export const CAMPO =
  "w-full rounded-xl border border-line/15 bg-app px-3 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted focus:border-domani-orange focus:bg-surface disabled:opacity-60";

export const BOTAO_PRINCIPAL =
  "inline-flex items-center justify-center gap-2 rounded-xl bg-domani-orange px-4 py-2.5 text-sm font-bold text-white transition hover:bg-domani-orange-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-domani-orange focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:cursor-not-allowed disabled:opacity-50";

export const BOTAO_SECUNDARIO =
  "inline-flex items-center justify-center gap-2 rounded-xl border border-line/20 px-4 py-2.5 text-sm font-semibold text-ink transition hover:bg-app focus:outline-none focus-visible:ring-2 focus-visible:ring-domani-orange disabled:cursor-not-allowed disabled:opacity-50";

/**
 * Ação repetida em cada linha de uma lista. Escura, e não laranja: com vinte
 * avaliações na tela, vinte botões laranja apagariam justamente o sinal que o
 * laranja carrega aqui (prazo curto, nota baixa).
 */
export const BOTAO_LINHA =
  "inline-flex items-center justify-center gap-2 rounded-xl bg-domani-graphite px-4 py-2 text-sm font-bold text-white transition hover:bg-domani-slate focus:outline-none focus-visible:ring-2 focus-visible:ring-domani-orange focus-visible:ring-offset-2 focus-visible:ring-offset-surface dark:bg-white dark:text-domani-graphite dark:hover:bg-white/85";

export const NOME_ORIGEM: Record<Origem, string> = {
  ifood: "iFood",
  google: "Google Meu Negócio",
};

/** Como cada plataforma chama uma unidade. */
export const NOME_UNIDADE: Record<Origem, { uma: string; varias: string }> = {
  ifood: { uma: "loja", varias: "lojas" },
  google: { uma: "unidade", varias: "unidades" },
};

/**
 * A nota é um quadrado pequeno, não um numeral gigante: número grande competiria
 * com o comentário, que é a informação que importa.
 */
export function Nota({ n, grande }: { n: number; grande?: boolean }) {
  const baixa = n > 0 && n <= 2;
  return (
    <span
      aria-label={`Nota ${n} de 5`}
      className={clsx(
        "inline-flex shrink-0 items-center justify-center rounded-lg font-display font-extrabold [font-variant-numeric:tabular-nums]",
        grande ? "h-11 w-11 text-xl" : "h-[30px] w-[30px] text-sm",
        // Laranja com tinta escura por cima: branco sobre o laranja da marca
        // não passa em contraste.
        baixa ? "bg-domani-orange text-domani-graphite" : "bg-line/[0.08] text-ink",
      )}
    >
      {n || "–"}
    </span>
  );
}

/**
 * A espinha à esquerda de cada avaliação do iFood mostra quanto do prazo de 5
 * dias já queimou: acesa nas últimas 24h, esmaecendo até sumir quando ainda há
 * dias. Avaliação respondida (ou do Google, que não tem prazo) não tem espinha.
 */
export function Espinha({ urgencia }: { urgencia: AvaliacaoExterna["urgencia"] }) {
  if (!urgencia) return null;
  return (
    <i
      aria-hidden="true"
      className={clsx(
        "absolute inset-y-0 left-0 w-1 rounded-l-2xl",
        urgencia === "quente" && "bg-domani-orange",
        urgencia === "morno" && "bg-domani-orange/45",
        urgencia === "frio" && "bg-line/15",
      )}
    />
  );
}

export function textoPrazo(seg: number | null): string {
  if (seg == null) return "";
  if (seg <= 0) return "prazo encerrado";
  const horas = Math.floor(seg / 3600);
  if (horas < 1) return "menos de 1h restante";
  if (horas < 24) return `${horas}h restantes`;
  const dias = Math.floor(horas / 24);
  return `${dias} ${dias === 1 ? "dia restante" : "dias restantes"}`;
}

/** 07/10 15:04 — curto, para caber na linha de cada avaliação. */
export function quando(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export function quandoCompleto(iso: string | null | undefined): string {
  if (!iso) return "não informada";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "não informada";
  return d.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function comentarioOu(texto: string | null | undefined): string {
  return (texto ?? "").trim() || "Sem comentário escrito.";
}

export function Aviso({ tipo = "info", children, className }: {
  tipo?: "erro" | "ok" | "info" | "atencao";
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role={tipo === "erro" ? "alert" : "status"}
      className={clsx(
        "rounded-2xl px-4 py-3 text-sm leading-relaxed [overflow-wrap:anywhere]",
        tipo === "erro" && "bg-red-500/[0.07] text-red-600 dark:text-red-400",
        tipo === "ok" && "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
        tipo === "info" && "bg-line/[0.05] text-ink/75",
        tipo === "atencao" && "bg-domani-orange/10 text-ink",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Carregando({ rotulo = "Carregando" }: { rotulo?: string }) {
  return (
    <div className="grid place-items-center rounded-2xl border border-line/12 bg-surface py-14 shadow-domani-lift" role="status">
      <div className="h-7 w-7 animate-spin rounded-full border-2 border-line/20 border-t-domani-orange" />
      <span className="sr-only">{rotulo}</span>
    </div>
  );
}

export function Vazio({ titulo, children }: { titulo: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-line/12 bg-surface px-6 py-12 text-center shadow-domani-lift">
      <p className="font-display text-base font-extrabold text-ink">{titulo}</p>
      {children && <div className="mx-auto mt-1.5 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Cartao({ titulo, descricao, acoes, children, className }: {
  titulo?: string;
  descricao?: React.ReactNode;
  acoes?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx("rounded-2xl border border-line/12 bg-surface shadow-domani-lift", className)}>
      {(titulo || acoes) && (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line/10 px-5 py-4">
          <div className="min-w-0">
            {titulo && <h3 className="font-display text-[15px] font-extrabold tracking-tight text-ink">{titulo}</h3>}
            {descricao && <p className="mt-0.5 text-xs text-muted">{descricao}</p>}
          </div>
          {acoes && <div className="flex shrink-0 flex-wrap gap-2">{acoes}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/** "há 4 min" — para dizer quando o agente passou pela última vez. */
export function desde(iso: string | null | undefined): string {
  if (!iso) return "nunca";
  const min = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (Number.isNaN(min)) return "nunca";
  if (min < 1) return "agora há pouco";
  if (min < 60) return `há ${min} min`;
  if (min < 1440) return `há ${Math.floor(min / 60)} h`;
  return `há ${Math.floor(min / 1440)} dias`;
}

export function Selo({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span className={clsx(
      "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
      ok ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : "bg-line/10 text-ink/65",
    )}>
      <i aria-hidden="true" className={clsx("h-1.5 w-1.5 rounded-full", ok ? "bg-emerald-500" : "bg-ink/35")} />
      {children}
    </span>
  );
}

export function mensagemDe(e: unknown, padrao: string): string {
  return e instanceof Error && e.message ? e.message : padrao;
}
