"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

interface State<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/**
 * Executa uma chamada de API e devolve { data, loading, error, reload }.
 * `deps` controla quando refazer a chamada (igual ao useEffect).
 */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []): State<T> & { reload: () => void } {
  const [state, setState] = useState<State<T>>({ data: null, loading: true, error: null });
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fnRef.current()
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((e: unknown) => {
        const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Falha ao carregar";
        if (alive) setState({ data: null, loading: false, error: msg });
      });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(run, [run]);

  return { ...state, reload: run };
}
