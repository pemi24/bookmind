import { ArrowRight, Menu, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { loadPref, savePref } from "../../utils";
import Logo from "../brand/Logo";
import { announcement, hero, heroChat, nav } from "../content";
import { ChatMockup } from "../mockups/Mockups";
import { ButtonLink, Reveal } from "../ui/kit";

/* ---------- 1. announcement bar ---------- */

export function AnnouncementBar() {
  const key = `landing:dismissed:${announcement.id}`;
  const [hidden, setHidden] = useState(() => loadPref(key, false));
  if (hidden) return null;
  return (
    <div className="bg-ink text-paper" role="region" aria-label="What's new">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-5 py-2.5 text-sm sm:px-8">
        <span className="hidden shrink-0 items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs font-semibold text-on-accent sm:inline-flex">
          <Sparkles size={12} aria-hidden="true" /> {announcement.label}
        </span>
        <p className="min-w-0 flex-1">
          <span className="sm:hidden">{announcement.label}: </span>
          {announcement.text}{" "}
          <a href={announcement.link.href} className="font-medium whitespace-nowrap underline underline-offset-4 hover:no-underline">
            {announcement.link.label}
            <ArrowRight size={13} className="ml-0.5 inline" aria-hidden="true" />
          </a>
        </p>
        <button
          onClick={() => {
            savePref(key, true);
            setHidden(true);
          }}
          className="shrink-0 rounded-full p-1 opacity-80 hover:bg-white/10 hover:opacity-100 focus-visible:outline-2 focus-visible:outline-paper"
          aria-label="Dismiss announcement"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

/* ---------- 2. navigation ---------- */

export function NavBar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  // Mobile menu: Escape closes it and returns focus to the button.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    menuRef.current?.querySelector<HTMLElement>("a")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header
      className={`sticky top-0 z-40 transition-[background-color,box-shadow,border-color] duration-300 ${
        scrolled || open ? "border-b border-line bg-paper/90 shadow-card backdrop-blur-md" : "border-b border-transparent"
      }`}
    >
      <nav aria-label="Main" className="mx-auto flex max-w-6xl items-center gap-6 px-5 py-3.5 sm:px-8">
        <a
          href="#top"
          className="rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
          aria-label="BookMind, back to top"
        >
          <Logo size={30} />
        </a>
        <ul className="ml-4 hidden items-center gap-1 lg:flex">
          {nav.links.map((l) => (
            <li key={l.href}>
              <a
                href={l.href}
                className="rounded-full px-3 py-2 text-sm whitespace-nowrap text-ink-muted transition hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
              >
                {l.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="ml-auto hidden items-center gap-2 lg:flex">
          <ButtonLink href={nav.login.href} variant="ghost">
            {nav.login.label}
          </ButtonLink>
          <ButtonLink href={nav.cta.href}>{nav.cta.label}</ButtonLink>
        </div>
        <button
          ref={buttonRef}
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="mobile-menu"
          className="ml-auto rounded-full p-2 text-ink hover:bg-paper-sunk focus-visible:outline-2 focus-visible:outline-accent lg:hidden"
        >
          {open ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
          <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
        </button>
      </nav>
      <div
        ref={menuRef}
        id="mobile-menu"
        hidden={!open}
        className="border-t border-line px-5 pt-2 pb-6 lg:hidden"
        onClick={(e) => (e.target as HTMLElement).closest("a") && setOpen(false)}
      >
        <ul className="flex flex-col">
          {nav.links.map((l) => (
            <li key={l.href}>
              <a
                href={l.href}
                className="block rounded-xl px-3 py-3 text-lg text-ink hover:bg-paper-sunk focus-visible:outline-2 focus-visible:outline-accent"
              >
                {l.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <ButtonLink href={nav.login.href} variant="secondary">
            {nav.login.label}
          </ButtonLink>
          <ButtonLink href={nav.cta.href}>{nav.cta.label}</ButtonLink>
        </div>
      </div>
    </header>
  );
}

/* ---------- 3. hero ---------- */

export function Hero() {
  return (
    <section aria-labelledby="hero-title" className="relative overflow-hidden px-5 pt-14 pb-20 sm:px-8 sm:pt-20 sm:pb-28">
      {/* soft glow behind the mockup */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute top-0 right-[-15%] h-[44rem] w-[44rem] bg-[radial-gradient(closest-side,var(--color-accent-soft),transparent)]"
      />
      <div className="relative mx-auto grid max-w-6xl items-center gap-14 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
        <Reveal>
          <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-line bg-paper-raised px-3 py-1 text-sm text-ink-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
            {hero.eyebrow}
          </p>
          <h1 id="hero-title" className="font-display text-[clamp(2.9rem,7.5vw,5.25rem)] leading-[1.02] font-medium tracking-tight text-ink">
            {hero.headline}
          </h1>
          <p className="mt-6 max-w-xl text-[clamp(1.05rem,1.6vw,1.25rem)] leading-relaxed text-ink-muted">{hero.sub}</p>
          <div className="mt-9 flex flex-wrap gap-3">
            <ButtonLink href={hero.primary.href} size="lg">
              {hero.primary.label}
              <ArrowRight size={18} aria-hidden="true" />
            </ButtonLink>
            <ButtonLink href={hero.secondary.href} size="lg" variant="secondary">
              {hero.secondary.label}
            </ButtonLink>
          </div>
          <p className="mt-5 text-sm text-ink-muted">{hero.note}</p>
        </Reveal>
        <Reveal delay={150} className="float-slow">
          <ChatMockup chat={heroChat} />
        </Reveal>
      </div>
    </section>
  );
}
