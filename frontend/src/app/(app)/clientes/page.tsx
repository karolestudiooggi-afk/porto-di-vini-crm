import { Suspense } from "react";
import type { Metadata } from "next";
import { ClientesView } from "@/components/clientes/clientes-view";

export const metadata: Metadata = { title: "Clientes" };

export default function ClientesPage() {
  return (
    <Suspense fallback={<div className="h-1 animate-pulse rounded-full bg-domani-orange/20" />}>
      <ClientesView />
    </Suspense>
  );
}
