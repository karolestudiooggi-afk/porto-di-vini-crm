"use client";

import { useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";

const INPUT = "w-full rounded-xl border border-white/12 bg-white/[0.04] px-3.5 py-3 text-sm text-white outline-none transition placeholder:text-white/35 focus:border-domani-orange focus:bg-white/[0.07]";
const LABEL = "mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-white/45";

export default function EsqueciSenhaPage() {
  const [sent, setSent] = useState(false);

  if (sent) {
    return (
      <div className="space-y-4 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-domani-orange/15 text-domani-orange-300">
          <Icon name="send" className="h-6 w-6" strokeWidth={2} />
        </div>
        <h1 className="font-display text-xl font-extrabold tracking-tight">Verifique seu e-mail</h1>
        <p className="text-sm text-white/55">Se houver uma conta com esse endereço, enviamos um link para redefinir a senha.</p>
        <Link href="/login" className="inline-flex rounded-xl bg-white px-5 py-2.5 text-sm font-bold text-domani-graphite transition hover:bg-domani-orange hover:text-white">Voltar ao login</Link>
      </div>
    );
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); setSent(true); }} className="space-y-4">
      <div>
        <h1 className="font-display text-xl font-extrabold tracking-tight">Recuperar senha</h1>
        <p className="mt-1 text-sm text-white/50">Enviaremos um link de redefinição para o seu e-mail.</p>
      </div>
      <div>
        <label className={LABEL}>Email</label>
        <input className={INPUT} type="email" placeholder="seu@email.com" required />
      </div>
      <button type="submit" className="w-full rounded-xl bg-domani-orange px-4 py-3 text-sm font-bold text-white transition hover:bg-domani-orange-600">Enviar link</button>
      <Link href="/login" className="block text-center text-xs font-semibold text-white/45 transition hover:text-white">Voltar ao login</Link>
    </form>
  );
}
