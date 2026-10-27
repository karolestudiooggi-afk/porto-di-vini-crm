"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { dataBR, dataHoraBR } from "@/lib/format";
import type { Convite, Usuario } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { useAuth } from "@/providers/auth";

const CAMPO =
  "w-full rounded-2xl border border-line/15 bg-app px-3 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted focus:border-domani-orange focus:bg-surface";

const PAPEIS = [
  { value: "operador", label: "Operador" },
  { value: "admin", label: "Administrador" },
];

/**
 * Equipe com acesso ao CRM.
 *
 * O acesso é fechado: convidar é o ÚNICO caminho. Criar conta no Supabase Auth
 * por fora não dá acesso a nada — o convite é consumido no primeiro login e é
 * ele que atribui o papel.
 */
export default function UsuariosPage() {
  // O contexto expõe o e-mail da sessão; é por ele que a tela reconhece a
  // própria conta (para não deixar o admin se desativar sozinho).
  const { can, email: meuEmail } = useAuth();
  const lista = useApi(() => api.usuarios.list(), []);
  const convites = useApi(() => api.usuarios.convites.list(), []);

  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState("operador");
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const [desativar, setDesativar] = useState<Usuario | null>(null);
  const [cancelar, setCancelar] = useState<Convite | null>(null);

  const podeGerenciar = can("usuarios:manage");

  async function convidar(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setAviso(null);
    try {
      await api.usuarios.convites.criar({ email: email.trim(), papel });
      setAviso({ tipo: "ok", texto: `Convite enviado para ${email.trim()}.` });
      setEmail("");
      convites.reload();
    } catch (err) {
      // O backend devolve o link no texto quando o e-mail falha — assim dá para
      // mandar por outro meio em vez de perder o convite.
      setAviso({
        tipo: "erro",
        texto: err instanceof Error ? err.message : "Não deu para convidar.",
      });
    } finally {
      setEnviando(false);
    }
  }

  async function trocarPapel(u: Usuario, novo: string) {
    await api.usuarios.patch(u.id, { papel: novo });
    lista.reload();
  }

  return (
    <div className="space-y-4">
      <header className="rounded-3xl border border-line/10 bg-surface px-5 py-5 shadow-domani-lift sm:px-6">
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-domani-orange-300">
          Acesso
        </p>
        <h1 className="mt-1 font-display text-2xl font-extrabold tracking-tight">Usuários</h1>
        <p className="mt-1 text-sm text-muted">
          Quem pode entrar no CRM. O acesso é só por convite.
        </p>
      </header>

      {podeGerenciar && (
        <form onSubmit={convidar}
              className="rounded-3xl border border-line/10 bg-surface p-5 shadow-domani-lift">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
            Convidar alguém
          </h2>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label className="min-w-[240px] flex-1">
              <span className="mb-1.5 block text-xs font-bold text-ink/70">E-mail</span>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                     placeholder="pessoa@empresa.com" className={CAMPO} />
            </label>
            <label className="w-44">
              <span className="mb-1.5 block text-xs font-bold text-ink/70">Perfil</span>
              <Select aria-label="Perfil" value={papel} onChange={setPapel}
                      options={PAPEIS} triggerClassName={CAMPO} />
            </label>
            <button type="submit" disabled={enviando}
                    className="rounded-xl bg-domani-orange px-5 py-2.5 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:opacity-50">
              {enviando ? "Enviando…" : "Convidar"}
            </button>
          </div>

          <p className="mt-2 text-[11px] text-muted">
            A pessoa recebe um link para criar a própria senha. O link vale 7 dias
            e só pode ser usado uma vez.
          </p>

          {aviso && (
            <p className={`mt-3 rounded-2xl px-4 py-3 text-sm ${
              aviso.tipo === "ok"
                ? "bg-emerald-500/10 text-emerald-700"
                : "bg-red-500/5 text-red-500"
            }`}>
              {aviso.texto}
            </p>
          )}
        </form>
      )}

      {convites.data && convites.data.length > 0 && (
        <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
          <div className="border-b border-line/10 px-5 py-4">
            <h2 className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
              Convites pendentes
            </h2>
          </div>
          <ul className="divide-y divide-line/10">
            {convites.data.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-4 px-5 py-3">
                <div className="min-w-0">
                  <p className="truncate font-medium text-ink">{c.email}</p>
                  <p className="text-xs text-muted">
                    {c.papel} · expira em {dataBR(c.expira_em)}
                  </p>
                </div>
                {podeGerenciar && (
                  <button onClick={() => setCancelar(c)}
                          className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-bold text-red-500 transition hover:bg-red-500/10">
                    Cancelar
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="overflow-hidden rounded-3xl border border-line/10 bg-surface shadow-domani-lift">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line/10 text-left text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
                <th className="px-5 py-3">Pessoa</th>
                <th className="px-5 py-3">Perfil</th>
                <th className="px-5 py-3">Situação</th>
                <th className="px-5 py-3">Último acesso</th>
                {podeGerenciar && <th className="px-5 py-3" />}
              </tr>
            </thead>
            <tbody>
              {lista.loading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i} className="border-b border-line/[0.06]">
                    <td colSpan={5} className="px-5 py-2"><div className="skeleton h-6 rounded-lg" /></td>
                  </tr>
                ))
              ) : lista.error ? (
                <tr><td colSpan={5} className="px-6 py-16 text-center text-sm text-red-500">{lista.error}</td></tr>
              ) : !lista.data?.length ? (
                <tr><td colSpan={5} className="px-6 py-16 text-center text-sm text-muted">Nenhum usuário ainda.</td></tr>
              ) : (
                lista.data.map((u) => (
                  <tr key={u.id} className="border-b border-line/[0.08]">
                    <td className="px-5 py-3">
                      <div className="font-semibold text-ink">
                        {u.nome ?? u.email}
                        {u.email === meuEmail && (
                          <span className="ml-1.5 text-[11px] font-normal text-muted">(você)</span>
                        )}
                      </div>
                      <div className="text-xs text-muted">{u.email}</div>
                    </td>
                    <td className="px-5 py-3">
                      {podeGerenciar && u.email !== meuEmail ? (
                        <Select aria-label={`Perfil de ${u.email}`} value={u.papel}
                                onChange={(v) => trocarPapel(u, v)} options={PAPEIS}
                                triggerClassName="rounded-lg border border-line/15 bg-app px-2.5 py-1 text-xs font-semibold text-ink" />
                      ) : (
                        <span className="text-ink/80">{u.papel}</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                        u.status === "ativo"
                          ? "bg-emerald-500/15 text-emerald-700"
                          : "bg-app text-muted"
                      }`}>
                        {u.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-ink/70">{dataHoraBR(u.ultimo_acesso)}</td>
                    {podeGerenciar && (
                      <td className="px-5 py-3 text-right">
                        {u.email !== meuEmail && u.status === "ativo" && (
                          <button onClick={() => setDesativar(u)}
                                  className="rounded-lg px-3 py-1.5 text-xs font-bold text-red-500 transition hover:bg-red-500/10">
                            Desativar
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <ConfirmDialog
        open={desativar !== null}
        variant="danger"
        title="Desativar este acesso?"
        description={<>{desativar?.email} deixa de conseguir entrar. Os dados e o histórico permanecem — dá para reativar depois.</>}
        confirmLabel="Desativar"
        cancelLabel="Manter"
        onConfirm={async () => {
          if (desativar) await api.usuarios.patch(desativar.id, { status: "inativo" });
          setDesativar(null);
          lista.reload();
        }}
        onClose={() => setDesativar(null)}
      />

      <ConfirmDialog
        open={cancelar !== null}
        variant="danger"
        title="Cancelar este convite?"
        description={<>O link enviado para {cancelar?.email} para de funcionar.</>}
        confirmLabel="Cancelar convite"
        cancelLabel="Manter"
        onConfirm={async () => {
          if (cancelar) await api.usuarios.convites.cancelar(cancelar.id);
          setCancelar(null);
          convites.reload();
        }}
        onClose={() => setCancelar(null)}
      />
    </div>
  );
}
