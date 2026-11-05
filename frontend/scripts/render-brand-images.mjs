// Renders BookMind's PNG icons and the social-sharing (Open Graph) image from the SVG mark,
// using headless Chrome or Edge (no extra packages). Run after changing the brand colours:
//
//   node scripts/render-brand-images.mjs
//
// Writes public/icons/*.png and public/og-image.png. Set CHROME=<path to chrome or msedge> if it
// isn't found automatically.
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ACCENT = "#1f5c46";
const PAPER = "#faf7f0";
const INK = "#1f1d1a";
const MUTED = "#5c574e";

const BROWSERS = [
  process.env.CHROME,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);
const browser = BROWSERS.find((p) => existsSync(p));
if (!browser) {
  console.error("Chrome or Edge not found. Set CHROME to its path.");
  process.exit(1);
}

const glyph = `
  <path d="M7.5 10.2c2.9-1.2 5.8-.9 8.5.9v11.5c-2.7-1.8-5.6-2.1-8.5-.9z" fill="${PAPER}"/>
  <path d="M16 11.1C18.7 9.3 21.6 9 24.5 10.2V25l-3.1-2.9C19.6 21.6 17.7 21.8 16 22.6z" fill="${PAPER}" opacity=".82"/>
  <path d="M10 13.6c1.3-.3 2.6-.1 3.9.5M10 16.4c1.3-.3 2.6-.1 3.9.5" stroke="${ACCENT}" stroke-width="1.1" stroke-linecap="round" fill="none"/>`;
const mark = (size) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="${size}" height="${size}"><rect width="32" height="32" rx="9" fill="${ACCENT}"/>${glyph}</svg>`;
/** The glyph on a full-bleed square (the OS rounds or masks the corners). `inset` = padding fraction. */
const fullBleed = (size, inset) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="${size}" height="${size}"><rect width="32" height="32" fill="${ACCENT}"/>
   <g transform="translate(${16 - 16 * (1 - 2 * inset) * 1.15} ${16 - 16 * (1 - 2 * inset) * 1.15}) scale(${(1 - 2 * inset) * 1.15})">${glyph}</g></svg>`;

const font = (file) => pathToFileURL(join(root, "node_modules/@fontsource-variable", file)).href;
const page = (w, h, body) => `<!doctype html><html><head><meta charset="utf-8"><style>
  @font-face { font-family: "Newsreader"; font-weight: 200 800; src: url("${font("newsreader/files/newsreader-latin-wght-normal.woff2")}") format("woff2"); }
  @font-face { font-family: "Newsreader"; font-style: italic; font-weight: 200 800; src: url("${font("newsreader/files/newsreader-latin-wght-italic.woff2")}") format("woff2"); }
  @font-face { font-family: "Inter"; font-weight: 100 900; src: url("${font("inter/files/inter-latin-wght-normal.woff2")}") format("woff2"); }
  html, body { margin: 0; width: ${w}px; height: ${h}px; overflow: hidden; background: transparent; }
  </style></head><body>${body}</body></html>`;

const og = page(
  1200,
  630,
  `<div style="box-sizing:border-box;width:1200px;height:630px;background:${PAPER};padding:72px 80px;display:flex;gap:56px;align-items:center;font-family:Inter;color:${INK};position:relative;overflow:hidden">
    <div style="position:absolute;right:-160px;top:-120px;width:620px;height:620px;border-radius:50%;background:#e3efe8;filter:blur(30px)"></div>
    <div style="flex:1.1;position:relative">
      <div style="display:flex;align-items:center;gap:14px">${mark(52)}
        <span style="font-family:Newsreader;font-size:40px;font-weight:600;letter-spacing:-0.5px">Book<span style="font-weight:400;font-style:italic">Mind</span></span></div>
      <div style="font-family:Newsreader;font-size:96px;line-height:1;font-weight:500;letter-spacing:-2px;margin-top:56px">Talk to<br>any book.</div>
      <div style="font-size:28px;line-height:1.4;color:${MUTED};margin-top:28px;max-width:520px">Cited answers from your own books. Then listen to them read aloud.</div>
    </div>
    <div style="flex:1;position:relative;background:#fffdf8;border:1px solid #e7e0d2;border-radius:28px;box-shadow:0 30px 60px -30px rgba(31,29,26,.35);padding:28px">
      <div style="margin-left:auto;width:fit-content;max-width:85%;background:${ACCENT};color:${PAPER};border-radius:20px 20px 6px 20px;padding:14px 20px;font-size:22px">Why does Alice follow the White Rabbit?</div>
      <div style="font-size:22px;line-height:1.5;margin-top:22px">Curiosity, mostly. A rabbit with a watch is far too strange to ignore, so she runs after it, burning with curiosity
        <span style="display:inline-block;background:#e3efe8;color:${ACCENT};border-radius:10px;font-size:15px;font-weight:600;padding:1px 8px;vertical-align:3px">1</span></div>
      <div style="margin-top:22px;border:1px solid #e7e0d2;border-radius:16px;padding:14px 16px;font-size:17px;color:${MUTED}"><b style="color:${INK};font-weight:600">Ch. 1 · Down the Rabbit-Hole</b><br>
        <span style="font-family:Newsreader;font-style:italic">and burning with curiosity, she ran across the field after it</span></div>
    </div>
  </div>`,
);

const jobs = [
  { out: "public/og-image.png", w: 1200, h: 630, html: og },
  { out: "public/icons/favicon-64.png", w: 64, h: 64, html: page(64, 64, mark(64)) },
  { out: "public/icons/icon-192.png", w: 192, h: 192, html: page(192, 192, mark(192)) },
  { out: "public/icons/icon-512.png", w: 512, h: 512, html: page(512, 512, mark(512)) },
  { out: "public/icons/apple-touch-icon.png", w: 180, h: 180, html: page(180, 180, fullBleed(180, 0.08)) },
  // maskable: everything inside the central 80% "safe zone"
  { out: "public/icons/icon-maskable-512.png", w: 512, h: 512, html: page(512, 512, fullBleed(512, 0.2)) },
];

const tmp = mkdtempSync(join(tmpdir(), "bookmind-brand-"));
try {
  for (const job of jobs) {
    const htmlFile = join(tmp, "page.html");
    writeFileSync(htmlFile, job.html);
    const out = join(root, job.out);
    execFileSync(
      browser,
      [
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--allow-file-access-from-files",
        "--force-device-scale-factor=1",
        "--default-background-color=00000000",
        "--virtual-time-budget=2000", // let the fonts load
        `--user-data-dir=${join(tmp, "profile")}`,
        `--window-size=${job.w},${job.h}`,
        `--screenshot=${out}`,
        pathToFileURL(htmlFile).href,
      ],
      { stdio: "ignore" },
    );
    console.log(`  ${job.out} (${job.w}×${job.h})`);
  }
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
