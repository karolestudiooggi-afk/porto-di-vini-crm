"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import clsx from "clsx";

import { PainelCota } from "@/components/campanhas/painel-cota";
import { ListaCampanhas, enderecoDe } from "@/components/campanhas/lista-campanhas";
import { CLIENTE } from "@/config/cliente";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { ListaEmail } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";

type Aba = "geral" | ListaEmail;

/** Aba Parceiros ligada (modulos.parceiros). Desligada, o E-mail tem uma lista só. */
const COM_PARCEIROS = CLIENTE.modulos.parceiros;

const ABAS: { id: Aba; rotulo: string }[] = [
  { id: "geral", rotulo: "Visão geral" },
  { id: "clientes", rotulo: "Clientes" },
  { id: "parceiros", rotulo: "Parceiros" },
];

const DESCRICAO: Record<Aba, string> = {
  geral: "Todas as campanhas, das duas listas. As de parceiro levam o selo.",
  clientes: "Campanhas para a base de clientes. O público sai dos mesmos filtros da tela de contatos.",
  parceiros: "Campanhas para a base de parceiros, com templates próprios e remetente de parcerias.",
};

const BOTAO = "rounded-xl border border-line/20 px-4 py-2 text-sm font-bold text-ink transition hover:bg-app";
const BOTAO_PRINCIPAL = "rounded-xl bg-domani-orange px-4 py-2 text-sm font-bold text-white transition hover:bg-domani-orange-600";

export default function CampanhasPage() {
  // useSearchParams exige um limite de Suspense no build do Next.
  return (
    <Suspense fallback={<div className="skeleton h-40 rounded-3xl" />}>
      <Email />
    </Suspense>
  );
}

/**
 * E-mail, em três abas. A aba mora na URL (?aba=parceiros) para o "← E-mail"
 * das telas internas voltar para a aba de onde a pessoa saiu. Sem o módulo de
 * parceiros há uma lista só (clientes), e as abas nem aparecem.
 */
function Email() {
  const params = useSearchParams();
  const router = useRouter();
  const pedida = params.get("aba");
  const aba: Aba = !COM_PARCEIROS ? "clientes"
    : pedida === "clientes" || pedida === "parceiros" ? pedida : "geral";

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
        <header className="flex flex-wrap items-end justify-between gap-3 px-5 pb-4 pt-5 sm:px-6">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-domani-orange-300">
              Relacionamento
            </p>
            <h1 className="mt-1 font-display text-2xl font-extrabold tracking-tight">E-mail</h1>
            <p className="mt-1 text-sm text-muted">{DESCRICAO[aba]}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {aba === "parceiros" ? (
              <>
                <Link href="/campanhas/parceiros" className={BOTAO}>Base de parceiros</Link>
                <Link href="/campanhas/templates?lista=parceiros" className={BOTAO}>Templates</Link>
                <Link href="/campanhas/nova?lista=parceiros" className={BOTAO_PRINCIPAL}>Nova campanha</Link>
              </>
            ) : (
              <>
                <Link href="/campanhas/templates" className={BOTAO}>Templates</Link>
                <Link href="/campanhas/nova" className={BOTAO_PRINCIPAL}>Nova campanha</Link>
              </>
            )}
          </div>
        </header>
        {COM_PARCEIROS && (
          <nav className="flex gap-1 overflow-x-auto border-t border-line/10 px-3 sm:px-5" aria-label="Listas de e-mail">
            {ABAS.map((a) => (
              <button
                key={a.id}
                onClick={() => router.push(a.id === "geral" ? "/campanhas" : `/campanhas?aba=${a.id}`)}
                aria-current={aba === a.id ? "page" : undefined}
                className={clsx(
                  "shrink-0 border-b-2 px-3 py-3 text-sm font-semibold transition",
                  aba === a.id ? "border-ink text-ink" : "border-transparent text-ink/55 hover:text-ink",
                )}
              >
                {a.rotulo}
              </button>
            ))}
          </nav>
        )}
      </section>

      <PainelCota />

      {aba === "parceiros" ? <AbaParceiros /> : <AbaCampanhas lista={aba === "clientes" ? "clientes" : undefined} />}

      <p className="px-1 text-xs text-muted">
        Aberturas são medidas por imagem no e-mail: quem lê com imagens bloqueadas
        não é contado. Trate o número como piso, não como total.
      </p>
    </div>
  );
}

function AbaCampanhas({ lista }: { lista?: ListaEmail }) {
  const q = useApi(() => api.email.campanhas.list(lista), [lista]);
  return (
    <ListaCampanhas
      campanhas={q.data} loading={q.loading} error={q.error}
      vazio={{ titulo: "Nenhuma campanha ainda", texto: "Crie um template e escolha um público para começar." }}
    />
  );
}

function AbaParceiros() {
  const campanhas = useApi(() => api.email.campanhas.list("parceiros"), []);
  const numeros = useApi(() => api.email.parceiros.numeros(), []);
  const n = numeros.data;
  const remetente = enderecoDe(campanhas.data?.[0]?.remetente);

  return (
    <>
      <section className="grid gap-3 sm:grid-cols-3">
        <Numero rotulo="Parceiros na base" valor={n ? num(n.total) : "—"}
                apoio={<Link href="/campanhas/parceiros" className="font-semibold text-ink underline underline-offset-2">ver a base</Link>} />
        <Numero rotulo="Recebem e-mail" valor={n ? num(n.recebem) : "—"}
                apoio="sem descadastro nem bloqueio" />
        <Numero rotulo="Saíram da lista" valor={n ? num(n.descadastrados + n.bloqueados) : "—"}
                apoio={n ? `${num(n.descadastrados)} descadastraram · ${num(n.bloqueados)} bloqueados` : undefined} />
      </section>

      {n && n.total === 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-domani-orange/25 bg-domani-orange/5 px-5 py-4">
          <p className="text-sm text-ink">
            A base de parceiros está vazia. Importe a planilha para poder montar a primeira campanha.
          </p>
          <Link href="/campanhas/parceiros?importar=1" className={BOTAO_PRINCIPAL}>Importar planilha</Link>
        </div>
      )}

      <p className="px-1 text-xs text-muted">
        {remetente
          ? <>Sai por <strong className="font-semibold text-ink/80">{remetente}</strong>.</>
          : <>Sai pelo remetente de parcerias configurado no servidor.</>}{" "}
        A cota de envio do provedor é uma só para as duas listas.
      </p>

      <ListaCampanhas
        campanhas={campanhas.data} loading={campanhas.loading} error={campanhas.error}
        marcarParceiro={false}
        vazio={{ titulo: "Nenhuma campanha de parceiros ainda",
                 texto: "Crie um template de parceiros e monte a primeira campanha." }}
      />
    </>
  );
}

function Numero({ rotulo, valor, apoio }: { rotulo: string; valor: string; apoio?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-line/12 bg-surface px-5 py-4 shadow-domani-lift">
      <p className="text-xs font-semibold text-muted">{rotulo}</p>
      <p className="mt-1 font-display text-3xl font-extrabold tracking-tight text-ink [font-variant-numeric:tabular-nums]">{valor}</p>
      {apoio && <p className="mt-1 text-xs text-muted">{apoio}</p>}
    </div>
  );
}
