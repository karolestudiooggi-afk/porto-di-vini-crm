"use client";

import { useState } from "react";
import { api, isApiConfigured } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { supabase } from "@/lib/supabase";
import { Icon } from "@/components/ui/icon";

export default function ContaPage() {
  const { data: me, loading, error } = useApi(() => api.usuarios.me(), []);
  const [resetMsg, setResetMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function redefinirSenha() {
    if (!supabase || !me) return;
    setBusy(true);
    setResetMsg(null);
    const { error: e } = await supabase.auth.resetPasswordForEmail(me.email);
    setBusy(false);
    setResetMsg(e ? e.message : "Enviamos um link de redefinição para o seu e-mail.");
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <section>
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-domani-orange-600">Conta</p>
        <h1 className="mt-1.5 font-display text-3xl font-extrabold tracking-tight text-ink">Minha conta</h1>
        <p className="mt-1.5 text-sm text-muted">Seus dados de acesso e permissões.</p>
      </section>

      {!isApiConfigured ? (
        <Card><p className="text-sm text-muted">Conecte a API (.env.local) para ver seus dados.</p></Card>
      ) : loading ? (
        <Card><div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton h-10 rounded-xl" />)}</div></Card>
      ) : error ? (
        <Card><p className="text-sm text-red-500">{error}</p></Card>
      ) : me ? (
        <>
          <Card>
            <h2 className="font-display text-lg font-extrabold tracking-tight text-ink">Perfil</h2>
            <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div><dt className="text-xs font-bold uppercase tracking-[0.1em] text-ink/45">Email</dt><dd className="mt-1 text-sm text-ink">{me.email}</dd></div>
              <div><dt className="text-xs font-bold uppercase tracking-[0.1em] text-ink/45">Papel</dt><dd className="mt-1 text-sm font-semibold capitalize text-ink">{me.papel}</dd></div>
            </dl>
          </Card>

          <Card>
            <h2 className="font-display text-lg font-extrabold tracking-tight text-ink">Permissões</h2>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {me.permissoes.length ? me.permissoes.map((p) => (
                <span key={p} className="rounded-full bg-app px-2.5 py-1 text-[11px] font-semibold text-ink/75">{p}</span>
              )) : <span className="text-sm text-ink/40">—</span>}
            </div>
          </Card>

          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-display text-lg font-extrabold tracking-tight text-ink">Segurança</h2>
                <p className="mt-0.5 text-sm text-muted">Enviamos um link seguro por e-mail para trocar a senha.</p>
              </div>
              <button onClick={redefinirSenha} disabled={busy} className="inline-flex items-center gap-2 rounded-xl bg-domani-graphite px-4 py-2.5 text-sm font-bold text-white transition hover:bg-domani-slate disabled:opacity-60">
                <Icon name="send" className="h-4 w-4" strokeWidth={2} />
                {busy ? "Enviando…" : "Redefinir senha"}
              </button>
            </div>
            {resetMsg && <p className="mt-3 rounded-xl border border-line/15 bg-app px-3 py-2 text-sm text-ink/80">{resetMsg}</p>}
          </Card>
        </>
      ) : null}
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <section className="rounded-3xl border border-line/12 bg-surface p-5 shadow-domani-lift sm:p-6">{children}</section>;
}
