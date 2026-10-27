import { CLIENTE } from "@/config/cliente";
import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ThemeProvider, THEME_SCRIPT } from "@/providers/theme";
import { AuthProvider } from "@/providers/auth";

export const metadata: Metadata = {
  title: { default: `CRM Domani.AI · ${CLIENTE.nome}`, template: "%s | CRM Domani.AI" },
  description: `Base de contatos e relacionamento — ${CLIENTE.nome}.`,
  icons: { icon: "/img/favicon.png", apple: "/img/favicon.png" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F5F3EF" },
    { media: "(prefers-color-scheme: dark)", color: "#0E0E10" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className="h-full">
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full bg-app font-sans text-ink antialiased">
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
