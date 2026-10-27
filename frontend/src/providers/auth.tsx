"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase, isAuthConfigured } from "@/lib/supabase";
import { api } from "@/lib/api";

interface AuthCtx {
  configured: boolean;
  loading: boolean;
  session: Session | null;
  email: string | null;
  papel: string | null;
  perms: Set<string>;
  can: (perm: string) => boolean;
  signIn: (email: string, password: string) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(isAuthConfigured);
  const [papel, setPapel] = useState<string | null>(null);
  const [perms, setPerms] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  // Perfil/permissões do logado (usados para esconder ações sem permissão).
  useEffect(() => {
    if (!session) { setPapel(null); setPerms(new Set()); return; }
    let alive = true;
    api.usuarios.me()
      .then((me) => { if (alive) { setPapel(me.papel); setPerms(new Set(me.permissoes)); } })
      .catch(() => { if (alive) { setPapel(null); setPerms(new Set()); } });
    return () => { alive = false; };
  }, [session]);

  const signIn = useCallback(async (email: string, password: string) => {
    if (!supabase) return { error: "Login não configurado (defina as variáveis do Supabase)." };
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return { error: error ? error.message : null };
  }, []);

  const signOut = useCallback(async () => {
    if (supabase) await supabase.auth.signOut();
    setSession(null);
  }, []);

  const can = useCallback(
    (perm: string) => (!isAuthConfigured ? true : perms.has(perm)),
    [perms],
  );

  return (
    <Ctx.Provider
      value={{
        configured: isAuthConfigured,
        loading,
        session,
        email: session?.user?.email ?? null,
        papel,
        perms,
        can,
        signIn,
        signOut,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth deve ser usado dentro de AuthProvider");
  return ctx;
}
