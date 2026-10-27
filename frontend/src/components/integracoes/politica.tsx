import { Cartao } from "./partes";

/**
 * Política de Avaliações — o mesmo texto da página `/politica` do painel de
 * origem. É o que a casa (e o iFood, na homologação) pode ler para saber o que
 * as respostas publicadas por aqui fazem e não fazem.
 */
export function Politica() {
  return (
    <Cartao titulo="Política de Avaliações">
      <div className="max-w-[68ch] space-y-5 px-5 py-5 text-[15px] leading-relaxed text-ink/85">
        <p>
          As respostas publicadas por este aplicativo aparecem no perfil público da
          loja no iFood e ficam visíveis para qualquer pessoa. Uma vez enviadas, não
          podem ser editadas nem removidas.
        </p>

        <Bloco titulo="Prazo">
          <p>
            Cada avaliação pode receber resposta durante 5 dias a partir da data em
            que foi criada. Passado esse prazo, ela é publicada sem a resposta da loja.
          </p>
        </Bloco>

        <Bloco titulo="O que as respostas fazem">
          <p>
            As respostas são redigidas com apoio de inteligência artificial a partir
            da nota e do comentário do cliente, e seguem regras fixas: agradecem
            elogios de forma específica, reconhecem problemas relatados e informam que
            o caso será apurado internamente.
          </p>
        </Bloco>

        <Bloco titulo="O que as respostas nunca fazem">
          <ul className="list-disc space-y-1 pl-5">
            <li>Prometer reembolso, cupom, desconto ou qualquer compensação.</li>
            <li>Pedir que o cliente altere ou refaça a avaliação.</li>
            <li>Citar nome de funcionários, endereços, telefones ou links.</li>
            <li>Afirmar fatos sobre o pedido que não estejam no comentário do cliente.</li>
          </ul>
        </Bloco>

        <Bloco titulo="Controle da loja">
          <p>
            A casa define a nota mínima que recebe resposta automática. Avaliações
            abaixo dessa nota ficam na fila para revisão manual antes da publicação.
            Toda resposta enviada fica registrada com data, texto e origem.
          </p>
        </Bloco>

        <Bloco titulo="Dados">
          <p>
            Este aplicativo lê apenas nota, comentário e data das avaliações, além do
            identificador da loja e do pedido. Não coleta telefone, endereço nem
            qualquer dado pessoal de quem avaliou.
          </p>
        </Bloco>
      </div>
    </Cartao>
  );
}

function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="mb-1.5 font-display text-sm font-extrabold tracking-tight text-ink">{titulo}</h4>
      {children}
    </section>
  );
}
