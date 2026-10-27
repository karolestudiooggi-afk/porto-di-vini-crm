/**
 * Ponte entre a tela de Contatos e a de campanha.
 *
 * O fluxo que isto viabiliza é o principal do módulo: importar uma planilha,
 * marcar quem deve receber e disparar — sem precisar montar filtro que descreva
 * exatamente aquele grupo.
 *
 * Usa `sessionStorage` porque a seleção é de uso imediato: vale para a aba
 * aberta, some ao fechar. Guardar no servidor exigiria uma tabela de rascunho
 * para algo que dura dois cliques.
 */

const CHAVE = "campanha:selecao";

export interface SelecaoManual {
  ids: number[];
  nomes: string[];
}

export function guardarSelecao(sel: SelecaoManual): void {
  try {
    sessionStorage.setItem(CHAVE, JSON.stringify(sel));
  } catch {
    /* modo privado do navegador pode bloquear — a tela segue sem a seleção */
  }
}

export function lerSelecao(): SelecaoManual | null {
  try {
    const cru = sessionStorage.getItem(CHAVE);
    if (!cru) return null;
    const s = JSON.parse(cru) as SelecaoManual;
    return s.ids?.length ? s : null;
  } catch {
    return null;
  }
}

export function limparSelecao(): void {
  try {
    sessionStorage.removeItem(CHAVE);
  } catch {
    /* idem */
  }
}
