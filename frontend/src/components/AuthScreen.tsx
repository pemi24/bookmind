import { BookOpen, CheckCircle2, Loader2, Lock, MessageSquareQuote, Quote, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { auth } from "../api";
import type { User } from "../types";

/* ---------- #/  ·  #/signup  ·  #/forgot  ·  #/reset?token=  ·  #/verify?token= ---------- */
export type AuthView = "signin" | "signup" | "forgot" | "reset" | "verify";

export function authViewFromHash(hash = window.location.hash): { view: AuthView; token: string } {
  const m = hash.match(/^#\/(signup|forgot|reset|verify)\/?(?:\?(.*))?$/);
  const token = new URLSearchParams(m?.[2] ?? "").get("token") ?? "";
  return { view: (m?.[1] as AuthView) ?? "signin", token };
}

const input =
  "w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-stone-700 dark:bg-stone-900";
const primary =
  "flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-brand-700 disabled:opacity-60";

function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-stone-500">{hint}</span>}
    </label>
  );
}

function Alert({ kind, children }: { kind: "error" | "ok"; children: ReactNode }) {
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      className={`rounded-lg px-3 py-2 text-sm ${
        kind === "error" ? "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300" : "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
      }`}
    >
      {children}
    </div>
  );
}

function useForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = (fn: () => Promise<void>) => async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, setError, run };
}

function SignIn({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const f = useForm();
  return (
    <form onSubmit={f.run(async () => onSignedIn((await auth.login(email, password, remember)).user))} className="space-y-4">
      <h2 className="text-xl font-semibold">Welcome back</h2>
      {f.error && <Alert kind="error">{f.error}</Alert>}
      <Field label="Email">
        <input type="email" required autoComplete="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className={input} />
      </Field>
      <Field label="Password">
        <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={input} />
      </Field>
      <div className="flex items-center justify-between text-sm">
        <label className="flex items-center gap-2 text-stone-600 dark:text-stone-400">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="accent-brand-600" />
          Keep me signed in
        </label>
        <a href="#/forgot" className="text-brand-600 hover:underline dark:text-brand-400">
          Forgot password?
        </a>
      </div>
      <button disabled={f.busy} className={primary}>
        {f.busy && <Loader2 size={16} className="animate-spin" />} Sign in
      </button>
      <p className="text-center text-sm text-stone-500">
        New to BookMind?{" "}
        <a href="#/signup" className="font-medium text-brand-600 hover:underline dark:text-brand-400">
          Create an account
        </a>
      </p>
    </form>
  );
}

function SignUp({ onSignedIn, minLength }: { onSignedIn: (u: User) => void; minLength: number }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState<string | null>(null); // email awaiting verification
  const f = useForm();

  if (pending) return <CheckEmail email={pending} />;
  return (
    <form
      onSubmit={f.run(async () => {
        if (password !== confirm) throw new Error("The two passwords don't match.");
        const r = await auth.signup(email, password, name);
        if (r.verification_required) setPending(r.user.email);
        else onSignedIn(r.user);
      })}
      className="space-y-4"
    >
      <h2 className="text-xl font-semibold">Create your library</h2>
      {f.error && <Alert kind="error">{f.error}</Alert>}
      <Field label="Name">
        <input required maxLength={100} autoComplete="name" autoFocus value={name} onChange={(e) => setName(e.target.value)} className={input} />
      </Field>
      <Field label="Email">
        <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={input} />
      </Field>
      <Field label="Password" hint={`At least ${minLength} characters. A short phrase is easy to remember and hard to guess.`}>
        <input type="password" required minLength={minLength} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={input} />
      </Field>
      <Field label="Confirm password">
        <input type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={input} />
      </Field>
      <button disabled={f.busy} className={primary}>
        {f.busy && <Loader2 size={16} className="animate-spin" />} Create account
      </button>
      <p className="text-center text-sm text-stone-500">
        Already have an account?{" "}
        <a href="#/" className="font-medium text-brand-600 hover:underline dark:text-brand-400">
          Sign in
        </a>
      </p>
    </form>
  );
}

function CheckEmail({ email }: { email: string }) {
  const [sent, setSent] = useState(false);
  const f = useForm();
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Check your email</h2>
      <p className="text-sm text-stone-600 dark:text-stone-400">
        We sent a link to <strong>{email}</strong>. Open it to confirm your address, then sign in.
      </p>
      {f.error && <Alert kind="error">{f.error}</Alert>}
      {sent && <Alert kind="ok">Sent again. It can take a minute to arrive.</Alert>}
      <form onSubmit={f.run(async () => (await auth.resendVerification(email), setSent(true)))}>
        <button disabled={f.busy} className="text-sm text-brand-600 hover:underline disabled:opacity-60 dark:text-brand-400">
          Didn't get it? Send it again
        </button>
      </form>
      <a href="#/" className="block text-sm text-stone-500 hover:underline">
        Back to sign in
      </a>
    </div>
  );
}

function Forgot() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const f = useForm();
  return (
    <form onSubmit={f.run(async () => setDone((await auth.forgot(email)).message))} className="space-y-4">
      <h2 className="text-xl font-semibold">Reset your password</h2>
      <p className="text-sm text-stone-600 dark:text-stone-400">Enter your account's email and we'll send you a link to choose a new password.</p>
      {f.error && <Alert kind="error">{f.error}</Alert>}
      {done ? (
        <Alert kind="ok">{done}</Alert>
      ) : (
        <>
          <Field label="Email">
            <input type="email" required autoComplete="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className={input} />
          </Field>
          <button disabled={f.busy} className={primary}>
            {f.busy && <Loader2 size={16} className="animate-spin" />} Send reset link
          </button>
        </>
      )}
      <a href="#/" className="block text-center text-sm text-stone-500 hover:underline">
        Back to sign in
      </a>
    </form>
  );
}

function Reset({ token, minLength }: { token: string; minLength: number }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const f = useForm();
  if (done)
    return (
      <div className="space-y-4">
        <Alert kind="ok">Your password has been changed and every device was signed out. Sign in with your new password.</Alert>
        <a href="#/" className={primary}>
          Sign in
        </a>
      </div>
    );
  return (
    <form
      onSubmit={f.run(async () => {
        if (password !== confirm) throw new Error("The two passwords don't match.");
        await auth.reset(token, password);
        setDone(true);
      })}
      className="space-y-4"
    >
      <h2 className="text-xl font-semibold">Choose a new password</h2>
      {!token && <Alert kind="error">This link is incomplete. Open the link from your email again, or ask for a new one.</Alert>}
      {f.error && <Alert kind="error">{f.error}</Alert>}
      <Field label="New password" hint={`At least ${minLength} characters.`}>
        <input type="password" required minLength={minLength} autoComplete="new-password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} className={input} />
      </Field>
      <Field label="Confirm new password">
        <input type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={input} />
      </Field>
      <button disabled={f.busy || !token} className={primary}>
        {f.busy && <Loader2 size={16} className="animate-spin" />} Change password
      </button>
      <a href="#/forgot" className="block text-center text-sm text-stone-500 hover:underline">
        Need a new link?
      </a>
    </form>
  );
}

/** Confirms an email address from the link in the verification email (works signed in or out). */
export function VerifyEmail({ token, onDone }: { token: string; onDone: () => void }) {
  const [state, setState] = useState<"working" | "ok" | string>("working");
  useEffect(() => {
    auth
      .verify(token)
      .then(() => setState("ok"))
      .catch((e) => setState((e as Error).message));
  }, [token]);
  return (
    <div className="space-y-4 text-center">
      {state === "working" ? (
        <Loader2 className="mx-auto animate-spin text-brand-500" />
      ) : state === "ok" ? (
        <>
          <CheckCircle2 className="mx-auto text-emerald-500" size={36} />
          <h2 className="text-xl font-semibold">Email confirmed</h2>
          <button onClick={onDone} className={primary}>
            Continue
          </button>
        </>
      ) : (
        <>
          <Alert kind="error">{state}</Alert>
          <button onClick={onDone} className="text-sm text-brand-600 hover:underline">
            Continue
          </button>
        </>
      )}
    </div>
  );
}

const FEATURES = [
  { icon: MessageSquareQuote, title: "Answers from the book itself", text: "Every answer is drawn from the text, with citations you can open in the reader." },
  { icon: Quote, title: "Study, quotes and essays", text: "Summaries, quizzes, flashcards, timelines and verified quotes for your essays." },
  { icon: Lock, title: "Your library is private", text: "Your books, chats and notes are visible only to you." },
];

/** The signed-out app: a short introduction beside the sign-in / sign-up / reset forms. */
export default function AuthScreen({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [{ view, token }, setView] = useState(authViewFromHash);
  const [minLength, setMinLength] = useState(10);
  useEffect(() => {
    const on = () => setView(authViewFromHash());
    window.addEventListener("hashchange", on);
    auth.config().then((c) => setMinLength(c.password_min_length)).catch(() => {});
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const form = (() => {
    switch (view) {
      case "signup":
        return <SignUp onSignedIn={onSignedIn} minLength={minLength} />;
      case "forgot":
        return <Forgot />;
      case "reset":
        return <Reset token={token} minLength={minLength} />;
      case "verify":
        return <VerifyEmail token={token} onDone={() => (window.location.hash = "#/")} />;
      default:
        return <SignIn onSignedIn={onSignedIn} />;
    }
  })();

  return (
    <div className="flex min-h-full flex-col bg-stone-50 lg:flex-row dark:bg-stone-950">
      <section className="flex flex-col justify-center bg-gradient-to-br from-brand-700 to-brand-900 px-6 py-6 text-white sm:px-12 sm:py-10 lg:w-1/2 lg:py-16">
        <div className="mx-auto w-full max-w-lg">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/15">
              <BookOpen size={20} />
            </span>
            <span className="text-xl font-semibold tracking-tight">BookMind</span>
          </div>
          <h1 className="mt-4 font-serif text-2xl leading-tight sm:mt-8 sm:text-4xl">Talk with your books.</h1>
          <p className="mt-2 text-sm text-brand-100 sm:mt-3 sm:text-base">Upload a PDF, EPUB or document, or pick a free classic, and ask it anything.</p>
          <ul className="mt-8 hidden space-y-5 sm:block">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex gap-3">
                <f.icon size={20} className="mt-0.5 shrink-0 text-brand-200" />
                <div>
                  <p className="font-medium">{f.title}</p>
                  <p className="text-sm text-brand-100/90">{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <section className="flex flex-1 items-start justify-center px-4 py-6 sm:items-center sm:py-10">
        <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8 dark:border-stone-800 dark:bg-stone-900">
          {form}
          <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-stone-400">
            <ShieldCheck size={13} /> Each account has its own private library.
          </p>
        </div>
      </section>
    </div>
  );
}
