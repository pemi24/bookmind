/** BookMind's mark: an open book whose right page ends in a speech-bubble tail (a book you talk to).
 * `onPanel`: cream tile with green pages, for the deep-green panel beside the sign-in forms. */
export function LogoMark({ size = 32, className = "", onPanel = false }: { size?: number; className?: string; onPanel?: boolean }) {
  const tile = onPanel ? "fill-on-panel" : "fill-accent";
  const page = onPanel ? "fill-panel" : "fill-paper";
  const lines = onPanel ? "stroke-on-panel" : "stroke-accent";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <rect width="32" height="32" rx="9" className={tile} />
      <path d="M7.5 10.2c2.9-1.2 5.8-.9 8.5.9v11.5c-2.7-1.8-5.6-2.1-8.5-.9z" className={page} />
      <path d="M16 11.1C18.7 9.3 21.6 9 24.5 10.2V25l-3.1-2.9C19.6 21.6 17.7 21.8 16 22.6z" className={page} opacity=".82" />
      <path d="M10 13.6c1.3-.3 2.6-.1 3.9.5M10 16.4c1.3-.3 2.6-.1 3.9.5" className={lines} strokeWidth="1.1" strokeLinecap="round" fill="none" />
    </svg>
  );
}

/** Mark + wordmark ("Book" upright, "Mind" in italic). */
export default function Logo({ size = 30, className = "", onPanel = false }: { size?: number; className?: string; onPanel?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <LogoMark size={size} onPanel={onPanel} />
      <span className={`font-display text-[1.35rem] leading-none font-semibold tracking-tight ${onPanel ? "text-on-panel" : "text-ink"}`}>
        Book<span className="font-normal italic">Mind</span>
      </span>
    </span>
  );
}
