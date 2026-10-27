import { CLIENTE } from "@/config/cliente";
import { ModuloDesligado } from "@/components/ui/modulo-desligado";

// Agente IA só existe com o módulo ligado em config/cliente.ts.
export default function AgenteLayout({ children }: { children: React.ReactNode }) {
  if (!CLIENTE.modulos.agente) return <ModuloDesligado nome="Agente IA" chave="agente" />;
  return <>{children}</>;
}
