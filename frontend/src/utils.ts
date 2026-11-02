export function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** Deterministic two-colour gradient for a generated book cover. */
export function coverGradient(seed: string): string {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const a = h % 360;
  const b = (a + 40 + (h % 60)) % 360;
  return `linear-gradient(145deg, hsl(${a} 55% 42%), hsl(${b} 60% 28%))`;
}

export function isIndexing(status: string): boolean {
  return status === "pending" || status === "processing";
}

/** Persist small per-browser UI preferences; storage may be unavailable. */
export function loadPref<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : (JSON.parse(v) as T);
  } catch {
    return fallback;
  }
}

export function savePref(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable */
  }
}

/**
 * Find `needle` in `haystack` ignoring case, whitespace runs and quote/dash styles.
 * Returns [start, end) offsets into the original haystack, or null. Mirrors the
 * backend's find_verbatim so saved highlights map back to exact chapter offsets.
 */
export function findLoose(haystack: string, needle: string, near = 0): [number, number] | null {
  const norm = (s: string) => {
    const map: number[] = [];
    let out = "";
    let space = false;
    for (let i = 0; i < s.length; i++) {
      let ch = s[i];
      if (/\s/.test(ch)) {
        if (space || !out) continue;
        ch = " ";
        space = true;
      } else {
        space = false;
        ch = ch.replace(/[“”„]/, '"').replace(/[‘’‚]/, "'").replace(/[–—]/, "-").toLowerCase();
      }
      out += ch;
      map.push(i);
    }
    return { out, map };
  };
  const h = norm(haystack);
  const n = norm(needle).out.trim();
  if (n.length < 2) return null;
  // Prefer the occurrence closest to `near` (the selection may repeat in the chapter).
  let best = -1;
  for (let pos = h.out.indexOf(n); pos !== -1; pos = h.out.indexOf(n, pos + 1)) {
    if (best === -1 || Math.abs(h.map[pos] - near) < Math.abs(h.map[best] - near)) best = pos;
  }
  if (best === -1) return null;
  return [h.map[best], h.map[best + n.length - 1] + 1];
}
