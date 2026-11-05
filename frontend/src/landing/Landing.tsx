/** BookMind's public landing page (signed-out visitors at #/). Copy lives in ./content.ts. */
import "@fontsource-variable/inter";
import "@fontsource-variable/newsreader";
import "@fontsource-variable/newsreader/wght-italic.css";
import { useEffect } from "react";
import { BackToTop, Closing, Faq, Footer, Testimonials } from "./sections/Bottom";
import { Capabilities, Highlights, HowItWorks, Pillars, Showcase, UseCases } from "./sections/Middle";
import { AnnouncementBar, Hero, NavBar } from "./sections/Top";
import { scrollToSection } from "./ui/motion";

// Scroll-reveal hides content only once script has run (see .js .reveal in index.css).
if (typeof document !== "undefined") document.documentElement.classList.add("js");

/** Section anchors (#features…) scroll smoothly; "#/…" links are routes and are left alone. */
export function useAnchorScrolling() {
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement).closest<HTMLAnchorElement>("a[href^='#']");
      const href = a?.getAttribute("href");
      if (!href || href.startsWith("#/") || href === "#") return;
      e.preventDefault();
      if (href === "#top") {
        window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        return;
      }
      scrollToSection(href.slice(1));
    };
    document.addEventListener("click", onClick);
    // Opened at a section (#faq): go there once the page has laid out.
    const start = window.location.hash;
    if (start && !start.startsWith("#/") && start.length > 1) requestAnimationFrame(() => scrollToSection(start.slice(1)));
    return () => document.removeEventListener("click", onClick);
  }, []);
}

export default function Landing() {
  useAnchorScrolling();
  useEffect(() => {
    const previous = document.title;
    document.title = "BookMind · Talk to any book";
    return () => {
      document.title = previous;
    };
  }, []);

  return (
    <div id="top" className="landing min-h-full">
      <a href="#main" className="sr-only z-50 rounded-full bg-accent px-4 py-2 text-on-accent focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
        Skip to content
      </a>
      <AnnouncementBar />
      <NavBar />
      <main id="main">
        <Hero />
        <Pillars />
        <Showcase />
        <Highlights />
        <HowItWorks />
        <Capabilities />
        <UseCases />
        <Testimonials />
        <Faq />
        <Closing />
      </main>
      <Footer />
      <BackToTop />
    </div>
  );
}
