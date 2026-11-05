/** BookMind's logo: the symbol (a brain rising from an open book, from the original artwork prepared by
 * scripts/prepare-logo.py) with "Book Mind" set beside it in the display serif. Light pages show the
 * symbol in its own purple-to-navy colours; dark mode and the green sign-in panel show a lighter
 * purple-to-lavender version. */

const RATIO = 640 / 354; // width / height of public/brand/symbol-*.png

/** The symbol alone. `size` is its height in pixels; `imgClassName` can size it per screen width
 * instead (e.g. "h-6 w-auto md:h-9"). */
export function LogoMark({
  size = 30,
  className = "",
  imgClassName = "",
  onPanel = false,
}: {
  size?: number;
  className?: string;
  imgClassName?: string;
  onPanel?: boolean;
}) {
  const dims = { height: size, width: Math.round(size * RATIO) };
  if (onPanel) return <img src="/brand/symbol-dark.png" alt="" aria-hidden="true" {...dims} className={`shrink-0 ${imgClassName} ${className}`} />;
  return (
    <span aria-hidden="true" className={`inline-flex shrink-0 ${className}`}>
      <img src="/brand/symbol-light.png" alt="" {...dims} className={`dark:hidden ${imgClassName}`} />
      <img src="/brand/symbol-dark.png" alt="" {...dims} className={`hidden dark:block ${imgClassName}`} />
    </span>
  );
}

/** The symbol with the wordmark beside it ("Book" upright, "Mind" in italic). */
export default function Logo({ size = 30, className = "", onPanel = false }: { size?: number; className?: string; onPanel?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <LogoMark size={size} onPanel={onPanel} />
      <span
        style={{ fontSize: size * 0.8 }}
        className={`font-display leading-none font-semibold tracking-tight ${onPanel ? "text-on-panel" : "text-ink"}`}
      >
        Book<span className="font-normal italic">Mind</span>
      </span>
    </span>
  );
}
