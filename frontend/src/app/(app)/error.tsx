"use client";

import { useEffect } from "react";

/**
 * Erro numa tela do CRM. Sem isto, qualquer exceção no navegador derrubava o
 * app inteiro numa página branca ("Application error"). Aqui o menu continua
 * de pé, a pessoa vê o que houve e tenta de novo.
 */
export default function ErroDaTela({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Fica no console do navegador para quem for investigar.
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-xl rounded-2xl border border-line/12 bg-surface px-6 py-8 shadow-domani-lift">
      <h1 className="font-display text-xl font-extrabold tracking-tight text-ink">
        Esta tela não abriu
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Algo deu errado ao montar a página. O resto do CRM continua funcionando. Se
        acabou de sair uma atualização, confira se a API do servidor também foi
        reiniciada.
      </p>
      {error?.message && (
        <pre className="mt-4 whitespace-pre-wrap rounded-xl bg-app px-3 py-2 text-xs text-ink/80 [overflow-wrap:anywhere]">
          {error.message}
        </pre>
      )}
      <div className="mt-5 flex flex-wrap gap-2">
        <button
          onClick={reset}
          className="rounded-xl bg-domani-graphite px-4 py-2.5 text-sm font-bold text-white transition hover:opacity-90 dark:bg-white dark:text-domani-graphite"
        >
          Tentar de novo
        </button>
        <a href="/" className="rounded-xl px-4 py-2.5 text-sm font-semibold text-ink/70 transition hover:text-ink">
          Ir para o início
        </a>
      </div>
    </div>
  );
}
