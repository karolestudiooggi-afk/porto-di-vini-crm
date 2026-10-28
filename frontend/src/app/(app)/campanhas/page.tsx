"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import clsx from "clsx";

import { PainelCota } from "@/components/campanhas/painel-cota";
import { ListaCampanhas, enderecoDe, pct } from "@/components/campanhas/lista-campanhas";
import { Icon } from "@/components/ui/icon";
import { CLIENTE } from "@/config/cliente";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { Campanha, ListaEmail, ResumoEmail } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";

type Aba = "geral" | ListaEmail;

/** Aba Parceiros ligada (modulos.parceiros). Desligada, só Visão geral e Clientes. */
const COM_PARCEIROS = CLIENTE.modulos.parceiros;

/** Janela dos números do topo, em dias. */
const PERIODO = 30;

const ABAS: { id: Aba; rotulo: string }[] = [
  { id: "geral", rotulo: "Visão geral" },
  { id: "clientes", rotulo: "Clientes" },
  ...(COM_PARCEIROS ? [{ id: "parceiros" as const, rotulo: "Parceiros" }] : []),
];

const DESCRICAO: Record<Aba, string> = {
  geral: COM_PARCEIROS
    ? "Todas as campanhas, das duas listas. As de parceiro levam o selo."
    : `Todas as campanhas e o resultado dos últimos ${PERIODO} dias.`,
  clientes: "Campanhas para a base de clientes. O público sai da base de contatos: toda a base, uma tag ou uma seleção feita à mão.",
  parceiros: "Campanhas para a base de parceiros, com templates próprios e remetente de parcerias.",
};

const BOTAO = "inline-flex items-center gap-1.5 rounded-xl border border-line/20 bg-surface px-4 py-2.5 text-sm font-bold text-ink transition hover:bg-app";
const BOTAO_PRINCIPAL = "inline-flex items-center gap-1.5 rounded-xl bg-domani-orange px-4 py-2.5 text-sm font-bold text-white transition hover:bg-domani-orange-600";

export default function CampanhasPage() {
  // useSearchParams exige um limite de Suspense no build do Next.
  return (
    <Suspense fallback={<div className="skeleton h-40 rounded-3xl" />}>
      <Email />
    </Suspense>
  );
}

/**
 * E-mail, em abas. A aba mora na URL (?aba=clientes) para o "← E-mail" das
 * telas internas voltar para a aba de onde a pessoa saiu.
 */
function Email() {
  const params = useSearchParams();
  const router = useRouter();
  const pedida = params.get("aba");
  const aba: Aba = pedida === "clientes" || (COM_PARCEIROS && pedida === "parceiros") ? pedida : "geral";

  // Uma leitura só da lista: a visão geral mostra todas, as abas filtram aqui
  // mesmo. Os contadores das abas saem dela.
  const campanhas = useApi(() => api.email.campanhas.list(), []);
  const resumo = useApi(() => api.email.resumo(PERIODO), []);
  const todas = campanhas.data;
  const daAba = (l: ListaEmail) => todas?.filter((c) => c.lista === l) ?? null;

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
        <header className="flex flex-wrap items-end justify-between gap-4 px-5 pb-5 pt-6 sm:px-6">
          <div className="max-w-2xl">
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-domani-orange-300">
              Relacionamento · no lugar do RD Station
            </p>
            <h1 className="mt-1 font-display text-2xl font-extrabold tracking-tight">E-mail</h1>
            <p className="mt-1 text-sm text-muted">{DESCRICAO[aba]}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {aba === "parceiros" ? (
              <>
                <Link href="/campanhas/parceiros" className={BOTAO}>Base de parceiros</Link>
                <Link href="/campanhas/templates?lista=parceiros" className={BOTAO}>Templates</Link>
                <Link href="/campanhas/nova?lista=parceiros" className={BOTAO_PRINCIPAL}>
                  <Icon name="plus" className="h-4 w-4" strokeWidth={2.2} /> Nova campanha
                </Link>
              </>
            ) : (
              <>
                <Link href="/campanhas/templates" className={BOTAO}>Templates</Link>
                <Link href="/campanhas/nova" className={BOTAO_PRINCIPAL}>
                  <Icon name="plus" className="h-4 w-4" strokeWidth={2.2} /> Nova campanha
                </Link>
              </>
            )}
          </div>
        </header>
        <nav className="flex gap-1 overflow-x-auto border-t border-line/10 px-3 sm:px-5" aria-label="Listas de e-mail">
          {ABAS.map((a) => {
            const n = a.id === "geral" ? null : daAba(a.id)?.length;
            return (
              <button
                key={a.id}
                onClick={() => router.push(a.id === "geral" ? "/campanhas" : `/campanhas?aba=${a.id}`)}
                aria-current={aba === a.id ? "page" : undefined}
                className={clsx(
                  "flex shrink-0 items-center gap-2 border-b-2 px-3 py-3.5 text-sm font-semibold transition",
                  aba === a.id ? "border-ink text-ink" : "border-transparent text-ink/55 hover:text-ink",
                )}
              >
                {a.rotulo}
                {n != null && n > 0 && (
                  <span className="grid h-5 min-w-5 place-items-center rounded-full bg-app px-1.5 text-[11px] font-bold text-ink/70 [font-variant-numeric:tabular-nums]">
                    {n}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </section>

      {aba === "geral" && <NumerosPeriodo resumo={resumo.data} erro={resumo.error} />}
      {aba === "clientes" && <NumerosBase resumo={resumo.data} />}
      {aba === "parceiros" && <NumerosParceiros campanhas={daAba("parceiros")} />}

      {aba === "geral" && <PainelCota />}

      {aba === "clientes" && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-domani-orange/25 bg-domani-orange/[0.06] px-5 py-4 sm:flex-nowrap">
          <p className="min-w-0 flex-1 text-sm text-ink">
            Para mandar só para um grupo escolhido a dedo, marque os contatos na tela de
            Contatos e use “Enviar campanha para estes”. Para um grupo por tag (como a
            base “migração” do RD), use Segmento na nova campanha.
          </p>
          <Link href="/clientes" className={clsx(BOTAO, "shrink-0")}>Ir para Contatos</Link>
        </div>
      )}

      <ListaCampanhas
        campanhas={aba === "geral" ? todas : daAba(aba)}
        loading={campanhas.loading} error={campanhas.error}
        marcarParceiro={aba !== "parceiros"}
        vazio={aba === "parceiros"
          ? { titulo: "Nenhuma campanha de parceiros ainda",
              texto: "Crie um template de parceiros e monte a primeira campanha." }
          : { titulo: "Nenhuma campanha ainda",
              texto: "Crie um template e escolha um público para começar." }}
      />

      <p className="px-1 text-xs text-muted">
        {aba !== "parceiros" && resumo.data?.remetente && (
          <>Sai por <strong className="font-semibold text-ink/80">{enderecoDe(resumo.data.remetente)}</strong>. </>
        )}
        Aberturas são medidas por imagem no e-mail: quem lê com imagens bloqueadas
        não é contado. Trate o número como piso, não como total.
      </p>
    </div>
  );
}

/** Visão geral: o resultado do que saiu nos últimos 30 dias. */
function NumerosPeriodo({ resumo: r, erro }: { resumo: ResumoEmail | null; erro: string | null }) {
  if (erro) {
    return <p className="rounded-3xl border border-red-500/20 bg-red-500/5 px-5 py-4 text-sm text-red-600">{erro}</p>;
  }
  return (
    <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      <Numero escuro rotulo="E-mails enviados" valor={r ? num(r.enviados) : null}
              apoio={r && `${num(r.campanhas)} ${r.campanhas === 1 ? "campanha" : "campanhas"} nos últimos ${r.dias} dias`} />
      <Numero rotulo="Abertura média" valor={r ? pct(r.taxa_abertura) : null}
              apoio={r && `${num(r.aberturas)} ${r.aberturas === 1 ? "pessoa abriu" : "pessoas abriram"}`} />
      <Numero rotulo="Cliques" valor={r ? pct(r.taxa_clique) : null}
              apoio={r && `${num(r.cliques)} ${r.cliques === 1 ? "pessoa clicou" : "pessoas clicaram"}`} />
      {/* No lugar do "retorno no funil" do modelo: a Porto não tem funil no CRM,
          e o número que pede ação aqui é quem está saindo da lista. */}
      <Numero rotulo="Descadastros" valor={r ? pct(r.taxa_descadastro) : null}
              alerta={Number(r?.taxa_descadastro ?? 0) > 0.5}
              apoio={r && `${num(r.descadastros)} ${r.descadastros === 1 ? "saiu" : "saíram"} · ${num(r.bounce_hard)} ${r.bounce_hard === 1 ? "e-mail inválido" : "e-mails inválidos"}`} />
    </section>
  );
}

/** Aba Clientes: a base, do ponto de vista do e-mail. */
function NumerosBase({ resumo }: { resumo: ResumoEmail | null }) {
  const b = resumo?.base;
  return (
    <section className="grid gap-3 sm:grid-cols-3">
      <Numero rotulo="Recebem e-mail" valor={b ? num(b.recebem) : null}
              apoio="têm e-mail e não recusaram receber" />
      <Numero rotulo="Sem autorização" valor={b ? num(b.sem_autorizacao) : null}
              apoio="têm e-mail, mas não autorizaram" />
      <Numero rotulo="Saíram da lista" valor={b ? num(b.sairam) : null}
              apoio="descadastro ou erro definitivo" />
    </section>
  );
}

function NumerosParceiros({ campanhas }: { campanhas: Campanha[] | null }) {
  const numeros = useApi(() => api.email.parceiros.numeros(), []);
  const n = numeros.data;
  const remetente = enderecoDe(campanhas?.[0]?.remetente);
  return (
    <>
      <section className="grid gap-3 sm:grid-cols-3">
        <Numero rotulo="Parceiros na base" valor={n ? num(n.total) : null}
                apoio={<Link href="/campanhas/parceiros" className="font-semibold text-ink underline underline-offset-2">ver a base</Link>} />
        <Numero rotulo="Recebem e-mail" valor={n ? num(n.recebem) : null}
                apoio="sem descadastro nem bloqueio" />
        <Numero rotulo="Saíram da lista" valor={n ? num(n.descadastrados + n.bloqueados) : null}
                apoio={n ? `${num(n.descadastrados)} descadastraram · ${num(n.bloqueados)} bloqueados` : undefined} />
      </section>
      {n && n.total === 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-domani-orange/25 bg-domani-orange/[0.06] px-5 py-4">
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
    </>
  );
}

function Numero({ rotulo, valor, apoio, escuro, alerta }: {
  rotulo: string;
  /** null = carregando. */
  valor: string | null;
  apoio?: React.ReactNode;
  /** O primeiro card da visão geral, em grafite, como no modelo. */
  escuro?: boolean;
  alerta?: boolean;
}) {
  return (
    <div className={clsx(
      "min-w-0 rounded-3xl border px-4 py-4 shadow-domani-lift sm:px-5 sm:py-5",
      escuro
        ? "border-transparent bg-domani-graphite text-white dark:bg-white dark:text-domani-graphite"
        : alerta ? "border-red-500/30 bg-surface" : "border-line/12 bg-surface",
    )}>
      <p className={clsx("text-xs font-semibold", escuro ? "text-white/70 dark:text-domani-graphite/70" : "text-muted")}>
        {rotulo}
      </p>
      {valor === null ? (
        <div className={clsx("skeleton mt-2 h-9 w-24 rounded-lg", escuro && "opacity-30")} />
      ) : (
        <p className={clsx(
          "mt-1 font-display text-[1.65rem] font-extrabold leading-tight tracking-tight [font-variant-numeric:tabular-nums] sm:text-[2rem]",
          escuro ? "" : alerta ? "text-red-500" : "text-ink",
        )}>
          {valor}
        </p>
      )}
      {apoio && (
        <p className={clsx("mt-1.5 text-xs", escuro ? "text-white/60 dark:text-domani-graphite/60" : "text-muted")}>
          {apoio}
        </p>
      )}
    </div>
  );
}
