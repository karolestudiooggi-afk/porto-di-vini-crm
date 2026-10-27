"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import type { ContatoDetail } from "@/lib/api-types";
import { api } from "@/lib/api";
import { CLIENTE, cap } from "@/config/cliente";
import { useApi } from "@/lib/use-api";
import { dataBR, dataHoraBR } from "@/lib/format";
import { Icon } from "@/components/ui/icon";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EditForm } from "./edit-form";

// Ficha do cliente — MODAL CENTRAL (card flutuante), ver + editar sem sair do contexto.
export function DetailDrawer({
  id,
  canWrite,
  canDelete,
  onClose,
  onChanged,
}: {
  id: number;
  canWrite: boolean;
  canDelete: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { data: c, loading, error, reload } = useApi(() => api.contatos.detalhe(id), [id]);
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Fecha no ESC.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const inicial = (c?.nome ?? "?").trim().charAt(0).toUpperCase() || "?";

  // Este CRM não tem segmentação derivada (VIP, recorrente, inativo): ela dependia
  // de compra e frequência, que o Domani não fornece. Os selos aqui refletem o que
  // a base realmente sabe — canal, status e consentimento.
  const segList = c
    ? ([
        c.canal,
        c.status,
        c.opted_in_email ? "Opt-in e-mail" : null,
        c.tags_manuais.length ? `${c.tags_manuais.length} tag manual` : null,
      ].filter(Boolean) as string[])
    : [];

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4 sm:p-6">
      {/* Fundo desfocado */}
      <div className="absolute inset-0 animate-overlay-fade bg-domani-ink/55 backdrop-blur-md" onClick={onClose} />

      {/* Card central */}
      <div className="relative flex max-h-[92vh] w-full max-w-5xl animate-modal-panel flex-col overflow-hidden rounded-3xl border border-line/15 bg-surface shadow-2xl">
        {mode === "edit" && c ? (
          <EditForm
            contato={c}
            onCancel={() => setMode("view")}
            onSaved={() => { setMode("view"); reload(); onChanged(); }}
          />
        ) : (
          <>
            {/* Cabeçalho grafite com avatar + badges */}
            <div className="relative shrink-0 bg-domani-graphite px-6 py-5 text-white">
              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-domani-orange text-xl font-extrabold text-white shadow-domani-lift">
                  {inicial}
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate font-display text-xl font-extrabold tracking-tight">{c?.nome ?? (loading ? "Carregando…" : "Ficha")}</h2>
                  <p className="mt-0.5 truncate text-sm text-white/55">
                    {c?.telefone ?? "—"}
                    {c?.origem ? <> · origem <span className="font-semibold text-white/80">{c.origem}</span></> : null}
                  </p>
                  {segList.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {segList.map((s) => (
                        <span key={s} className="rounded-full bg-domani-orange/20 px-2.5 py-0.5 text-[11px] font-bold text-domani-orange-300">{s}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {canWrite && c && (
                    <button onClick={() => setMode("edit")} title="Editar" className="rounded-xl p-2 text-white/70 transition hover:bg-white/10 hover:text-white">
                      <Icon name="edit" className="h-4 w-4" />
                    </button>
                  )}
                  {canDelete && c && (
                    <button onClick={() => setConfirmDel(true)} title="Apagar" className="rounded-xl p-2 text-white/70 transition hover:bg-red-500/20 hover:text-red-300">
                      <Icon name="trash" className="h-4 w-4" />
                    </button>
                  )}
                  <button onClick={onClose} title="Fechar" className="rounded-xl p-2 text-white/70 transition hover:bg-white/10 hover:text-white">
                    <Icon name="close" className="h-4 w-4" strokeWidth={2} />
                  </button>
                </div>
              </div>
            </div>

            {/* Corpo */}
            <div className="scroll-area flex-1 overflow-y-auto bg-app/40 px-7 py-7">
              {loading ? (
                <div className="grid gap-5 sm:grid-cols-2">
                  {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-28 rounded-2xl" />)}
                </div>
              ) : error ? (
                <p className="rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-500">{error}</p>
              ) : c ? (
                <div className="grid gap-5 sm:grid-cols-2">
                  {/* Identificação */}
                  <Card title="Identificação">
                    <Grid>
                      <Field label="Nome" value={[c.primeiro_nome, c.sobrenome].filter(Boolean).join(" ") || c.nome} />
                      <Field label="Telefone" value={c.telefone} />
                      <Field label="E-mail" value={c.email} />
                      <Field label="Gênero" value={c.genero} />
                      <Field label="Idioma" value={c.idioma ?? c.locale} />
                      <Field label="Fontes" value={c.origens.join(", ") || "—"} />
                    </Grid>
                  </Card>

                  {/* Conversa — o que o Domani sabe */}
                  <Card title={`${cap(CLIENTE.vocab.interacao.um)} no Domani`} tag="Domani" tagAccent>
                    <Grid>
                      <Field label={cap(CLIENTE.vocab.local.um)} value={c.canal} />
                      <Field label="Status" value={c.status} />
                      <Field label="Última interação" value={dataHoraBR(c.last_interaction)} />
                      <Field label="Última mensagem" value={dataHoraBR(c.last_message_at)} />
                      <Field label="Tipo da mensagem" value={c.last_message_type} />
                      <Field label="Inscrito desde" value={dataBR(c.subscribed)} />
                    </Grid>
                    {c.observacoes && (
                      <div className="mt-3 border-t border-line/10 pt-3">
                        <p className="text-xs text-ink/45">Observações</p>
                        <p className="mt-0.5 whitespace-pre-line text-sm text-ink/90">{c.observacoes}</p>
                      </div>
                    )}
                  </Card>

                  {/* Consentimento — separado porque é decisão do titular, não dado de perfil */}
                  <Card title="Consentimento de e-mail">
                    <Grid>
                      <Field label="Aceita receber" value={c.opt_in_email === null ? "—" : c.opt_in_email ? "Sim" : "Não"} />
                      <Field label="Confirmou" value={c.opted_in_email === null ? "—" : c.opted_in_email ? "Sim" : "Não"} />
                      <Field label="Por onde" value={c.opted_in_through} />
                    </Grid>
                  </Card>

                  {/* Tags: as do Domani e as manuais ficam separadas de propósito —
                      o sync sobrescreve as primeiras e nunca toca nas segundas. */}
                  <Card title="Tags & etiquetas">
                    <div className="space-y-3">
                      <TagRow label="Tags Domani" items={c.tags_domani} />
                      <TagRow label="Tags manuais" items={c.tags_manuais} accent />
                      <TagRow label="Etiquetas" items={c.etiquetas} />
                    </div>
                  </Card>

                  {/* Sincronização */}
                  <Card title="Registro">
                    <Grid>
                      <Field label="Sincronizado em" value={dataHoraBR(c.domani_synced_at)} />
                      <Field label="Criado em" value={dataHoraBR(c.created_at)} />
                      <Field label="Atualizado em" value={dataHoraBR(c.updated_at)} />
                      <Field label="ID Domani" value={c.domani_user_id ?? c.user_ns} />
                    </Grid>
                  </Card>
                </div>
              ) : null}
            </div>
          </>
        )}
      </div>

      <ConfirmDialog
        open={confirmDel}
        variant="danger"
        title="Excluir esta ficha?"
        description={<>{c?.nome ?? "O contato"} deixa de aparecer nas listas, no dashboard e nas exportações. A exclusão é lógica e auditada: se o Domani registrar uma interação nova, ou uma importação trouxer a ficha de volta, ela é restaurada.</>}
        confirmLabel={deleting ? "Excluindo…" : "Excluir ficha"}
        cancelLabel="Manter"
        onConfirm={async () => {
          setDeleting(true);
          try {
            await api.contatos.remover(id);
            setConfirmDel(false);
            onChanged();
            onClose();
          } finally {
            setDeleting(false);
          }
        }}
        onClose={() => setConfirmDel(false)}
      />
    </div>
  );
}

function Card({ title, tag, tagAccent, children }: { title: string; tag?: string; tagAccent?: boolean; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-line/12 bg-surface p-5 shadow-domani-lift">
      <div className="mb-4 flex items-center gap-2">
        <h3 className="text-xs font-bold uppercase tracking-[0.14em] text-ink/45">{title}</h3>
        {tag && (
          <span className={clsx("rounded px-1.5 py-0.5 text-[10px] font-semibold", tagAccent ? "bg-domani-orange/10 text-domani-orange-600" : "bg-ink/10 text-ink/45")}>{tag}</span>
        )}
      </div>
      {children}
    </section>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <dl className="grid grid-cols-2 gap-x-10 gap-y-5 text-sm">{children}</dl>;
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink/45">{label}</dt>
      <dd className="mt-1.5 break-words text-[15px] leading-relaxed text-ink/90">{value ?? "—"}</dd>
    </div>
  );
}

function TagRow({ label, items, accent }: { label: string; items: string[]; accent?: boolean }) {
  return (
    <div>
      <p className="mb-1 text-xs text-ink/45">{label}</p>
      <div className="flex flex-wrap gap-1">
        {items.length ? items.map((t) => (
          <span key={t} className={clsx("rounded-full px-2 py-0.5 text-[11px] font-semibold", accent ? "bg-domani-orange/10 text-domani-orange-600" : "bg-ink/10 text-ink/75")}>{t}</span>
        )) : <span className="text-sm text-ink/40">—</span>}
      </div>
    </div>
  );
}
