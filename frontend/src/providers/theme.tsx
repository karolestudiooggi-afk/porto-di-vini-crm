"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";

interface ThemeCtx {
  theme: Theme;
  toggleTheme: () => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  // Sincroniza com o estado já aplicado pelo script anti-flash do layout.
  useEffect(() => {
    setTheme(document.documentElement.classList.contains("dark") ? "dark" : "light");
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      document.documentElement.classList.toggle("dark", next === "dark");
      try {
        localStorage.setItem("domani-theme", next);
      } catch {}
      return next;
    });
  }, []);

  return <Ctx.Provider value={{ theme, toggleTheme }}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme deve ser usado dentro de ThemeProvider");
  return ctx;
}

/** Script inline anti-flash — aplica o tema antes da pintura (sem flash). */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("domani-theme");var p=window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches;if(t==="dark"||(!t&&p))document.documentElement.classList.add("dark");localStorage.removeItem("domani-density");document.documentElement.removeAttribute("data-density");}catch(e){}})();`;
