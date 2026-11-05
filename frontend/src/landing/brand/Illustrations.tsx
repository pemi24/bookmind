/** Original line illustrations for "How it works". Ink lines, one accent fill, paper highlights:
 * they follow the theme tokens, so they work in light and dark mode. */

const ink = "stroke-ink";
const common = { fill: "none", strokeWidth: 2.2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

/** A book dropping into a tray. */
export function UploadIllustration({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 160 120" className={className} role="img" aria-label="A book being placed into an upload tray">
      <ellipse cx="80" cy="104" rx="56" ry="6" className="fill-paper-sunk" />
      <path d="M30 78h100l-10 22H40z" className={`fill-paper-raised ${ink}`} {...common} fillOpacity={1} />
      <path d="M58 30h40a6 6 0 0 1 6 6v40H58a6 6 0 0 1-6-6V36a6 6 0 0 1 6-6z" className="fill-accent" />
      <path d="M58 30h40a6 6 0 0 1 6 6v40H58a6 6 0 0 1-6-6V36a6 6 0 0 1 6-6z" className={ink} {...common} />
      <path d="M52 70a6 6 0 0 0 6 6h46" className={ink} {...common} />
      <path d="M64 42h28M64 50h20" className="stroke-paper" {...common} />
      <path d="M80 6v14M73 13l7 7 7-7" className="stroke-accent" {...common} />
    </svg>
  );
}

/** A question bubble meeting an answer bubble with a citation chip. */
export function AskIllustration({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 160 120" className={className} role="img" aria-label="A question and an answer with a citation">
      <ellipse cx="80" cy="108" rx="56" ry="6" className="fill-paper-sunk" />
      <rect x="18" y="16" width="78" height="34" rx="14" className={`fill-paper-raised ${ink}`} {...common} fillOpacity={1} />
      <path d="M34 50l-6 12 16-12" className={`fill-paper-raised ${ink}`} {...common} fillOpacity={1} />
      <path d="M32 29h46M32 38h30" className={ink} {...common} />
      <rect x="58" y="58" width="86" height="40" rx="14" className="fill-accent" />
      <path d="M126 98l8 10-2-10" className="fill-accent" />
      <path d="M72 72h40M72 82h24" className="stroke-paper" {...common} />
      <rect x="102" y="76" width="24" height="12" rx="6" className="fill-paper" />
      <path d="M110 82h8" className="stroke-accent" {...common} strokeWidth={2.6} />
    </svg>
  );
}

/** An open book with a lightbulb-like spark and sound waves: summarize, study, listen. */
export function LearnIllustration({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 160 120" className={className} role="img" aria-label="An open book with ideas and sound coming from it">
      <ellipse cx="80" cy="108" rx="56" ry="6" className="fill-paper-sunk" />
      <path d="M80 50c-12-8-26-9-42-4v50c16-5 30-4 42 4z" className={`fill-paper-raised ${ink}`} {...common} fillOpacity={1} />
      <path d="M80 50c12-8 26-9 42-4v50c-16-5-30-4-42 4z" className={`fill-paper-raised ${ink}`} {...common} fillOpacity={1} />
      <path d="M80 50v50" className={ink} {...common} />
      <path d="M48 60c8-2 16-1 24 2M48 70c8-2 16-1 24 2M48 80c8-2 16-1 24 2" className="stroke-ink-muted" {...common} strokeWidth={1.8} />
      <rect x="88" y="60" width="26" height="9" rx="2" className="fill-highlight" />
      <path d="M90 64.5c7-2 14-1.5 22 .5M90 80c7-2 14-1.5 22 .5" className="stroke-ink-muted" {...common} strokeWidth={1.8} />
      <circle cx="80" cy="22" r="10" className="fill-accent" />
      <path d="M80 6v-2M64 14l-2-2M96 14l2-2M80 17v7M76.5 21.5h7" className="stroke-paper" {...common} />
      <path d="M64 14l-2-2M96 14l2-2" className="stroke-accent" {...common} />
      <path d="M130 58c4 4 4 12 0 16M138 52c7 7 7 21 0 28" className="stroke-accent" {...common} />
    </svg>
  );
}
