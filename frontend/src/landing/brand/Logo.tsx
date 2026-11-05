/** BookMind's mark: an open book whose right page ends in a speech-bubble tail (a book you talk to). */
export function LogoMark({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <rect width="32" height="32" rx="9" className="fill-accent" />
      <path d="M7.5 10.2c2.9-1.2 5.8-.9 8.5.9v11.5c-2.7-1.8-5.6-2.1-8.5-.9z" className="fill-paper" />
      <path d="M16 11.1C18.7 9.3 21.6 9 24.5 10.2V25l-3.1-2.9C19.6 21.6 17.7 21.8 16 22.6z" className="fill-paper" opacity=".82" />
      <path
        d="M10 13.6c1.3-.3 2.6-.1 3.9.5M10 16.4c1.3-.3 2.6-.1 3.9.5"
        className="stroke-accent"
        strokeWidth="1.1"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

/** Mark + wordmark ("Book" upright, "Mind" in italic). */
export default function Logo({ size = 30, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <LogoMark size={size} />
      <span className="font-display text-[1.35rem] leading-none font-semibold tracking-tight text-ink">
        Book<span className="font-normal italic">Mind</span>
      </span>
    </span>
  );
}
