import Link from "next/link";

/**
 * Tela de um módulo desligado em `config/cliente.ts`.
 *
 * O menu já esconde o item; isto cobre quem chega pela URL (favorito, link
 * antigo). Diz o que está desligado e onde liga, em vez de abrir uma tela que
 * só ia mostrar erro da API.
 */
export function ModuloDesligado({ nome, chave, children }: {
  /** Nome do módulo como aparece para a pessoa. */
  nome: string;
  /** Caminho da chave dentro de `CLIENTE.modulos`. */
  chave: string;
  /** Explicação própria, no lugar da padrão. */
  children?: React.ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-line/10 bg-surface px-6 py-16 text-center shadow-domani-lift">
      <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-muted">Módulo desligado</p>
      <h1 className="mt-2 font-display text-xl font-extrabold tracking-tight text-ink">{nome}</h1>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted">
        {children ?? <>Este módulo não está ligado neste CRM.</>}{" "}
        Para ligar, ajuste <code>modulos.{chave}</code> em <code>config/cliente.ts</code> e
        gere o build de novo.
      </p>
      <Link href="/dashboards"
            className="mt-5 inline-block rounded-xl border border-line/20 px-4 py-2 text-sm font-bold text-ink transition hover:bg-app">
        Voltar ao dashboard
      </Link>
    </section>
  );
}
