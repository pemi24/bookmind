/** Placeholder Privacy and Terms pages (#/privacy, #/terms). Text lives in content.ts → legal. */
import "@fontsource-variable/inter";
import "@fontsource-variable/newsreader";
import "@fontsource-variable/newsreader/wght-italic.css";
import { ArrowLeft, Info } from "lucide-react";
import { useEffect } from "react";
import Logo from "../brand/Logo";
import { legal } from "../content";
import { Footer } from "../sections/Bottom";
import { ButtonLink } from "../ui/kit";

export default function LegalPage({ page }: { page: "privacy" | "terms" }) {
  const doc = legal[page];
  useEffect(() => {
    window.scrollTo(0, 0);
    const previous = document.title;
    document.title = `${doc.title} · BookMind`;
    return () => {
      document.title = previous;
    };
  }, [doc.title]);

  return (
    <div className="landing min-h-full">
      <header className="border-b border-line">
        <nav aria-label="Main" className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5 sm:px-8">
          <a href="#/" aria-label="BookMind home" className="rounded-lg focus-visible:outline-2 focus-visible:outline-accent">
            <Logo size={30} />
          </a>
          <ButtonLink href="#/signup">Get started free</ButtonLink>
        </nav>
      </header>
      <main className="px-5 py-16 sm:px-8 sm:py-24">
        <article className="mx-auto max-w-2xl">
          <a href="#/" className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink">
            <ArrowLeft size={15} aria-hidden="true" /> Back to home
          </a>
          <h1 className="mt-6 font-display text-[clamp(2.5rem,6vw,3.75rem)] leading-tight font-medium tracking-tight text-ink">{doc.title}</h1>
          <p className="mt-2 text-ink-muted">Last updated {doc.updated}</p>
          <p role="note" className="mt-8 flex gap-2.5 rounded-xl border border-dashed border-ink-muted bg-paper-sunk px-4 py-3 text-sm text-ink">
            <Info size={17} className="mt-0.5 shrink-0" aria-hidden="true" />
            {legal.placeholderNote}
          </p>
          {doc.sections.map((s) => (
            <section key={s.heading} className="mt-10">
              <h2 className="font-display text-2xl font-medium text-ink">{s.heading}</h2>
              <p className="mt-3 text-lg leading-relaxed text-ink-muted">{s.body}</p>
            </section>
          ))}
        </article>
      </main>
      <Footer />
    </div>
  );
}
