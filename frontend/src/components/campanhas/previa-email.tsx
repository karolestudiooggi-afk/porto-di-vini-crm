"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui/icon";

/** Quem "recebe" a prévia. Os campos são os do e-mail real (services/render.py). */
export interface PessoaPrevia {
  nome: string | null;
  email: string | null;
}

/** Mesmo padrão do servidor: {{chave}} com letras minúsculas e _. */
const VAR = /\{\{\s*([a-z_]+)\s*\}\}/g;

const ESCAPE: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;" };

function variaveis(p: PessoaPrevia | null): Record<string, string> {
  const nome = (p?.nome ?? "").trim();
  return {
    nome,
    primeiro_nome: nome.split(" ")[0] ?? "",
    email: p?.email ?? "",
  };
}

/**
 * Troca {{chave}} como o servidor troca no envio: no HTML com escape, no
 * assunto sem; chave desconhecida vira vazio (nunca fica "{{fulano}}" à vista).
 */
export function aplicarVariaveis(texto: string, p: PessoaPrevia | null, escapar = true): string {
  const v = variaveis(p);
  return (texto ?? "").replace(VAR, (_, chave: string) => {
    const valor = v[chave] ?? "";
    return escapar ? valor.replace(/[&<>"']/g, (c) => ESCAPE[c]) : valor;
  });
}

/** Nome para o botão "Ver prévia com dados de …": o primeiro nome, ou o e-mail. */
export function chamarDe(p: PessoaPrevia | null): string {
  const primeiro = (p?.nome ?? "").trim().split(" ")[0];
  return primeiro || p?.email || "um contato";
}

/** Largura de desenho do e-mail: a dos templates (560–600 px) com folga. */
const LARGURA_EMAIL = 640;

/**
 * O e-mail como a pessoa vai ver, num iframe sem scripts. O rodapé de
 * descadastro e o pixel entram só no envio, então não aparecem aqui.
 *
 * Num quadro mais estreito que o e-mail, ele é desenhado na largura real e
 * reduzido — como na prévia do celular — em vez de sair cortado do lado.
 */
export function QuadroEmail({ html, pessoa, altura = 460 }: {
  html: string;
  pessoa: PessoaPrevia | null;
  altura?: number;
}) {
  const caixa = useRef<HTMLDivElement>(null);
  const [largura, setLargura] = useState(LARGURA_EMAIL);
  useEffect(() => {
    const el = caixa.current;
    if (!el) return;
    const medir = () => setLargura(el.clientWidth || LARGURA_EMAIL);
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const escala = Math.min(1, largura / LARGURA_EMAIL);
  return (
    <div ref={caixa} className="overflow-hidden bg-white" style={{ height: altura }}>
      <iframe
        title="Prévia do e-mail"
        sandbox=""
        srcDoc={aplicarVariaveis(html, pessoa)}
        className="block border-0 bg-white"
        style={{
          width: escala < 1 ? LARGURA_EMAIL : "100%",
          height: altura / escala,
          transform: escala < 1 ? `scale(${escala})` : undefined,
          transformOrigin: "0 0",
        }}
      />
    </div>
  );
}

/** Para a prévia, alguém com nome (fica mais perto do e-mail "bom"); sem
 *  ninguém com nome, o primeiro da lista. */
export function escolherPessoa<T extends PessoaPrevia>(lista: T[] | null | undefined): T | null {
  if (!lista?.length) return null;
  return lista.find((p) => (p.nome ?? "").trim()) ?? lista[0];
}

/** Cartão "Prévia do e-mail" do relatório, com o assunto e o botão Expandir. */
export function CartaoPreviaEmail({ html, assunto, pessoa }: {
  html: string;
  assunto: string;
  pessoa: PessoaPrevia | null;
}) {
  const [aberto, setAberto] = useState(false);
  const assuntoFinal = aplicarVariaveis(assunto, pessoa, false);
  return (
    <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
      <div className="flex items-start justify-between gap-3 border-b border-line/10 px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">Prévia do e-mail</h2>
          <p className="mt-1 truncate text-sm font-semibold text-ink" title={assuntoFinal}>{assuntoFinal}</p>
        </div>
        <button type="button" onClick={() => setAberto(true)}
                className="shrink-0 text-xs font-bold text-domani-orange-600 hover:underline">
          Expandir
        </button>
      </div>
      <QuadroEmail html={html} pessoa={pessoa} altura={560} />
      <JanelaPreviaEmail aberto={aberto} onFechar={() => setAberto(false)}
                         html={html} assunto={assunto} pessoa={pessoa} />
    </section>
  );
}

/** A prévia em tela cheia: usada no Expandir e na nova campanha. */
export function JanelaPreviaEmail({ aberto, onFechar, html, assunto, pessoa }: {
  aberto: boolean;
  onFechar: () => void;
  html: string;
  assunto: string;
  pessoa: PessoaPrevia | null;
}) {
  useEffect(() => {
    if (!aberto) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onFechar(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [aberto, onFechar]);

  if (!aberto) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 animate-overlay-fade bg-domani-ink/55 backdrop-blur-sm" onClick={onFechar} />
      <div role="dialog" aria-modal="true" aria-label="Prévia do e-mail"
           className="relative flex max-h-[92vh] w-full max-w-3xl animate-modal-panel flex-col overflow-hidden rounded-2xl border border-line/12 bg-surface shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-line/10 px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
              Prévia com os dados de {chamarDe(pessoa)}
            </p>
            <p className="mt-1 text-sm font-semibold text-ink">{aplicarVariaveis(assunto, pessoa, false) || "(sem assunto)"}</p>
            {pessoa?.email && <p className="text-xs text-muted">para {pessoa.email}</p>}
          </div>
          <button type="button" onClick={onFechar} aria-label="Fechar"
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-app hover:text-ink">
            <Icon name="close" className="h-5 w-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <QuadroEmail html={html} pessoa={pessoa} altura={720} />
        </div>
      </div>
    </div>
  );
}
