import { CLIENTE } from "@/config/cliente";
import { ModuloDesligado } from "@/components/ui/modulo-desligado";

// Avaliações (NPS e QR) só existem com o módulo ligado em config/cliente.ts.
export default function AvaliacoesLayout({ children }: { children: React.ReactNode }) {
  if (!CLIENTE.modulos.avaliacoes) return <ModuloDesligado nome="Avaliações" chave="avaliacoes" />;
  return <>{children}</>;
}
