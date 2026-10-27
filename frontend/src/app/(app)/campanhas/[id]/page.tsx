"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AvisoSimulacao, PainelCota } from "@/components/campanhas/painel-cota";
import { SeloParceiro, enderecoDe } from "@/components/campanhas/lista-campanhas";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { CLIENTE } from "@/config/cliente";
import { api } from "@/lib/api";
import { dataHoraBR, num } from "@/lib/format";
import type { Destinatario, DisparoIniciado } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { useAuth } from "@/providers/auth";

const TOM_DEST: Record<string, string> = {
  enviado: "bg-emerald-500/15 text-emerald-700",
  pendente: "bg-app text-ink/60",
  suprimido: "bg-red-500/10 text-red-600",
  falhou: "bg-amber-500/15 text-amber-700",
};

export default function CampanhaPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const rel = useApi(() => api.email.campanhas.relatorio(id), [id]);
  const dest = useApi(() => api.email.campanhas.destinatarios(id), [id]);

  const [confirmar, setConfirmar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<DisparoIniciado | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const c = rel.data?.campanha;
  const s = rel.data?.stats;

  // Enquanto a campanha está enviando, o relatório se atualiza sozinho.
  //
  // Dois motivos: quem disparou vê o número subindo em vez de olhar uma tela
  // parada achando que travou; e se a aba for fechada e reaberta, o estado real
  // aparece na hora — sem depender de a pessoa lembrar de atualizar.
  const emAndamento = c?.status === "enviando";
  useEffect(() => {
    if (!emAndamento) return;
    const t = setInterval(() => { rel.reload(); dest.reload(); }, 8000);
    return () => clearInterval(t);
  }, [emAndamento]); // eslint-disable-line react-hooks/exhaustive-deps

  async function disparar() {
    setEnviando(true);
    setErro(null);
    try {
      // Responde na hora: o envio segue em segundo plano no servidor. O
      // relatório abaixo se atualiza sozinho e mostra o número subindo.
      const r = await api.email.campanhas.enviar(id);
      setResultado(r);
      setConfirmar(false);
      rel.reload();
      dest.reload();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha no disparo.");
      setConfirmar(false);
    } finally {
      setEnviando(false);
    }
  }

  if (rel.error) return <p className="px-6 py-16 text-center text-sm text-red-500">{rel.error}</p>;
  if (!c) return <div className="skeleton h-40 rounded-3xl" />;

  // TRAVA DE DISPARO
  //
  // O botão só existe para campanha que ainda não terminou, e fica bloqueado
  // enquanto o envio está em curso. É deliberado que a trava venha do STATUS da
  // campanha (que está no banco) e não de um estado da tela: atualizar a página,
  // fechar a aba ou abrir em outro computador não libera o botão.
  //
  // Isso não substitui as proteções do backend — índice único por
  // (campanha, e-mail), status por destinatário e commit por mensagem já impedem
  // o reenvio. A trava aqui evita o SUSTO: sem ela, quem vê a tela parada clica
  // de novo e fica achando que mandou duas vezes.
  const terminou = ["enviada", "cancelada"].includes(c.status);

  // Campanha AGENDADA para o futuro não mostra o botão de disparar.
  //
  // Quem cria uma campanha com data costuma clicar em "Disparar" logo depois,
  // por hábito — como faz com as sem data — e o e-mail sairia na hora. No lugar
  // do botão, a tela diz quando ela vai sair, e que sai sozinha.
  const agendadaFutura =
    c.status === "agendada" &&
    !!c.agendada_para &&
    new Date(c.agendada_para).getTime() > Date.now();
  const podeDisparar = can("campanhas:send") && !terminou && !agendadaFutura;

  // Há gente reservada por um disparo em curso? Enquanto houver, o botão fica
  // travado — é o sinal de que existe processo rodando AGORA, mesmo que a tela
  // desta pessoa não seja a que disparou.
  //
  // Já uma campanha 'enviando' com fila e NADA em processamento é o caso legítimo
  // de continuar: a cota acabou no meio e a leva seguinte precisa sair. Bloquear
  // isso deixaria a campanha parada esperando o timer.
  const emProcessamento = (s?.processando ?? 0) > 0;
  const botaoBloqueado = enviando || emProcessamento;
  // Volta para a aba de parceiros só se ela existir neste CRM.
  const daAbaParceiros = c.lista === "parceiros" && CLIENTE.modulos.parceiros;

  return (
    <div className="space-y-4">
      <header className="rounded-3xl border border-line/10 bg-surface px-5 py-5 shadow-domani-lift sm:px-6">
        <Link href={daAbaParceiros ? "/campanhas?aba=parceiros" : "/campanhas"}
              className="text-xs font-bold text-muted hover:text-domani-orange-600">
          ← E-mail{daAbaParceiros ? " · Parceiros" : ""}
        </Link>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-2xl font-extrabold tracking-tight">{c.nome}</h1>
              {c.lista === "parceiros" && <SeloParceiro />}
            </div>
            <p className="mt-1 text-sm text-muted">
              {c.segmento_label} · {num(c.com_email)} destinatários · {c.status}
              {c.remetente && <> · sai por {enderecoDe(c.remetente)}</>}
            </p>
          </div>
          {agendadaFutura && (
            <div className="flex flex-col items-end gap-1 text-right">
              <span className="rounded-xl border border-domani-orange/30 bg-domani-orange/10 px-4 py-2.5 text-sm font-bold text-domani-orange-600">
                Agendada para{" "}
                {new Date(c.agendada_para as string).toLocaleString("pt-BR", {
                  day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
                })}
              </span>
              <span className="text-[11px] text-muted">
                Sai sozinha nesse horário · não é preciso disparar
              </span>
            </div>
          )}
          {podeDisparar && (
            <div className="flex flex-col items-end gap-1">
              <button onClick={() => setConfirmar(true)} disabled={botaoBloqueado}
                      className="rounded-xl bg-domani-orange px-5 py-2.5 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:cursor-not-allowed disabled:opacity-40">
                {botaoBloqueado
                  ? "Enviando…"
                  : c.status === "enviando"
                    ? "Continuar envio"
                    : "Disparar campanha"}
              </button>
              {emProcessamento && (
                <span className="text-[11px] text-muted">
                  Envio em andamento · não é preciso clicar de novo
                </span>
              )}
            </div>
          )}
        </div>
      </header>

      {resultado && (
        <div className="space-y-3">
          <AvisoSimulacao simulado={resultado.simulado} />
          <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
            <p className="text-sm font-bold text-emerald-700">
              Envio iniciado · {num(resultado.na_fila)} na fila
            </p>
            <p className="mt-0.5 text-xs text-emerald-700/90">
              Pode fechar esta tela — o envio continua no servidor. Os números
              abaixo se atualizam sozinhos.
            </p>
            {resultado.cabe_agora < resultado.na_fila && (
              <p className="mt-0.5 text-xs text-emerald-700/90">
                {num(resultado.cabe_agora)} saem agora; o restante entra
                automaticamente quando a cota liberar.
              </p>
            )}
          </div>
        </div>
      )}

      {erro && (
        <p className="rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          {erro}
        </p>
      )}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metrica rotulo="Enviados" valor={num(s?.enviados ?? 0)}
                 apoio={`de ${num(s?.publico ?? 0)} no público`} destaque />
        <Metrica rotulo="Aberturas" valor={pct(s?.taxa_abertura)}
                 apoio={`${num(s?.aberturas ?? 0)} pessoas · quem bloqueia imagem não conta`} />
        <Metrica rotulo="Cliques" valor={pct(s?.taxa_clique)}
                 apoio={`${num(s?.cliques ?? 0)} pessoas`} />
        <Metrica rotulo="Na fila" valor={num(s?.pendentes ?? 0)}
                 apoio="saem quando a cota liberar" />
      </section>

      {/* Saúde da entrega. Fica separado das métricas de engajamento porque
          responde outra pergunta: não "deu resultado?", mas "está queimando a
          reputação do domínio?". */}
      <section className="grid gap-3 sm:grid-cols-3">
        <Metrica rotulo="Bounce definitivo" valor={pct(s?.taxa_bounce_hard)}
                 apoio={`${num(s?.bounce_hard ?? 0)} caixas inexistentes · removidas da base`}
                 alerta={Number(s?.taxa_bounce_hard ?? 0) > 2} />
        <Metrica rotulo="Bounce temporário" valor={pct(s?.taxa_bounce_soft)}
                 apoio={`${num(s?.bounce_soft ?? 0)} · voltam para a fila`} />
        <Metrica rotulo="Descadastros" valor={pct(s?.taxa_descadastro)}
                 apoio={`${num(s?.descadastros ?? 0)} pediram para sair`}
                 alerta={Number(s?.taxa_descadastro ?? 0) > 0.5} />
      </section>

      <PainelCota />

      <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
        <div className="border-b border-line/10 px-5 py-4">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
            Destinatários
          </h2>
        </div>
        {dest.loading ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-9 rounded-lg" />)}
          </div>
        ) : !dest.data?.length ? (
          <p className="px-6 py-12 text-center text-sm text-muted">
A lista de quem recebeu aparece aqui depois do disparo.
          </p>
        ) : (
          <div className="max-h-[420px] overflow-y-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead className="sticky top-0 bg-surface">
                <tr className="border-b border-line/10 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
                  <th className="px-5 py-3">Contato</th>
                  <th className="px-5 py-3">Situação</th>
                  <th className="px-5 py-3 text-right">Aberturas</th>
                  <th className="px-5 py-3 text-right">Cliques</th>
                  <th className="px-5 py-3">Enviado</th>
                </tr>
              </thead>
              <tbody>
                {dest.data.map((d: Destinatario) => (
                  <tr key={d.id} className="border-b border-line/[0.08]">
                    <td className="px-5 py-2.5">
                      <div className="font-medium text-ink">{d.nome ?? "—"}</div>
                      <div className="text-xs text-muted">{d.email}</div>
                    </td>
                    <td className="px-5 py-2.5">
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${TOM_DEST[d.status]}`}>
                        {d.status}
                      </span>
                      {d.erro && (
                        <div className="mt-0.5 max-w-[280px] truncate text-[11px] text-muted" title={d.erro}>
                          {d.erro}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-2.5 text-right text-ink/70 [font-variant-numeric:tabular-nums]">
                      {d.aberturas}
                    </td>
                    <td className="px-5 py-2.5 text-right text-ink/70 [font-variant-numeric:tabular-nums]">
                      {d.cliques}
                    </td>
                    <td className="px-5 py-2.5 text-xs text-ink/70">{dataHoraBR(d.sent_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <ConfirmDialog
        open={confirmar}
        title="Disparar esta campanha?"
        description={
          <>
            {num(c.com_email)} pessoa(s) vão receber. <strong>Não tem como desfazer</strong>:
            e-mail enviado não volta. O envio roda em segundo plano, então você pode
            fechar a tela — e se a cota não cobrir tudo agora, o restante sai
            automaticamente quando ela liberar.
          </>
        }
        confirmLabel={enviando ? "Iniciando…" : "Sim, disparar"}
        cancelLabel="Cancelar"
        onConfirm={disparar}
        onClose={() => setConfirmar(false)}
      />
    </div>
  );
}

/** Percentual vindo da API. Nulo vira "—": sem envio, 0% seria mentira. */
function pct(valor: string | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return `${Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function Metrica({
  rotulo, valor, apoio, destaque, alerta,
}: {
  rotulo: string;
  valor: string;
  apoio?: string;
  destaque?: boolean;
  /** Vermelho quando o número exige ação — bounce ou descadastro acima do normal. */
  alerta?: boolean;
}) {
  return (
    <div className={`rounded-3xl border bg-surface p-5 shadow-domani-lift ${
      alerta ? "border-red-500/30" : "border-line/10"
    }`}>
      <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">{rotulo}</p>
      <p className={`mt-2 font-display text-3xl font-extrabold tracking-tight [font-variant-numeric:tabular-nums] ${
        alerta ? "text-red-500" : destaque ? "text-domani-orange" : "text-ink"
      }`}>
        {valor}
      </p>
      {apoio && <p className="mt-1 text-xs text-muted">{apoio}</p>}
    </div>
  );
}
