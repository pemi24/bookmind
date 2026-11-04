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

  const [main, ...others] = info?.addresses ?? [];

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
            <code className="rounded bg-amber-100 px-1 dark:bg-amber-900">start.bat lan</code> (Windows) or{" "}
            <code className="rounded bg-amber-100 px-1 dark:bg-amber-900">./start.sh --lan</code> (macOS/Linux). The address below will then work.
          </p>
        </div>
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
