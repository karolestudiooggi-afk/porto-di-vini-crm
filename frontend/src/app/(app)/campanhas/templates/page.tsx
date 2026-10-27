"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";

import type { BlockEditorApi } from "@/components/campanhas/block-editor";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { CLIENTE } from "@/config/cliente";
import { api } from "@/lib/api";
import { dataHoraBR } from "@/lib/format";
import type { EmailTemplate, ListaEmail } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";

// O Unlayer toca em `window` na importação: sem ssr:false o build quebra.
const BlockEditor = dynamic(() => import("@/components/campanhas/block-editor"), {
  ssr: false,
  loading: () => <div className="skeleton h-[560px] rounded-2xl" />,
});

const CAMPO =
  "w-full rounded-2xl border border-line/15 bg-app px-3 py-3 text-sm text-ink outline-none transition placeholder:text-muted focus:border-domani-orange focus:bg-surface";

export default function TemplatesPage() {
  // useSearchParams exige um limite de Suspense no build do Next.
  return (
    <Suspense fallback={<div className="skeleton h-40 rounded-3xl" />}>
      <Templates />
    </Suspense>
  );
}

/**
 * Templates de UMA aba do e-mail (?lista=parceiros). Cada aba vê só os seus:
 * template de cliente fala com quem é cliente, e não serve para parceiro. Sem o
 * módulo de parceiros, é sempre a lista de clientes.
 */
function Templates() {
  const params = useSearchParams();
  const aba: ListaEmail =
    CLIENTE.modulos.parceiros && params.get("lista") === "parceiros" ? "parceiros" : "clientes";
  const lista = useApi(() => api.email.templates.list(aba), [aba]);
  const [editando, setEditando] = useState<EmailTemplate | null>(null);
  const [novo, setNovo] = useState(false);
  const [apagar, setApagar] = useState<EmailTemplate | null>(null);

  const emEdicao = novo || editando;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3 rounded-3xl border border-line/10 bg-surface px-5 py-5 shadow-domani-lift sm:px-6">
        <div>
          <Link href={aba === "parceiros" ? "/campanhas?aba=parceiros" : "/campanhas?aba=clientes"}
                className="text-xs font-bold text-muted hover:text-domani-orange-600">
            ← E-mail · {aba === "parceiros" ? "Parceiros" : "Clientes"}
          </Link>
          <h1 className="mt-2 font-display text-2xl font-extrabold tracking-tight">
            Templates {aba === "parceiros" ? "de parceiros" : "de clientes"}
          </h1>
          <p className="mt-1 text-sm text-muted">
            O HTML é congelado na criação da campanha — editar depois não muda o que já foi enviado.
          </p>
        </div>
        {!emEdicao && (
          <button onClick={() => setNovo(true)}
                  className="rounded-xl bg-domani-orange px-4 py-2 text-sm font-bold text-white transition hover:bg-domani-orange-600">
            Novo template
          </button>
        )}
      </header>

      {emEdicao ? (
        <Editor
          lista={aba}
          inicial={editando}
          aoFechar={() => { setNovo(false); setEditando(null); }}
          aoSalvar={() => { setNovo(false); setEditando(null); lista.reload(); }}
        />
      ) : (
        <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
          {lista.loading ? (
            <div className="space-y-2 p-5">
              {Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton h-10 rounded-lg" />)}
            </div>
          ) : !lista.data?.length ? (
            <p className="px-6 py-16 text-center text-sm text-muted">
              Nenhum template {aba === "parceiros" ? "de parceiros" : ""} ainda. Crie o primeiro para poder montar uma campanha.
            </p>
          ) : (
            <ul className="divide-y divide-line/10">
              {lista.data.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-4 px-5 py-3.5">
                  <div className="min-w-0">
                    <p className="font-semibold text-ink">{t.nome}</p>
                    <p className="truncate text-xs text-muted">
                      {t.assunto || "sem assunto"} · atualizado {dataHoraBR(t.updated_at)}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button onClick={() => setEditando(t)}
                            className="rounded-lg border border-line/20 px-3 py-1.5 text-xs font-bold text-ink transition hover:bg-app">
                      Editar
                    </button>
                    <button onClick={() => setApagar(t)}
                            className="rounded-lg px-3 py-1.5 text-xs font-bold text-red-500 transition hover:bg-red-500/10">
                      Apagar
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <ConfirmDialog
        open={apagar !== null}
        variant="danger"
        title="Apagar este template?"
        description={<>{apagar?.nome} some da lista. Campanhas já criadas com ele não são afetadas.</>}
        confirmLabel="Apagar"
        cancelLabel="Manter"
        onConfirm={async () => {
          if (apagar) await api.email.templates.apagar(apagar.id);
          setApagar(null);
          lista.reload();
        }}
        onClose={() => setApagar(null)}
      />
    </div>
  );
}

function Editor({
  lista, inicial, aoFechar, aoSalvar,
}: {
  lista: ListaEmail;
  inicial: EmailTemplate | null;
  aoFechar: () => void;
  aoSalvar: () => void;
}) {
  const [nome, setNome] = useState(inicial?.nome ?? "");
  const [assunto, setAssunto] = useState(inicial?.assunto ?? "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const editor = useRef<BlockEditorApi | null>(null);

  async function salvar() {
    if (!nome.trim()) { setErro("Dê um nome ao template."); return; }
    if (!editor.current) { setErro("O editor ainda está carregando."); return; }

    setSalvando(true);
    setErro(null);
    try {
      // O editor devolve os dois: o HTML que vai no e-mail e o `design` (JSON dos
      // blocos). Guardar os dois é o que permite reabrir e editar depois — só com
      // o HTML, o template viraria somente leitura.
      const { html, design } = await editor.current.exportHtml();
      const body = { nome: nome.trim(), assunto, html, design };
      if (inicial) await api.email.templates.atualizar(inicial.id, body);
      else await api.email.templates.criar({ ...body, lista });
      aoSalvar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não deu para salvar.");
      setSalvando(false);
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-3xl border border-line/10 bg-surface p-5 shadow-domani-lift">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-xs font-bold text-ink/70">Nome</span>
            <input value={nome} onChange={(e) => setNome(e.target.value)}
                   placeholder={lista === "parceiros" ? "Proposta de parceria" : "Boas-vindas"} className={CAMPO} />
            <span className="mt-1 block text-[11px] text-muted">
              Só para identificar aqui — o cliente não vê.
            </span>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-bold text-ink/70">Assunto sugerido</span>
            <input value={assunto} onChange={(e) => setAssunto(e.target.value)}
                   placeholder={lista === "parceiros" ? "Uma proposta para a {{empresa}}" : "Oi {{primeiro_nome}}!"}
                   className={CAMPO} />
            <span className="mt-1 block text-[11px] text-muted">
              Pode ser trocado na hora de criar a campanha.
            </span>
          </label>
        </div>
      </section>

      <BlockEditor
        lista={lista}
        initialDesign={inicial?.design ?? null}
        onReady={(api2) => { editor.current = api2; }}
      />

      <p className="px-1 text-xs text-muted">
        Use o botão de variáveis do editor para inserir o nome da pessoa
        {lista === "parceiros" ? " ou da empresa" : ""}. O rodapé
        de descadastro e o rastreio de abertura são acrescentados automaticamente
        no envio — não precisa montá-los aqui.
      </p>

      {erro && (
        <p className="rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          {erro}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <button onClick={aoFechar}
                className="rounded-xl border border-line/20 px-4 py-2 text-sm font-bold text-ink transition hover:bg-app">
          Cancelar
        </button>
        <button onClick={salvar} disabled={salvando}
                className="rounded-xl bg-domani-orange px-5 py-2 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:opacity-50">
          {salvando ? "Salvando…" : "Salvar template"}
        </button>
      </div>
    </div>
  );
}
