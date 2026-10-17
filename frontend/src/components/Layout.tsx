import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, TallyStatus } from "../api";
import { formatDate } from "../dates";

type Props = {
  username: string;
  onLogout: () => void;
};

export type LayoutContext = {
  status: TallyStatus | null;
  statusError: string;
  refreshStatus: () => void;
};

const navClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-3 py-2 text-sm ${
    isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
  }`;

export function Layout({ username, onLogout }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const [status, setStatus] = useState<TallyStatus | null>(null);
  const [statusError, setStatusError] = useState("");

  const refreshStatus = useCallback(() => {
    api
      .tallyStatus()
      .then((row) => {
        setStatus(row);
        setStatusError("");
      })
      .catch((err: unknown) => {
        setStatus(null);
        setStatusError(err instanceof Error ? err.message : "Could not load Tally status");
      });
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus, location.pathname]);

  async function logout() {
    await api.logout();
    onLogout();
    navigate("/login");
  }

  const extraCompanies = (status?.companies?.length ?? 0) > 1;
  const outlet: LayoutContext = { status, statusError, refreshStatus };

  return (
    <div className="flex h-screen w-full flex-col bg-zinc-950">
      <header className="flex h-14 shrink-0 items-stretch border-b border-zinc-800">
        <div className="flex w-56 shrink-0 items-center border-r border-zinc-800 px-4">
          <span className="text-sm font-semibold tracking-tight text-emerald-400">Tally sync</span>
        </div>
        <div className="flex min-w-0 flex-1 items-center justify-between gap-4 px-6">
          {statusError ? (
            <p className="truncate text-sm text-red-400">{statusError}</p>
          ) : !status ? (
            <p className="text-sm text-zinc-500">Checking Tally…</p>
          ) : status.online ? (
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-wider text-emerald-600">Loaded company</p>
              <p className="truncate text-sm font-medium leading-tight text-white" title={status.company}>
                {status.company || "—"}
              </p>
            </div>
          ) : (
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-wider text-amber-500">Tally offline</p>
              <p className="truncate text-sm leading-tight text-zinc-400" title={status.error || status.url}>
                {status.error || status.url}
              </p>
            </div>
          )}
          <div className="shrink-0 text-right font-mono text-xs leading-tight text-zinc-500">
            {status?.online && status.from_date && status.to_date ? (
              <p>
                {formatDate(status.from_date)} – {formatDate(status.to_date)}
              </p>
            ) : null}
            {status?.url ? <p>{status.url}</p> : null}
            {extraCompanies ? <p className="text-amber-400">Keep only one company open</p> : null}
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-56 shrink-0 flex-col border-r border-zinc-800">
          <nav className="flex flex-1 flex-col gap-1 p-3">
            <NavLink to="/" className={navClass} end>
              Home
            </NavLink>
            <NavLink to="/settings" className={navClass}>
              Settings
            </NavLink>
          </nav>
          <div className="border-t border-zinc-800 p-3">
            <p className="truncate px-3 text-sm text-zinc-500" title={username}>
              {username}
            </p>
            <button
              type="button"
              onClick={() => void logout()}
              className="mt-1 w-full rounded-md px-3 py-2 text-left text-sm text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
            >
              Log out
            </button>
          </div>
        </aside>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-6">
          <Outlet context={outlet} />
        </main>
      </div>
    </div>
  );
}
