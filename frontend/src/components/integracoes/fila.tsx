"use client";

import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { api } from "@/lib/api";
import type { AvaliacaoExterna, FilaGoogle as FilaGoogleApi, Origem } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { num } from "@/lib/format";
import {
  Aviso, BOTAO_LINHA, BOTAO_SECUNDARIO, CAMPO, Carregando, Espinha, Nota, Vazio,
  comentarioOu, desde, mensagemDe, quando, textoPrazo,
} from "./partes";

interface PropsFila {
  lojaId: string;
  /** Abre a tela de responder naquela avaliação. */
  onAbrir: (reviewId: string) => void;
}

/* -------------------------------------------------------------------------- */
/* Linha                                                                      */
/* -------------------------------------------------------------------------- */

function encurtar(texto: string, n: number): string {
  const t = texto.trim();
  return t.length <= n ? t : t.slice(0, n).trim() + "…";
}

function Linha({ origem, av, onAbrir }: { origem: Origem; av: AvaliacaoExterna; onAbrir: () => void }) {
  const respostaPublicada = av.registro?.resposta ?? av.respostas[0]?.texto ?? "";
  return (
    <li className={clsx(
      "relative overflow-hidden rounded-2xl border border-line/12 bg-surface shadow-domani-lift",
      av.respondida && "opacity-75",
    )}>
      <Espinha urgencia={av.urgencia} />
      <div className="flex flex-col gap-3 py-4 pl-5 pr-4 sm:flex-row sm:items-start sm:gap-5 sm:pl-6">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Nota n={av.nota} />
            {av.encaminhamento === "aguardando" ? (
              <span className="text-xs font-semibold text-muted">aguardando o Google</span>
            ) : av.encaminhamento === "sem_confirmacao" ? (
              <span className="text-xs font-bold text-domani-orange-600">não confirmada, publique de novo</span>
            ) : av.respondida ? (
              <span className="text-xs font-semibold text-muted">respondida</span>
            ) : av.prazo_seg != null ? (
              <span className={clsx(
                "text-xs font-bold",
                av.urgencia === "quente" ? "text-domani-orange-600" : "text-ink/70",
              )}>
                {textoPrazo(av.prazo_seg)}
              </span>
            ) : (
              <span className="text-xs font-bold text-ink/70">sem resposta</span>
            )}
            {av.autor && <span className="truncate text-xs font-semibold text-ink/80">{av.autor}</span>}
            <span className="ml-auto text-xs text-muted [font-variant-numeric:tabular-nums]">
              {quando(av.criada_em)}
              {av.pedido && <>, pedido {av.pedido}</>}
            </span>
          </p>

          <p className={clsx(
            "mt-2.5 text-[15px] leading-relaxed [overflow-wrap:anywhere]",
            av.comentario ? "text-ink" : "text-muted",
          )}>
            {comentarioOu(av.comentario)}
          </p>

          {av.respondida && respostaPublicada && (
            <p className="mt-2 border-l-2 border-line/15 pl-3 text-sm text-ink/65 [overflow-wrap:anywhere]">
              {encurtar(respostaPublicada, 180)}
            </p>
          )}
          {av.registro?.erro && (
            <p className="mt-2 text-xs text-red-600 [overflow-wrap:anywhere] dark:text-red-400">
              Última tentativa falhou: {encurtar(av.registro.erro, 180)}
            </p>
          )}

          {origem === "ifood" && (
            // ID e status crus ficam visíveis de propósito: a homologação do
            // iFood pede esses campos na listagem.
            <p className="mt-2 break-all text-[11px] text-muted">
              {av.id}{av.status && <>, {av.status}</>}
            </p>
          )}
        </div>

        <button
          onClick={onAbrir}
          className={clsx(av.respondida ? [BOTAO_SECUNDARIO, "px-4 py-2"] : BOTAO_LINHA, "shrink-0")}
        >
          {av.respondida ? "Ver" : "Responder"}
        </button>
      </div>
    </li>
  );
}

/* -------------------------------------------------------------------------- */
/* iFood                                                                      */
/* -------------------------------------------------------------------------- */

interface FiltroIfood { de: string; ate: string; tamanho: string; pagina: number }

export function FilaIfood({ lojaId, onAbrir }: PropsFila) {
  // Dois estados: o que está digitado e o que foi aplicado. A consulta só sai
  // no "Filtrar" — cada tecla no campo de data não deve virar requisição.
  const [form, setForm] = useState<FiltroIfood>({ de: "", ate: "", tamanho: "", pagina: 1 });
  const [aplicado, setAplicado] = useState<FiltroIfood>(form);
  const [idBusca, setIdBusca] = useState("");

  const q = useApi(() => api.integracoes.filaIfood(lojaId, {
    de: aplicado.de || undefined,
    ate: aplicado.ate || undefined,
    // Valor acima do teto segue como está: é a API do iFood que recusa, e o
    // erro dela aparece logo abaixo.
    tamanho: aplicado.tamanho ? Number(aplicado.tamanho) : undefined,
    pagina: aplicado.pagina,
  }), [lojaId, aplicado]);
  const d = q.data;

  const irPara = (pagina: number) => {
    const novo = { ...form, pagina: Math.max(1, pagina) };
    setForm(novo);
    setAplicado(novo);
  };

  return (
    <div className="space-y-3">
      <form
        onSubmit={(e) => { e.preventDefault(); setAplicado({ ...form }); }}
        className="rounded-2xl border border-line/12 bg-surface p-4 shadow-domani-lift"
      >
        <div className="flex flex-wrap items-end gap-3">
          <label className="w-40">
            <span className="mb-1.5 block text-xs font-bold text-ink/70">De</span>
            <input type="date" value={form.de} className={CAMPO}
                   onChange={(e) => setForm({ ...form, de: e.target.value })} />
          </label>
          <label className="w-40">
            <span className="mb-1.5 block text-xs font-bold text-ink/70">Até</span>
            <input type="date" value={form.ate} className={CAMPO}
                   onChange={(e) => setForm({ ...form, ate: e.target.value })} />
          </label>
          <label className="w-28">
            <span className="mb-1.5 block text-xs font-bold text-ink/70">Por página</span>
            <input type="number" min={1} inputMode="numeric" value={form.tamanho} className={CAMPO}
                   placeholder={String(d?.filtro.tamanho ?? 20)}
                   onChange={(e) => setForm({ ...form, tamanho: e.target.value })} />
          </label>
          <label className="w-24">
            <span className="mb-1.5 block text-xs font-bold text-ink/70">Página</span>
            <input type="number" min={1} inputMode="numeric" value={form.pagina} className={CAMPO}
                   onChange={(e) => setForm({ ...form, pagina: Math.max(1, Number(e.target.value) || 1) })} />
          </label>
          <button type="submit" className={BOTAO_SECUNDARIO}>Filtrar</button>
        </div>
        <p className="mt-2.5 text-xs text-muted">
          Sem datas, a fila mostra os últimos 85 dias. O iFood aceita no máximo{" "}
          {d?.max_por_pagina ?? 50} itens por página; valores maiores são enviados
          assim mesmo e a resposta da API aparece abaixo.
        </p>
      </form>

      {q.loading && <Carregando rotulo="Consultando o iFood" />}
      {q.error && <Aviso tipo="erro">{q.error}</Aviso>}
      {d?.erro && <Aviso tipo="erro">{d.erro}</Aviso>}

      {d && !q.loading && !d.erro && (
        <>
          {d.pagina.total > 0 && (
            <p className="px-1 text-sm text-muted">
              {num(d.pagina.total)} {d.pagina.total === 1 ? "avaliação" : "avaliações"} no período,
              página {d.pagina.page} de {Math.max(1, d.pagina.page_count)}
            </p>
          )}

          {d.avaliacoes.length === 0 ? (
            <Vazio titulo="Nenhuma avaliação neste período">
              Ajuste as datas acima, ou volte mais tarde: o iFood publica as
              avaliações conforme os clientes respondem.
            </Vazio>
          ) : (
            <ul className="space-y-2.5">
              {d.avaliacoes.map((av) => (
                <Linha key={av.id} origem="ifood" av={av} onAbrir={() => onAbrir(av.id)} />
              ))}
            </ul>
          )}

          {(aplicado.pagina > 1 || d.avaliacoes.length > 0) && (
            <nav className="flex items-center justify-between gap-3" aria-label="Paginação">
              <button onClick={() => irPara(aplicado.pagina - 1)} disabled={aplicado.pagina <= 1}
                      className={BOTAO_SECUNDARIO}>
                Página anterior
              </button>
              <button onClick={() => irPara(aplicado.pagina + 1)}
                      disabled={d.pagina.page_count > 0 && aplicado.pagina >= d.pagina.page_count}
                      className={BOTAO_SECUNDARIO}>
                Próxima página
              </button>
            </nav>
          )}
        </>
      )}

      <form
        onSubmit={(e) => { e.preventDefault(); if (idBusca.trim()) onAbrir(idBusca.trim()); }}
        className="flex flex-wrap items-end gap-3 rounded-2xl border border-dashed border-line/20 px-4 py-4"
      >
        <label className="min-w-[240px] flex-1">
          <span className="mb-1.5 block text-xs font-bold text-ink/70">Consultar avaliação por ID</span>
          <input value={idBusca} onChange={(e) => setIdBusca(e.target.value)} required
                 placeholder="Cole o ID da avaliação" className={CAMPO} />
        </label>
        <button type="submit" className={BOTAO_SECUNDARIO}>Consultar</button>
      </form>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Google                                                                     */
/* -------------------------------------------------------------------------- */

type FiltroGoogle = "pendentes" | "todas";

export function FilaGoogle({ lojaId, onAbrir }: PropsFila) {
  const [filtro, setFiltro] = useState<FiltroGoogle>("pendentes");
  const [dados, setDados] = useState<FilaGoogleApi | null>(null);
  const [itens, setItens] = useState<AvaliacaoExterna[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [maisCarregando, setMaisCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Vem do que a leitura automática guardou, em páginas de 50: "carregar mais"
  // acumula as páginas em vez de trocar a lista, senão o que a pessoa já leu
  // some da tela.
  const carregar = useCallback(async (token: string | null) => {
    if (token) setMaisCarregando(true);
    else setCarregando(true);
    setErro(null);
    try {
      const r = await api.integracoes.filaGoogle(lojaId, { filtro, page_token: token });
      setDados(r);
      setItens((antes) => (token ? [...antes, ...r.avaliacoes] : r.avaliacoes));
    } catch (e) {
      setErro(mensagemDe(e, "Não foi possível carregar as avaliações."));
    } finally {
      setCarregando(false);
      setMaisCarregando(false);
    }
  }, [lojaId, filtro]);

  useEffect(() => { void carregar(null); }, [carregar]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-xl border border-line/15 bg-surface p-1" role="group" aria-label="Filtro">
          {([["pendentes", "Sem resposta"], ["todas", "Todas"]] as const).map(([valor, rotulo]) => (
            <button
              key={valor}
              onClick={() => setFiltro(valor)}
              aria-pressed={filtro === valor}
              className={clsx(
                "rounded-lg px-3.5 py-1.5 text-sm font-semibold transition",
                filtro === valor ? "bg-domani-graphite text-white dark:bg-white dark:text-domani-graphite" : "text-ink/65 hover:text-ink",
              )}
            >
              {rotulo}
            </button>
          ))}
        </div>
        {dados && !dados.erro && (
          <p className="text-sm text-muted">
            {dados.media != null && <>Média {dados.media.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}, </>}
            {dados.total > 0 && <>{num(dados.total)} avaliações no perfil, </>}
            lidas do Google {desde(dados.lida_em)}
          </p>
        )}
      </div>

      {carregando && <Carregando rotulo="Carregando as avaliações" />}
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {dados?.erro && <Aviso tipo="erro">{dados.erro}</Aviso>}

      {dados && !carregando && !dados.erro && (
        <>
          {itens.length === 0 ? (
            <Vazio titulo={filtro === "pendentes" ? "Tudo respondido por aqui" : "Nenhuma avaliação"}>
              {filtro === "pendentes"
                ? <>Nenhuma avaliação sem resposta entre as {num(dados.varridas)} lidas desta unidade.</>
                : "Nenhuma avaliação lida desta unidade ainda."}
            </Vazio>
          ) : (
            <ul className="space-y-2.5">
              {itens.map((av) => (
                <Linha key={av.id} origem="google" av={av} onAbrir={() => onAbrir(av.id)} />
              ))}
            </ul>
          )}

          {dados.proxima && (
            <div className="flex justify-center pt-1">
              <button onClick={() => carregar(dados.proxima)} disabled={maisCarregando} className={BOTAO_SECUNDARIO}>
                {maisCarregando ? "Carregando…" : "Carregar avaliações mais antigas"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
