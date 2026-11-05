import { Fragment, useEffect, useState } from "react";
import { useReducedMotion } from "./motion";

/** Reveals `text` a few characters at a time once `start` is true; all at once with reduced motion. */
export function useTyping(text: string, start: boolean, { cps = 55, delay = 300 }: { cps?: number; delay?: number } = {}) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(0);
  useEffect(() => {
    setShown(0);
  }, [text]);
  useEffect(() => {
    if (!start) return;
    if (reduced) return setShown(text.length);
    let n = 0;
    let timer = 0;
    const tick = () => {
      // a word at a time feels more like a model streaming than single letters
      const next = text.indexOf(" ", n + 1);
      const end = next === -1 ? text.length : next;
      const wordLength = end - n;
      n = end;
      setShown(n);
      if (n < text.length) timer = window.setTimeout(tick, (wordLength * 1000) / cps);
    };
    timer = window.setTimeout(tick, delay);
    return () => window.clearTimeout(timer);
  }, [text, start, reduced, cps, delay]);
  return { typed: text.slice(0, shown), done: shown >= text.length };
}

/** Text with [n] markers turned into small citation chips (like the real app's). */
export function WithCitations({ text }: { text: string }) {
  const parts = text.split(/(\[\d+\])/);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d+)\]$/);
        return m ? (
          <sup
            key={i}
            className="mx-0.5 inline-flex h-4 min-w-4 -translate-y-px items-center justify-center rounded-full bg-accent-soft px-1 font-body text-[0.65rem] leading-none font-semibold text-accent-ink not-italic"
          >
            {m[1]}
          </sup>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        );
      })}
    </>
  );
}

/** A blinking caret while text is still being typed. */
export function Caret({ show }: { show: boolean }) {
  return show ? <span aria-hidden="true" className="caret ml-0.5 inline-block h-[1.05em] w-[2px] translate-y-[3px] bg-accent" /> : null;
}
