import { CLIENTE } from "@/config/cliente";
import { Logo } from "@/components/ui/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen place-items-center bg-mesh-light px-4 py-10 dark:bg-mesh-dark">
      <div className="w-full max-w-md">
        <div className="overflow-hidden rounded-4xl border border-white/10 bg-domani-graphite text-white shadow-domani-card">
          <div className="flex flex-col items-center gap-3 border-b border-white/10 px-8 pt-8 pb-6 text-center">
            <Logo variant="branco" className="h-6 w-auto" />
            <span className="rounded-full border border-white/15 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-white/55">
              CRM · {CLIENTE.nome}
            </span>
          </div>
          <div className="px-8 py-7">{children}</div>
        </div>
        <p className="mt-5 text-center text-xs text-domani-graphite/55 dark:text-white/40">
          Domani.AI · plataforma de relacionamento com clientes
        </p>
      </div>
    </div>
  );
}
