"use client";

import { useEffect, useRef } from "react";
import clsx from "clsx";
import { Icon } from "./icon";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "default";
  onConfirm: () => void;
  onClose: () => void;
}

/**
 * Diálogo de confirmação no padrão Domani — substitui o confirm()/alert() nativo.
 * Use para ações destrutivas (apagar/excluir) ou avisos que pedem decisão.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  variant = "default",
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => confirmRef.current?.focus(), 20);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  const danger = variant === "danger";

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 animate-overlay-fade bg-domani-ink/55 backdrop-blur-sm" onClick={onClose} />

      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        className="relative w-full max-w-sm animate-modal-panel overflow-hidden rounded-2xl border border-line/12 bg-surface shadow-2xl"
      >
        <div className="px-6 pb-2 pt-6 text-center">
          <div
            className={clsx(
              "mx-auto flex h-14 w-14 items-center justify-center rounded-2xl",
              danger ? "bg-red-500/12 text-red-500" : "bg-domani-orange/12 text-domani-orange-600",
            )}
          >
            <Icon name="alert" className="h-7 w-7" strokeWidth={1.9} />
          </div>
          <h2 id="confirm-title" className="mt-4 font-display text-lg font-extrabold tracking-tight text-ink">
            {title}
          </h2>
          {description && <p className="mt-1.5 text-sm text-muted">{description}</p>}
        </div>

        <div className="flex items-center gap-2 px-6 py-5">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl border border-line/25 px-4 py-2.5 text-sm font-semibold text-ink transition hover:bg-app"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            onClick={onConfirm}
            className={clsx(
              "flex-1 rounded-xl px-4 py-2.5 text-sm font-bold text-white transition focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
              danger
                ? "bg-red-500 hover:bg-red-600 focus-visible:ring-red-500"
                : "bg-domani-orange hover:bg-domani-orange-600 focus-visible:ring-domani-orange",
            )}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
