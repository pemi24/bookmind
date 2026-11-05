import { ArrowRight, ArrowUp, Moon, Quote, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { applyTheme } from "../../utils";
import Logo from "../brand/Logo";
import { closing, faq, footer, testimonials } from "../content";
import { prefersReducedMotion } from "../ui/motion";
import { Accordion, Card, Icon, Reveal, Section } from "../ui/kit";

/* ---------- 10. testimonials (sample content until replaced) ---------- */

export function Testimonials() {
  return (
    <Section id={testimonials.id} title={testimonials.title}>
      <ul className="grid gap-5 md:grid-cols-3">
        {testimonials.items.map((t, i) => (
          <Reveal as="li" key={t.quote} delay={i * 120}>
            <Card className="relative flex h-full flex-col p-7">
              {testimonials.sample && (
                <span className="absolute top-4 right-4 rounded-full border border-dashed border-ink-muted px-2 py-0.5 text-[0.7rem] font-medium tracking-wide text-ink-muted uppercase">
                  Sample
                </span>
              )}
              <Quote size={26} className="text-accent-ink" aria-hidden="true" />
              <blockquote className="mt-4 flex-1 font-display text-xl leading-snug text-ink">“{t.quote}”</blockquote>
              <p className="mt-6 text-sm">
                <span className="block font-medium text-ink">{t.name}</span>
                <span className="text-ink-muted">{t.role}</span>
              </p>
            </Card>
          </Reveal>
        ))}
      </ul>
    </Section>
  );
}

/* ---------- 11. FAQ ---------- */

export function Faq() {
  return (
    <Section id={faq.id} title={faq.title} tone="sunk">
      <Reveal className="mx-auto max-w-3xl">
        <Accordion items={faq.items} />
      </Reveal>
    </Section>
  );
}

/* ---------- 12. closing call to action ---------- */

export function Closing() {
  return (
    <section aria-labelledby="closing-title" className="px-5 py-20 sm:px-8 sm:py-28">
      <Reveal className="mx-auto max-w-5xl overflow-hidden rounded-[2rem] bg-accent px-6 py-16 text-center text-on-accent sm:px-12 sm:py-24">
        <h2 id="closing-title" className="mx-auto max-w-3xl font-display text-[clamp(2.25rem,5.5vw,4rem)] leading-[1.05] font-medium tracking-tight">
          {closing.title}
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-lg opacity-90">{closing.sub}</p>
        <a
          href={closing.cta.href}
          className="mt-9 inline-flex items-center gap-2 rounded-full bg-paper px-7 py-3.5 text-base font-medium text-ink shadow-float transition hover:bg-paper-raised focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-paper"
        >
          {closing.cta.label}
          <ArrowRight size={18} aria-hidden="true" />
        </a>
      </Reveal>
    </section>
  );
}

/* ---------- 13. footer ---------- */

function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    // follow the page itself (the system theme can change it too)
    const html = document.documentElement;
    const obs = new MutationObserver(() => setDark(html.classList.contains("dark")));
    obs.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return (
    <button
      onClick={() => applyTheme(dark ? "light" : "dark")}
      className="inline-flex items-center gap-2 rounded-full border border-line px-3 py-1.5 text-sm text-ink-muted transition hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {dark ? <Sun size={15} aria-hidden="true" /> : <Moon size={15} aria-hidden="true" />}
      {dark ? "Light" : "Dark"}
    </button>
  );
}

export function Footer() {
  return (
    // bottom padding leaves room for the floating back-to-top button
    <footer className="border-t border-line px-5 pt-16 pb-24 sm:px-8">
      <div className="mx-auto grid max-w-6xl gap-12 md:grid-cols-[1.4fr_repeat(3,1fr)]">
        <div>
          <Logo />
          <p className="mt-4 max-w-xs text-ink-muted">{footer.tagline}</p>
          <ul className="mt-6 flex gap-2" aria-label="Elsewhere">
            {footer.social.map((s) => (
              <li key={s.label}>
                <a
                  href={s.href}
                  aria-label={s.label}
                  className="flex h-10 w-10 items-center justify-center rounded-full border border-line text-ink-muted transition hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
                >
                  <Icon name={s.icon} size={17} />
                </a>
              </li>
            ))}
          </ul>
        </div>
        {footer.columns.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <h2 className="text-sm font-semibold text-ink">{col.title}</h2>
            <ul className="mt-4 space-y-3">
              {col.links.map((l) => (
                <li key={l.label}>
                  <a href={l.href} className="text-ink-muted transition hover:text-ink focus-visible:outline-2 focus-visible:outline-accent">
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="mx-auto mt-14 flex max-w-6xl flex-wrap items-center justify-between gap-4 border-t border-line pt-6 text-sm text-ink-muted">
        <p>{footer.copyright}</p>
        <ThemeToggle />
      </div>
    </footer>
  );
}

/* ---------- back to top ---------- */

export function BackToTop() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const on = () => setShow(window.scrollY > window.innerHeight * 1.5);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <button
      onClick={() => {
        window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
        document.querySelector<HTMLElement>("#hero-title")?.focus({ preventScroll: true });
      }}
      aria-label="Back to top"
      tabIndex={show ? 0 : -1}
      aria-hidden={!show}
      className={`fixed right-5 bottom-5 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-line bg-paper-raised text-ink shadow-float transition-all duration-300 focus-visible:outline-2 focus-visible:outline-accent ${
        show ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-3 opacity-0"
      }`}
    >
      <ArrowUp size={19} aria-hidden="true" />
    </button>
  );
}
