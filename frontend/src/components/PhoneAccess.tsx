import { Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { NetworkInfo } from "../types";
import { ErrorBox } from "./ui";

/** "Use on your phone" (in Settings): the address (and a QR code) for opening BookMind from another device. */
export default function PhoneAccess() {
  const [info, setInfo] = useState<NetworkInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    api
      .network()
      .then(setInfo)
      .catch((e) => setError(e.message));
  }, []);

  const copy = (url: string) =>
    navigator.clipboard?.writeText(url).then(() => {
      setCopied(url);
      window.setTimeout(() => setCopied(null), 2000);
    });

  const https = info?.https;
  const secure = https?.enabled ? https.addresses : [];
  // With HTTPS on, the secure address is the one to install: phones keep the offline app only there.
  const [main, ...others] = secure.length > 0 ? secure : (info?.addresses ?? []);
  const plain = info?.addresses[0];

  return (
    <div>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!info && !error && <p className="text-sm text-stone-500">Finding this computer's address…</p>}

      {info && !main && <ErrorBox>This computer doesn't seem to be on a network. Connect it to Wi-Fi and try again.</ErrorBox>}

      {info && main && !info.lan_mode && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          <p className="font-medium">One step first: start BookMind in phone mode</p>
          <p className="mt-1">
            Right now only this computer can open BookMind. Close the BookMind windows, then run{" "}
            <code className="rounded bg-amber-100 px-1 dark:bg-amber-900">start.bat lan https</code> (Windows) or{" "}
            <code className="rounded bg-amber-100 px-1 dark:bg-amber-900">./start.sh --lan --https</code> (macOS/Linux). The address below will then work.
          </p>
        </div>
      )}

      {https?.enabled && https.ca_url && (
        <details className="mt-4 rounded-lg border border-stone-200 p-3 text-sm dark:border-stone-700">
          <summary className="cursor-pointer font-medium">First time on this phone? Trust BookMind's certificate (once)</summary>
          <p className="mt-2 text-stone-600 dark:text-stone-300">
            Until the phone trusts it, the secure address shows a warning and can't work offline. On the phone, open:
          </p>
          <div className="mt-2 flex flex-col items-center text-center">
            {https.ca_qr_svg && (
              <div className="rounded-xl bg-white p-2 shadow-sm ring-1 ring-stone-200" dangerouslySetInnerHTML={{ __html: https.ca_qr_svg }} />
            )}
            <button
              onClick={() => copy(https.ca_url!)}
              className="mt-1 flex items-center gap-2 rounded-lg bg-stone-100 px-3 py-1 font-mono text-xs hover:bg-stone-200 dark:bg-stone-800 dark:hover:bg-stone-700"
              title="Copy address"
            >
              {https.ca_url} <Copy size={12} className="text-stone-400" />
            </button>
            {copied === https.ca_url && <span className="mt-1 text-xs text-emerald-600">Copied</span>}
          </div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-stone-600 dark:text-stone-300">
            <li>
              <b>iPhone</b>: open it in Safari → Allow. Then Settings → <i>Profile Downloaded</i> → Install. Then Settings → General → About →
              Certificate Trust Settings → turn on <i>BookMind local CA</i>.
            </li>
            <li>
              <b>Android</b>: download it, then Settings → Security → <i>Encryption &amp; credentials</i> → Install a certificate → CA
              certificate, and pick <i>BookMind-CA.crt</i> (menu names vary by phone).
            </li>
          </ul>
          {https.ca_fingerprint && <p className="mt-2 break-all text-xs text-stone-400">SHA-256 fingerprint: {https.ca_fingerprint}</p>}
        </details>
      )}

      {main && (
        <div className="mt-4 flex flex-col items-center text-center">
          <div className="rounded-xl bg-white p-2 shadow-sm ring-1 ring-stone-200" dangerouslySetInnerHTML={{ __html: main.qr_svg }} />
          <p className="mt-2 text-xs text-stone-500">Scan with the phone's camera, or type the address:</p>
          <button
            onClick={() => copy(main.url)}
            className="mt-1 flex items-center gap-2 rounded-lg bg-stone-100 px-3 py-1.5 font-mono text-base font-semibold hover:bg-stone-200 dark:bg-stone-800 dark:hover:bg-stone-700"
            title="Copy address"
          >
            {main.url} <Copy size={14} className="text-stone-400" />
          </button>
          {copied === main.url && <span className="mt-1 text-xs text-emerald-600">Copied</span>}
          {others.length > 0 && <p className="mt-2 text-xs text-stone-500">If it doesn't load, try: {others.map((a) => a.url).join(" or ")}</p>}
          {secure.length > 0 && plain && (
            <p className="mt-1 text-xs text-stone-500">Without the certificate, {plain.url} works too (but not offline).</p>
          )}
          {info?.lan_mode && !https?.enabled && (
            <p className="mt-2 max-w-sm text-xs text-stone-500">
              To use it offline as an installed app, restart with <code>start.bat lan https</code> (or <code>./start.sh --lan --https</code>)
              for a secure address.
            </p>
          )}
        </div>
      )}

      <ol className="mt-5 list-decimal space-y-1 pl-5 text-sm text-stone-600 dark:text-stone-300">
        <li>Connect the phone to the same Wi-Fi as this computer.</li>
        <li>Open the address in the phone's browser and sign in.</li>
        <li>
          Install it: <b>iPhone</b> (Safari) Share → Add to Home Screen; <b>Android</b> (Chrome) ⋮ → Add to Home screen.
        </li>
      </ol>
      <p className="mt-3 text-xs text-stone-400">
        Only on a network you trust. If the phone can't connect, allow Python through the computer's firewall for private networks.
      </p>
    </div>
  );
}
