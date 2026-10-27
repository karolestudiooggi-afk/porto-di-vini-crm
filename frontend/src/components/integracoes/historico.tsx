"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { LojaIntegracao, Origem } from "@/lib/api-types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/select";
import { Aviso, CAMPO, Carregando, Nota, Vazio, comentarioOu, quando } from "./partes";

const STATUS = [
  { value: "", label: "Todos os desfechos" },
  { value: "enviada", label: "Publicadas" },
  { value: "encaminhada", label: "Aguardando o Google" },
  { value: "erro", label: "Falharam" },
  { value: "ignorada", label: "Ignoradas pelo agente" },
];

const ROTULO: Record<string, string> = {
  enviada: "publicada",
  // Google: entregue ao NichoChat, ainda não confirmada no Google. Vira
  // "publicada" quando o subfluxo do NichoChat avisa que publicou.
  encaminhada: "aguardando o Google",
  erro: "falhou",
  ignorada: "ignorada",
};

/** Tudo o que foi publicado, ignorado ou falhou pelo CRM nesta plataforma. */
export function Historico({ origem, lojas, statusInicial = "" }: {
  origem: Origem;
  lojas: LojaIntegracao[];
  /** Vem do "ver quais" da visão geral, que abre já filtrado nas falhas. */
  statusInicial?: string;
}) {
  const [loja, setLoja] = useState("");
  const [status, setStatus] = useState(statusInicial);
  const q = useApi(
    () => api.integracoes.historico(origem, { loja: loja || undefined, status: status || undefined }),
    [origem, loja, status],
  );

  const opcoesLoja = [
    { value: "", label: origem === "ifood" ? "Todas as lojas" : "Todas as unidades" },
    ...lojas.map((l) => ({ value: l.loja_id, label: l.nome })),
  ];
  // "Ignoradas" só existe onde há agente automático; "aguardando o Google",
  // só no Google.
  const opcoesStatus = STATUS.filter((s) =>
    origem === "ifood" ? s.value !== "encaminhada" : s.value !== "ignorada");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        <div className="w-full sm:w-64">
          <Select aria-label="Loja" value={loja} onChange={setLoja} options={opcoesLoja} triggerClassName={CAMPO} />
        </div>
        <div className="w-full sm:w-56">
          <Select aria-label="Desfecho" value={status} onChange={setStatus} options={opcoesStatus} triggerClassName={CAMPO} />
        </div>
      </div>

      {q.loading && <Carregando />}
      {q.error && <Aviso tipo="erro">{q.error}</Aviso>}

      {q.data && !q.loading && (q.data.length === 0 ? (
        <Vazio titulo="Nada por aqui ainda">
          As respostas publicadas pelo CRM aparecem aqui, com quem publicou e quando.
        </Vazio>
      ) : (
        <ul className="space-y-2.5">
          {q.data.map((h) => (
            <li key={h.review_id} className="rounded-2xl border border-line/12 bg-surface px-5 py-4 shadow-domani-lift">
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                <Nota n={h.nota ?? 0} />
                <span className={h.status === "erro"
                  ? "font-bold text-red-600 dark:text-red-400"
                  : "font-semibold text-ink/70"}>
                  {ROTULO[h.status] ?? h.status}
                </span>
                <span className="font-semibold text-ink/80">{h.loja}</span>
                {h.autor && <span className="text-muted">{h.autor}</span>}
                <span className="ml-auto text-muted [font-variant-numeric:tabular-nums]">
                  {quando(h.atualizado_em)}
                  {h.via === "agente" ? ", agente de IA" : h.usuario ? `, ${h.usuario}` : ""}
                </span>
              </p>
              <p className="mt-2.5 text-sm leading-relaxed text-ink/70 [overflow-wrap:anywhere]">
                {comentarioOu(h.comentario)}
              </p>
              {h.resposta && (
                <p className="mt-2 border-l-2 border-line/15 pl-3 text-sm leading-relaxed text-ink [overflow-wrap:anywhere]">
                  {h.resposta}
                </p>
              )}
              {h.erro && (
                <p className="mt-2 text-xs text-red-600 [overflow-wrap:anywhere] dark:text-red-400">{h.erro}</p>
              )}
            </li>
          ))}
        </ul>
      ))}
    </div>
  );
}
