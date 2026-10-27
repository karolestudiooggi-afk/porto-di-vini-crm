"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { CLIENTE } from "@/config/cliente";
import { api } from "@/lib/api";
import type {
  ConfigIntegracao, ConfigIntegracaoPatch, LojaIntegracao, Origem,
  SincronizacaoGoogle, SituacaoIntegracoes,
} from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { dataHoraBR } from "@/lib/format";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import {
  Aviso, BOTAO_PRINCIPAL, BOTAO_SECUNDARIO, CAMPO, Carregando, Cartao,
  NOME_UNIDADE, desde, mensagemDe,
} from "./partes";

interface Props {
  origem: Origem;
  situacao: SituacaoIntegracoes;
  lojas: LojaIntegracao[];
  /** Tem `integracoes:config`. Sem ela a tela é só leitura. */
  podeConfigurar: boolean;
  /** Algo mudou (loja, conexão): quem está acima recarrega situação e lojas. */
  onMudou: () => void;
}

type Recado = { tipo: "ok" | "erro"; texto: string } | null;

const ROTULO = "mb-1.5 block text-xs font-bold text-ink/70";
const AJUDA = "mt-1.5 text-xs leading-relaxed text-muted";
const BOTAO_MENOR = "px-3 py-1.5 text-xs";

export function Configuracao(props: Props) {
  const { origem, podeConfigurar } = props;
  return (
    <div className="space-y-3">
      {!podeConfigurar && (
        <Aviso>
          Você pode ver a configuração, mas só administradores alteram conexão
          e modo de resposta.
        </Aviso>
      )}
      {origem === "ifood" ? <ConexaoIfood {...props} /> : <LigacaoNichoChat {...props} />}
      <ComoResponder {...props} />
      <Lojas {...props} />
      {/* No Google o caminho é o NichoChat; a conexão direta fica no fim, como opcional. */}
      {origem === "google" && <ConexaoGoogle {...props} />}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Conexão                                                                    */
/* -------------------------------------------------------------------------- */

function Situacao({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2.5 text-sm text-ink/85">
      <span aria-hidden="true" className={clsx(
        "mt-[7px] h-2 w-2 shrink-0 rounded-full",
        ok ? "bg-emerald-500" : "bg-domani-orange",
      )} />
      <span className="min-w-0 [overflow-wrap:anywhere]">{children}</span>
    </p>
  );
}

/** A chave e o modelo da IA ficam só no servidor: a tela apenas diz se há. */
function LinhaIA({ ia }: { ia: SituacaoIntegracoes["ia"] }) {
  return (
    <Situacao ok={ia.configurada}>
      {ia.configurada
        ? <>Sugestão por IA ligada (configurada no servidor).</>
        : <>Sugestão por IA desligada: falta <code>OPENAI_API_KEY</code> no <code>.env</code> do
            servidor. Dá para responder escrevendo à mão.</>}
    </Situacao>
  );
}

function ConexaoIfood({ situacao }: Props) {
  const s = situacao.ifood;
  return (
    <Cartao titulo="Conexão com o iFood"
            descricao="As credenciais do aplicativo ficam no servidor, não nesta tela.">
      <div className="space-y-2.5 px-5 py-4">
        <Situacao ok={s.configurado}>
          {s.configurado
            ? <>Aplicativo configurado. Client ID: <code className="break-all">{s.client_id}</code></>
            : <>Faltam <code>IFOOD_CLIENT_ID</code> e <code>IFOOD_CLIENT_SECRET</code> no <code>.env</code> do servidor.</>}
        </Situacao>
        <Situacao ok={s.agente_agendado}>
          {s.agente_agendado
            ? <>Agente rodando sozinho, a cada 15 minutos.</>
            : <>Agente desligado no servidor (<code>WORKER_DESLIGADO</code> no <code>.env</code>).</>}
        </Situacao>
        <LinhaIA ia={situacao.ia} />
        <p className={AJUDA}>
          Cada loja também precisa autorizar o aplicativo no Portal do Parceiro do
          iFood. Sem isso, a fila daquela loja mostra “não autorizou este aplicativo”.
        </p>
      </div>
    </Cartao>
  );
}

/** "5511900000000" → "+55 11 90000-0000". Outro formato volta como veio. */
function telefone(userId: string): string {
  const d = userId.replace(/\D/g, "");
  if (d.length < 12 || !d.startsWith("55")) return userId;
  const ddd = d.slice(2, 4);
  const resto = d.slice(4);
  return `+55 ${ddd} ${resto.slice(0, resto.length - 4)}-${resto.slice(-4)}`;
}

/**
 * Google: o caminho de verdade. A busca e a resposta passam pelo NichoChat, que
 * já tem a conexão com o Google; esta tela mostra se cada ponta está ligada e
 * o que o fluxo de lá precisa chamar.
 */
function LigacaoNichoChat({ situacao }: Props) {
  const n = situacao.google.nichochat;
  if (!n) {
    // Tela nova com a API antiga: acontece quando o frontend é atualizado e a
    // API não foi reiniciada. Explica em vez de derrubar a página inteira.
    return (
      <Cartao titulo="Ligação com o NichoChat">
        <div className="px-5 py-4">
          <Situacao ok={false}>
            A API do servidor ainda está na versão anterior. Reinicie o serviço da
            API no servidor e recarregue a página.
          </Situacao>
        </div>
      </Cartao>
    );
  }
  const buscaOk = n.api_configurada && n.busca_agendada && !n.ultimo_disparo_erro;
  return (
    <Cartao titulo="Ligação com o NichoChat"
            descricao="As avaliações do Google chegam e as respostas saem pelo NichoChat, que já tem a conexão com o Google. As chaves ficam no servidor, não nesta tela.">
      <div className="space-y-2.5 px-5 py-4">
        <Situacao ok={n.api_configurada}>
          {n.api_configurada
            ? <>CRM ligado à API do NichoChat. Busca pelo contato <code>{telefone(n.contato_user_id)}</code>;
                respostas pelo contato <code>{telefone(n.contato_resposta_user_id ?? n.contato_user_id)}</code>.
                Contato que não existir lá, o CRM cria.</>
            : <>Faltam <code>DOMANI_API_URL</code> e <code>DOMANI_API_KEY</code> no <code>.env</code> do servidor.</>}
        </Situacao>
        <Situacao ok={n.entrega_configurada}>
          {n.entrega_configurada
            ? <>Chave da entrega configurada: o CRM aceita as avaliações e as confirmações que o NichoChat envia.</>
            : <>Falta <code>WEBHOOK_GOOGLE_KEY</code> no <code>.env</code> do servidor: o CRM recusa o que o NichoChat envia.</>}
        </Situacao>
        <Situacao ok={buscaOk}>
          {!n.busca_agendada
            ? <>Busca automática desligada no servidor (<code>WORKER_DESLIGADO</code> no <code>.env</code>).</>
            : n.ultimo_disparo_erro
              ? <>O último pedido de busca ({desde(n.ultimo_disparo_em)}) falhou: {n.ultimo_disparo_erro}</>
              : <>Busca a cada {n.intervalo_min} min. Último pedido {desde(n.ultimo_disparo_em)}; última
                  avaliação nova entregue pelo NichoChat {desde(n.ultima_entrega_em)} (ele só entrega
                  quando há avaliação nova).</>}
        </Situacao>
        <LinhaIA ia={situacao.ia} />

        <details className="pt-1 text-sm">
          <summary className="cursor-pointer select-none font-semibold text-ink/70 transition hover:text-ink">
            O que o fluxo do NichoChat usa
          </summary>
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 text-xs sm:grid-cols-[auto_minmax(0,1fr)]">
            <dt className="text-muted">Subfluxo da busca</dt>
            <dd><code>{n.subfluxo_busca}</code></dd>
            <dt className="text-muted">Subfluxo da resposta</dt>
            <dd><code>{n.subfluxo_resposta}</code></dd>
            <dt className="text-muted">Entrega das avaliações</dt>
            <dd className="break-all"><code>POST {n.url_entrega}</code></dd>
            <dt className="text-muted">Confirmação da resposta</dt>
            <dd className="break-all"><code>POST {n.url_confirmacao}</code></dd>
            <dt className="text-muted">Cabeçalho</dt>
            <dd><code>X-API-Key</code> com a <code>WEBHOOK_GOOGLE_KEY</code> do servidor</dd>
          </dl>
        </details>
      </div>
    </Cartao>
  );
}

function ConexaoGoogle({ situacao, podeConfigurar, onMudou }: Props) {
  const s = situacao.google;
  const [ocupado, setOcupado] = useState<"" | "conectar" | "sincronizar" | "desconectar">("");
  const [recado, setRecado] = useState<Recado>(null);
  const [sinc, setSinc] = useState<SincronizacaoGoogle | null>(null);
  const [confirmar, setConfirmar] = useState(false);

  async function conectar() {
    setOcupado("conectar");
    setRecado(null);
    try {
      const { url } = await api.integracoes.google.urlConexao();
      // Sai do CRM para o consentimento do Google e volta pela rota de callback.
      window.location.href = url;
    } catch (e) {
      setRecado({ tipo: "erro", texto: mensagemDe(e, "Não foi possível iniciar a conexão.") });
      setOcupado("");
    }
  }

  async function sincronizar() {
    setOcupado("sincronizar");
    setRecado(null);
    try {
      const r = await api.integracoes.google.sincronizar();
      setSinc(r);
      setRecado({
        tipo: "ok",
        texto: `${r.achadas.length} ${r.achadas.length === 1 ? "unidade encontrada" : "unidades encontradas"} na conta, ${r.vinculadas} já cadastrada${r.vinculadas === 1 ? "" : "s"} aqui.`,
      });
      onMudou();
    } catch (e) {
      setRecado({ tipo: "erro", texto: mensagemDe(e, "Não foi possível ler as unidades.") });
    } finally {
      setOcupado("");
    }
  }

  async function desconectar() {
    setConfirmar(false);
    setOcupado("desconectar");
    setRecado(null);
    try {
      await api.integracoes.google.desconectar();
      setSinc(null);
      onMudou();
    } catch (e) {
      setRecado({ tipo: "erro", texto: mensagemDe(e, "Não foi possível desconectar.") });
    } finally {
      setOcupado("");
    }
  }

  const novas = sinc?.achadas.filter((a) => !a.cadastrada) ?? [];

  return (
    <Cartao
      titulo="Conexão direta com o Google (opcional)"
      descricao="As avaliações chegam e as respostas saem pelo NichoChat. Esta conexão só serve para conferir uma avaliação no Google na hora em que ela é aberta."
      acoes={podeConfigurar && s.configurado && (
        s.conectado ? (
          <>
            <button onClick={sincronizar} disabled={ocupado !== ""} className={clsx(BOTAO_SECUNDARIO, BOTAO_MENOR)}>
              {ocupado === "sincronizar" ? "Lendo…" : "Sincronizar unidades"}
            </button>
            <button onClick={() => setConfirmar(true)} disabled={ocupado !== ""}
                    className="rounded-xl px-3 py-1.5 text-xs font-bold text-red-600 transition hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400">
              Desconectar
            </button>
          </>
        ) : (
          <button onClick={conectar} disabled={ocupado !== ""} className={BOTAO_PRINCIPAL}>
            {ocupado === "conectar" ? "Abrindo o Google…" : "Conectar conta Google"}
          </button>
        )
      )}
    >
      <div className="space-y-2.5 px-5 py-4">
        {!s.configurado ? (
          <>
            <Situacao ok>
              Não configurada, e não é necessária: a fila e as respostas funcionam pelo
              NichoChat.
            </Situacao>
            <p className={AJUDA}>
              Para ligar mesmo assim: <code>GOOGLE_CLIENT_ID</code> e{" "}
              <code>GOOGLE_CLIENT_SECRET</code> no <code>.env</code> do servidor, de um
              cliente OAuth com acesso à Business Profile API e este endereço de retorno:
            </p>
            <p className="break-all rounded-xl bg-app px-3 py-2 text-xs text-ink"><code>{s.callback_url}</code></p>
          </>
        ) : s.conectado ? (
          <Situacao ok>
            Conectado como <strong>{s.conta_email ?? "conta Google"}</strong>
            {s.conectado_em && <> desde {dataHoraBR(s.conectado_em)}</>}.
          </Situacao>
        ) : (
          <>
            <Situacao ok={false}>Nenhuma conta Google conectada.</Situacao>
            <p className={AJUDA}>
              Entre com a conta que é <strong>proprietária ou administradora</strong> dos
              perfis no Google Meu Negócio. Endereço de retorno que precisa estar
              cadastrado no Google Cloud: <code className="break-all">{s.callback_url}</code>
            </p>
          </>
        )}

        {s.conectado && s.lojas_sem_conta > 0 && (
          <Situacao ok={false}>
            {s.lojas_sem_conta} {s.lojas_sem_conta === 1 ? "unidade ativa ainda não foi vinculada" : "unidades ativas ainda não foram vinculadas"} a
            esta conta. Use “Sincronizar unidades”; se continuar, a conta conectada não
            administra esses perfis.
          </Situacao>
        )}

        {recado && <Aviso tipo={recado.tipo}>{recado.texto}</Aviso>}

        {novas.length > 0 && (
          <div className="rounded-xl border border-line/12">
            <p className="border-b border-line/10 px-4 py-2.5 text-xs font-bold text-ink/70">
              Unidades da conta que ainda não estão cadastradas no servidor
            </p>
            <ul className="divide-y divide-line/[0.08]">
              {novas.map((u) => (
                <li key={u.loja_id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-ink">{u.nome || u.loja_id}</span>
                    <span className="block truncate text-xs text-muted">
                      {[u.cidade, u.conta_nome].filter(Boolean).join(", ") || u.loja_id}
                    </span>
                  </span>
                  <code className="shrink-0 text-[11px] text-muted">{u.loja_id}</code>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmar}
        variant="danger"
        title="Desconectar a conta Google?"
        description="A fila continua chegando pelo NichoChat. Só deixa de conferir a avaliação no Google na hora em que ela é aberta."
        confirmLabel="Desconectar"
        onConfirm={desconectar}
        onClose={() => setConfirmar(false)}
      />
    </Cartao>
  );
}

/* -------------------------------------------------------------------------- */
/* Como responder                                                             */
/* -------------------------------------------------------------------------- */

const NOTAS = [
  { value: "4", label: "Nota 4 e 5" },
  { value: "3", label: "Nota 3, 4 e 5" },
  { value: "2", label: "Nota 2 a 5" },
  { value: "1", label: "Todas as notas" },
];

function ComoResponder({ origem, podeConfigurar, onMudou }: Props) {
  const q = useApi(() => api.integracoes.config(origem), [origem]);
  const [f, setF] = useState<ConfigIntegracao | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [recado, setRecado] = useState<Recado>(null);
  const [ligarAutomatico, setLigarAutomatico] = useState(false);

  useEffect(() => { if (q.data) setF(q.data); }, [q.data]);

  if (q.loading && !f) return <Carregando />;
  if (q.error) return <Aviso tipo="erro">{q.error}</Aviso>;
  if (!f) return null;

  const mudar = (patch: Partial<ConfigIntegracao>) => setF({ ...f, ...patch });

  async function salvar(e?: React.FormEvent) {
    e?.preventDefault();
    if (!f) return;
    setSalvando(true);
    setRecado(null);
    const patch: ConfigIntegracaoPatch = {
      assinatura: f.assinatura ?? "",
      prompt: f.prompt ?? "",
      observacoes: f.observacoes ?? "",
      ...(origem === "ifood" ? {
        ativo: f.ativo, modo: f.modo, nota_minima: f.nota_minima,
        tom: f.tom ?? "", webhook_url: f.webhook_url ?? "",
      } : {}),
    };
    try {
      setF(await api.integracoes.salvarConfig(origem, patch));
      setRecado({ tipo: "ok", texto: "Configuração salva." });
      onMudou();
    } catch (err) {
      setRecado({ tipo: "erro", texto: mensagemDe(err, "Não foi possível salvar.") });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Cartao
      titulo="Como responder"
      descricao={origem === "ifood"
        ? "Vale para todas as lojas. Campo vazio usa o padrão do sistema."
        : "Vale para a sugestão da IA em todas as unidades. Campo vazio usa o padrão do sistema."}
    >
      <form onSubmit={salvar} className="space-y-5 px-5 py-5">
        <fieldset disabled={!podeConfigurar || salvando} className="space-y-5">
          {origem === "ifood" && (
            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <span className={ROTULO}>Quem publica</span>
                <div className="inline-flex rounded-xl border border-line/15 bg-app p-1" role="group">
                  {([["manual", "A equipe (manual)"], ["automatico", "O agente (automático)"]] as const).map(([valor, rotulo]) => (
                    <button
                      key={valor}
                      type="button"
                      aria-pressed={f.modo === valor}
                      onClick={() => {
                        if (valor === "automatico" && f.modo !== "automatico") setLigarAutomatico(true);
                        else mudar({ modo: valor });
                      }}
                      className={clsx(
                        "rounded-lg px-3.5 py-1.5 text-sm font-semibold transition",
                        f.modo === valor ? "bg-surface text-ink shadow-sm" : "text-ink/60 hover:text-ink",
                      )}
                    >
                      {rotulo}
                    </button>
                  ))}
                </div>
                <p className={AJUDA}>
                  {f.modo === "automatico"
                    ? "O agente escreve e publica sozinho a cada passada. No iFood não dá para editar nem apagar depois."
                    : "O agente só avisa que chegou avaliação. A equipe responde pela fila, com a sugestão da IA."}
                </p>
              </div>

              {f.modo === "automatico" && (
                <div>
                  <span className={ROTULO}>O agente responde sozinho</span>
                  <Select aria-label="Nota mínima" value={String(f.nota_minima)}
                          onChange={(v) => mudar({ nota_minima: Number(v) })}
                          options={NOTAS} triggerClassName={CAMPO} />
                  <p className={AJUDA}>
                    Comece em nota 4 e 5, onde a resposta é um agradecimento e o risco é
                    baixo. As notas abaixo disso ficam na fila para uma pessoa.
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="grid gap-5 sm:grid-cols-2">
            {origem === "ifood" && (
              <label>
                <span className={ROTULO}>Tom de voz</span>
                <input value={f.tom ?? ""} onChange={(e) => mudar({ tom: e.target.value })}
                       placeholder="cordial e profissional" maxLength={300} className={CAMPO} />
                <p className={AJUDA}>Entra no prompt padrão. É ignorado se houver prompt próprio abaixo.</p>
              </label>
            )}
            <label>
              <span className={ROTULO}>Assinatura</span>
              <input value={f.assinatura ?? ""} onChange={(e) => mudar({ assinatura: e.target.value })}
                     placeholder={`Equipe ${CLIENTE.nome}`} maxLength={120} className={CAMPO} />
              <p className={AJUDA}>
                Vai no fim da sugestão. A assinatura própria de cada {NOME_UNIDADE[origem].uma} é cadastrada no servidor.
              </p>
            </label>
          </div>

          <div>
            <div className="flex flex-wrap items-end justify-between gap-2">
              <label htmlFor="prompt-ia" className={clsx(ROTULO, "mb-0")}>Prompt da IA</label>
              {podeConfigurar && !(f.prompt ?? "").trim() && (
                <button type="button" onClick={() => mudar({ prompt: f.prompt_padrao })}
                        className="text-xs font-semibold text-ink/65 underline-offset-2 transition hover:text-ink hover:underline">
                  Começar pelo padrão
                </button>
              )}
            </div>
            <textarea id="prompt-ia" rows={(f.prompt ?? "").trim() ? 14 : 4} value={f.prompt ?? ""}
                      onChange={(e) => mudar({ prompt: e.target.value })}
                      placeholder="Vazio: usa o prompt padrão do sistema."
                      className={clsx(CAMPO, "mt-1.5 resize-y font-mono text-[13px] leading-relaxed")} />
            <p className={AJUDA}>
              Preencher substitui o padrão <strong>por inteiro</strong>, inclusive as
              proibições de prometer cupom ou reembolso
              {origem === "ifood" ? " e de pedir mudança de nota" : ""}. Se for escrever o
              seu, comece pelo padrão e ajuste.
            </p>
            {!(f.prompt ?? "").trim() && (
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer select-none font-semibold text-ink/65 transition hover:text-ink">
                  Ver o prompt padrão em uso
                </summary>
                <pre className="scroll-area mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-app p-3 font-mono text-[12px] leading-relaxed text-ink/80">{f.prompt_padrao}</pre>
              </details>
            )}
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            {origem === "ifood" && (
              <label>
                <span className={ROTULO}>Webhook do NichoChat</span>
                <input type="url" value={f.webhook_url ?? ""} onChange={(e) => mudar({ webhook_url: e.target.value })}
                       placeholder="https://…" maxLength={500} autoComplete="off" className={CAMPO} />
                <p className={AJUDA}>
                  Recebe um aviso a cada avaliação nova e a cada resposta publicada. O
                  que fazer com cada uma é decisão do fluxo no NichoChat.
                </p>
              </label>
            )}
          </div>

          <label className="block">
            <span className={ROTULO}>Anotações internas</span>
            <textarea rows={3} value={f.observacoes ?? ""} onChange={(e) => mudar({ observacoes: e.target.value })}
                      maxLength={4000} placeholder="Combinados, contatos, o que foi decidido sobre o tom."
                      className={clsx(CAMPO, "resize-y")} />
            <p className={AJUDA}>Só aparecem nesta tela. Não entram na resposta nem no prompt.</p>
          </label>

          {origem === "ifood" && (
            <label className="flex items-start gap-3">
              <input type="checkbox" checked={f.ativo} onChange={(e) => mudar({ ativo: e.target.checked })}
                     className="mt-0.5 h-4 w-4 shrink-0 accent-domani-orange" />
              <span className="text-sm text-ink">
                Agente ligado
                <span className="mt-0.5 block text-xs text-muted">
                  Desmarque para pausar tudo: o agente para de consultar, de avisar e de
                  responder. A fila manual continua funcionando.
                </span>
              </span>
            </label>
          )}
        </fieldset>

        {recado && <Aviso tipo={recado.tipo}>{recado.texto}</Aviso>}

        {podeConfigurar && (
          <button type="submit" disabled={salvando} className={BOTAO_PRINCIPAL}>
            {salvando ? "Salvando…" : "Salvar configuração"}
          </button>
        )}
      </form>

      <ConfirmDialog
        open={ligarAutomatico}
        title="Deixar o agente publicar sozinho?"
        description="As respostas do iFood são públicas e definitivas: não dá para editar nem apagar. O agente passa a publicar sem ninguém revisar, a partir da nota escolhida. Só vale depois de salvar."
        confirmLabel="Usar o automático"
        onConfirm={() => { mudar({ modo: "automatico" }); setLigarAutomatico(false); }}
        onClose={() => setLigarAutomatico(false)}
      />
    </Cartao>
  );
}

/* -------------------------------------------------------------------------- */
/* Lojas / unidades                                                           */
/* -------------------------------------------------------------------------- */

/**
 * Lojas (iFood) e unidades (Google): cadastradas no servidor, por SQL. A tela só
 * mostra — nada de cadastrar, editar ou excluir por aqui.
 */
function Lojas({ origem, lojas }: Props) {
  const u = NOME_UNIDADE[origem];
  return (
    <Cartao
      titulo={origem === "ifood" ? "Lojas" : "Unidades"}
      descricao={origem === "ifood"
        ? "Cada loja é uma unidade no iFood, identificada pelo merchant UUID. O cadastro é feito no servidor."
        : "Cada unidade é um perfil no Google Meu Negócio, lido pelo NichoChat. O cadastro é feito no servidor."}
    >
      {lojas.length === 0 ? (
        <p className="px-5 py-6 text-sm text-muted">
          Nenhuma {u.uma} cadastrada no servidor ainda.
        </p>
      ) : (
        <ul className="divide-y divide-line/[0.08]">
          {lojas.map((l) => (
            <li key={l.loja_id} className="px-5 py-3.5">
              <p className="flex flex-wrap items-center gap-2">
                <span className={clsx("font-semibold", l.ativo ? "text-ink" : "text-ink/45")}>{l.nome}</span>
                {!l.ativo && <span className="rounded-md bg-line/10 px-1.5 py-0.5 text-[11px] font-semibold text-muted">pausada</span>}
                {origem === "google" && l.ativo && (
                  // O vínculo de cada unidade é a leitura pelo NichoChat.
                  l.lida_em
                    ? <span className="rounded-md bg-emerald-500/10 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-400">lida {desde(l.lida_em)}</span>
                    : <span className="rounded-md bg-domani-orange/15 px-1.5 py-0.5 text-[11px] font-semibold text-ink">aguardando a primeira leitura</span>
                )}
              </p>
              <p className="mt-0.5 break-all text-xs text-muted">
                {[l.cidade, l.loja_id, l.assinatura ? `assina “${l.assinatura}”` : null].filter(Boolean).join(", ")}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Cartao>
  );
}
