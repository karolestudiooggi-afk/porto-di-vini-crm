"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import clsx from "clsx";

import { enderecoDe } from "@/components/campanhas/lista-campanhas";
import { PainelCota } from "@/components/campanhas/painel-cota";
import { JanelaPreviaEmail, chamarDe, escolherPessoa } from "@/components/campanhas/previa-email";
import { Icon } from "@/components/ui/icon";
import { Select } from "@/components/ui/select";
import { CLIENTE } from "@/config/cliente";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { ListaEmail, PreviaSegmento, SegmentoIn } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { lerSelecao, limparSelecao } from "@/lib/selecao";

const CAMPO =
  "w-full rounded-2xl border border-line/15 bg-app px-4 py-3 text-sm text-ink outline-none transition placeholder:text-muted focus:border-domani-orange focus:bg-surface";
const ROTULO = "mb-1.5 block text-xs font-bold text-ink/70";
const AJUDA = "mt-1.5 block text-[11px] leading-relaxed text-muted";
const CARTAO = "rounded-3xl border border-line/10 bg-surface p-5 shadow-domani-lift sm:p-6";
const TITULO = "text-[11px] font-bold uppercase tracking-[0.16em] text-muted";

const OPCOES_PERIODO = [
  { value: "", label: "Não excluir ninguém" },
  { value: "7", label: "7 dias" },
  { value: "15", label: "15 dias" },
  { value: "30", label: "30 dias" },
  { value: "60", label: "60 dias" },
  { value: "90", label: "90 dias" },
];

/** Com mais tags que isto, aparece a busca acima delas. */
const TAGS_SEM_BUSCA = 14;

type Origem = "todos" | "segmento" | "selecao";

export default function NovaCampanhaPage() {
  // useSearchParams exige um limite de Suspense no build do Next.
  return (
    <Suspense fallback={<div className="skeleton h-40 rounded-3xl" />}>
      <NovaCampanha />
    </Suspense>
  );
}

/**
 * Nova campanha de UMA aba (?lista=parceiros). A aba decide a base do público,
 * os templates oferecidos e o remetente — que o servidor grava sozinho. Sem o
 * módulo de parceiros, é sempre a lista de clientes.
 */
function NovaCampanha() {
  const router = useRouter();
  const params = useSearchParams();
  const lista: ListaEmail =
    CLIENTE.modulos.parceiros && params.get("lista") === "parceiros" ? "parceiros" : "clientes";
  const ehParceiro = lista === "parceiros";
  const templates = useApi(() => api.email.templates.list(lista), [lista]);
  // Tags: as da base de parceiros, ou as dos contatos (Domani + manuais + RD).
  const tagsDisponiveis = useApi(
    () => (ehParceiro ? api.email.parceiros.tags() : api.contatos.filtros().then((f) => f.tags)),
    [ehParceiro]);
  const resumo = useApi(
    () => (ehParceiro ? Promise.resolve(null) : api.email.resumo()), [ehParceiro]);
  const remetente = enderecoDe(resumo.data?.remetente);

  const [nome, setNome] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [assunto, setAssunto] = useState("");
  const [quando, setQuando] = useState("");

  // Origem do público. "selecao" aparece quando o operador veio da tela de
  // Contatos com gente marcada — é o caminho de quem importou uma planilha.
  const [origem, setOrigem] = useState<Origem>("todos");
  const [selecao, setSelecao] = useState<{ ids: number[]; nomes: string[] } | null>(null);
  const [tagsEscolhidas, setTagsEscolhidas] = useState<string[]>([]);
  const [semEmailDias, setSemEmailDias] = useState("");

  const [previa, setPrevia] = useState<PreviaSegmento | null>(null);
  const [carregandoPrevia, setCarregandoPrevia] = useState(false);
  const [verEmail, setVerEmail] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Três origens: toda a base elegível, um segmento por tag, ou os contatos
  // marcados na tela de Contatos. Filtro por canal/status/idioma ficou de fora
  // de propósito — são atributos da conversa, não critério de quem recebe
  // e-mail. As regras de consentimento e descadastro valem nas três.
  const segmento: SegmentoIn = useMemo(() => {
    if (!ehParceiro && origem === "selecao" && selecao) return { ids: selecao.ids };
    const porTag = ehParceiro || origem === "segmento";
    return {
      ...(porTag && tagsEscolhidas.length ? { tags: tagsEscolhidas } : {}),
      ...(semEmailDias ? { sem_email_dias: Number(semEmailDias) } : {}),
    };
  }, [ehParceiro, origem, selecao, tagsEscolhidas, semEmailDias]);

  // Chegou da tela de Contatos com seleção? Entra já nesse modo. (Só na aba de
  // clientes: a seleção é de contatos, não de parceiros.)
  useEffect(() => {
    if (ehParceiro) return;
    const s = lerSelecao();
    if (s) { setSelecao(s); setOrigem("selecao"); }
  }, [ehParceiro]);

  // Assunto do template entra como sugestão quando o campo ainda está vazio.
  const template = templates.data?.find((x) => x.id === templateId);
  useEffect(() => {
    if (template && !assunto) setAssunto(template.assunto);
  }, [template]); // eslint-disable-line react-hooks/exhaustive-deps

  // Recalcula o público sempre que um filtro muda, com respiro para não bater
  // na API a cada clique numa tag.
  const chave = JSON.stringify(segmento);
  useEffect(() => {
    const t = setTimeout(async () => {
      setCarregandoPrevia(true);
      try {
        setPrevia(await api.email.previa(JSON.parse(chave), lista));
      } catch (e) {
        setErro(e instanceof Error ? e.message : "Falha ao calcular o público.");
      } finally {
        setCarregandoPrevia(false);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [chave, lista]);

  const barrados = previa
    ? previa.excluidos.sem_email + previa.excluidos.recusou +
      previa.excluidos.excluido + previa.excluidos.suprimido
    : 0;
  const primeiro = escolherPessoa(previa?.amostra);
  const segmentoVazio = !ehParceiro && origem === "segmento" && !tagsEscolhidas.length;

  async function criar() {
    if (!nome.trim() || !templateId) {
      setErro("Dê um nome à campanha e escolha o template.");
      return;
    }
    if (segmentoVazio) {
      setErro("Escolha pelo menos uma tag, ou volte para Toda a base.");
      return;
    }
    if (previa && previa.com_email === 0) {
      setErro("Ninguém deste público pode receber e-mail. Ajuste quem recebe.");
      return;
    }
    setSalvando(true);
    setErro(null);
    try {
      const c = await api.email.campanhas.criar({
        nome: nome.trim(), template_id: templateId, assunto, segmento, lista,
        // datetime-local vem no fuso do navegador; toISOString normaliza para UTC,
        // que é como o banco guarda.
        agendada_para: quando ? new Date(quando).toISOString() : null,
      });
      router.push(`/campanhas/${c.id}`);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não deu para criar a campanha.");
      setSalvando(false);
    }
  }

  const linkTemplates = ehParceiro ? "/campanhas/templates?lista=parceiros" : "/campanhas/templates";

  return (
    <div className="space-y-4">
      <header className="rounded-3xl border border-line/10 bg-surface px-5 py-6 shadow-domani-lift sm:px-6">
        <Link href={`/campanhas?aba=${lista}`}
              className="inline-flex items-center gap-1 text-xs font-bold text-ink/70 hover:text-domani-orange-600">
          <Icon name="chevronLeft" className="h-3.5 w-3.5" strokeWidth={2.2} />
          E-mail · {ehParceiro ? "Parceiros" : "Clientes"}
        </Link>
        <h1 className="mt-2 font-display text-[1.7rem] font-extrabold tracking-tight">
          Nova campanha {ehParceiro ? "para parceiros" : "para clientes"}
        </h1>
        <p className="mt-1 text-sm text-muted">
          Nada é enviado ao criar. O disparo é um passo separado, na tela seguinte.
          {ehParceiro
            ? " Sai pelo remetente de parcerias."
            : remetente && <> Sai por <strong className="font-semibold text-ink/80">{remetente}</strong>.</>}
        </p>
      </header>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <section className={CARTAO}>
            <h2 className={TITULO}>Conteúdo</h2>
            <div className="mt-4 grid gap-x-4 gap-y-4 sm:grid-cols-2">
              <label className="block">
                <span className={ROTULO}>Nome da campanha</span>
                <input value={nome} onChange={(e) => setNome(e.target.value)}
                       placeholder={ehParceiro ? "Proposta para hotéis" : "Clube · novidades de novembro"}
                       className={CAMPO} />
                <span className={AJUDA}>Só para identificar aqui. O cliente não vê.</span>
              </label>

              <label className="block">
                <span className={ROTULO}>Template</span>
                <Select aria-label="Template" value={templateId} onChange={setTemplateId}
                        triggerClassName={CAMPO}
                        options={[
                          { value: "", label: "Escolha um template" },
                          ...(templates.data ?? []).map((t) => ({ value: t.id, label: t.nome })),
                        ]} />
                {!templates.data?.length && !templates.loading ? (
                  <span className={clsx(AJUDA, "text-amber-700")}>
                    Nenhum template {ehParceiro ? "de parceiros " : ""}ainda.{" "}
                    <Link href={linkTemplates} className="font-bold underline">Crie o primeiro.</Link>
                  </span>
                ) : (
                  <span className={AJUDA}>
                    Templates de {ehParceiro ? "parceiros" : "clientes"}.{" "}
                    <Link href={linkTemplates} className="font-bold text-domani-orange-600 hover:underline">
                      Criar ou editar
                    </Link>
                  </span>
                )}
              </label>

              <label className="block sm:col-span-2">
                <span className={ROTULO}>Assunto do e-mail</span>
                <input value={assunto} onChange={(e) => setAssunto(e.target.value)}
                       placeholder={ehParceiro ? "Uma proposta para a {{empresa}}" : "{{primeiro_nome}}, chegou vinho novo na Porto"}
                       className={CAMPO} />
                <span className={AJUDA}>
                  {ehParceiro
                    ? <>Variáveis: {"{{empresa}}"}, {"{{nome}}"}, {"{{primeiro_nome}}"}</>
                    : <>Variáveis: {"{{nome}}"}, {"{{primeiro_nome}}"}, {"{{email}}"}. Quem não tem nome cadastrado recebe o trecho em branco.</>}
                </span>
              </label>

              <label className="block">
                <span className={ROTULO}>Agendar para (opcional)</span>
                <input type="datetime-local" value={quando}
                       onChange={(e) => setQuando(e.target.value)} className={CAMPO} />
                <span className={AJUDA}>
                  Vazio: você dispara na próxima tela. Com data, sai sozinha e
                  continua se a cota não cobrir tudo de uma vez.
                </span>
              </label>

              <div className="flex items-end pb-6">
                <button type="button" onClick={() => setVerEmail(true)} disabled={!template}
                        className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-line/15 px-4 py-3 text-sm font-bold text-ink transition hover:bg-app disabled:cursor-not-allowed disabled:text-ink/35 disabled:hover:bg-transparent">
                  <Icon name="search" className="h-4 w-4" />
                  {template ? `Ver prévia com dados de ${chamarDe(primeiro)}` : "Escolha o template para ver a prévia"}
                </button>
              </div>
            </div>
          </section>

          <section className={CARTAO}>
            <h2 className={TITULO}>Quem recebe</h2>

            {ehParceiro ? (
              <PublicoPorTag
                tags={tagsDisponiveis.data ?? []} carregando={tagsDisponiveis.loading}
                escolhidas={tagsEscolhidas} onTags={setTagsEscolhidas}
                titulo={tagsEscolhidas.length ? "Parceiros com as tags escolhidas" : "Toda a base de parceiros"}
                texto={<>Quem está na <Link href="/campanhas/parceiros" className="font-bold text-domani-orange-600 hover:underline">base de parceiros</Link>, não saiu da lista e não tem o e-mail bloqueado. Clientes não entram aqui.</>}
                vazio="Nenhuma tag na base ainda. Elas vêm da coluna “tags” da planilha."
                rotulo="Só estas tags (opcional)"
              />
            ) : (
              <>
                <div className="mt-4 flex flex-wrap gap-2">
                  <BotaoOrigem ativo={origem === "todos"} onClick={() => setOrigem("todos")}>
                    Toda a base
                  </BotaoOrigem>
                  <BotaoOrigem ativo={origem === "segmento"} onClick={() => setOrigem("segmento")}>
                    Segmento
                  </BotaoOrigem>
                  <BotaoOrigem ativo={origem === "selecao"} onClick={() => setOrigem("selecao")}
                               disabled={!selecao}
                               title={selecao ? undefined : "Marque os contatos na tela de Contatos e use “Enviar campanha para estes”"}>
                    Seleção manual{selecao ? ` (${num(selecao.ids.length)})` : ""}
                  </BotaoOrigem>
                </div>

                {origem === "selecao" && selecao ? (
                  <div className="mt-4 rounded-2xl bg-app p-4">
                    <p className="text-sm font-semibold text-ink">
                      {num(selecao.ids.length)} contato(s) escolhidos na tela de Contatos
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      {selecao.nomes.slice(0, 5).join(", ")}
                      {selecao.nomes.length > 5 && ` e mais ${num(selecao.nomes.length - 5)}`}
                    </p>
                    <button type="button"
                            onClick={() => { limparSelecao(); setSelecao(null); setOrigem("todos"); }}
                            className="mt-3 text-xs font-bold text-domani-orange-600 hover:underline">
                      Descartar seleção
                    </button>
                  </div>
                ) : origem === "segmento" ? (
                  <PublicoPorTag
                    tags={tagsDisponiveis.data ?? []} carregando={tagsDisponiveis.loading}
                    erro={tagsDisponiveis.error}
                    escolhidas={tagsEscolhidas} onTags={setTagsEscolhidas}
                    titulo={tagsEscolhidas.length
                      ? `Quem tem ${tagsEscolhidas.length === 1 ? "a tag" : "qualquer uma das tags"} ${tagsEscolhidas.map((t) => `“${t}”`).join(", ")}`
                      : "Escolha uma ou mais tags"}
                    texto="Tags do WhatsApp (Domani), as colocadas à mão e as que vieram do RD. As regras de sempre continuam: precisa ter e-mail, não ter recusado e não ter saído da lista."
                    vazio="Nenhuma tag na base ainda."
                    rotulo="Tags"
                  />
                ) : (
                  <div className="mt-4 rounded-2xl bg-app p-4">
                    <p className="text-sm font-semibold text-ink">Toda a base elegível</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted">
                      Quem tem e-mail, não recusou receber e não está na lista de
                      descadastro. Para um grupo específico, use Segmento; para
                      escolher pessoa por pessoa, marque na tela de{" "}
                      <Link href="/clientes" className="font-bold text-domani-orange-600 hover:underline">Contatos</Link>.
                    </p>
                  </div>
                )}
              </>
            )}

            {/* Exclusão por período: evita mandar duas campanhas seguidas para a
                mesma pessoa, que é como uma base se cansa e começa a marcar spam. */}
            {!(origem === "selecao" && selecao && !ehParceiro) && (
              <label className="mt-5 block sm:max-w-md">
                <span className={ROTULO}>Excluir quem já recebeu nos últimos…</span>
                <Select aria-label="Excluir quem recebeu recentemente" value={semEmailDias}
                        onChange={setSemEmailDias} options={OPCOES_PERIODO} triggerClassName={CAMPO} />
                <span className={AJUDA}>
                  {ehParceiro
                    ? "Conta só as campanhas de parceiros. Quem nunca recebeu entra sempre."
                    : "Evita duas campanhas seguidas para a mesma pessoa, que é como uma base começa a marcar spam. Quem nunca recebeu entra sempre."}
                </span>
              </label>
            )}
          </section>
        </div>

        <aside className="lg:sticky lg:top-4">
          <section className={CARTAO}>
            <h2 className={TITULO}>Público</h2>

            {carregandoPrevia && !previa ? (
              <div className="skeleton mt-4 h-16 rounded-2xl" />
            ) : previa ? (
              <div className={clsx("transition-opacity", carregandoPrevia && "opacity-50")}>
                <p className="mt-3 font-display text-5xl font-extrabold tracking-tight text-domani-orange [font-variant-numeric:tabular-nums]">
                  {segmentoVazio ? "—" : num(previa.com_email)}
                </p>
                <p className="mt-1 text-xs text-muted">
                  destinatários · {segmentoVazio ? "escolha as tags" : previa.label}
                </p>

                {barrados > 0 && !segmentoVazio && (
                  <div className="mt-4 rounded-2xl bg-app p-3.5">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-ink/70">
                      Não recebem ({num(barrados)})
                    </p>
                    <ul className="mt-1.5 space-y-0.5 text-xs text-ink/70">
                      {previa.excluidos.sem_email > 0 && (
                        <li>{num(previa.excluidos.sem_email)} sem e-mail cadastrado</li>
                      )}
                      {previa.excluidos.recusou > 0 && (
                        <li>
                          {num(previa.excluidos.recusou)}{" "}
                          {ehParceiro ? "saíram da lista de parceiros" : "não autorizaram"}
                        </li>
                      )}
                      {previa.excluidos.suprimido > 0 && (
                        <li>
                          {num(previa.excluidos.suprimido)}{" "}
                          {ehParceiro ? "bloqueados (erro, spam ou descadastro como cliente)" : "descadastraram ou deram erro"}
                        </li>
                      )}
                      {previa.excluidos.excluido > 0 && (
                        <li>{num(previa.excluidos.excluido)} com ficha excluída</li>
                      )}
                    </ul>
                  </div>
                )}

                {previa.amostra.length > 0 && !segmentoVazio && (
                  <div className="mt-4">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-ink/70">Amostra</p>
                    <ul className="mt-1.5 space-y-0.5 text-xs text-ink/70">
                      {previa.amostra.map((a) => (
                        <li key={a.id} className="truncate">
                          {a.nome ? <>{a.nome} · {a.email}</> : a.email}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-muted">Calculando…</p>
            )}

            {erro && (
              <p className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/5 px-3.5 py-2.5 text-xs text-red-600">
                {erro}
              </p>
            )}

            <button onClick={criar} disabled={salvando}
                    className="mt-5 w-full rounded-2xl bg-domani-orange px-4 py-3.5 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:opacity-50">
              {salvando ? "Criando…" : quando ? "Agendar campanha" : "Criar campanha"}
            </button>
            <div className="mt-3 text-center">
              <PainelCota compacto />
            </div>
          </section>
        </aside>
      </div>

      {template && (
        <JanelaPreviaEmail aberto={verEmail} onFechar={() => setVerEmail(false)}
                           html={template.html} assunto={assunto || template.assunto}
                           pessoa={primeiro} />
      )}
    </div>
  );
}

function BotaoOrigem({ ativo, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { ativo: boolean }) {
  return (
    <button type="button" {...props}
            className={clsx(
              "rounded-xl px-4 py-2.5 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-40",
              ativo ? "bg-domani-orange text-white" : "border border-line/20 text-ink hover:bg-app",
            )}>
      {children}
    </button>
  );
}

/** Escolha por tags: segmento de clientes ou recorte da base de parceiros. */
function PublicoPorTag({ tags, carregando, erro, escolhidas, onTags, titulo, texto, vazio, rotulo }: {
  tags: string[];
  carregando: boolean;
  erro?: string | null;
  escolhidas: string[];
  onTags: (t: string[]) => void;
  titulo: string;
  texto: React.ReactNode;
  vazio: string;
  rotulo: string;
}) {
  const [busca, setBusca] = useState("");
  const alternar = (t: string) =>
    onTags(escolhidas.includes(t) ? escolhidas.filter((x) => x !== t) : [...escolhidas, t]);
  const termo = busca.trim().toLowerCase();
  const visiveis = termo ? tags.filter((t) => t.toLowerCase().includes(termo) || escolhidas.includes(t)) : tags;

  return (
    <>
      <div className="mt-4 rounded-2xl bg-app p-4">
        <p className="text-sm font-semibold text-ink">{titulo}</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">{texto}</p>
      </div>

      <div className="mt-4">
        <span className={ROTULO}>{rotulo}</span>
        {tags.length > TAGS_SEM_BUSCA && (
          <input value={busca} onChange={(e) => setBusca(e.target.value)}
                 placeholder="Buscar tag" className={clsx(CAMPO, "mb-2.5 py-2.5")} />
        )}
        {carregando ? (
          <div className="flex gap-1.5">
            {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-7 w-20 rounded-full" />)}
          </div>
        ) : erro ? (
          <p className="text-xs text-red-600">Não deu para ler as tags: {erro}</p>
        ) : tags.length ? (
          <div className="flex max-h-56 flex-wrap gap-1.5 overflow-y-auto">
            {visiveis.map((t) => (
              <button key={t} type="button" onClick={() => alternar(t)}
                      aria-pressed={escolhidas.includes(t)}
                      className={clsx(
                        "rounded-full px-3 py-1.5 text-xs font-bold transition",
                        escolhidas.includes(t)
                          ? "bg-domani-orange text-white"
                          : "border border-line/20 text-ink/75 hover:bg-app",
                      )}>
                {t}
              </button>
            ))}
            {!visiveis.length && <p className="text-xs text-muted">Nenhuma tag com “{busca}”.</p>}
          </div>
        ) : (
          <p className="text-xs text-muted">{vazio}</p>
        )}
      </div>
    </>
  );
}
