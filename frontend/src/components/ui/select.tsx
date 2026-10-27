"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { Icon } from "./icon";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  triggerClassName?: string;
  "aria-label"?: string;
}

/**
 * Select próprio do Domani — substitui o <select> nativo para que a lista aberta
 * siga o tema (claro/escuro), com item ativo em laranja e navegação por teclado.
 * O menu é renderizado via portal, então nunca é cortado por overflow do card.
 */
export function Select({ value, onChange, options, placeholder = "Selecionar", triggerClassName, ...aria }: SelectProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [pos, setPos] = useState<{ top: number; left: number; width: number; up: boolean } | null>(null);
  const [mounted, setMounted] = useState(false);

  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const selected = options.find((o) => o.value === value);

  const place = () => {
    const btn = btnRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const menuH = Math.min(options.length * 40 + 12, 288);
    const below = window.innerHeight - r.bottom;
    const up = below < menuH + 10 && r.top > below;
    setPos({ top: up ? r.top - menuH - 6 : r.bottom + 6, left: r.left, width: r.width, up });
  };

  useEffect(() => {
    if (!open) return;
    place();
    // Fecha quando a PÁGINA rola (o menu é `position: fixed`, ficaria solto no ar),
    // mas ignora o scroll de DENTRO do menu: com lista longa o usuário rola a lista,
    // e sem esta checagem o menu se fecharia na cara dele. O listener é de captura
    // (`true`) porque scroll não borbulha — daí ele receber os dois casos.
    const onScroll = (e: Event) => {
      if (menuRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    const onResize = () => setOpen(false);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setActive(Math.max(0, options.findIndex((o) => o.value === value)));
    const onDown = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node) && !btnRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Foca o menu ao abrir: sem isso o onKeyDown do listbox só responde depois de um
  // clique, e a navegação por seta não funciona logo de cara.
  useEffect(() => {
    if (open && pos) menuRef.current?.focus();
  }, [open, pos]);

  const choose = (v: string) => {
    onChange(v);
    setOpen(false);
    btnRef.current?.focus();
  };

  return (
    <>
      <button
        type="button"
        ref={btnRef}
        aria-haspopup="listbox"
        aria-expanded={open}
        {...aria}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(true); }
        }}
        className={clsx(
          "flex w-full items-center justify-between gap-2 text-left outline-none",
          open && "border-domani-orange",
          triggerClassName,
        )}
      >
        <span className={clsx("truncate", !selected && "text-muted")}>{selected?.label ?? placeholder}</span>
        <Icon name="arrowUp" className={clsx("h-4 w-4 shrink-0 text-domani-orange transition-transform", open ? "" : "rotate-180")} strokeWidth={2.2} />
      </button>

      {mounted && open && pos && createPortal(
        <div
          ref={menuRef}
          role="listbox"
          tabIndex={-1}
          style={{ position: "fixed", top: pos.top, left: pos.left, width: pos.width }}
          className="scroll-area z-[70] max-h-72 overflow-y-auto rounded-xl border border-line/15 bg-surface p-1.5 shadow-2xl animate-modal-panel"
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, options.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
            else if (e.key === "Enter") { e.preventDefault(); choose(options[active].value); }
            else if (e.key === "Escape") { setOpen(false); btnRef.current?.focus(); }
          }}
        >
          {options.map((o, i) => {
            const isSel = o.value === value;
            return (
              <button
                key={o.value}
                type="button"
                role="option"
                aria-selected={isSel}
                ref={i === active ? (el) => el?.scrollIntoView({ block: "nearest" }) : undefined}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(o.value)}
                className={clsx(
                  "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm transition",
                  isSel ? "bg-domani-orange/10 font-semibold text-domani-orange-600" : i === active ? "bg-app text-ink" : "text-ink/80",
                )}
              >
                <span className="truncate">{o.label}</span>
                {isSel && <Icon name="check" className="h-4 w-4 shrink-0" strokeWidth={2} />}
              </button>
            );
          })}
        </div>,
        document.body,
      )}
    </>
  );
}
