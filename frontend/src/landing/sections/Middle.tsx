import { ArrowRight, Check } from "lucide-react";
import { useId, useState } from "react";
import { AskIllustration, LearnIllustration, UploadIllustration } from "../brand/Illustrations";
import { capabilities, highlights, howItWorks, pillars, showcase, useCases, type Audience } from "../content";
import { FeatureMockup, ResultCard, Window } from "../mockups/Mockups";
import { useInView } from "../ui/motion";
import { Card, Icon, Reveal, Section, Tabs, tabPanelProps } from "../ui/kit";
import { Caret, useTyping } from "../ui/typing";

/* ---------- 4. three numbered pillars ---------- */

export function Pillars() {
  return (
    <section aria-labelledby="pillars-title" className="px-5 pb-20 sm:px-8 sm:pb-28">
      {/* keeps the heading outline h1 → h2 → h3 for screen readers */}
      <h2 id="pillars-title" className="sr-only">
        What BookMind does
      </h2>
      <ol className="mx-auto grid max-w-6xl gap-5 md:grid-cols-3">
        {pillars.map((p, i) => (
          <Reveal as="li" key={p.title} delay={i * 120}>
            <Card className="h-full p-7">
              <div className="flex items-center justify-between">
                <span className="font-display text-sm font-medium text-ink-muted tabular-nums">0{i + 1}</span>
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent-soft text-accent-ink">
                  <Icon name={p.icon} size={22} />
                </span>
              </div>
              <h3 className="mt-10 font-display text-2xl leading-tight font-medium text-ink">{p.title}</h3>
              <p className="mt-3 leading-relaxed text-ink-muted">{p.body}</p>
            </Card>
          </Reveal>
        ))}
      </ol>
    </section>
  );
}

/* ---------- 5. see it in action ---------- */

export function Showcase() {
  const [tab, setTab] = useState<Audience>(showcase.tabs[0].id);
  const prefix = useId();
  const [ref, seen] = useInView<HTMLDivElement>();
  const current = showcase.tabs.find((t) => t.id === tab)!;
  const { typed, done } = useTyping(current.reply, seen, { delay: 450 });
  return (
    <Section id={showcase.id} title={showcase.title} sub={showcase.sub} tone="sunk">
      <div ref={ref} className="mx-auto max-w-3xl">
        <Tabs label="Who it's for" tabs={showcase.tabs} value={tab} onChange={setTab} idPrefix={prefix} className="mx-auto mb-8 w-fit max-w-full" />
        <div
          {...tabPanelProps(prefix, tab)}
          className="rounded-[var(--radius-card)] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
        >
          <Window title={`${current.book.title} · ${current.book.author}`}>
            <div className="space-y-4 p-5 sm:p-6">
              <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm text-on-accent">{current.ask}</div>
              <p className="sr-only">{current.reply}</p>
              <p aria-hidden="true" className="min-h-[3em] text-[0.95rem] leading-relaxed text-ink">
                {typed}
                <Caret show={!done} />
              </p>
              <div className={`transition-all duration-500 ${done ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"}`}>
                <ResultCard result={current.result} />
              </div>
            </div>
          </Window>
        </div>
      </div>
    </Section>
  );
}

/* ---------- 6. feature highlights (alternating rows) ---------- */

export function Highlights() {
  return (
    <Section id={highlights.id} title={highlights.title} sub={highlights.sub}>
      <div className="space-y-24 sm:space-y-32">
        {highlights.rows.map((row, i) => (
          <article id={row.id} key={row.id} className="grid scroll-mt-28 items-center gap-10 md:grid-cols-2 md:gap-16">
            <Reveal className={i % 2 ? "md:order-2" : ""}>
              <FeatureMockup name={row.mockup} />
            </Reveal>
            <Reveal delay={120}>
              <p className="text-sm font-semibold tracking-wide text-accent-ink uppercase">{row.eyebrow}</p>
              <h3 className="mt-3 font-display text-[clamp(1.75rem,3.2vw,2.5rem)] leading-[1.12] font-medium tracking-tight text-ink">{row.title}</h3>
              <p className="mt-4 text-lg leading-relaxed text-ink-muted">{row.body}</p>
              <ul className="mt-6 space-y-2.5">
                {row.bullets.map((b) => (
                  <li key={b} className="flex items-start gap-3 text-ink">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent-ink">
                      <Check size={13} strokeWidth={3} aria-hidden="true" />
                    </span>
                    {b}
                  </li>
                ))}
              </ul>
            </Reveal>
          </article>
        ))}
      </div>
    </Section>
  );
}

/* ---------- 7. how it works ---------- */

const ILLUSTRATIONS = { upload: UploadIllustration, ask: AskIllustration, learn: LearnIllustration };

export function HowItWorks() {
  return (
    <Section id={howItWorks.id} title={howItWorks.title} sub={howItWorks.sub} tone="sunk">
      <ol className="grid gap-10 md:grid-cols-3 md:gap-8">
        {howItWorks.steps.map((s, i) => {
          const Art = ILLUSTRATIONS[s.illustration];
          return (
            <Reveal as="li" key={s.title} delay={i * 140} className="relative text-center">
              <Art className="mx-auto h-36 w-auto" />
              <p className="mx-auto mt-6 flex h-8 w-8 items-center justify-center rounded-full bg-accent font-display text-sm font-semibold text-on-accent">
                {i + 1}
              </p>
              <h3 className="mt-4 font-display text-2xl font-medium text-ink">{s.title}</h3>
              <p className="mx-auto mt-2 max-w-xs leading-relaxed text-ink-muted">{s.body}</p>
              {i < howItWorks.steps.length - 1 && (
                <ArrowRight aria-hidden="true" size={22} className="absolute top-16 -right-6 hidden text-line md:block" />
              )}
            </Reveal>
          );
        })}
      </ol>
    </Section>
  );
}

/* ---------- 8. capabilities grid ---------- */

export function Capabilities() {
  return (
    <Section id={capabilities.id} title={capabilities.title}>
      <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {capabilities.groups.map((g, i) => (
          <Reveal as="li" key={g.title} delay={(i % 3) * 100}>
            <Card className="h-full p-7">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent-soft text-accent-ink">
                <Icon name={g.icon} size={21} />
              </span>
              <h3 className="mt-5 font-display text-xl font-medium text-ink">{g.title}</h3>
              <ul className="mt-3 space-y-2">
                {g.items.map((item) => (
                  <li key={item} className="flex gap-2.5 text-[0.95rem] leading-relaxed text-ink-muted">
                    <span className="mt-2.5 h-1 w-1 shrink-0 rounded-full bg-ink-muted" aria-hidden="true" />
                    {item}
                  </li>
                ))}
              </ul>
            </Card>
          </Reveal>
        ))}
      </ul>
    </Section>
  );
}

/* ---------- 9. use-case gallery ---------- */

export function UseCases() {
  const [filter, setFilter] = useState<"all" | Audience>("all");
  const shown = useCases.cards.filter((c) => filter === "all" || c.audiences.includes(filter));
  return (
    <Section id={useCases.id} title={useCases.title} sub={useCases.sub} tone="sunk">
      <div role="group" aria-label="Filter use cases" className="mb-10 flex flex-wrap justify-center gap-2">
        {useCases.filters.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            aria-pressed={filter === f.id}
            className={`rounded-full border px-4 py-2 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
              filter === f.id ? "border-accent bg-accent text-on-accent" : "border-line bg-paper-raised text-ink-muted hover:text-ink"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      <p className="sr-only" aria-live="polite">
        {shown.length} use cases shown
      </p>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((c) => (
          <li key={c.title}>
            <Card className="flex h-full flex-col p-6 transition hover:-translate-y-0.5 hover:shadow-float">
              <h3 className="font-display text-xl font-medium text-ink">{c.title}</h3>
              <p className="mt-2 flex-1 leading-relaxed text-ink-muted">{c.line}</p>
              <a
                href={useCases.tryHref}
                className="mt-5 inline-flex w-fit items-center gap-1.5 rounded-full text-sm font-medium text-accent-ink hover:underline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
              >
                {useCases.tryLabel}
                <span className="sr-only">: {c.title}</span>
                <ArrowRight size={15} aria-hidden="true" />
              </a>
            </Card>
          </li>
        ))}
      </ul>
    </Section>
  );
}
