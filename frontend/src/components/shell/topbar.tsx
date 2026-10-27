"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import { NAV, CLIENT_NAME } from "@/lib/nav";
import { useTheme } from "@/providers/theme";
import { useAuth } from "@/providers/auth";
import { Logo } from "@/components/ui/logo";
import { Icon } from "@/components/ui/icon";
import { CommandPalette } from "./command-palette";

export function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { toggleTheme } = useTheme();
  const { signOut, can } = useAuth();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const items = NAV.filter((n) => !n.staffOnly || can("usuarios:read"));

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-line/10 bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Link href="/dashboards" className="flex items-center gap-3 lg:hidden">
            <Logo variant="auto" className="h-5 w-auto" />
            <span className="h-5 w-px shrink-0 bg-line/20" />
            <span className="text-sm font-bold text-ink">{CLIENT_NAME}</span>
          </Link>

          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            title="Buscar"
            className="inline-flex min-w-0 flex-1 items-center gap-3 rounded-2xl border border-line/15 bg-app px-4 py-2.5 text-left text-sm text-muted transition hover:border-domani-orange/35 hover:bg-surface sm:max-w-md"
          >
            <Icon name="search" className="h-4 w-4 shrink-0" strokeWidth={2} />
            <span className="truncate">Buscar clientes ou navegar</span>
          </button>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={toggleTheme}
              title="Alternar tema claro/escuro"
              aria-label="Alternar tema"
              className="rounded-xl border border-line/10 bg-surface p-2 text-muted transition hover:border-domani-orange/35 hover:text-ink"
            >
              <Icon name="moon" className="block h-4 w-4 dark:hidden" />
              <Icon name="sun" className="hidden h-4 w-4 dark:block" />
            </button>
            <button
              onClick={async () => { await signOut(); router.push("/login"); }}
              className="rounded-xl border border-line/10 bg-surface px-3 py-2 text-xs font-bold text-ink transition hover:border-domani-orange/35 lg:hidden"
            >
              Sair
            </button>
          </div>
        </div>

        <nav className="flex items-center gap-2 overflow-x-auto border-t border-line/10 px-4 pb-3 pt-2 text-sm font-semibold lg:hidden">
          {items.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "whitespace-nowrap rounded-full px-3 py-1.5",
                  active ? "bg-domani-orange text-white" : "bg-app text-muted",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </header>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}
