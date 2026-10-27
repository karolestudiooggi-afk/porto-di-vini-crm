"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import clsx from "clsx";

import { PainelCota } from "@/components/campanhas/painel-cota";
import { Select } from "@/components/ui/select";
import { CLIENTE } from "@/config/cliente";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { ListaEmail, PreviaSegmento, SegmentoIn } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { lerSelecao, limparSelecao } from "@/lib/selecao";

const CAMPO =
  "w-full rounded-2xl border border-line/15 bg-app px-3 py-3 text-sm text-ink outline-none transition placeholder:text-muted focus:border-domani-orange focus:bg-surface";

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
  // Tags da base de parceiros: é por elas que se escolhe um grupo de parceiros.
  const tagsParceiros = useApi(
    () => (ehParceiro ? api.email.parceiros.tags() : Promise.resolve([] as string[])), [ehParceiro]);
  const [tagsEscolhidas, setTagsEscolhidas] = useState<string[]>([]);

  const [nome, setNome] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [assunto, setAssunto] = useState("");

  // Origem do público. "selecao" aparece quando o operador veio da tela de
  // Contatos com gente marcada — é o caminho de quem importou uma planilha.
  const [origemPublico, setOrigemPublico] = useState<"todos" | "selecao">("todos");
  const [selecao, setSelecao] = useState<{ ids: number[]; nomes: string[] } | null>(null);


  const [previa, setPrevia] = useState<PreviaSegmento | null>(null);
  const [carregandoPrevia, setCarregandoPrevia] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [quando, setQuando] = useState("");
  const [semEmailDias, setSemEmailDias] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  // Duas origens só: toda a base elegível, ou os contatos marcados na tela de
  // Contatos. Filtro por canal/status/idioma foi retirado de propósito — são
  // atributos da conversa, não critério de quem recebe e-mail: quem tem e-mail e
  // não recusou recebe, tenha chegado pelo Instagram ou pelo WhatsApp.
  const segmento: SegmentoIn = ehParceiro
    ? {
        ...(tagsEscolhidas.length ? { tags: tagsEscolhidas } : {}),
        ...(semEmailDias ? { sem_email_dias: Number(semEmailDias) } : {}),
      }
    : origemPublico === "selecao" && selecao
      ? { ids: selecao.ids }
      : semEmailDias
        ? { sem_email_dias: Number(semEmailDias) }
        : {};

  // Chegou da tela de Contatos com seleção? Entra já nesse modo. (Só na aba de
  // clientes: a seleção é de contatos, não de parceiros.)
  useEffect(() => {
    if (ehParceiro) return;
    const s = lerSelecao();
    if (s) { setSelecao(s); setOrigemPublico("selecao"); }
  }, [ehParceiro]);

  // Assunto do template entra como sugestão quando o campo ainda está vazio.
  useEffect(() => {
    const t = templates.data?.find((x) => x.id === templateId);
    if (t && !assunto) setAssunto(t.assunto);
  }, [templateId, templates.data]); // eslint-disable-line react-hooks/exhaustive-deps

  // Recalcula o público sempre que um filtro muda, com respiro para não bater na
  // API a cada tecla digitada no campo de tags.
  useEffect(() => {
    const chave = JSON.stringify(segmento);
    const t = setTimeout(async () => {
      setCarregandoPrevia(true);
      try {
        setPrevia(await api.email.previa(JSON.parse(chave), lista));
      } catch (e) {
        setErro(e instanceof Error ? e.message : "Falha ao calcular o público.");
      } finally {
        setCarregandoPrevia(false);
      }
    }, 400);
    return () => clearTimeout(t);
  }, [origemPublico, selecao, semEmailDias, tagsEscolhidas, lista]); // eslint-disable-line react-hooks/exhaustive-deps


  const barrados = previa
    ? previa.excluidos.sem_email + previa.excluidos.recusou +
      previa.excluidos.excluido + previa.excluidos.suprimido
    : 0;

  async function criar() {
    if (!nome.trim() || !templateId) {
      setErro("Dê um nome à campanha e escolha o template.");
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

  return (
    <div className="space-y-4">
      <header className="rounded-3xl border border-line/10 bg-surface px-5 py-5 shadow-domani-lift sm:px-6">
        <Link href={`/campanhas?aba=${lista}`} className="text-xs font-bold text-muted hover:text-domani-orange-600">
          ← E-mail · {ehParceiro ? "Parceiros" : "Clientes"}
        </Link>
        <h1 className="mt-2 font-display text-2xl font-extrabold tracking-tight">
          Nova campanha {ehParceiro ? "para parceiros" : "para clientes"}
        </h1>
        <p className="mt-1 text-sm text-muted">
          Nada é enviado ao criar. O disparo é um passo separado, na tela seguinte.
          {ehParceiro && " Sai pelo remetente de parcerias."}
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <section className="rounded-3xl border border-line/10 bg-surface p-5 shadow-domani-lift">
            <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
              Conteúdo
            </h2>
            <div className="mt-4 space-y-3">
              <label className="block">
                <span className="mb-1.5 block text-xs font-bold text-ink/70">Nome da campanha</span>
                <input value={nome} onChange={(e) => setNome(e.target.value)}
                       placeholder={ehParceiro ? "Proposta para hotéis" : "Novidades de agosto"} className={CAMPO} />
                <span className="mt-1 block text-[11px] text-muted">
                  Só para você identificar aqui — o cliente não vê.
                </span>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs font-bold text-ink/70">Template</span>
                <Select aria-label="Template" value={templateId} onChange={setTemplateId}
                        triggerClassName={CAMPO}
                        options={[
                          { value: "", label: "Escolha um template" },
                          ...(templates.data ?? []).map((t) => ({ value: t.id, label: t.nome })),
                        ]} />
                {!templates.data?.length && !templates.loading && (
                  <span className="mt-1 block text-[11px] text-amber-700">
                    Nenhum template {ehParceiro ? "de parceiros" : ""} ainda.{" "}
                    <Link href={ehParceiro ? "/campanhas/templates?lista=parceiros" : "/campanhas/templates"} className="underline">
                      Crie um primeiro.
                    </Link>
                  </span>
                )}
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs font-bold text-ink/70">
                  Agendar para (opcional)
                </span>
                <input type="datetime-local" value={quando}
                       onChange={(e) => setQuando(e.target.value)} className={CAMPO} />
                <span className="mt-1 block text-[11px] text-muted">
                  Deixe vazio para disparar manualmente. Com data marcada, a campanha
                  sai sozinha na hora — e continua sozinha se a cota do provedor não
                  cobrir tudo de uma vez.
                </span>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs font-bold text-ink/70">Assunto do e-mail</span>
                <input value={assunto} onChange={(e) => setAssunto(e.target.value)}
                       placeholder={ehParceiro ? "Uma proposta para a {{empresa}}" : "Oi {{primeiro_nome}}, temos novidade para você"}
                       className={CAMPO} />
                <span className="mt-1 block text-[11px] text-muted">
                  {ehParceiro
                    ? <>Variáveis: {"{{empresa}}"}, {"{{nome}}"}, {"{{primeiro_nome}}"}</>
                    : <>Variáveis: {"{{nome}}"}, {"{{primeiro_nome}}"}, {"{{canal}}"}, {"{{origem}}"}</>}
                </span>
              </label>
            </div>
          </section>

          <section className="rounded-3xl border border-line/10 bg-surface p-5 shadow-domani-lift">
            <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
              Quem recebe
            </h2>

            {ehParceiro ? (
              <PublicoParceiros
                tags={tagsParceiros.data ?? []}
                escolhidas={tagsEscolhidas}
                onTags={setTagsEscolhidas}
                semEmailDias={semEmailDias}
                onSemEmailDias={setSemEmailDias}
              />
            ) : (<>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={() => setOrigemPublico("todos")}
                      className={`rounded-xl px-4 py-2 text-sm font-bold transition ${
                        origemPublico === "todos"
                          ? "bg-domani-orange text-white"
                          : "border border-line/20 text-ink hover:bg-app"}`}>
                Toda a base
              </button>
              <button type="button" onClick={() => setOrigemPublico("selecao")}
                      disabled={!selecao}
                      className={`rounded-xl px-4 py-2 text-sm font-bold transition disabled:opacity-40 ${
                        origemPublico === "selecao"
                          ? "bg-domani-orange text-white"
                          : "border border-line/20 text-ink hover:bg-app"}`}>
                Seleção manual{selecao ? ` (${selecao.ids.length})` : ""}
              </button>
              {!selecao && (
                <span className="self-center text-xs text-muted">
                  Para escolher pessoa por pessoa, marque os contatos na tela de{" "}
                  <Link href="/clientes" className="font-bold text-domani-orange-600 hover:underline">
                    Contatos
                  </Link>{" "}
                  e use “Enviar campanha para estes”.
                </span>
              )}
            </div>

            {origemPublico === "selecao" && selecao ? (
              <div className="mt-4 rounded-2xl bg-app p-4">
                <p className="text-sm font-semibold text-ink">
                  {selecao.ids.length} contato(s) escolhidos na tela de Contatos
                </p>
                <p className="mt-1 text-xs text-muted">
                  {selecao.nomes.slice(0, 5).join(", ")}
                  {selecao.nomes.length > 5 && ` e mais ${selecao.nomes.length - 5}`}
                </p>
                <button type="button"
                        onClick={() => { limparSelecao(); setSelecao(null); setOrigemPublico("todos"); }}
                        className="mt-3 text-xs font-bold text-domani-orange-600 hover:underline">
                  Descartar seleção
                </button>
              </div>
            ) : (
              <>
                <div className="mt-4 rounded-2xl bg-app p-4">
                  <p className="text-sm font-semibold text-ink">Toda a base elegível</p>
                  <p className="mt-1 text-xs text-muted">
                    Quem tem e-mail cadastrado, não recusou receber e não está na lista
                    de descadastro. Para escolher um grupo específico, marque os contatos
                    na tela de Contatos e volte por “Enviar campanha para estes”.
                  </p>
                </div>

                {/* Exclusão por período: evita mandar duas campanhas seguidas
                    para a mesma pessoa, que é como uma base se cansa e começa a
                    marcar como spam. */}
                <label className="mt-3 block">
                  <span className="mb-1.5 block text-xs font-bold text-ink/70">
                    Excluir quem já recebeu nos últimos… (opcional)
                  </span>
                  <Select
                    aria-label="Excluir quem recebeu recentemente"
                    value={semEmailDias}
                    onChange={setSemEmailDias}
                    options={[
                      { value: "", label: "Não excluir ninguém" },
                      { value: "7", label: "7 dias" },
                      { value: "15", label: "15 dias" },
                      { value: "30", label: "30 dias" },
                      { value: "60", label: "60 dias" },
                      { value: "90", label: "90 dias" },
                    ]}
                    triggerClassName={CAMPO}
                  />
                  <span className="mt-1 block text-[11px] text-muted">
                    Quem nunca recebeu campanha entra sempre.
                  </span>
                </label>
              </>
            )}
            </>)}
          </section>
        </div>

        <div className="space-y-4">
          <section className="rounded-3xl border border-line/10 bg-surface p-5 shadow-domani-lift">
            <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
              Público
            </h2>

            {carregandoPrevia ? (
              <div className="skeleton mt-4 h-16 rounded-2xl" />
            ) : previa ? (
              <>
                <p className="mt-3 font-display text-4xl font-extrabold tracking-tight text-domani-orange [font-variant-numeric:tabular-nums]">
                  {num(previa.com_email)}
                </p>
                <p className="text-xs text-muted">destinatários · {previa.label}</p>

                {barrados > 0 && (
                  <div className="mt-4 rounded-2xl bg-app p-3">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-muted">
                      Não recebem ({num(barrados)})
                    </p>
                    <ul className="mt-1.5 space-y-0.5 text-xs text-ink/70">
                      {previa.excluidos.sem_email > 0 && (
                        <li>{num(previa.excluidos.sem_email)} sem e-mail cadastrado</li>
                      )}
                      {previa.excluidos.recusou > 0 && (
                        <li>
                          {num(previa.excluidos.recusou)}{" "}
                          {ehParceiro ? "saíram da lista de parceiros" : "recusaram receber"}
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

                {previa.amostra.length > 0 && (
                  <div className="mt-3">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-muted">Amostra</p>
                    <ul className="mt-1 space-y-0.5 text-xs text-ink/70">
                      {previa.amostra.map((a) => (
                        <li key={a.id} className="truncate">{a.nome ?? "—"} · {a.email}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <p className="mt-3 text-sm text-muted">Calculando…</p>
            )}
          </section>

          <PainelCota />

          {erro && (
            <p className="rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-500">
              {erro}
            </p>
          )}

          <button onClick={criar} disabled={salvando}
                  className="w-full rounded-xl bg-domani-orange px-4 py-3 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:opacity-50">
            {salvando ? "Criando…" : quando ? "Agendar campanha" : "Criar campanha"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-bold text-ink/70">{label}</span>
      {children}
    </label>
  );
}

const OPCOES_PERIODO = [
  { value: "", label: "Não excluir ninguém" },
  { value: "7", label: "7 dias" },
  { value: "15", label: "15 dias" },
  { value: "30", label: "30 dias" },
  { value: "60", label: "60 dias" },
  { value: "90", label: "90 dias" },
];

/** Público da aba Parceiros: a base inteira ou só algumas tags. */
function PublicoParceiros({ tags, escolhidas, onTags, semEmailDias, onSemEmailDias }: {
  tags: string[];
  escolhidas: string[];
  onTags: (t: string[]) => void;
  semEmailDias: string;
  onSemEmailDias: (v: string) => void;
}) {
  const alternar = (t: string) =>
    onTags(escolhidas.includes(t) ? escolhidas.filter((x) => x !== t) : [...escolhidas, t]);

  return (
    <>
      <div className="mt-4 rounded-2xl bg-app p-4">
        <p className="text-sm font-semibold text-ink">
          {escolhidas.length ? "Parceiros com as tags escolhidas" : "Toda a base de parceiros"}
        </p>
        <p className="mt-1 text-xs text-muted">
          Quem está na <Link href="/campanhas/parceiros" className="font-bold text-domani-orange-600 hover:underline">base de parceiros</Link>,
          não saiu da lista e não tem o e-mail bloqueado. Clientes não entram aqui.
        </p>
      </div>

      <div className="mt-3">
        <span className="mb-1.5 block text-xs font-bold text-ink/70">Só estas tags (opcional)</span>
        {tags.length ? (
          <div className="flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <button key={t} type="button" onClick={() => alternar(t)}
                      aria-pressed={escolhidas.includes(t)}
                      className={clsx(
                        "rounded-full px-3 py-1 text-xs font-bold transition",
                        escolhidas.includes(t)
                          ? "bg-domani-orange text-white"
                          : "border border-line/20 text-ink/75 hover:bg-app",
                      )}>
                {t}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted">
            Nenhuma tag na base ainda. Elas vêm da coluna “tags” da planilha.
          </p>
        )}
      </div>

      <label className="mt-3 block">
        <span className="mb-1.5 block text-xs font-bold text-ink/70">
          Excluir quem já recebeu nos últimos… (opcional)
        </span>
        <Select aria-label="Excluir quem recebeu recentemente" value={semEmailDias}
                onChange={onSemEmailDias} options={OPCOES_PERIODO} triggerClassName={CAMPO} />
        <span className="mt-1 block text-[11px] text-muted">
          Conta só as campanhas de parceiros. Quem nunca recebeu entra sempre.
        </span>
      </label>
    </>
  );
}
