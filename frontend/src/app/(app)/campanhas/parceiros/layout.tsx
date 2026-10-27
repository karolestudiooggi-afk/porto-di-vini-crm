import { CLIENTE } from "@/config/cliente";
import { ModuloDesligado } from "@/components/ui/modulo-desligado";

// A base de parceiros é uma aba opcional do E-mail (modulos.parceiros).
export default function ParceirosLayout({ children }: { children: React.ReactNode }) {
  if (!CLIENTE.modulos.parceiros) {
    return (
      <ModuloDesligado nome="Parceiros" chave="parceiros">
        A aba de parceiros do E-mail não está ligada neste CRM.
      </ModuloDesligado>
    );
  }
  return <>{children}</>;
}
