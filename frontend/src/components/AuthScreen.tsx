import { ArrowLeft, CheckCircle2, Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { auth } from "../api";
import AuthShowcase from "../landing/AuthShowcase";
import Logo from "../landing/brand/Logo";
import type { User } from "../types";

/* ---------- #/  ·  #/signup  ·  #/forgot  ·  #/reset?token=  ·  #/verify?token= ---------- */
export type AuthView = "signin" | "signup" | "forgot" | "reset" | "verify";

export function authViewFromHash(hash = window.location.hash): { view: AuthView; token: string } {
  const m = hash.match(/^#\/(signup|forgot|reset|verify)\/?(?:\?(.*))?$/);
  const token = new URLSearchParams(m?.[2] ?? "").get("token") ?? "";
  return { view: (m?.[1] as AuthView) ?? "signin", token };
}

const input =
  "w-full rounded-xl border border-line bg-paper px-3.5 py-2.5 text-[0.95rem] text-ink outline-none transition placeholder:text-ink-muted focus:border-accent focus:ring-2 focus:ring-accent/25";
const primary =
  "flex w-full items-center justify-center gap-2 rounded-full bg-accent px-4 py-3 text-[0.95rem] font-medium text-on-accent shadow-card transition hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60";

function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-muted">{hint}</span>}
    </label>
  );
}

function Alert({ kind, children }: { kind: "error" | "ok"; children: ReactNode }) {
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      className={`rounded-lg px-3 py-2 text-sm ${
        kind === "error" ? "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300" : "bg-accent-soft text-accent-ink"
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
      <h2 className="font-display text-[1.85rem] leading-tight font-medium tracking-tight text-ink">Welcome back</h2>
      {f.error && <Alert kind="error">{f.error}</Alert>}
      <Field label="Email">
        <input type="email" required autoComplete="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className={input} />
      </Field>
      <Field label="Password">
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={input}
        />
      </Field>
      <div className="flex items-center justify-between text-sm">
        <label className="flex items-center gap-2 text-ink-muted">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="accent-accent" />
          Keep me signed in
        </label>
        <a href="#/forgot" className="text-accent-ink hover:underline">
          Forgot password?
        </a>
      </div>
      <button disabled={f.busy} className={primary}>
        {f.busy && <Loader2 size={16} className="animate-spin" />} Sign in
      </button>
      <p className="text-center text-sm text-ink-muted">
        New to BookMind?{" "}
        <a href="#/signup" className="font-medium text-accent-ink hover:underline">
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
      <h2 className="font-display text-[1.85rem] leading-tight font-medium tracking-tight text-ink">Create your library</h2>
      {f.error && <Alert kind="error">{f.error}</Alert>}
      <Field label="Name">
        <input required maxLength={100} autoComplete="name" autoFocus value={name} onChange={(e) => setName(e.target.value)} className={input} />
      </Field>
      <Field label="Email">
        <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={input} />
      </Field>
      <Field label="Password" hint={`At least ${minLength} characters. A short phrase is easy to remember and hard to guess.`}>
        <input
          type="password"
          required
          minLength={minLength}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={input}
        />
      </Field>
      <Field label="Confirm password">
        <input type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={input} />
      </Field>
      <button disabled={f.busy} className={primary}>
        {f.busy && <Loader2 size={16} className="animate-spin" />} Create account
      </button>
      <p className="text-center text-sm text-ink-muted">
        Already have an account?{" "}
        <a href="#/login" className="font-medium text-accent-ink hover:underline">
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
      <h2 className="font-display text-[1.85rem] leading-tight font-medium tracking-tight text-ink">Check your email</h2>
      <p className="text-sm text-ink-muted">
        We sent a link to <strong>{email}</strong>. Open it to confirm your address, then sign in.
      </p>
      {f.error && <Alert kind="error">{f.error}</Alert>}
      {sent && <Alert kind="ok">Sent again. It can take a minute to arrive.</Alert>}
      <form onSubmit={f.run(async () => (await auth.resendVerification(email), setSent(true)))}>
        <button disabled={f.busy} className="text-sm text-accent-ink hover:underline disabled:opacity-60">
          Didn't get it? Send it again
        </button>
      </form>
      <a href="#/login" className="block text-sm text-ink-muted hover:underline">
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
      <h2 className="font-display text-[1.85rem] leading-tight font-medium tracking-tight text-ink">Reset your password</h2>
      <p className="text-sm text-ink-muted">Enter your account's email and we'll send you a link to choose a new password.</p>
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
      <a href="#/login" className="block text-center text-sm text-ink-muted hover:underline">
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
        <a href="#/login" className={primary}>
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
      <h2 className="font-display text-[1.85rem] leading-tight font-medium tracking-tight text-ink">Choose a new password</h2>
      {!token && <Alert kind="error">This link is incomplete. Open the link from your email again, or ask for a new one.</Alert>}
      {f.error && <Alert kind="error">{f.error}</Alert>}
      <Field label="New password" hint={`At least ${minLength} characters.`}>
        <input
          type="password"
          required
          minLength={minLength}
          autoComplete="new-password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={input}
        />
      </Field>
      <Field label="Confirm new password">
        <input type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={input} />
      </Field>
      <button disabled={f.busy || !token} className={primary}>
        {f.busy && <Loader2 size={16} className="animate-spin" />} Change password
      </button>
      <a href="#/forgot" className="block text-center text-sm text-ink-muted hover:underline">
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
        <Loader2 className="mx-auto animate-spin text-accent-ink" />
      ) : state === "ok" ? (
        <>
          <CheckCircle2 className="mx-auto text-accent-ink" size={36} />
          <h2 className="font-display text-[1.85rem] leading-tight font-medium tracking-tight text-ink">Email confirmed</h2>
          <button onClick={onDone} className={primary}>
            Continue
          </button>
        </>
      ) : (
        <>
          <Alert kind="error">{state}</Alert>
          <button onClick={onDone} className="text-sm text-accent-ink hover:underline">
            Continue
          </button>
        </>
      )}
    </div>
  );
}

/** Sign in, sign up and password resets, beside a slideshow of what BookMind does (wide screens).
 * Same palette and type as the landing page (theme tokens in index.css). */
export default function AuthScreen({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [{ view, token }, setView] = useState(authViewFromHash);
  const [minLength, setMinLength] = useState(10);
  useEffect(() => {
    const on = () => setView(authViewFromHash());
    window.addEventListener("hashchange", on);
    auth
      .config()
      .then((c) => setMinLength(c.password_min_length))
      .catch(() => {});
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
        return <VerifyEmail token={token} onDone={() => (window.location.hash = "#/login")} />;
      default:
        return <SignIn onSignedIn={onSignedIn} />;
    }
  })();

  return (
    <div className="landing flex min-h-full flex-col lg:flex-row">
      {/* wide screens: a deep-green panel with a slideshow of features */}
      <aside className="relative hidden flex-col overflow-hidden bg-panel px-12 py-10 text-on-panel lg:flex lg:w-[52%] xl:px-16">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-40 -right-40 h-[36rem] w-[36rem] bg-[radial-gradient(closest-side,rgb(255_255_255/0.09),transparent)]"
        />
        <a
          href="#/"
          className="relative w-fit rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-on-panel"
          aria-label="BookMind home"
        >
          <Logo onPanel size={32} />
        </a>
        <div className="relative flex flex-1 items-center py-10">
          <AuthShowcase />
        </div>
      </aside>

      <main className="flex flex-1 flex-col px-5 py-6 sm:px-10 sm:py-10">
        <div className="flex items-center justify-between">
          <a
            href="#/"
            className="rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent lg:hidden"
            aria-label="BookMind home"
          >
            <Logo size={30} />
          </a>
          <a
            href="#/"
            className="ml-auto inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm text-ink-muted transition hover:bg-paper-sunk hover:text-ink"
          >
            <ArrowLeft size={15} aria-hidden="true" /> Home
          </a>
        </div>
        <div className="flex flex-1 items-start justify-center pt-8 sm:items-center sm:pt-0">
          <div className="w-full max-w-md rounded-[var(--radius-card)] border border-line bg-paper-raised p-6 shadow-card sm:p-9">
            {form}
            <p className="mt-7 flex items-center justify-center gap-1.5 text-xs text-ink-muted">
              <ShieldCheck size={13} aria-hidden="true" /> Each account has its own private library.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
