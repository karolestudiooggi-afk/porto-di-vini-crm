import type { Metadata } from "next";
import Avaliacao from "./avaliacao-client";
import { CLIENTE } from "@/config/cliente";
import { CLIENT_NAME } from "@/lib/nav";

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

/**
 * Nome da unidade, para o título da página do QR.
 *
 * Vem SEMPRE da API: as unidades são derivadas dos dados (o seed de
 * `avaliacao.contas` lê o campo `unidade` da ficha), então unidade nova aparece
 * sozinha. Um mapa fixo aqui nasceria desatualizado — e, num template, levaria
 * as unidades de um cliente para o CRM de outro.
 *
 * Se a API estiver fora, cai no nome do cliente: título genérico é melhor que
 * título errado.
 */
async function getNome(slug: string): Promise<string> {
  try {
    const r = await fetch(`${BASE}/avaliacao/conta/${slug}`, { cache: "no-store" });
    if (r.ok) {
      const nome = (await r.json())?.nome;
      if (typeof nome === "string" && nome.trim()) return nome;
    }
  } catch {
    /* API indisponível: usa o nome do cliente abaixo */
  }
  return CLIENT_NAME;
}

export async function generateMetadata({ params }: { params: { slug: string } }): Promise<Metadata> {
  if (!CLIENTE.modulos.avaliacoes) return { title: "Avaliação indisponível" };
  return { title: `Avaliação · ${await getNome(params.slug)}` };
}

// Rota PÚBLICA (fora do grupo (app)) — sem sidebar, sem login. O QR de avaliação aponta aqui.
export default async function Page({ params }: { params: { slug: string } }) {
  // Módulo de avaliações desligado em config/cliente.ts: nada de formulário, nem
  // de consulta à API.
  if (!CLIENTE.modulos.avaliacoes) return <Indisponivel />;
  const nome = await getNome(params.slug);
  return <Avaliacao slug={params.slug} nome={nome} />;
}

function Indisponivel() {
  return (
    <main className="flex min-h-[100dvh] items-center justify-center bg-app px-4 py-8 text-ink">
      <div className="w-full max-w-md rounded-3xl border border-line bg-surface p-7 text-center shadow-domani-lift">
        <h1 className="font-display text-2xl font-semibold">Avaliação indisponível</h1>
        <p className="mt-2 text-[15px] text-muted">
          Esta página de avaliação não está disponível no momento. Obrigado pelo interesse.
        </p>
      </div>
    </main>
  );
}
