"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { api } from "@/lib/api";
import type { AvaliacaoExterna, DetalheAvaliacao, Origem } from "@/lib/api-types";
import { Icon } from "@/components/ui/icon";
import {
  Aviso, BOTAO_PRINCIPAL, BOTAO_SECUNDARIO, CAMPO, Carregando, Nota,
  comentarioOu, mensagemDe, quandoCompleto, textoPrazo,
} from "./partes";

const MIN_IFOOD = 10;
const MAX_IFOOD = 300;
const MAX_BYTES_GOOGLE = 4096;

interface Props {
  origem: Origem;
  lojaId: string;
  reviewId: string;
  /** Vai para outra avaliação da mesma loja. */
  onIr: (reviewId: string) => void;
  /** Volta para a fila da loja. */
  onVoltar: () => void;
}

/**
 * Superfície de trabalho, não formulário: a fila da loja fica numa coluna à
 * esquerda, o comentário do cliente aparece em corpo grande, e o botão principal
 * é "publicar e ir para a próxima". Dá para zerar a fila sem voltar à listagem a
 * cada resposta.
 */
export function Responder({ origem, lojaId, reviewId, onIr, onVoltar }: Props) {
  const [d, setD] = useState<DetalheAvaliacao | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [falha, setFalha] = useState<string | null>(null);

  const [texto, setTexto] = useState("");
  const [publicando, setPublicando] = useState(false);
  const [sugerindo, setSugerindo] = useState(false);
  const [erroAcao, setErroAcao] = useState<string | null>(null);
  const [publicada, setPublicada] = useState(false);
  // A última resposta que saiu daqui. Sobrevive à troca de avaliação: o
  // "publicar e ir para a próxima" abre a seguinte na hora, e sem isto não
  // sobrava nenhum sinal de que a anterior foi enviada.
  const [enviada, setEnviada] = useState<{ proxima: string; autor: string | null; hora: string } | null>(null);
  const campo = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let vivo = true;
    setCarregando(true);
    setFalha(null);
    setErroAcao(null);
    setPublicada(false);
    setTexto("");
    api.integracoes.detalhe(origem, lojaId, reviewId)
      .then((r) => {
        if (!vivo) return;
        setD(r);
        // No Google a resposta pode ser editada: o campo já abre com o texto
        // que está publicado, pronto para corrigir — ou, se ainda não apareceu
        // lá, com o que foi enviado ao NichoChat.
        if (origem === "google") {
          const reg = r.avaliacao?.registro;
          const enviado = reg?.status === "encaminhada" ? reg.resposta : null;
          const publicado = r.avaliacao?.respostas[0]?.texto;
          if (enviado || publicado) setTexto(enviado || publicado || "");
        }
      })
      .catch((e) => { if (vivo) setFalha(mensagemDe(e, "Não foi possível abrir a avaliação.")); })
      .finally(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [origem, lojaId, reviewId]);

  // Aparece na avaliação que abriu logo depois do envio. Se a respondida era a
  // última da fila, quem confirma é o rodapé dela.
  const confirmacao = enviada && enviada.proxima === reviewId && (
    <Aviso tipo="ok">
      <strong>Resposta {enviada.autor ? `para ${enviada.autor} ` : ""}
        {origem === "google" ? "enviada" : "publicada no iFood"} às {enviada.hora}.</strong>{" "}
      {origem === "google" ? "Aparece no Google em instantes. " : ""}
      Esta é a próxima da fila.
    </Aviso>
  );

  if (carregando) {
    return <div className="space-y-3">{confirmacao}<Carregando rotulo="Abrindo a avaliação" /></div>;
  }
  if (falha || !d) return <Aviso tipo="erro">{falha ?? "Não foi possível abrir a avaliação."}</Aviso>;

  const av = d.avaliacao;
  const fila = d.fila;
  const posicao = fila.findIndex((f) => f.id === reviewId);
  // A que vem depois desta na fila; se esta era a última, volta para a primeira
  // que sobrou.
  const proxima = fila.find((_, i) => i > posicao && fila[i].id !== reviewId)
    ?? fila.find((f) => f.id !== reviewId)
    ?? null;

  const tamanho = Array.from(texto).length;
  const bytes = new TextEncoder().encode(texto).length;
  const foraDoLimite = origem === "ifood"
    ? tamanho < MIN_IFOOD || tamanho > MAX_IFOOD
    : bytes > MAX_BYTES_GOOGLE;

  async function sugerir() {
    setSugerindo(true);
    setErroAcao(null);
    try {
      const r = await api.integracoes.sugerir(origem, lojaId, reviewId);
      setTexto(r.texto);
      campo.current?.focus();
    } catch (e) {
      setErroAcao(mensagemDe(e, "A sugestão não pôde ser gerada."));
    } finally {
      setSugerindo(false);
    }
  }

  async function publicar(e: React.FormEvent) {
    e.preventDefault();
    setPublicando(true);
    setErroAcao(null);
    setEnviada(null);
    try {
      await api.integracoes.responder(origem, lojaId, reviewId, texto);
      if (proxima) {
        setEnviada({
          proxima: proxima.id, autor: av?.autor ?? null,
          hora: new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
        });
        onIr(proxima.id);
      }
      else setPublicada(true);
    } catch (err) {
      // A mensagem é a da plataforma, como veio. No iFood o texto segue sem
      // validação local justamente para o erro real aparecer aqui.
      setErroAcao(mensagemDe(err, "A resposta não foi publicada."));
    } finally {
      setPublicando(false);
    }
  }

  const jaRespondida = Boolean(av?.respondida);
  // iFood: resposta publicada é definitiva. O formulário continua acessível
  // (recolhido) porque demonstrar a recusa da API é um cenário de homologação.
  const recolherFormulario = origem === "ifood" && jaRespondida;

  const formulario = av && (
    <form onSubmit={publicar} className="space-y-3">
      <div className="flex items-end justify-between gap-3">
        <label htmlFor="texto-resposta" className="text-sm font-bold text-ink">
          Resposta pública
        </label>
        <span
          aria-live="polite"
          className={clsx(
            "text-xs [font-variant-numeric:tabular-nums]",
            foraDoLimite && texto ? "font-bold text-domani-orange-600" : "text-muted",
          )}
        >
          {origem === "ifood" ? `${tamanho} / ${MAX_IFOOD}` : `${tamanho} caracteres`}
        </span>
      </div>

      <textarea
        id="texto-resposta"
        ref={campo}
        rows={6}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder="Escreva, ou peça uma sugestão à IA."
        className={clsx(CAMPO, "resize-y text-[15px] leading-relaxed")}
      />

      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" disabled={publicando || sugerindo} className={BOTAO_PRINCIPAL}>
          {publicando ? (origem === "google" ? "Enviando…" : "Publicando…")
            : origem === "google" && jaRespondida ? "Atualizar resposta"
            : proxima ? "Publicar e ir para a próxima"
            : "Publicar resposta"}
        </button>
        <button type="button" onClick={sugerir} disabled={publicando || sugerindo} className={BOTAO_SECUNDARIO}>
          <Icon name="sparkles" className="h-4 w-4" strokeWidth={1.8} />
          {sugerindo ? "Escrevendo…" : texto ? "Gerar outra sugestão" : "Gerar sugestão"}
        </button>
        {proxima && (
          <button type="button" onClick={() => onIr(proxima.id)} disabled={publicando}
                  className="rounded-xl px-3 py-2.5 text-sm font-semibold text-ink/60 transition hover:text-ink">
            Pular
          </button>
        )}
      </div>

      <p className="text-xs leading-relaxed text-muted">
        {origem === "ifood" ? (
          <>O iFood aceita entre {MIN_IFOOD} e {MAX_IFOOD} caracteres. O texto é enviado
          como está e a resposta da API aparece nesta tela. Publicação é definitiva:
          não dá para editar depois.</>
        ) : (
          <>A resposta aparece no perfil da unidade no Google, logo abaixo da avaliação.
          Dá para corrigir depois: publicar de novo substitui o texto.</>
        )}
      </p>
    </form>
  );

  // grid-cols-1, e não a coluna implícita: sem o minmax(0,1fr) a faixa rolável
  // da fila empurraria a página para além da largura do celular.
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_minmax(0,1fr)] lg:items-start">
      <Trilho origem={origem} fila={fila} atual={reviewId} onIr={onIr} />

      <div className="min-w-0 space-y-3">
        {confirmacao}
        {d.erro && <Aviso tipo="erro">{d.erro}</Aviso>}

        {!av ? (
          <div className="rounded-2xl border border-line/12 bg-surface p-6 shadow-domani-lift">
            <p className="text-sm text-muted">ID consultado</p>
            <p className="mt-1 break-all font-semibold text-ink">{d.review_id}</p>
            <button onClick={onVoltar} className={clsx(BOTAO_SECUNDARIO, "mt-5")}>Voltar para a fila</button>
          </div>
        ) : (
          <article className="rounded-2xl border border-line/12 bg-surface shadow-domani-lift">
            <header className="flex flex-wrap items-start gap-4 border-b border-line/10 px-5 py-5 sm:px-7">
              <Nota n={av.nota} grande />
              <div className="min-w-0 flex-1">
                <p className="font-display text-base font-extrabold tracking-tight text-ink">
                  {av.autor ?? (origem === "ifood" && av.pedido ? `Pedido ${av.pedido}` : "Cliente não identificado")}
                </p>
                <p className="mt-0.5 text-xs text-muted">
                  {d.loja.nome}, {quandoCompleto(av.criada_em)}
                </p>
              </div>

              {av.prazo_seg != null && !av.respondida && (
                <div className="w-full sm:w-44">
                  <p className={clsx(
                    "font-display text-base font-extrabold tracking-tight sm:text-right",
                    av.urgencia === "quente" ? "text-domani-orange-600" : "text-ink",
                  )}>
                    {textoPrazo(av.prazo_seg)}
                  </p>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line/10"
                       role="progressbar" aria-label="Prazo de resposta consumido"
                       aria-valuemin={0} aria-valuemax={100} aria-valuenow={av.prazo_perc ?? 0}>
                    <i className={clsx(
                      "block h-full rounded-full",
                      av.urgencia === "quente" ? "bg-domani-orange" : av.urgencia === "morno" ? "bg-domani-orange/45" : "bg-ink/25",
                    )} style={{ width: `${av.prazo_perc ?? 0}%` }} />
                  </div>
                  <p className="mt-1 text-[11px] text-muted sm:text-right">do prazo de 5 dias</p>
                </div>
              )}
            </header>

            <div className="space-y-5 px-5 py-6 sm:px-7">
              <blockquote className={clsx(
                "max-w-[68ch] text-lg leading-relaxed [overflow-wrap:anywhere] sm:text-xl",
                av.comentario ? "text-ink" : "text-muted",
              )}>
                {comentarioOu(av.comentario)}
              </blockquote>

              {av.respostas.length > 0 && (
                <div>
                  <h3 className="text-sm font-bold text-ink">
                    {av.respostas.length === 1 ? "Resposta publicada" : "Respostas publicadas"}
                  </h3>
                  {av.respostas.map((r, i) => (
                    <div key={i} className="mt-2 max-w-[68ch] border-l-2 border-line/15 pl-4">
                      <p className="text-[15px] leading-relaxed text-ink/80 [overflow-wrap:anywhere]">{r.texto}</p>
                      {r.criada_em && <p className="mt-1 text-xs text-muted">{quandoCompleto(r.criada_em)}</p>}
                    </div>
                  ))}
                </div>
              )}

              {av.registro && av.registro.status !== "pendente" && (
                <Aviso tipo={av.registro.status === "erro" ? "erro"
                  : av.encaminhamento === "sem_confirmacao" ? "atencao" : "info"}>
                  {av.registro.status === "encaminhada" && av.encaminhamento !== "sem_confirmacao" && (
                    <>Resposta enviada em {quandoCompleto(av.registro.atualizado_em)}. Aparece no
                    Google em instantes; quando o Google confirmar, a avaliação sai da fila.</>
                  )}
                  {av.registro.status === "encaminhada" && av.encaminhamento === "sem_confirmacao" && (
                    <>{av.respostas.length > 0
                      ? <>No Google está outro texto, e não a resposta enviada em {quandoCompleto(av.registro.atualizado_em)}.</>
                      : <>A resposta enviada em {quandoCompleto(av.registro.atualizado_em)} não foi confirmada pelo Google.</>}
                    {" "}O texto já está no campo abaixo: é só publicar de novo. Se continuar
                    assim, avise o suporte.</>
                  )}
                  {av.registro.status === "enviada" && (
                    <>Publicada pelo CRM{av.registro.via === "agente" ? " (agente de IA)" : ""} em {quandoCompleto(av.registro.atualizado_em)}.
                    {av.respostas.length === 0 && av.registro.resposta && <> Texto enviado: “{av.registro.resposta}”</>}</>
                  )}
                  {av.registro.status === "ignorada" && (
                    <>O agente não respondeu esta avaliação: a nota ficou abaixo da nota mínima configurada.</>
                  )}
                  {av.registro.status === "erro" && (
                    <>A última tentativa de publicar falhou. {av.registro.erro}</>
                  )}
                </Aviso>
              )}

              {origem === "ifood" && (
                <details className="group text-sm">
                  <summary className="cursor-pointer select-none font-semibold text-ink/70 transition hover:text-ink">
                    Ver todos os campos da avaliação
                  </summary>
                  <dl className="mt-3 grid max-w-xl grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
                    <Campo rotulo="ID" valor={av.id} quebra />
                    <Campo rotulo="Nota" valor={String(av.score ?? av.nota)} />
                    <Campo rotulo="Status" valor={av.status ?? "não informado"} />
                    <Campo rotulo="Pedido" valor={texto_(av.campos.pedido_id)} quebra />
                    <Campo rotulo="Data do pedido" valor={quandoCompleto(texto_(av.campos.pedido_em) || null)} />
                    <Campo rotulo="Questionário" valor={texto_(av.campos.questionario)} quebra />
                    <Campo rotulo="Descartada" valor={simNao(av.campos.descartada)} />
                    <Campo rotulo="Moderada" valor={simNao(av.campos.moderada)} />
                    <Campo rotulo="Publicada" valor={simNao(av.campos.publicada)} />
                  </dl>
                </details>
              )}
            </div>

            <footer className="border-t border-line/10 px-5 py-5 sm:px-7">
              {publicada ? (
                <div className="space-y-4">
                  <Aviso tipo="ok">
                    {origem === "google"
                      ? "Resposta enviada. Aparece no Google em instantes."
                      : "Resposta publicada."}{" "}
                    Era a última da fila desta {origem === "ifood" ? "loja" : "unidade"}.
                  </Aviso>
                  <button onClick={onVoltar} className={BOTAO_SECUNDARIO}>Voltar para a fila</button>
                </div>
              ) : (
                <div className="space-y-3">
                  {erroAcao && <Aviso tipo="erro">{erroAcao}</Aviso>}
                  {recolherFormulario ? (
                    <>
                      <p className="text-sm text-muted">
                        Esta avaliação já tem resposta. No iFood a resposta é definitiva
                        e não aceita uma segunda.
                      </p>
                      <details className="text-sm">
                        <summary className="cursor-pointer select-none font-semibold text-ink/70 transition hover:text-ink">
                          Tentar publicar mesmo assim
                        </summary>
                        <div className="mt-4">{formulario}</div>
                      </details>
                    </>
                  ) : formulario}
                </div>
              )}
            </footer>
          </article>
        )}
      </div>
    </div>
  );
}

function texto_(v: string | boolean | null | undefined): string {
  return typeof v === "string" ? v : "";
}

function simNao(v: string | boolean | null | undefined): string {
  return v === true ? "sim" : "não";
}

function Campo({ rotulo, valor, quebra }: { rotulo: string; valor: string; quebra?: boolean }) {
  return (
    <>
      <dt className="text-muted">{rotulo}</dt>
      <dd className={clsx("text-ink", quebra && "break-all")}>{valor || "—"}</dd>
    </>
  );
}

/** A coluna lateral: o que ainda espera resposta nesta loja. */
function Trilho({ origem, fila, atual, onIr }: {
  origem: Origem;
  fila: AvaliacaoExterna[];
  atual: string;
  onIr: (id: string) => void;
}) {
  if (fila.length === 0) return <div className="hidden lg:block" />;
  return (
    <aside className="min-w-0 rounded-2xl border border-line/12 bg-surface shadow-domani-lift lg:sticky lg:top-20"
           aria-label="Fila de avaliações sem resposta">
      <p className="flex items-baseline gap-2 border-b border-line/10 px-4 py-3.5">
        <strong className="font-display text-xl font-extrabold text-ink [font-variant-numeric:tabular-nums]">{fila.length}</strong>
        <span className="text-xs text-muted">na fila</span>
      </p>
      {/* No celular a fila vira uma faixa rolável na horizontal, para o
          comentário — que é o trabalho — continuar no alto da tela. */}
      <ul className="scroll-area flex gap-1 overflow-x-auto p-1.5 lg:max-h-[calc(100vh-13rem)] lg:flex-col lg:overflow-y-auto lg:overflow-x-hidden">
        {fila.map((f) => {
          const ativo = f.id === atual;
          return (
            <li key={f.id} className="w-56 shrink-0 lg:w-auto">
              <button
                onClick={() => onIr(f.id)}
                aria-current={ativo ? "true" : undefined}
                className={clsx(
                  "block w-full rounded-xl px-3 py-2.5 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-domani-orange",
                  ativo ? "bg-app" : "hover:bg-app/60",
                )}
              >
                <span className="flex items-center gap-2">
                  <Nota n={f.nota} />
                  <span className={clsx(
                    "truncate text-xs",
                    f.urgencia === "quente" ? "font-bold text-domani-orange-600" : "text-muted",
                  )}>
                    {origem === "ifood" ? textoPrazo(f.prazo_seg) : (f.autor ?? "anônimo")}
                  </span>
                </span>
                <span className={clsx(
                  "mt-1.5 line-clamp-2 text-[13px] leading-snug",
                  ativo ? "text-ink" : "text-ink/65",
                )}>
                  {comentarioOu(f.comentario)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
