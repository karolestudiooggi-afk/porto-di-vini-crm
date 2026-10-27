"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const INPUT = "w-full rounded-xl border border-white/12 bg-white/[0.04] px-3.5 py-3 text-sm text-white outline-none transition placeholder:text-white/35 focus:border-domani-orange focus:bg-white/[0.07]";
const LABEL = "mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-white/45";

export default function RedefinirSenhaPage() {
  const router = useRouter();
  const [done, setDone] = useState(false);

  if (done) {
    return (
      <div className="space-y-4 text-center">
        <h1 className="font-display text-xl font-extrabold tracking-tight">Senha redefinida</h1>
        <p className="text-sm text-white/55">Pronto! Você já pode entrar com a nova senha.</p>
        <Link href="/login" className="inline-flex rounded-xl bg-white px-5 py-2.5 text-sm font-bold text-domani-graphite transition hover:bg-domani-orange hover:text-white">Ir para o login</Link>
      </div>
    );
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); setDone(true); setTimeout(() => router.push("/login"), 1600); }} className="space-y-4">
      <div>
        <h1 className="font-display text-xl font-extrabold tracking-tight">Nova senha</h1>
        <p className="mt-1 text-sm text-white/50">Defina uma senha de pelo menos 8 caracteres.</p>
      </div>
      <div>
        <label className={LABEL}>Nova senha</label>
        <input className={INPUT} type="password" placeholder="••••••••" minLength={8} required />
      </div>
      <div>
        <label className={LABEL}>Confirmar senha</label>
        <input className={INPUT} type="password" placeholder="••••••••" minLength={8} required />
      </div>
      <button type="submit" className="w-full rounded-xl bg-domani-orange px-4 py-3 text-sm font-bold text-white transition hover:bg-domani-orange-600">Salvar nova senha</button>
    </form>
  );
}
