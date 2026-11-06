import { Download, Laptop, Monitor, Moon, Smartphone, Sun } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { account, type AiOptions, type DeviceSession } from "../api";
import type { Theme, User } from "../types";
import { applyTheme } from "../utils";
import { resolveVoice, useVoiceCatalog, voicePrefs, type VoicePrefs } from "../audio/voices";
import PhoneAccess from "./PhoneAccess";
import { AudioSlider, formatPercent, formatSpeed, PreviewButton, VoiceSelect } from "./VoicePicker";
import { Button, buttonClasses, ErrorBox } from "./ui";

const input =
  "w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-stone-700 dark:bg-stone-900";

function Section({ title, description, children, danger }: { title: string; description?: string; children: ReactNode; danger?: boolean }) {
  return (
    <section
      className={`rounded-xl border bg-white p-5 dark:bg-stone-900 ${danger ? "border-red-200 dark:border-red-900/60" : "border-stone-200 dark:border-stone-800"}`}
    >
      <h2 className={`font-semibold ${danger ? "text-red-700 dark:text-red-400" : ""}`}>{title}</h2>
      {description && <p className="mt-0.5 text-sm text-stone-500">{description}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-stone-500">{hint}</span>}
    </label>
  );
}

/** Busy / error / success state for one form. */
function useSave() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const run = (fn: () => Promise<string | void>) => async (e?: FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const msg = await fn();
      if (msg) setDone(msg);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const status = (
    <>
      {error && <div className="mt-3"><ErrorBox>{error}</ErrorBox></div>}
      {done && <p role="status" className="mt-3 text-sm text-emerald-700 dark:text-emerald-400">{done}</p>}
    </>
  );
  return { busy, run, status };
}

function Profile({ user, onUser }: { user: User; onUser: (u: User) => void }) {
  const [name, setName] = useState(user.display_name);
  const s = useSave();
  return (
    <Section title="Profile">
      <form onSubmit={s.run(async () => (onUser((await account.updateProfile(name)).user), "Saved."))} className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1 basis-60">
          <Field label="Name">
            <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} className={input} />
          </Field>
        </div>
        <Button variant="primary" loading={s.busy} disabled={name.trim() === user.display_name}>
          Save
        </Button>
      </form>
      {s.status}
    </Section>
  );
}

function Email({ user, onUser }: { user: User; onUser: (u: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const s = useSave();
  return (
    <Section title="Email" description={`You sign in with ${user.email}.`}>
      <form
        onSubmit={s.run(async () => {
          const r = await account.changeEmail(email, password);
          onUser(r.user);
          setEmail("");
          setPassword("");
          return r.user.email_verified ? `Your email is now ${r.user.email}.` : `Check ${r.user.email} for a link to confirm it.`;
        })}
        className="grid gap-3 sm:grid-cols-2"
      >
        <Field label="New email">
          <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={input} />
        </Field>
        <Field label="Current password">
          <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={input} />
        </Field>
        <div className="sm:col-span-2">
          <Button variant="primary" loading={s.busy}>
            Change email
          </Button>
        </div>
      </form>
      {s.status}
    </Section>
  );
}

function Password({ onChanged }: { onChanged: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const s = useSave();
  return (
    <Section title="Password" description="Changing it signs you out on every other device.">
      <form
        onSubmit={s.run(async () => {
          if (next !== confirm) throw new Error("The two new passwords don't match.");
          await account.changePassword(current, next);
          setCurrent("");
          setNext("");
          setConfirm("");
          onChanged();
          return "Password changed. Other devices have been signed out.";
        })}
        className="grid gap-3 sm:grid-cols-3"
      >
        <Field label="Current password">
          <input type="password" required autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} className={input} />
        </Field>
        <Field label="New password">
          <input type="password" required autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} className={input} />
        </Field>
        <Field label="Confirm new password">
          <input type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={input} />
        </Field>
        <div className="sm:col-span-3">
          <Button variant="primary" loading={s.busy}>
            Change password
          </Button>
        </div>
      </form>
      {s.status}
    </Section>
  );
}

function Appearance({ user, onUser }: { user: User; onUser: (u: User) => void }) {
  const [theme, setTheme] = useState<Theme>(user.settings.theme ?? "system");
  const s = useSave();
  const choose = (t: Theme) => {
    setTheme(t);
    applyTheme(t);
    s.run(async () => onUser((await account.updatePreferences({ theme: t })).user))();
  };
  return (
    <Section title="Appearance" description="Saved to your account, so it follows you to other devices.">
      <div className="flex flex-wrap gap-2">
        {([
          ["system", "Same as device", Monitor],
          ["light", "Light", Sun],
          ["dark", "Dark", Moon],
        ] as const).map(([value, label, Icon]) => (
          <button
            key={value}
            onClick={() => choose(value)}
            aria-pressed={theme === value}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
              theme === value
                ? "border-brand-500 bg-brand-50 font-medium text-brand-800 dark:bg-brand-900/30 dark:text-brand-200"
                : "border-stone-300 hover:bg-stone-50 dark:border-stone-700 dark:hover:bg-stone-800"
            }`}
          >
            <Icon size={16} /> {label}
          </button>
        ))}
      </div>
      {s.status}
    </Section>
  );
}

const PROVIDER_NAMES: Record<string, string> = {
  gemini: "Google Gemini",
  groq: "Groq",
  openrouter: "OpenRouter",
  anthropic: "Anthropic Claude",
  ollama: "Ollama (on this computer)",
};

function AiModel({ user, onUser }: { user: User; onUser: (u: User) => void }) {
  const [options, setOptions] = useState<AiOptions | null>(null);
  const [provider, setProvider] = useState(user.settings.llm_provider ?? "");
  const [model, setModel] = useState(user.settings.llm_model ?? "");
  const s = useSave();
  useEffect(() => {
    account.aiOptions().then(setOptions).catch(() => {});
  }, []);
  const chosen = options?.providers.find((p) => p.name === provider);
  const serverDefault = options ? `${PROVIDER_NAMES[options.server_default.name] ?? options.server_default.name}${options.server_default.model ? ` · ${options.server_default.model}` : ""}` : "";
  const changed = provider !== (user.settings.llm_provider ?? "") || model !== (user.settings.llm_model ?? "");
  return (
    <Section
      title="AI model"
      description="Which AI answers your questions. If it's busy or out of free quota, BookMind falls back to the server's backups."
    >
      <form
        onSubmit={s.run(async () => {
          onUser((await account.updatePreferences({ llm_provider: provider, llm_model: provider ? model : "" })).user);
          return "Saved. New questions will use this model.";
        })}
        className="grid gap-3 sm:grid-cols-2"
      >
        <Field label="Provider">
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              setModel("");
            }}
            className={input}
          >
            <option value="">Server default{serverDefault ? ` (${serverDefault})` : ""}</option>
            {options?.providers.map((p) => (
              <option key={p.name} value={p.name} disabled={!p.available && p.name !== provider}>
                {PROVIDER_NAMES[p.name] ?? p.name}
                {p.available ? "" : " (not running)"}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Model" hint={provider ? "Leave empty for the provider's recommended model." : "Pick a provider to choose a model."}>
          <input
            value={model}
            disabled={!provider}
            onChange={(e) => setModel(e.target.value)}
            placeholder={chosen?.default_model ?? ""}
            maxLength={120}
            className={`${input} disabled:opacity-50`}
          />
        </Field>
        <div className="sm:col-span-2">
          <Button variant="primary" loading={s.busy} disabled={!changed}>
            Save
          </Button>
        </div>
      </form>
      {s.status}
    </Section>
  );
}

function Listening({ user, onUser }: { user: User; onUser: (u: User) => void }) {
  const catalog = useVoiceCatalog();
  const saved = voicePrefs(user);
  const [prefs, setPrefs] = useState(saved);
  const set = (change: Partial<VoicePrefs>) => setPrefs((p) => ({ ...p, ...change }));
  const s = useSave();
  const chat = resolveVoice(catalog, prefs.chatVoice);
  const read = resolveVoice(catalog, prefs.readVoice);
  const sound = { rate: prefs.speed, pitch: prefs.pitch, volume: prefs.volume };
  const browserChosen = [chat, read].some((v) => v.id.startsWith("browser:"));
  const changed = (Object.keys(prefs) as (keyof VoicePrefs)[]).some((k) => prefs[k] !== saved[k]);
  const unavailable = catalog.providers.filter((p) => !p.available && !p.client_side);

  const voiceField = (label: string, key: "chatVoice" | "readVoice", resolved: typeof chat) => (
    <div>
      <label htmlFor={`voice-${key}`} className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
        {label}
      </label>
      <div className="flex flex-wrap items-start gap-2">
        <VoiceSelect id={`voice-${key}`} catalog={catalog} value={prefs[key]} onChange={(v) => set({ [key]: v })} className="flex-1 basis-60" />
        <PreviewButton catalog={catalog} voiceId={resolved.id} sound={sound} />
      </div>
      {resolved.notice && <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{resolved.notice}</p>}
    </div>
  );

  return (
    <Section title="Listening" description="The voices that read chat replies and books aloud. Saved to your account, so they follow you to other devices.">
      <form
        onSubmit={s.run(async () => {
          onUser(
            (
              await account.updatePreferences({
                tts_chat_voice: prefs.chatVoice,
                tts_read_voice: prefs.readVoice,
                tts_speed: prefs.speed,
                tts_pitch: prefs.pitch,
                tts_volume: prefs.volume,
                tts_auto_read: prefs.autoRead,
                tts_announce_verses: prefs.announceVerses ? "every" : "off",
                tts_announce_chapter: prefs.announceChapter,
              })
            ).user,
          );
          return "Saved.";
        })}
        className="space-y-4"
      >
        {catalog.error && <ErrorBox>Couldn't load this server's voices ({catalog.error}). This device's own voices still work.</ErrorBox>}
        {voiceField("Voice for chat replies", "chatVoice", chat)}
        {voiceField("Voice for reading books", "readVoice", read)}
        <div className="grid gap-4 sm:grid-cols-3">
          <AudioSlider label="Speed" value={prefs.speed} onChange={(speed) => set({ speed })} min={0.5} max={2} step={0.05} format={formatSpeed} />
          <AudioSlider
            label="Pitch"
            value={prefs.pitch}
            onChange={(pitch) => set({ pitch })}
            min={0.5}
            max={2}
            step={0.05}
            format={formatSpeed}
            disabled={!browserChosen}
            hint="Device voices only."
          />
          <AudioSlider label="Volume" value={prefs.volume} onChange={(volume) => set({ volume })} min={0} max={1} step={0.05} format={formatPercent} />
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={prefs.autoRead} onChange={(e) => set({ autoRead: e.target.checked })} className="mt-0.5 accent-brand-600" />
          <span>
            Read new chat replies aloud automatically
            <span className="block text-xs text-stone-500">Each answer starts playing as soon as its first sentence is ready.</span>
          </span>
        </label>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-stone-700 dark:text-stone-300">Books with chapters and verses</legend>
          <p className="text-xs text-stone-500">The Bible, the Quran and other books numbered by verse. The numbers are never read out as “one colon four”.</p>
          <label className="flex flex-wrap items-center gap-2 text-sm">
            <span>Announce verse numbers</span>
            <select
              value={prefs.announceVerses ? "every" : "off"}
              onChange={(e) => set({ announceVerses: e.target.value === "every" })}
              className="rounded-md border border-stone-300 bg-transparent px-2 py-1 text-sm dark:border-stone-700 dark:bg-stone-900"
            >
              <option value="every">Every verse (“Verse 1”, then the verse)</option>
              <option value="off">Off (just the text)</option>
            </select>
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={prefs.announceChapter} onChange={(e) => set({ announceChapter: e.target.checked })} className="mt-0.5 accent-brand-600" />
            <span>
              Announce each chapter
              <span className="block text-xs text-stone-500">“Genesis, chapter 1”, once when the chapter starts.</span>
            </span>
          </label>
        </fieldset>
        {unavailable.length > 0 && (
          <ul className="space-y-0.5 text-xs text-stone-500">
            {unavailable.map((p) => (
              <li key={p.id}>
                {p.label}: {p.reason}
              </li>
            ))}
          </ul>
        )}
        <Button variant="primary" loading={s.busy} disabled={!changed}>
          Save
        </Button>
      </form>
      {s.status}
    </Section>
  );
}

function deviceName(ua: string | null): { label: string; phone: boolean } {
  if (!ua) return { label: "Unknown device", phone: false };
  const browser = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /iPhone|iPad/.test(ua) ? "iPhone/iPad" : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows" : /Mac OS X/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : "";
  return { label: os ? `${browser} on ${os}` : browser, phone: /iPhone|Android|Mobile/.test(ua) };
}

function when(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return "Active now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function Devices({ refreshKey, onSignOutEverywhere }: { refreshKey: number; onSignOutEverywhere: () => void }) {
  const [devices, setDevices] = useState<DeviceSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => account.sessions().then(setDevices).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, [refreshKey]);
  const end = async (id: number) => {
    try {
      await account.endSession(id);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <Section title="Signed-in devices" description="Browsers and phones where you're signed in to BookMind.">
      {error && <ErrorBox>{error}</ErrorBox>}
      <ul className="divide-y divide-stone-100 dark:divide-stone-800">
        {devices?.map((d) => {
          const { label, phone } = deviceName(d.user_agent);
          return (
            <li key={d.id} className="flex items-center gap-3 py-2.5">
              {phone ? <Smartphone size={18} className="shrink-0 text-stone-400" /> : <Laptop size={18} className="shrink-0 text-stone-400" />}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">
                  {label} {d.current && <span className="ml-1 rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-normal text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">This device</span>}
                </p>
                <p className="truncate text-xs text-stone-500">
                  {d.current ? "Active now" : when(d.last_seen_at)}
                  {d.ip ? ` · ${d.ip}` : ""}
                </p>
              </div>
              {!d.current && (
                <Button variant="ghost" onClick={() => end(d.id)}>
                  Sign out
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <Button className="mt-3" onClick={() => confirm("Sign out of BookMind on every device, including this one?") && onSignOutEverywhere()}>
        Sign out everywhere
      </Button>
    </Section>
  );
}

function DeleteAccount({ user, onDeleted }: { user: User; onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [sure, setSure] = useState(false);
  const s = useSave();
  return (
    <Section title="Delete account" description="Permanently deletes your account with all its books, chats, notes, quizzes and flashcards." danger>
      {!open ? (
        <Button variant="danger" className="border border-red-300 dark:border-red-900" onClick={() => setOpen(true)}>
          Delete my account…
        </Button>
      ) : (
        <form onSubmit={s.run(async () => (await account.deleteAccount(password), onDeleted()))} className="space-y-3">
          <p className="text-sm text-stone-600 dark:text-stone-300">
            This can't be undone. Download your data first if you want to keep anything.
          </p>
          <Field label={`Password for ${user.email}`}>
            <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={`${input} sm:max-w-sm`} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} className="accent-red-600" />
            I understand everything in this account will be deleted.
          </label>
          <div className="flex gap-2">
            <Button type="submit" variant="destructive" loading={s.busy} disabled={!sure || !password}>
              Delete account permanently
            </Button>
            <Button type="button" variant="ghost" onClick={() => (setOpen(false), setPassword(""), setSure(false))}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {s.status}
    </Section>
  );
}

export default function SettingsPage({
  user,
  onUser,
  onSignOut,
}: {
  user: User;
  onUser: (u: User) => void;
  onSignOut: (everywhere?: boolean) => void;
}) {
  const [devicesKey, setDevicesKey] = useState(0);
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-5 px-4 py-6 sm:px-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="text-sm text-stone-500">Your account, preferences and data.</p>
        </div>
        <Profile user={user} onUser={onUser} />
        <Appearance user={user} onUser={onUser} />
        <AiModel user={user} onUser={onUser} />
        <Listening user={user} onUser={onUser} />
        <Email user={user} onUser={onUser} />
        <Password onChanged={() => setDevicesKey((k) => k + 1)} />
        <Devices refreshKey={devicesKey} onSignOutEverywhere={() => onSignOut(true)} />
        <Section title="Use on your phone" description="BookMind keeps running on this computer; your phone opens it over the same Wi-Fi.">
          <PhoneAccess />
        </Section>
        <Section title="Your data" description="A zip with your book files, notes, highlights, chats (with their sources), quizzes and flashcards.">
          <a href={account.exportUrl} download className={buttonClasses("secondary")}>
            <Download size={15} /> Download my data
          </a>
        </Section>
        <DeleteAccount user={user} onDeleted={() => onSignOut()} />
      </div>
    </div>
  );
}

