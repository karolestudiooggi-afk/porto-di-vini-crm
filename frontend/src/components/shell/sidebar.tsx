"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import { NAV, CLIENT_NAME } from "@/lib/nav";
import { useAuth } from "@/providers/auth";
import { Logo } from "@/components/ui/logo";
import { Icon } from "@/components/ui/icon";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { email, papel, signOut, configured, can } = useAuth();

  return (
    <aside className="sticky top-0 hidden h-screen flex-col border-r border-white/10 bg-domani-graphite text-white lg:flex">
      <div className="px-6 pb-5 pt-6">
        <Link href="/dashboards" className="flex min-w-0 items-center gap-3">
          <Logo variant="branco" className="h-5 w-auto" />
          <span className="h-5 w-px shrink-0 bg-white/20" />
          <span className="truncate text-sm font-semibold text-white/80">{CLIENT_NAME}</span>
        </Link>
      </div>

      <nav className="flex-1 space-y-1 px-3 text-sm font-semibold">
        {NAV.filter((n) => !n.staffOnly || can("usuarios:read")).map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "group flex items-center gap-3 rounded-xl px-3 py-2.5 transition",
                active
                  ? "bg-white text-domani-graphite shadow-lg shadow-black/15"
                  : "text-white/60 hover:bg-white/10 hover:text-white",
              )}
            >
              <Icon
                name={item.icon}
                className={clsx("h-4 w-4 shrink-0", active ? "text-domani-orange" : "text-white/40 group-hover:text-white/75")}
              />
              <span className="flex min-w-0 flex-1 items-center gap-2">
                {item.label}
                {item.beta && (
                  <span className="rounded bg-domani-orange px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">
                    beta
                  </span>
                )}
              </span>
            </Link>
          );
        })}
      </nav>

      <div className="space-y-3 border-t border-white/10 p-4">
        <div className="min-w-0 rounded-xl bg-white/[0.04] px-3 py-2.5">
          <p className="truncate text-xs font-semibold text-white/80">{(configured && email) || "conta@demo"}</p>
          <p className="mt-0.5 text-[10px] uppercase tracking-[0.14em] text-white/35">{papel ?? "—"}</p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Link
            href="/conta"
            className="inline-flex items-center justify-center rounded-xl border border-white/10 px-3 py-2 text-xs font-semibold text-white/65 transition hover:bg-white/10 hover:text-white"
          >
            Minha conta
          </Link>
          <button
            onClick={async () => { await signOut(); router.push("/login"); }}
            className="rounded-xl bg-white px-3 py-2 text-center text-xs font-bold text-domani-graphite transition hover:bg-domani-orange hover:text-white"
          >
            Sair
          </button>
        </div>
      </div>
    </aside>
  );
}
