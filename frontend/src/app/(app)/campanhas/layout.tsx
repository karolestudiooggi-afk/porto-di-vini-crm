import { CLIENTE } from "@/config/cliente";
import { ModuloDesligado } from "@/components/ui/modulo-desligado";

// E-mail (campanhas, templates e disparo) só existe com o módulo ligado em config/cliente.ts.
export default function CampanhasLayout({ children }: { children: React.ReactNode }) {
  if (!CLIENTE.modulos.campanhas) return <ModuloDesligado nome="E-mail" chave="campanhas" />;
  return <>{children}</>;
}
