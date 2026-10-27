import { CLIENTE } from "@/config/cliente";
import { ModuloDesligado } from "@/components/ui/modulo-desligado";

// Auditoria só existe com o módulo ligado em config/cliente.ts.
export default function AuditoriaLayout({ children }: { children: React.ReactNode }) {
  if (!CLIENTE.modulos.auditoria) return <ModuloDesligado nome="Auditoria" chave="auditoria" />;
  return <>{children}</>;
}
