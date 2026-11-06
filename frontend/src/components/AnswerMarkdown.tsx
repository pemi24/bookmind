import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "../types";

/** Turn "[1]" / "[2, 3]" / "[1-3]" / "[Passage 1]" into links the renderer turns into citation chips. */
function linkifyCitations(text: string, max: number): string {
  return text.replace(/\[(?:passages?|sources?)?\s*(\d+(?:\s*[,–-]\s*\d+)*)\](?!\()/gi, (whole, inner: string) => {
    const nums: number[] = [];
    for (const part of inner.split(/\s*,\s*/)) {
      const [a, b] = part.split(/\s*[–-]\s*/).map(Number);
      if (b) for (let i = a; i <= b; i++) nums.push(i);
      else nums.push(a);
    }
    const valid = nums.filter((n) => n >= 1 && n <= max);
    if (!valid.length) return whole;
    return valid.map((n) => `[${n}](#cite-${n})`).join("");
  });
}

/** Remove "[1]" / "[2, 3]" / "[Passage 1]" markers (the same forms linkifyCitations turns into chips). */
export function stripCitations(text: string): string {
  return text.replace(/\s?\[(?:passages?|sources?)?\s*\d+(?:\s*[,–-]\s*\d+)*\](?!\()/gi, "");
}

export default function AnswerMarkdown({
  text,
  sources,
  onCite,
}: {
  text: string;
  sources: Source[];
  onCite: (s: Source) => void;
}) {
  return (
    <div className="prose-answer text-[15px]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            const m = href?.match(/^#cite-(\d+)$/);
            if (m) {
              const src = sources[Number(m[1]) - 1];
              if (!src) return <span>[{children}]</span>;
              const loc = [src.label ?? src.chapter_title, src.page_start ? `p. ${src.page_start}` : null].filter(Boolean).join(" · ");
              return (
                <button
                  type="button"
                  onClick={() => onCite(src)}
                  title={loc}
                  className="mx-0.5 inline-flex h-5 min-w-5 -translate-y-px items-center justify-center rounded-md bg-brand-100 px-1 align-middle text-[11px] font-semibold text-brand-700 transition hover:bg-brand-600 hover:text-white dark:bg-brand-900/60 dark:text-brand-200 dark:hover:bg-brand-500"
                >
                  {children}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" className="text-brand-600 underline dark:text-brand-300">
                {children}
              </a>
            );
          },
        }}
      >
        {linkifyCitations(text, sources.length)}
      </ReactMarkdown>
    </div>
  );
}
