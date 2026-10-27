"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import clsx from "clsx";
import { api, isApiConfigured } from "@/lib/api";
import type { Origem, OrigemMonitor } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { useAuth } from "@/providers/auth";
import { integracoesLigadas } from "@/config/cliente";
import { Icon } from "@/components/ui/icon";
import { ModuloDesligado } from "@/components/ui/modulo-desligado";
import { Agente } from "@/components/integracoes/agente";
import { Configuracao } from "@/components/integracoes/configuracao";
import { FilaGoogle, FilaIfood } from "@/components/integracoes/fila";
import { Historico } from "@/components/integracoes/historico";
import { Politica } from "@/components/integracoes/politica";
import { Responder } from "@/components/integracoes/responder";
import { VisaoLojas } from "@/components/integracoes/visao";
import {
  MonitorConfig, MonitorLista, MonitorPainel, NOME_MONITOR, type FiltroMonitor,
} from "@/components/integracoes/monitor";
import {
  Aviso, BOTAO_PRINCIPAL, Carregando, NOME_UNIDADE, Vazio,
} from "@/components/integracoes/partes";

type Secao = "avaliacoes" | "historico" | "agente" | "config" | "politica";
type Plataforma = Origem | OrigemMonitor;
type SecaoMonitor = "painel" | "lista" | "config";

/** Só as plataformas ligadas em `config/cliente.ts` (modulos.integracoes). */
const PLATAFORMAS: Plataforma[] = integracoesLigadas;
/** Tripadvisor e Reclame Aqui: lidos pelos e-mails, sem responder daqui. */
const MONITOR: OrigemMonitor[] = (["tripadvisor", "reclameaqui"] as const)
  .filter((o) => PLATAFORMAS.includes(o));
const NOME_PLATAFORMA: Record<Plataforma, string> = {
  ifood: "iFood", google: "Google", ...NOME_MONITOR,
};

const SECOES: { id: Secao; rotulo: string; so?: Origem }[] = [
  { id: "avaliacoes", rotulo: "Avaliações" },
  { id: "historico", rotulo: "Histórico" },
  { id: "agente", rotulo: "Agente de IA", so: "ifood" },
  { id: "config", rotulo: "Configuração" },
  { id: "politica", rotulo: "Política", so: "ifood" },
];

/**
 * Integrações — avaliações do iFood e do Google Meu Negócio, respondidas daqui,
 * e do Tripadvisor e do Reclame Aqui, acompanhadas pelos e-mails. Cada
 * plataforma liga e desliga em `config/cliente.ts`; só as ligadas aparecem.
 *
 * O lugar em que a pessoa está (plataforma, seção, loja, avaliação) mora na URL,
 * não em estado da tela. Três coisas dependem disso: o link do aviso no WhatsApp
 * abre direto na avaliação, o botão Voltar do navegador funciona entre fila e
 * resposta, e o retorno do login do Google cai na aba certa.
 */
export default function IntegracoesPage() {
  if (!PLATAFORMAS.length) {
    return (
      <ModuloDesligado nome="Integrações" chave="integracoes">
        Nenhuma plataforma (iFood, Google, Tripadvisor, Reclame Aqui) está ligada neste CRM.
      </ModuloDesligado>
    );
  }
  // useSearchParams exige um limite de Suspense no build do Next.
  return (
    <Suspense fallback={<Carregando />}>
      <Integracoes />
    </Suspense>
  );
}

function Integracoes() {
  const params = useSearchParams();
  const router = useRouter();
  const { can } = useAuth();

  // Plataforma desligada (ou nenhuma na URL) cai na primeira ligada.
  const pedida = params.get("origem") as Plataforma | null;
  const plataforma: Plataforma = pedida && PLATAFORMAS.includes(pedida) ? pedida : PLATAFORMAS[0];
  const ehMonitor = MONITOR.includes(plataforma as OrigemMonitor);
  // As telas de iFood/Google continuam recebendo só as duas origens delas.
  const origem: Origem = plataforma === "google" ? "google" : "ifood";
  const lojaId = params.get("loja");
  const reviewId = params.get("avaliacao");
  const secaoPedida = params.get("secao") as Secao | null;
  const secao: Secao = SECOES.some((s) => s.id === secaoPedida && (!s.so || s.so === origem))
    ? (secaoPedida as Secao) : "avaliacoes";

  // Retorno do login do Google: o desfecho vem na URL. Guarda o recado, limpa a
  // URL (para um F5 não repetir a mensagem) e cai na configuração do Google.
  const [retorno, setRetorno] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);

  const ir = useCallback((destino: {
    origem?: Plataforma; secao?: Secao; loja?: string | null; avaliacao?: string | null;
    status?: string;
  }, substituir = false) => {
    const q = new URLSearchParams();
    const o = destino.origem ?? plataforma;
    // A primeira plataforma ligada é o padrão: não precisa ir na URL.
    if (o !== PLATAFORMAS[0]) q.set("origem", o);
    const s = destino.secao ?? "avaliacoes";
    if (s !== "avaliacoes") q.set("secao", s);
    if (destino.loja) q.set("loja", destino.loja);
    if (destino.loja && destino.avaliacao) q.set("avaliacao", destino.avaliacao);
    if (s === "historico" && destino.status) q.set("status", destino.status);
    const consulta = q.toString();
    const url = consulta ? `/integracoes?${consulta}` : "/integracoes";
    if (substituir) {
      router.replace(url);
    } else {
      // Navegou por conta própria: o recado do retorno do Google já cumpriu o papel.
      setRetorno(null);
      router.push(url);
    }
  }, [plataforma, router]);

  // Navegação das plataformas lidas por e-mail (seção, item aberto, filtro).
  const irMonitor = useCallback((destino: {
    secao?: SecaoMonitor; item?: number | null; filtro?: FiltroMonitor;
  }) => {
    const q = new URLSearchParams({ origem: plataforma });
    const s = destino.secao ?? "painel";
    if (s !== "painel") q.set("secao", s);
    if (destino.item != null) q.set("item", String(destino.item));
    const f = destino.filtro ?? {};
    if (f.pendente) q.set("pendente", "1");
    if (f.critico) q.set("critico", "1");
    if (f.unidade) q.set("unidade", f.unidade);
    if (f.nivel) q.set("nivel", f.nivel);
    router.push(`/integracoes?${q.toString()}`);
  }, [plataforma, router]);
  const desfecho = params.get("google");
  const motivo = params.get("motivo");
  useEffect(() => {
    if (!desfecho) return;
    setRetorno(desfecho === "conectado"
      ? { tipo: "ok", texto: "Conta Google conectada. Confira abaixo se todas as unidades foram vinculadas." }
      : { tipo: "erro", texto: `A conexão com o Google não foi concluída: ${motivo || "tente de novo"}.` });
    ir({ origem: "google", secao: "config" }, true);
  }, [desfecho, motivo, ir]);

  const situacao = useApi(() => api.integracoes.situacao(), []);
  const lojas = useApi(
    () => (ehMonitor ? Promise.resolve([]) : api.integracoes.lojas(origem)), [origem, ehMonitor]);
  const monitor = useApi(
    () => (ehMonitor ? api.monitor.situacao() : Promise.resolve(null)), [ehMonitor]);
  const recarregar = () => { situacao.reload(); lojas.reload(); };

  const loja = lojas.data?.find((l) => l.loja_id === lojaId) ?? null;
  const u = NOME_UNIDADE[origem];

  const secaoMonitor: SecaoMonitor =
    params.get("secao") === "lista" || params.get("item") ? "lista"
      : params.get("secao") === "config" ? "config" : "painel";
  const itemAberto = params.get("item") ? Number(params.get("item")) : null;
  const filtroMonitor: FiltroMonitor = {
    pendente: params.get("pendente") === "1",
    critico: params.get("critico") === "1",
    unidade: params.get("unidade") ?? undefined,
    nivel: params.get("nivel") ?? undefined,
  };

  let corpo: React.ReactNode;
  if (!isApiConfigured) {
    corpo = <Vazio titulo="Conecte a API">Defina NEXT_PUBLIC_API_URL no .env do frontend.</Vazio>;
  } else if (ehMonitor) {
    const om = plataforma as OrigemMonitor;
    if (monitor.loading && !monitor.data) {
      corpo = <Carregando />;
    } else if (monitor.error || !monitor.data) {
      corpo = <Aviso tipo="erro">{monitor.error ?? "Não foi possível carregar."}</Aviso>;
    } else if (secaoMonitor === "config") {
      corpo = <MonitorConfig origem={om} situacao={monitor.data}
                             podeConfigurar={can("integracoes:config")} onMudou={monitor.reload} />;
    } else if (secaoMonitor === "lista") {
      corpo = (
        // A chave refaz a lista quando o filtro chega pela URL (clique no painel).
        <MonitorLista key={`${om}-${params.get("pendente")}-${params.get("critico")}-${params.get("unidade")}-${params.get("nivel")}`}
                      origem={om} itemId={itemAberto} filtroInicial={filtroMonitor}
                      onAbrir={(id) => irMonitor({ secao: "lista", item: id, filtro: filtroMonitor })} />
      );
    } else {
      corpo = <MonitorPainel origem={om} situacao={monitor.data}
                             onLista={(f) => irMonitor({ secao: "lista", filtro: f })}
                             onConfig={() => irMonitor({ secao: "config" })} />;
    }
  } else if (situacao.loading && !situacao.data) {
    corpo = <Carregando />;
  } else if (situacao.error || !situacao.data) {
    corpo = <Aviso tipo="erro">{situacao.error ?? "Não foi possível carregar as integrações."}</Aviso>;
  } else if (secao === "config") {
    corpo = (
      <Configuracao origem={origem} situacao={situacao.data} lojas={lojas.data ?? []}
                    podeConfigurar={can("integracoes:config")} onMudou={recarregar} />
    );
  } else if (secao === "historico") {
    // A chave refaz a tela quando o filtro vem pela URL ("ver quais" falharam).
    corpo = <Historico key={`${origem}-${params.get("status") ?? ""}`} origem={origem}
                       lojas={lojas.data ?? []} statusInicial={params.get("status") ?? ""} />;
  } else if (secao === "politica") {
    corpo = <Politica />;
  } else if (secao === "agente") {
    corpo = <Agente situacao={situacao.data.ifood} />;
  } else {
    // Avaliações. Antes da fila, o que falta para ela existir — dito com o
    // próximo passo, e não como erro.
    const s = situacao.data;
    const abrirConfig = (
      <button onClick={() => ir({ secao: "config" })} className={clsx(BOTAO_PRINCIPAL, "mt-4")}>
        Abrir configuração
      </button>
    );
    // Google não depende mais da conexão OAuth do CRM: as avaliações chegam pelo
    // NichoChat e a resposta volta por ele. O que faltar para isso (chave do
    // NichoChat, chave da entrega) a própria visão geral explica.
    const falta =
      origem === "ifood" && !s.ifood.configurado
        ? { titulo: "O iFood ainda não está configurado", texto: "Faltam as credenciais do aplicativo no servidor." }
      : lojas.data && lojas.data.length === 0
        ? { titulo: `Nenhuma ${u.uma} cadastrada`, texto: `Cadastre a primeira ${u.uma} para a fila aparecer aqui.` }
      : null;

    if (falta && !lojaId) {
      corpo = <Vazio titulo={falta.titulo}><p>{falta.texto}</p>{abrirConfig}</Vazio>;
    } else if (lojaId && reviewId) {
      corpo = (
        <>
          <Caminho origem={origem} loja={loja?.nome ?? "Loja"}
                   onInicio={() => ir({})} onLoja={() => ir({ loja: lojaId })} />
          <Responder
            origem={origem} lojaId={lojaId} reviewId={reviewId}
            onIr={(id) => ir({ loja: lojaId, avaliacao: id })}
            onVoltar={() => ir({ loja: lojaId })}
          />
        </>
      );
    } else if (lojaId) {
      const abrir = (id: string) => ir({ loja: lojaId, avaliacao: id });
      corpo = (
        <>
          <Caminho origem={origem} loja={loja?.nome ?? "Loja"} onInicio={() => ir({})} />
          {origem === "ifood"
            ? <FilaIfood key={lojaId} lojaId={lojaId} onAbrir={abrir} />
            : <FilaGoogle key={lojaId} lojaId={lojaId} onAbrir={abrir} />}
        </>
      );
    } else {
      corpo = <VisaoLojas origem={origem} situacao={s} onAbrir={(id) => ir({ loja: id })}
                          onVerFalhas={() => ir({ secao: "historico", status: "erro" })} />;
    }
  }

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-3xl border border-line/12 shadow-domani-lift">
        <div className="flex flex-col gap-4 bg-domani-graphite px-5 py-6 text-white sm:flex-row sm:items-end sm:justify-between sm:px-7">
          <div>
            <h1 className="font-display text-2xl font-extrabold tracking-tight sm:text-3xl">Integrações</h1>
            <p className="mt-1.5 max-w-xl text-sm text-white/55">
              {ehMonitor
                ? `As avaliações do ${NOME_MONITOR[plataforma as OrigemMonitor]} chegam pelos e-mails de notificação. Aqui é acompanhar, alertar e medir; responder é na plataforma.`
                : `As avaliações do ${NOME_PLATAFORMA[plataforma]} chegam aqui. Responda sem sair do CRM, com a IA sugerindo o texto.`}
            </p>
          </div>
          {/* Com uma plataforma só ligada, não há o que alternar. */}
          {PLATAFORMAS.length > 1 && (
            <div className="flex max-w-full shrink-0 overflow-x-auto rounded-2xl bg-white/10 p-1" role="tablist" aria-label="Plataforma">
              {PLATAFORMAS.map((o) => (
                <button
                  key={o}
                  role="tab"
                  aria-selected={plataforma === o}
                  onClick={() => ir({ origem: o })}
                  className={clsx(
                    "shrink-0 rounded-xl px-4 py-2 text-sm font-bold transition",
                    plataforma === o ? "bg-white text-domani-graphite" : "text-white/70 hover:text-white",
                  )}
                >
                  {NOME_PLATAFORMA[o]}
                </button>
              ))}
            </div>
          )}
        </div>

        <nav className="flex gap-1 overflow-x-auto bg-surface px-3 sm:px-5" aria-label="Seções">
          {ehMonitor && ([
            { id: "painel", rotulo: "Painel" },
            { id: "lista", rotulo: plataforma === "tripadvisor" ? "Avaliações" : "Reclamações" },
            { id: "config", rotulo: "Configuração" },
          ] as { id: SecaoMonitor; rotulo: string }[]).map((s) => (
            <button
              key={s.id}
              onClick={() => irMonitor({ secao: s.id })}
              aria-current={secaoMonitor === s.id ? "page" : undefined}
              className={clsx(
                "shrink-0 border-b-2 px-3 py-3 text-sm font-semibold transition",
                secaoMonitor === s.id ? "border-ink text-ink" : "border-transparent text-ink/55 hover:text-ink",
              )}
            >
              {s.rotulo}
              {s.id === "lista" && (monitor.data?.origens[plataforma as OrigemMonitor]?.pendentes ?? 0) > 0 && (
                <span className="ml-1.5 rounded-full bg-domani-orange px-1.5 py-0.5 text-[10px] font-bold text-domani-graphite">
                  {monitor.data?.origens[plataforma as OrigemMonitor].pendentes}
                </span>
              )}
            </button>
          ))}
          {!ehMonitor && SECOES.filter((s) => !s.so || s.so === origem).map((s) => (
            <button
              key={s.id}
              onClick={() => ir({ secao: s.id })}
              aria-current={secao === s.id ? "page" : undefined}
              className={clsx(
                "shrink-0 border-b-2 px-3 py-3 text-sm font-semibold transition",
                secao === s.id
                  ? "border-ink text-ink"
                  : "border-transparent text-ink/55 hover:text-ink",
              )}
            >
              {s.rotulo}
            </button>
          ))}
        </nav>
      </section>

      {retorno && <Aviso tipo={retorno.tipo}>{retorno.texto}</Aviso>}
      {corpo}
    </div>
  );
}

/** Onde a pessoa está dentro da fila, com o caminho de volta. */
function Caminho({ origem, loja, onInicio, onLoja }: {
  origem: Origem;
  loja: string;
  onInicio: () => void;
  onLoja?: () => void;
}) {
  return (
    <nav aria-label="Caminho" className="flex flex-wrap items-center gap-1.5 px-1 text-sm">
      <button onClick={onInicio} className="font-semibold text-ink/60 transition hover:text-ink">
        {origem === "ifood" ? "Lojas" : "Unidades"}
      </button>
      <Icon name="chevronRight" className="h-3.5 w-3.5 text-ink/30" strokeWidth={2} />
      {onLoja ? (
        <>
          <button onClick={onLoja} className="font-semibold text-ink/60 transition hover:text-ink">{loja}</button>
          <Icon name="chevronRight" className="h-3.5 w-3.5 text-ink/30" strokeWidth={2} />
          <span className="font-semibold text-ink">Responder</span>
        </>
      ) : (
        <span className="font-semibold text-ink">{loja}</span>
      )}
    </nav>
  );
}
