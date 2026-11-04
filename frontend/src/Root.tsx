import { BookOpen, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ApiError, auth, setSignedOutHandler } from "./api";
import App from "./App";
import AuthScreen, { authViewFromHash, VerifyEmail } from "./components/AuthScreen";
import type { User } from "./types";

/** Signed in → the app; signed out → the landing page with sign-in. Also handles email links. */
export default function Root() {
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined = still checking
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(() => {
    const { view, token } = authViewFromHash();
    return view === "verify" ? token : null;
  });

  const check = useCallback(() => {
    setError(null);
    auth
      .me()
      .then((r) => setUser(r.user))
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
    setUser(u);
  };

  const signOut = async (everywhere = false) => {
    try {
      await (everywhere ? auth.logoutAll() : auth.logout());
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
              window.location.hash = "#/";
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
        <BookOpen className="text-brand-500" />
        <Loader2 size={18} className="mt-3 animate-spin text-stone-400" />
      </Centered>
    );
  if (user === null) return <AuthScreen onSignedIn={signedIn} />;
  // keyed by user: nothing from one account's session survives into the next
  return <App key={user.id} user={user} onSignOut={signOut} />;
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="flex h-full flex-col items-center justify-center bg-stone-50 p-4 dark:bg-stone-950">{children}</div>;
}
