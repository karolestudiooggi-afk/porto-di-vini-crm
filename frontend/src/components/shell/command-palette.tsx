"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { NAV } from "@/lib/nav";
import { useAuth } from "@/providers/auth";
import { Icon } from "@/components/ui/icon";


export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const { can } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    const items = NAV.filter((n) => !n.staffOnly || can("usuarios:read"));
    const navMatches = items.filter(
      (i) => !query || (i.keywords + " " + i.label).toLowerCase().includes(query),
    ).map((i) => ({ label: `Ir para ${i.label}`, href: i.href }));
    if (query) {
      navMatches.push({ label: `Buscar cliente: "${q}"`, href: `/clientes?q=${encodeURIComponent(q)}` });
    }
    return navMatches;
  }, [q, can]);

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
      const t = setTimeout(() => inputRef.current?.focus(), 10);
      return () => clearTimeout(t);
    }
  }, [open]);

  useEffect(() => setActive(0), [q]);

  if (!open) return null;

  const go = (href: string) => {
    onClose();
    router.push(href);
  };

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 animate-overlay-fade bg-domani-ink/55 backdrop-blur-sm" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        className="absolute left-1/2 top-20 w-[92%] max-w-xl -translate-x-1/2 animate-modal-panel overflow-hidden rounded-2xl border border-line/15 bg-surface shadow-2xl"
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter") { e.preventDefault(); if (filtered[active]) go(filtered[active].href); }
        }}
      >
        <div className="flex items-center gap-3 border-b border-line/10 px-4">
          <Icon name="search" className="h-4 w-4 text-muted" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar clientes ou navegar..."
            className="w-full bg-transparent py-3.5 text-sm text-ink placeholder:text-muted focus:outline-none"
          />
          <kbd className="rounded bg-line/10 px-1.5 py-0.5 text-[10px] text-muted">esc</kbd>
        </div>
        <ul className="scroll-area max-h-80 overflow-y-auto p-2 text-sm">
          {filtered.map((item, i) => (
            <li key={item.href + item.label}>
              <button
                onMouseEnter={() => setActive(i)}
                onClick={() => go(item.href)}
                className={clsx(
                  "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition",
                  i === active ? "bg-domani-orange/10 text-domani-orange-600" : "text-ink hover:bg-app",
                )}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
