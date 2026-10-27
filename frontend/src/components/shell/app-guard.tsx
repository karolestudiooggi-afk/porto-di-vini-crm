"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/providers/auth";

export function AppGuard({ children }: { children: React.ReactNode }) {
  const { configured, loading, session } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (configured && !loading && !session) router.replace("/login");
  }, [configured, loading, session, router]);

  // Modo demo (sem credenciais): libera tudo, como antes.
  if (!configured) return <>{children}</>;

  if (loading || !session) {
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-line/20 border-t-domani-orange" />
      </div>
    );
  }
  return <>{children}</>;
}
