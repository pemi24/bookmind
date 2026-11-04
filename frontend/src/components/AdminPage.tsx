import { ShieldCheck, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { admin, type AdminUser } from "../api";
import { Button, EmptyState, ErrorBox } from "./ui";

function size(bytes: number): string {
  if (!bytes) return "0 KB";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function date(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "Never";
}

/** Accounts on this BookMind server. Admins see usage only, never what's inside anyone's library. */
export default function AdminPage() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const load = useCallback(() => admin.users().then(setUsers).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
  }, [load]);

  const act = async (u: AdminUser, fn: () => Promise<unknown>) => {
    setBusy(u.id);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const totals = users && {
    accounts: users.length,
    books: users.reduce((n, u) => n + u.books, 0),
    storage: users.reduce((n, u) => n + u.storage_bytes, 0),
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <ShieldCheck size={22} className="text-brand-600" /> Admin
        </h1>
        <p className="text-sm text-stone-500">Accounts on this server. You can see how much each one uses, but not what's in their libraries.</p>
        {totals && (
          <p className="mt-3 text-sm text-stone-600 dark:text-stone-300">
            {totals.accounts} account{totals.accounts === 1 ? "" : "s"} · {totals.books} book{totals.books === 1 ? "" : "s"} · {size(totals.storage)} of book files
          </p>
        )}
        {error && <div className="mt-4"><ErrorBox>{error}</ErrorBox></div>}
        {users?.length === 0 && <EmptyState icon={<Users size={22} />} title="No accounts yet" />}
        {users && users.length > 0 && (
          <ul className="mt-4 divide-y divide-stone-100 rounded-xl border border-stone-200 bg-white dark:divide-stone-800 dark:border-stone-800 dark:bg-stone-900">
            {users.map((u) => (
              <li key={u.id} className={`flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 ${u.is_active ? "" : "opacity-60"}`}>
                <div className="min-w-0 flex-1 basis-56">
                  <p className="flex flex-wrap items-center gap-1.5 font-medium">
                    <span className="truncate">{u.display_name}</span>
                    {u.is_me && <Badge>You</Badge>}
                    {u.is_admin && <Badge tone="brand">Admin</Badge>}
                    {!u.is_active && <Badge tone="red">Suspended</Badge>}
                    {!u.has_password && <Badge tone="amber">No password set</Badge>}
                  </p>
                  <p className="truncate text-sm text-stone-500">{u.email}</p>
                  <p className="text-xs text-stone-400">
                    Joined {date(u.created_at)} · last active {date(u.last_seen_at)}
                  </p>
                </div>
                <div className="text-sm text-stone-600 tabular-nums dark:text-stone-300">
                  {u.books} book{u.books === 1 ? "" : "s"} · {size(u.storage_bytes)} · {u.chats} chat{u.chats === 1 ? "" : "s"}
                </div>
                {!u.is_me && (
                  <div className="flex flex-wrap gap-1.5">
                    <Button
                      loading={busy === u.id}
                      onClick={() => {
                        if (u.is_active && !confirm(`Suspend ${u.email}? They'll be signed out and can't sign in until you reactivate them.`)) return;
                        act(u, () => admin.updateUser(u.id, { is_active: !u.is_active }));
                      }}
                    >
                      {u.is_active ? "Suspend" : "Reactivate"}
                    </Button>
                    <Button
                      disabled={busy === u.id}
                      onClick={() => {
                        if (!u.is_admin && !confirm(`Make ${u.email} an admin? Admins can manage every account.`)) return;
                        act(u, () => admin.updateUser(u.id, { is_admin: !u.is_admin }));
                      }}
                    >
                      {u.is_admin ? "Remove admin" : "Make admin"}
                    </Button>
                    <Button
                      variant="danger"
                      disabled={busy === u.id}
                      onClick={() =>
                        confirm(`Delete ${u.email} and everything in their library (${u.books} books, ${u.chats} chats)? This cannot be undone.`) &&
                        act(u, () => admin.deleteUser(u.id))
                      }
                    >
                      Delete
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Badge({ children, tone = "stone" }: { children: string; tone?: "stone" | "brand" | "red" | "amber" }) {
  const tones = {
    stone: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
    brand: "bg-brand-100 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200",
    red: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
    amber: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  };
  return <span className={`rounded px-1.5 py-0.5 text-xs font-normal ${tones[tone]}`}>{children}</span>;
}
