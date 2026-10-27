"use client";

import { useState } from "react";
import clsx from "clsx";

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

type Step = "rate" | "comment" | "contact" | "done";
type Rota = "google" | "obrigado" | null;

const HINTS = ["", "Que pena", "Precisa melhorar", "Foi ok", "Gostei!", "Amei!"];

export default function Avaliacao({ slug, nome }: { slug: string; nome: string }) {
  const [step, setStep] = useState<Step>("rate");
  const [nota, setNota] = useState(0);
  const [hover, setHover] = useState(0);
  const [comentario, setComentario] = useState("");
  const [nomeCliente, setNomeCliente] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [rota, setRota] = useState<Rota>(null);
  const [googleUrl, setGoogleUrl] = useState<string | null>(null);

  const promotor = nota >= 4;
  const marcadas = hover || nota;

  function escolher(n: number) {
    setNota(n);
    window.setTimeout(() => setStep("comment"), 240);
  }

  async function finalizar(pular: boolean) {
    setEnviando(true);
    try {
      const res = await fetch(`${BASE}/avaliacao/responder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slug,
          nota,
          comentario,
          nome: pular ? "" : nomeCliente,
          whatsapp: pular ? "" : whatsapp,
        }),
      });
      const data = (await res.json()) as { rota?: Rota; google_url?: string | null };
      setRota(data.rota ?? "obrigado");
      setGoogleUrl(data.google_url ?? null);
    } catch {
      setRota("obrigado");
    } finally {
      setEnviando(false);
      setStep("done");
    }
  }

  function reset() {
    setNota(0);
    setHover(0);
    setComentario("");
    setNomeCliente("");
    setWhatsapp("");
    setRota(null);
    setGoogleUrl(null);
    setStep("rate");
  }

  return (
    <main className="flex min-h-[100dvh] items-start justify-center bg-app px-4 py-8 text-ink">
      <div className="w-full max-w-md">
        <div className="mb-4 flex items-center justify-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-domani-orange text-sm font-semibold text-white">
            {nome.trim().charAt(0).toUpperCase()}
          </span>
          <b className="font-display text-[15px] font-semibold">{nome}</b>
        </div>

        <div className="rounded-3xl border border-line bg-surface p-7 shadow-domani-lift">
          {step === "rate" && (
            <section key="rate" className="animate-rise">
              <p className="mb-2.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
                Sua opinião
              </p>
              <h1 className="font-display text-2xl font-semibold leading-snug">
                Como foi sua experiência em{" "}
                <span className="text-domani-orange">{nome}</span>?
              </h1>
              <p className="mt-2 text-[15px] text-muted">Toque nas estrelas. Leva 10 segundos.</p>
              <div className="mt-6 flex justify-center gap-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <button
                    key={i}
                    aria-label={`${i} ${i === 1 ? "estrela" : "estrelas"}`}
                    onClick={() => escolher(i)}
                    onMouseEnter={() => setHover(i)}
                    onMouseLeave={() => setHover(0)}
                    className="p-1 transition-transform active:scale-90"
                  >
                    <Star on={i <= marcadas} />
                  </button>
                ))}
              </div>
              <p className="mt-1 min-h-[20px] text-center text-sm text-muted">
                {HINTS[marcadas] ?? ""}
              </p>
            </section>
          )}

          {step === "comment" && (
            <section key="comment" className="animate-rise">
              <p className="mb-2.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
                {promotor ? "Conte mais" : "O que houve?"}
              </p>
              <h1 className="font-display text-2xl font-semibold leading-snug">
                {promotor ? "O que mais te agradou?" : "Onde a gente errou?"}
              </h1>
              <p className="mt-2 text-[15px] text-muted">
                {promotor ? "Opcional, mas ajuda demais." : "Sua resposta vai direto pro gerente."}
              </p>
              <textarea
                value={comentario}
                onChange={(e) => setComentario(e.target.value)}
                placeholder="Escreva aqui..."
                className="mt-4 min-h-[96px] w-full resize-y rounded-2xl border border-line bg-app p-3.5 text-base outline-none focus:border-domani-orange"
              />
              <button
                onClick={() => setStep("contact")}
                className="mt-5 w-full rounded-2xl bg-domani-orange p-3.5 font-semibold text-white transition hover:brightness-105"
              >
                Continuar
              </button>
            </section>
          )}

          {step === "contact" && (
            <section key="contact" className="animate-rise">
              <p className="mb-2.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
                Quase lá
              </p>
              <h1 className="font-display text-2xl font-semibold leading-snug">
                Quer receber novidades e mimos?
              </h1>
              <p className="mt-2 text-[15px] text-muted">Deixe seu contato — sem spam, prometido.</p>
              <div className="mt-4 space-y-3">
                <div>
                  <label className="mb-1.5 block text-sm font-semibold">Seu nome</label>
                  <input
                    value={nomeCliente}
                    onChange={(e) => setNomeCliente(e.target.value)}
                    placeholder="Como podemos te chamar?"
                    className="w-full rounded-2xl border border-line bg-app p-3 text-base outline-none focus:border-domani-orange"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-semibold">WhatsApp</label>
                  <input
                    value={whatsapp}
                    onChange={(e) => setWhatsapp(e.target.value)}
                    inputMode="numeric"
                    type="tel"
                    placeholder="(00) 00000-0000"
                    className="w-full rounded-2xl border border-line bg-app p-3 text-base outline-none focus:border-domani-orange"
                  />
                </div>
              </div>
              <button
                disabled={enviando}
                onClick={() => finalizar(false)}
                className="mt-5 w-full rounded-2xl bg-domani-orange p-3.5 font-semibold text-white transition hover:brightness-105 disabled:opacity-50"
              >
                {enviando ? "Enviando..." : "Enviar avaliação"}
              </button>
              <button
                disabled={enviando}
                onClick={() => finalizar(true)}
                className="mt-2 w-full p-2.5 text-sm font-medium text-muted disabled:opacity-50"
              >
                Prefiro não informar
              </button>
            </section>
          )}

          {step === "done" && (
            <section key="done" className="animate-rise text-center">
              {rota === "google" ? (
                <>
                  <div className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-full bg-domani-orange/15 text-3xl">
                    ⭐
                  </div>
                  <h1 className="font-display text-2xl font-semibold">Que alegria ter você aqui!</h1>
                  <p className="mt-2 text-[15px] text-muted">
                    Sua opinião vale ouro. Que tal deixar isso registrado no Google? Ajuda muito quem
                    ainda não conhece a gente.
                  </p>
                  {googleUrl && (
                    <a
                      href={googleUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-5 block w-full rounded-2xl bg-domani-orange p-3.5 font-semibold text-white transition hover:brightness-105"
                    >
                      Avaliar no Google
                    </a>
                  )}
                  <button onClick={reset} className="mt-2 w-full p-2.5 text-sm font-medium text-muted">
                    Agora não
                  </button>
                </>
              ) : (
                <>
                  <div className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-full bg-domani-orange/10 text-3xl">
                    🙏
                  </div>
                  <h1 className="font-display text-2xl font-semibold">Obrigado por contar pra gente</h1>
                  <p className="mt-2 text-[15px] text-muted">
                    Sua mensagem já chegou ao gerente e vamos cuidar disso. Queremos muito te ver de volta.
                  </p>
                  <button
                    onClick={reset}
                    className="mt-5 w-full rounded-2xl bg-domani-orange p-3.5 font-semibold text-white transition hover:brightness-105"
                  >
                    Concluir
                  </button>
                </>
              )}
            </section>
          )}
        </div>
      </div>
    </main>
  );
}

function Star({ on }: { on: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      className={clsx("h-11 w-11 transition-colors", on ? "text-domani-orange" : "text-ink/20")}
    >
      <path d="M12 17.3l-5.4 3.3 1.5-6.1L3.3 10l6.3-.5L12 3.7l2.4 5.8 6.3.5-4.8 4.5 1.5 6.1z" />
    </svg>
  );
}
