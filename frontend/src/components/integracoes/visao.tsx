"use client";

import { useState } from "react";
import clsx from "clsx";
import { api } from "@/lib/api";
import type { Origem, SituacaoIntegracoes } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { num } from "@/lib/format";
import { Icon } from "@/components/ui/icon";
import {
  Aviso, BOTAO_SECUNDARIO, Carregando, Cartao, NOME_UNIDADE, Selo, Vazio, desde, mensagemDe,
} from "./partes";

/** Tempo para o NichoChat ler todas as unidades e devolver ao CRM, antes de recarregar. */
const ESPERA_LEITURA_MS = 45_000;

/**
 * Ponto de partida de cada integração: quantas avaliações esperam resposta em
 * cada unidade. iFood: o número vem da plataforma ao vivo, então a tela leva
 * alguns segundos para abrir. Google: vem do que o NichoChat entregou (o CRM
 * pede a busca a cada 29 min), e "Ler agora" pede fora do horário.
 */
export function VisaoLojas({ origem, situacao, onAbrir, onVerFalhas }: {
  origem: Origem;
  situacao: SituacaoIntegracoes;
  onAbrir: (lojaId: string) => void;
  /** Abre o histórico já filtrado no que falhou. */
  onVerFalhas: () => void;
}) {
  const q = useApi(() => api.integracoes.resumo(origem), [origem]);
  const d = q.data;
  const u = NOME_UNIDADE[origem];
  const [lendo, setLendo] = useState(false);
  const [erroLer, setErroLer] = useState<string | null>(null);

  async function lerAgora() {
    setLendo(true);
    setErroLer(null);
    try {
      await api.integracoes.lerGoogle();
      // A leitura segue no servidor; recarrega quando ela deve ter terminado.
      window.setTimeout(() => { setLendo(false); q.reload(); }, ESPERA_LEITURA_MS);
    } catch (e) {
      setErroLer(mensagemDe(e, "Não deu para iniciar a leitura."));
      setLendo(false);
    }
  }

  if (q.loading) return <Carregando rotulo="Consultando as avaliações" />;
  if (q.error || !d) return <Aviso tipo="erro">{q.error ?? "Não foi possível carregar."}</Aviso>;

  const totalPendentes = d.lojas.reduce((s, l) => s + (l.pendentes ?? 0), 0);
  // Quem tem mais para responder vem primeiro; erro vai para o fim.
  const linhas = [...d.lojas].sort((a, b) =>
    (b.pendentes ?? -1) - (a.pendentes ?? -1) || a.nome.localeCompare(b.nome, "pt-BR"));

  return (
    <div className="space-y-3">
      {origem === "ifood" && (
        // O estado do agente e o modo ficam à vista logo na entrada, como na
        // visão geral do painel de origem: é o que diz se alguém (ou algo)
        // está cuidando da fila.
        <p className="flex flex-wrap items-center gap-2 px-1">
          <Selo ok={situacao.ifood.agente_agendado && situacao.ifood.ativo}>
            {!situacao.ifood.agente_agendado ? "agente desligado"
              : !situacao.ifood.ativo ? "agente pausado" : "agente ativo"}
          </Selo>
          <Selo ok={situacao.ifood.modo === "manual"}>
            {situacao.ifood.modo === "automatico" ? "agente publica" : "resposta manual"}
          </Selo>
        </p>
      )}

      {origem === "google" && d.leitura && (
        // Diz logo na entrada se o CRM está buscando as avaliações sozinho.
        <p className="flex flex-wrap items-center gap-2 px-1">
          <Selo ok={d.leitura.agendada && !d.erro}>
            {!d.leitura.agendada ? "leitura automática desligada"
              : d.erro ? "leitura automática parada"
              : `leitura automática a cada ${d.leitura.intervalo_min} min`}
          </Selo>
          {(d.leitura.lendo || lendo) && <Selo ok>lendo o Google agora</Selo>}
        </p>
      )}

      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Numero rotulo="Esperando resposta" valor={num(totalPendentes)} destaque={totalPendentes > 0} />
        <Numero rotulo="Respondidas hoje" valor={num(d.respondidas_hoje)}
                apoio={`${num(d.respondidas_7d)} em 7 dias`} />
        <Numero rotulo="Falhas em 7 dias" valor={num(d.erros_7d)}
                apoio={d.erros_7d > 0
                  ? <button onClick={onVerFalhas} className="font-semibold text-ink underline underline-offset-2">ver quais</button>
                  : undefined} />
        {origem === "ifood" ? (
          <Numero rotulo="Última passada do agente" valor={desde(d.ultima_execucao?.iniciado_em)} pequeno
                  apoio={d.ultima_execucao ? `${num(d.ultima_execucao.respondidas)} respondidas nela` : undefined} />
        ) : (
          // O NichoChat só entrega quando acha avaliação nova: a busca é o
          // pedido aceito; a entrega, a última vez que veio alguma.
          <Numero rotulo="Última busca no Google"
                  valor={desde(d.leitura?.ultimo_disparo_em ?? d.ultima_execucao?.iniciado_em)} pequeno
                  apoio={d.ultima_execucao
                    ? `última avaliação nova chegou ${desde(d.ultima_execucao.iniciado_em)}`
                    : "nenhuma avaliação chegou ainda"} />
        )}
      </dl>

      {d.erro && <Aviso tipo="erro">{d.erro}</Aviso>}
      {erroLer && <Aviso tipo="erro">{erroLer}</Aviso>}

      {d.lojas.length === 0 ? (
        <Vazio titulo={`Nenhuma ${u.uma} ativa`}>
          Cadastre ou ative uma {u.uma} na aba Configuração para a fila aparecer aqui.
        </Vazio>
      ) : (
        <Cartao
          titulo={origem === "ifood" ? "Lojas" : "Unidades"}
          descricao={origem === "google"
            ? `Chegam do Google sozinhas, a cada ${d.leitura?.intervalo_min ?? 29} min.`
            : "Avaliações dentro do prazo de 5 dias que ainda não têm resposta."}
          acoes={
            <div className="flex flex-wrap gap-2">
              {origem === "google" && (
                <button onClick={lerAgora} disabled={lendo || d.leitura?.lendo}
                        className={clsx(BOTAO_SECUNDARIO, "px-3 py-1.5 text-xs")}>
                  {lendo ? "Lendo…" : "Ler agora"}
                </button>
              )}
              <button onClick={q.reload} className={clsx(BOTAO_SECUNDARIO, "px-3 py-1.5 text-xs")}>
                <Icon name="refresh" className="h-3.5 w-3.5" strokeWidth={2} />
                Atualizar
              </button>
            </div>
          }
        >
          <ul className="divide-y divide-line/[0.08]">
            {linhas.map((l) => (
              <li key={l.loja_id}>
                <button
                  onClick={() => onAbrir(l.loja_id)}
                  className="group flex w-full items-center gap-4 px-5 py-3.5 text-left transition hover:bg-app/70 focus:outline-none focus-visible:bg-app"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold text-ink">{l.nome}</span>
                    <span className="mt-0.5 block truncate text-xs text-muted">
                      {l.erro
                        ? <span className="text-red-600 dark:text-red-400">{l.erro}</span>
                        : [
                            l.cidade,
                            l.media != null ? `média ${l.media.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}` : null,
                            l.total != null ? `${num(l.total)} avaliações` : null,
                          ].filter(Boolean).join(", ") || "\u00a0"}
                    </span>
                  </span>

                  {l.pendentes != null && (
                    <span className="shrink-0 text-right">
                      <span className={clsx(
                        "block font-display text-xl font-extrabold leading-none [font-variant-numeric:tabular-nums]",
                        l.pendentes > 0 ? "text-domani-orange-600" : "text-ink/35",
                      )}>
                        {l.parcial && l.pendentes > 0 ? `${l.pendentes}+` : l.pendentes}
                      </span>
                      <span className="mt-1 block text-[11px] text-muted">
                        {l.pendentes === 1 ? "pendente" : "pendentes"}
                      </span>
                    </span>
                  )}
                  <Icon name="chevronRight" className="h-4 w-4 shrink-0 text-ink/30 transition group-hover:text-ink/70" strokeWidth={2} />
                </button>
              </li>
            ))}
          </ul>
        </Cartao>
      )}
    </div>
  );
}

function Numero({ rotulo, valor, destaque, pequeno, apoio }: {
  rotulo: string;
  valor: string;
  destaque?: boolean;
  /** Para valor em texto ("há 4 min"), que não cabe no corpo dos números. */
  pequeno?: boolean;
  apoio?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-line/12 bg-surface px-5 py-4 shadow-domani-lift">
      <dt className="text-xs font-semibold text-muted">{rotulo}</dt>
      <dd className={clsx(
        "mt-1 font-display font-extrabold tracking-tight [font-variant-numeric:tabular-nums]",
        pequeno ? "pt-1.5 text-xl" : "text-3xl",
        destaque ? "text-domani-orange-600" : "text-ink",
      )}>
        {valor}
      </dd>
      {apoio && <dd className="mt-1 text-xs text-muted">{apoio}</dd>}
    </div>
  );
}
