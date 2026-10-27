"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SituacaoIntegracoes } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { Aviso, BOTAO_PRINCIPAL, Carregando, Cartao, desde, mensagemDe, quandoCompleto } from "./partes";

function duracao(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`;
}

/**
 * O agente do iFood: se rodou, quando, e o que fez em cada passada.
 *
 * O iFood não avisa quando chega avaliação — é o agente que consulta de tempos
 * em tempos. Por isso "há quanto tempo foi a última passada" é a pergunta que
 * esta tela responde primeiro: se a resposta for "há dias", ninguém está sendo
 * avisado de nada.
 */
export function Agente({ situacao }: { situacao: SituacaoIntegracoes["ifood"] }) {
  const q = useApi(() => api.integracoes.agente(), []);
  const [disparando, setDisparando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const d = q.data;

  // Enquanto há passada em andamento, a tela se atualiza sozinha.
  const rodando = d?.rodando ?? false;
  const recarregar = q.reload;
  useEffect(() => {
    if (!rodando) return;
    const t = window.setInterval(recarregar, 4000);
    return () => window.clearInterval(t);
  }, [rodando, recarregar]);

  async function rodar() {
    setDisparando(true);
    setAviso(null);
    try {
      await api.integracoes.rodarAgente();
      setAviso({ tipo: "ok", texto: "Passada iniciada. O resultado aparece na lista em instantes." });
      window.setTimeout(recarregar, 1500);
    } catch (e) {
      setAviso({ tipo: "erro", texto: mensagemDe(e, "Não foi possível iniciar a passada.") });
    } finally {
      setDisparando(false);
    }
  }

  if (q.loading && !d) return <Carregando />;
  if (q.error || !d) return <Aviso tipo="erro">{q.error ?? "Não foi possível carregar."}</Aviso>;

  const ultima = d.execucoes[0];
  // Duas janelas sem passada com o agente ligado: algo travou.
  const atrasado = d.agendado && ultima != null
    && Date.now() - new Date(ultima.iniciado_em).getTime() > d.intervalo_min * 2 * 60000;

  return (
    <div className="space-y-3">
      <Cartao
        titulo={rodando ? "Passada em andamento" : ultima ? `Última passada ${desde(ultima.iniciado_em)}` : "O agente ainda não rodou"}
        descricao={<>Roda sozinho a cada {d.intervalo_min} minutos: consulta cada loja, avisa o NichoChat
          do que chegou e, no modo automático, responde a partir da nota mínima.</>}
        acoes={
          <button onClick={rodar} disabled={disparando || rodando || !situacao.configurado} className={BOTAO_PRINCIPAL}>
            {rodando ? "Rodando…" : "Rodar agora"}
          </button>
        }
      >
        <div className="space-y-3 px-5 py-4">
          <p className="text-sm text-ink/80">
            Modo atual: <strong>{situacao.modo === "automatico" ? "automático" : "manual"}</strong>.{" "}
            {situacao.modo === "automatico"
              ? "O agente publica sozinho as avaliações dentro da nota mínima."
              : "O agente só avisa; quem publica é a equipe, pela fila."}
            {!situacao.ativo && <> A integração está <strong>pausada</strong> na configuração, então as passadas não fazem nada.</>}
          </p>
          {aviso && <Aviso tipo={aviso.tipo}>{aviso.texto}</Aviso>}
          {!d.agendado && (
            <Aviso tipo="atencao">
              O agente está <strong>desligado no servidor</strong> (variável{" "}
              <code>WORKER_DESLIGADO</code> no <code>.env</code>). As avaliações novas só são
              vistas quando alguém clica em “Rodar agora”. Para religar, apague a variável e
              reinicie a API.
            </Aviso>
          )}
          {d.agendado && !ultima && !rodando && (
            <Aviso>A primeira passada sai sozinha, cerca de 30 segundos depois de a API subir.</Aviso>
          )}
          {atrasado && !rodando && (
            <Aviso tipo="atencao">
              Nenhuma passada nos últimos {d.intervalo_min * 2} minutos, e o agente deveria
              estar rodando. Vale olhar o log da API no servidor.
            </Aviso>
          )}
        </div>
      </Cartao>

      {d.execucoes.length > 0 && (
        <Cartao titulo="Passadas recentes">
          <div className="scroll-area overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line/10 text-left text-xs text-muted">
                  <th className="px-5 py-3 font-semibold">Quando</th>
                  <th className="px-4 py-3 text-right font-semibold">Lojas</th>
                  <th className="px-4 py-3 text-right font-semibold">Pendentes</th>
                  <th className="px-4 py-3 text-right font-semibold">Respondidas</th>
                  <th className="px-4 py-3 text-right font-semibold">Erros</th>
                  <th className="px-5 py-3 text-right font-semibold">Duração</th>
                </tr>
              </thead>
              <tbody className="[font-variant-numeric:tabular-nums]">
                {d.execucoes.map((e) => (
                  <tr key={e.iniciado_em} className="border-b border-line/[0.08] last:border-0">
                    <td className="px-5 py-3 text-ink/80">{quandoCompleto(e.iniciado_em)}</td>
                    <td className="px-4 py-3 text-right text-ink/80">{e.lojas}</td>
                    <td className="px-4 py-3 text-right text-ink/80">{e.encontradas}</td>
                    <td className="px-4 py-3 text-right font-semibold text-ink">{e.respondidas}</td>
                    <td className={e.erros > 0
                      ? "px-4 py-3 text-right font-bold text-red-600 dark:text-red-400"
                      : "px-4 py-3 text-right text-ink/40"}>{e.erros}</td>
                    <td className="px-5 py-3 text-right text-muted">{duracao(e.duracao_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Cartao>
      )}
    </div>
  );
}
