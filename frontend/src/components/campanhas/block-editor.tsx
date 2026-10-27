"use client";

import { useRef } from "react";
import EmailEditor from "react-email-editor";

import { api, isApiConfigured } from "@/lib/api";
import { useTheme } from "@/providers/theme";

export interface BlockEditorApi {
  exportHtml: () => Promise<{ html: string; design: unknown }>;
  loadDesign: (design: unknown) => void;
}

interface Props {
  initialDesign?: unknown | null;
  onReady?: (api: BlockEditorApi) => void;
  /** Muda as variáveis oferecidas: parceiro tem {{empresa}}, não tem canal. */
  lista?: "clientes" | "parceiros";
}

/**
 * Editor visual de e-mail por blocos (Unlayer).
 *
 * Existe para a equipe montar campanha sem escrever HTML — que era a única opção
 * antes e, na prática, significava depender de alguém técnico para cada envio.
 *
 * O upload de imagem vai para o Storage do Supabase via POST /email/uploads e usa
 * a URL pública. Sem API configurada (modo demo) cai num data URL local, para o
 * editor continuar utilizável.
 *
 * SEMPRE carregar com dynamic(() => import(...), { ssr: false }): o Unlayer toca
 * em `window` na importação e quebra a renderização no servidor.
 */
export default function BlockEditor({ initialDesign, onReady, lista = "clientes" }: Props) {
  const ref = useRef<any>(null);
  const { theme } = useTheme();

  function handleReady() {
    const unlayer = ref.current?.editor;
    if (!unlayer) return;

    if (initialDesign) {
      try { unlayer.loadDesign(initialDesign); } catch { /* design inválido: começa em branco */ }
    }

    unlayer.registerCallback(
      "image",
      async (
        file: { attachments: File[] },
        done: (a: { progress: number; url?: string }) => void,
      ) => {
        const f = file.attachments[0];
        if (isApiConfigured) {
          try {
            const { url } = await api.email.upload(f);
            done({ progress: 100, url });
            return;
          } catch {
            // upload falhou — cai no data URL abaixo para não travar o editor
          }
        }
        const reader = new FileReader();
        reader.onload = () => done({ progress: 100, url: String(reader.result) });
        reader.onerror = () => done({ progress: 0 });
        reader.readAsDataURL(f);
      },
    );

    onReady?.({
      exportHtml: () =>
        new Promise((resolve) => {
          unlayer.exportHtml((d: { html: string; design: unknown }) =>
            resolve({ html: d.html, design: d.design }));
        }),
      loadDesign: (design: unknown) => {
        try { unlayer.loadDesign(design); } catch { /* ignora */ }
      },
    });
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-line/15">
      <EmailEditor
        ref={ref}
        onReady={handleReady}
        minHeight={560}
        options={{
          locale: "pt-BR",
          appearance: { theme: theme === "dark" ? "modern_dark" : "modern_light" },
          // Variáveis que a equipe pode inserir clicando, sem decorar sintaxe.
          // Precisa bater com services/render.py::variaveis_de — variável que não
          // existe lá vira string vazia no e-mail enviado.
          mergeTags: lista === "parceiros"
            ? {
                primeiro_nome: { name: "Primeiro nome do contato", value: "{{primeiro_nome}}" },
                nome: { name: "Nome do contato", value: "{{nome}}" },
                empresa: { name: "Empresa", value: "{{empresa}}" },
              }
            : {
                primeiro_nome: { name: "Primeiro nome", value: "{{primeiro_nome}}" },
                nome: { name: "Nome completo", value: "{{nome}}" },
                canal: { name: "Canal", value: "{{canal}}" },
                origem: { name: "Origem", value: "{{origem}}" },
              },
        }}
      />
    </div>
  );
}
