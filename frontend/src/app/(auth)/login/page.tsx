"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/providers/auth";
import { Icon } from "@/components/ui/icon";

const INPUT = "w-full rounded-xl border border-white/12 bg-white/[0.04] px-3.5 py-3 text-sm text-white outline-none transition placeholder:text-white/35 focus:border-domani-orange focus:bg-white/[0.07]";
const LABEL = "mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-white/45";

export default function LoginPage() {
  const router = useRouter();
  const { signIn, configured } = useAuth();
  const [show, setShow] = useState(false);
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!configured) { router.push("/dashboards"); return; }
    setBusy(true);
    const { error } = await signIn(email, senha);
    setBusy(false);
    if (error) { setErro(error); return; }
    router.push("/dashboards");
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <h1 className="font-display text-xl font-extrabold tracking-tight">Entrar</h1>
        <p className="mt-1 text-sm text-white/50">Acesse o painel da sua operação.</p>
      </div>

      {erro && (
        <p className="rounded-xl border border-red-500/30 bg-red-500/10 px-3.5 py-2.5 text-sm font-semibold text-red-300">
          {erro}
        </p>
      )}

      <div>
        <label className={LABEL}>Email</label>
        <input className={INPUT} type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="seu@email.com" autoComplete="email" required={configured} />
      </div>

      <div>
        <div className="flex items-center justify-between">
          <label className={LABEL}>Senha</label>
          <Link href="/esqueci-senha" className="mb-1.5 text-xs font-semibold text-domani-orange-300 transition hover:text-domani-orange">Esqueci a senha</Link>
        </div>
        <div className="relative">
          <input className={`${INPUT} pr-11`} type={show ? "text" : "password"} value={senha} onChange={(e) => setSenha(e.target.value)} placeholder="••••••••" autoComplete="current-password" required={configured} />
          <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-2 text-white/40 transition hover:text-white" aria-label="Mostrar senha">
            <Icon name={show ? "sun" : "moon"} className="h-4 w-4" />
          </button>
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-white/60">
        <input type="checkbox" defaultChecked className="accent-domani-orange" /> Manter conectado
      </label>

      <button type="submit" disabled={busy} className="w-full rounded-xl bg-domani-orange px-4 py-3 text-sm font-bold text-white transition hover:bg-domani-orange-600 disabled:opacity-60">
        {busy ? "Entrando…" : "Entrar"}
      </button>

      {!configured && (
        <p className="text-center text-xs text-white/35">
          Modo demo: sem Supabase configurado, qualquer clique leva ao painel.
        </p>
      )}
    </form>
  );
}
