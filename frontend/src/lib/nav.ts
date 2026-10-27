import { CLIENTE, cap, integracoesLigadas } from "@/config/cliente";

/**
 * Menu principal.
 *
 * Os itens são montados a partir de `config/cliente.ts`: rótulos que dependem do
 * vocabulário do negócio saem de lá, e os módulos desligados nem entram na lista.
 * Assim, clonar o template para um cliente novo não exige editar este arquivo —
 * só o `cliente.ts`.
 *
 * Para acrescentar uma tela específica de um cliente (algo que só ele tem),
 * acrescente o item aqui e crie a rota em `app/(app)/`. Nesse caso vale um
 * comentário dizendo de quem é, para o próximo não achar que é do template.
 */

export type IconKey =
  | "clientes"
  | "rankings"
  | "dashboards"
  | "agente"
  | "usuarios"
  | "campanhas"
  | "integracoes";

export interface NavItem {
  href: string;
  label: string;
  icon: IconKey;
  beta?: boolean;
  staffOnly?: boolean;
  /** Termos que encontram este item na paleta de comandos (Ctrl+K). Sem acento. */
  keywords: string;
}

const { modulos, vocab } = CLIENTE;

export const NAV: NavItem[] = [
  {
    href: "/dashboards", label: "Dashboard", icon: "dashboards",
    keywords: "dashboards insights graficos indicadores painel",
  },
  {
    href: "/clientes", label: cap(vocab.pessoa.muitos), icon: "clientes",
    keywords: `${vocab.pessoa.muitos} lista busca base ticket ${vocab.interacao.muitos} listas estrategicas`,
  },
  ...(modulos.campanhas ? [{
    href: "/campanhas", label: "Email", icon: "campanhas" as IconKey,
    keywords: "email campanhas disparo marketing newsletter envio",
  }] : []),
  ...(modulos.avaliacoes ? [{
    href: "/avaliacoes", label: "Avaliações", icon: "rankings" as IconKey,
    keywords: "avaliacoes nps satisfacao estrelas google review nota promotor detrator",
  }] : []),
  // Integrações: o item existe se ao menos uma plataforma estiver ligada.
  ...(integracoesLigadas.length ? [{
    href: "/integracoes", label: "Integrações", icon: "integracoes" as IconKey,
    keywords: "integracoes ifood google meu negocio empresas my business avaliacoes responder review loja unidade",
  }] : []),
  ...(modulos.agente ? [{
    href: "/agente", label: "Agente IA", icon: "agente" as IconKey, beta: true,
    keywords: "agente ia chat assistente",
  }] : []),
  ...(modulos.auditoria ? [{
    href: "/auditoria", label: "Auditoria", icon: "rankings" as IconKey, staffOnly: true,
    keywords: "auditoria log historico alteracoes quem mexeu",
  }] : []),
  {
    href: "/usuarios", label: "Usuários", icon: "usuarios", staffOnly: true,
    keywords: "usuarios equipe acesso convite papel permissao",
  },
];

export const CLIENT_NAME = CLIENTE.nome;
