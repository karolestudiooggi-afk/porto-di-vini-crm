import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

/** true quando as credenciais do Supabase estão configuradas no .env.local */
export const isAuthConfigured = Boolean(url && anon);

/**
 * Instância única do Supabase no browser. Quando não há credenciais,
 * fica null e o app roda em "modo demo" (sem login obrigatório).
 */
export const supabase: SupabaseClient | null = isAuthConfigured
  ? createClient(url, anon, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    })
  : null;
