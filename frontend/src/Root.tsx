import { Loader2 } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { ApiError, auth, setSignedOutHandler } from "./api";
import AuthScreen, { authViewFromHash, VerifyEmail } from "./components/AuthScreen";
import { LogoMark } from "./landing/brand/Logo";
import Landing from "./landing/Landing";
import type { User } from "./types";
import { applyTheme } from "./utils";

// The landing page is in the first download (~19 kB gzipped): visitors see it one round trip
// sooner, which phones notice. The app itself loads only after sign-in.
const App = lazy(() => import("./App"));
const LegalPage = lazy(() => import("./landing/pages/LegalPage"));

type PublicRoute = "landing" | "privacy" | "terms" | "auth";

/** Signed out: the landing page at #/ (and its #section anchors), legal pages, or the sign-in forms. */
export function publicRouteFromHash(hash = window.location.hash): PublicRoute {
  if (/^#\/(login|signup|forgot|reset|verify)\b/.test(hash)) return "auth";
  if (/^#\/privacy\/?$/.test(hash)) return "privacy";
  if (/^#\/terms\/?$/.test(hash)) return "terms";
  return "landing";
}

/** Cross-fade between pages where the browser supports view transitions (and motion is welcome). */
function transition(update: () => void) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
  if (!doc.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) return update();
  doc.startViewTransition(() => flushSync(update));
}

/** Signed in → the app; signed out → the landing page with sign-in. Also handles email links. */
export default function Root() {
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined = still checking
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(() => {
    const { view, token } = authViewFromHash();
    return view === "verify" ? token : null;
  });
  const [route, setRoute] = useState(publicRouteFromHash);
  const routeRef = useRef(route);
  routeRef.current = route;
  useEffect(() => {
    const on = () => {
      const next = publicRouteFromHash();
      if (next !== routeRef.current) transition(() => setRoute(next));
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  // The account's theme wins over this browser's (it may have been changed on another device).
  const signedInAs = (u: User) => {
    if (u.settings.theme) applyTheme(u.settings.theme);
    setUser(u);
  };

  const check = useCallback(() => {
    setError(null);
    // No sign-in cookie: certainly signed out, so show the landing page at once (no request, no 401).
    // The CSRF cookie is set and cleared together with the session cookie, and only it is readable.
    if (!/(?:^|;\s*)bm_csrf=/.test(document.cookie)) return setUser(null);
    auth
      .me()
      .then((r) => signedInAs(r.user))
      .catch((e: ApiError) => (e.status === 401 ? setUser(null) : setError(e.message)));
  }, []);

  useEffect(() => {
    check();
    // A session that ends while the app is open (expired, or "sign out everywhere" on another device).
    setSignedOutHandler(() => setUser(null));
    return () => setSignedOutHandler(null);
  }, [check]);

  const signedIn = (u: User) => {
    window.location.hash = "#/";
    signedInAs(u);
  };

  const signOut = async (everywhere = false) => {
    try {
      await (everywhere ? auth.logoutAll() : auth.logout());
    } catch {
      /* already signed out (e.g. the account was just deleted) */
    } finally {
      window.location.hash = "#/";
      setUser(null);
    }
  };

  if (verifying !== null)
    return (
      <Centered>
        <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-8 dark:border-stone-800 dark:bg-stone-900">
          <VerifyEmail
            token={verifying}
            onDone={() => {
              window.location.hash = "#/login"; // signed in already: the app shows the library anyway
              setVerifying(null);
              check();
            }}
          />
        </div>
      </Centered>
    );

  if (error)
    return (
      <Centered>
        <p className="max-w-sm text-center text-sm text-stone-600 dark:text-stone-300">{error}</p>
        <button onClick={check} className="mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm text-white hover:bg-brand-700">
          Try again
        </button>
      </Centered>
    );
  if (user === undefined)
    return (
      <Centered>
        <LogoMark size={44} />
        <Loader2 size={18} className="mt-3 animate-spin text-stone-400" />
      </Centered>
    );
  if (user === null) {
    if (route === "auth") return <AuthScreen onSignedIn={signedIn} />;
    return (
      <Suspense
        fallback={
          <Centered>
            <Loader2 size={18} className="animate-spin text-stone-400" />
          </Centered>
        }
      >
        {route === "landing" ? <Landing /> : <LegalPage page={route} />}
      </Suspense>
    );
  }
  // keyed by user: nothing from one account's session survives into the next
  return (
    <Suspense
      fallback={
        <Centered>
          <LogoMark size={44} />
          <Loader2 size={18} className="mt-3 animate-spin text-stone-400" />
        </Centered>
      }
    >
      <App key={user.id} user={user} onUser={setUser} onSignOut={signOut} />
    </Suspense>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="flex h-full flex-col items-center justify-center bg-stone-50 p-4 dark:bg-stone-950">{children}</div>;
}
