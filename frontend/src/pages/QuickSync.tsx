import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, CollectionInfo, FetchResult, TallyStatus } from "../api";
import { FetchTerminal, TerminalComplete } from "../components/FetchTerminal";
import { formatDate } from "../dates";

function formatCountdown(totalSeconds: number) {
  const secs = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function todayIso() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function clampDate(value: string, min?: string, max?: string) {
  if (min && value && value < min) return min;
  if (max && value && value > max) return max;
  return value;
}

function addDays(iso: string, days: number) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, (m || 1) - 1, d || 1);
  dt.setDate(dt.getDate() + days);
  const yy = dt.getFullYear();
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

function amountLabel(row: FetchResult) {
  if (row.vouchers != null && row.lines != null && (row.id === "sales" || row.id === "purchase")) {
    return `${row.vouchers} vouchers · ${row.lines} lines`;
  }
  return `${row.count}`;
}

type QsConfig = {
  company: string;
  database: string;
  days: number;
  auto_minutes: number;
  tally_host: string;
  tally_port: number;
  mysql_host: string;
};

type Props = {
  /** Full-screen content only — no app chrome around it. */
  bare?: boolean;
};

export function QuickSync({ bare = false }: Props) {
  const [status, setStatus] = useState<TallyStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const [config, setConfig] = useState<QsConfig | null>(null);
  const [boundDatabase, setBoundDatabase] = useState("");
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [loadError, setLoadError] = useState("");
  const [running, setRunning] = useState<{
    collections: string[];
    from_date: string;
    to_date: string;
    full_fetch: boolean;
  } | null>(null);
  const [report, setReport] = useState<TerminalComplete | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);
  const startRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    let cancelled = false;
    api
      .tallyStatus()
      .then((row) => {
        if (cancelled) return;
        setStatus(row);
        setStatusError("");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStatus(null);
        setStatusError(err instanceof Error ? err.message : "Could not load Tally status");
      });
    api
      .qsSettings()
      .then((row) => {
        if (!cancelled) {
          setConfig({
            company: row.company || "",
            database: row.database || "",
            days: Math.max(1, row.days || 1),
            auto_minutes: Math.max(0, row.auto_minutes || 0),
            tally_host: row.tally_host || "",
            tally_port: row.tally_port || 9000,
            mysql_host: row.mysql_host || "",
          });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Could not load quick sync settings");
        }
      });
    api
      .collections()
      .then((rows) => {
        if (!cancelled) setCollections(rows);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Could not load collections");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!status?.online || !status.company) {
      setBoundDatabase("");
      return;
    }
    api
      .mysqlBinding()
      .then((row) => {
        if (!cancelled) setBoundDatabase(row.database || "");
      })
      .catch(() => {
        if (!cancelled) setBoundDatabase("");
      });
    return () => {
      cancelled = true;
    };
  }, [status?.online, status?.company]);

  const range = useMemo(() => {
    const to = clampDate(todayIso(), status?.from_date, status?.to_date);
    const days = config?.days || 1;
    const from = clampDate(addDays(to, -(days - 1)), status?.from_date, to);
    return { from, to, days };
  }, [status?.from_date, status?.to_date, config?.days]);

  const periodLabel = useMemo(() => {
    if (!range.from || !range.to) return "—";
    if (range.days === 1) return `${formatDate(range.to)} (1 day)`;
    return `${formatDate(range.from)} – ${formatDate(range.to)} (${range.days} days)`;
  }, [range]);

  const norm = (value: string) => value.trim();
  const extraCompanies = (status?.companies?.length ?? 0) > 1;
  const companyMismatch = Boolean(
    config?.company &&
      status?.online &&
      (!status.company || norm(status.company) !== norm(config.company)),
  );
  const databaseMismatch = Boolean(
    config?.database &&
      status?.online &&
      !companyMismatch &&
      boundDatabase &&
      norm(boundDatabase) !== norm(config.database),
  );
  const mismatches: string[] = [];
  if (extraCompanies) mismatches.push("Keep only one company open in Tally");
  if (companyMismatch) {
    mismatches.push(
      `Company mismatch: settings “${config?.company}” vs Tally “${status?.company || "none"}”`,
    );
  }
  if (databaseMismatch) {
    mismatches.push(
      `Database mismatch: settings “${config?.database}” vs binding “${boundDatabase}”`,
    );
  }
  const hasMismatch = mismatches.length > 0;
  const ready = Boolean(
    status?.online &&
      status.company &&
      !hasMismatch &&
      config?.company &&
      config?.database &&
      collections.some((row) => row.id !== "daybook") &&
      range.from &&
      range.to,
  );

  function start() {
    const names = collections.filter((row) => row.id !== "daybook").map((row) => row.id);
    if (!names.length) {
      setLoadError("No quick collections available");
      return;
    }
    setLoadError("");
    setRunning({
      collections: names,
      from_date: range.from,
      to_date: range.to,
      full_fetch: true,
    });
  }
  startRef.current = start;

  const autoMinutes = config?.auto_minutes ?? 0;

  useEffect(() => {
    if (!autoMinutes || !ready || running) {
      if (!autoMinutes) setCountdown(null);
      return;
    }
    setCountdown(autoMinutes * 60);
    const timer = window.setInterval(() => {
      setCountdown((prev) => {
        if (prev === null) return autoMinutes * 60;
        if (prev <= 1) {
          startRef.current();
          return autoMinutes * 60;
        }
        return prev - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [autoMinutes, ready, running]);

  const content = (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-2xl flex-col">
      <div className="shrink-0">
      {bare ? (
        <div className="mb-4 flex items-center justify-between gap-3">
          <span
            className="text-xl font-bold tracking-[0.18em]"
            style={{ fontFamily: '"IBM Plex Sans", sans-serif' }}
          >
            <span className="text-[#f3efe6]">TALLY</span>
            <span className="text-[#e2c08a]">SYNC</span>
          </span>
          <Link to="/qs/settings" className="text-sm text-zinc-400 hover:text-zinc-100">
            Settings
          </Link>
        </div>
      ) : (
        <>
          <h1 className="text-2xl font-semibold tracking-tight text-white">Quick sync</h1>
          <p className="mt-1 text-sm text-zinc-500">
            One click: fetch and sync quick collections for the configured period.
          </p>
        </>
      )}

      {statusError ? <p className={`${bare ? "" : "mt-4"} text-sm text-red-400`}>{statusError}</p> : null}
      {loadError ? <p className="mt-4 text-sm text-red-400">{loadError}</p> : null}

      <div
        className={`${bare && !statusError && !loadError ? "mt-0" : bare ? "mt-4" : "mt-6"} space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6`}
      >
        <div>
          <p className="text-[11px] uppercase tracking-wider text-zinc-500">Company</p>
          <p
            className="mt-1 text-sm font-medium text-white"
            style={{ fontFamily: '"IBM Plex Sans", sans-serif' }}
          >
            {config?.company || (config ? "Not set" : "Loading…")}
          </p>
          {status?.online && status.company ? (
            <p className="mt-1 text-xs text-zinc-500">Tally loaded: {status.company}</p>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">Tally host</p>
            <p className="mt-1 font-mono text-sm text-zinc-200">
              {config?.tally_host
                ? `${config.tally_host}:${config.tally_port}`
                : status?.url?.replace(/^https?:\/\//, "") || "—"}
            </p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">MySQL host</p>
            <p className="mt-1 font-mono text-sm text-zinc-200">{config?.mysql_host || "—"}</p>
          </div>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wider text-zinc-500">MySQL database</p>
          <p className="mt-1 font-mono text-sm text-zinc-200">{config?.database || "Not set"}</p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">Mode</p>
            <p className="mt-1 text-sm text-zinc-200">Quick</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">Period</p>
            <p className="mt-1 font-mono text-sm text-amber-300">{periodLabel}</p>
          </div>
        </div>
        {autoMinutes > 0 ? (
          <div>
            <p className="text-[11px] uppercase tracking-wider text-zinc-500">Auto sync</p>
            <p className="mt-1 font-mono text-sm text-emerald-300">
              {!ready
                ? "Waiting — fix mismatches first"
                : running
                  ? "Paused while running…"
                  : countdown !== null
                    ? `Next in ${formatCountdown(countdown)}`
                    : `Every ${autoMinutes} min`}
            </p>
            <p className="mt-1 text-xs text-zinc-500">Runs only while this page stays open.</p>
          </div>
        ) : null}
        {mismatches.map((text) => (
          <p key={text} className="text-sm text-amber-400">
            {text}
          </p>
        ))}
        {config && (!config.company || !config.database) ? (
          <p className="text-sm text-amber-400">
            {bare ? (
              <>
                Set company and database in{" "}
                <Link to="/qs/settings" className="text-emerald-400 hover:text-emerald-300">
                  Settings
                </Link>
              </>
            ) : (
              "Configure company and database in /qs/settings"
            )}
          </p>
        ) : null}
        <button
          type="button"
          disabled={!ready || hasMismatch || Boolean(running)}
          onClick={start}
          title={hasMismatch ? mismatches.join(" · ") : undefined}
          className="w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
        >
          {running ? "Running…" : "Fetch & Sync"}
        </button>
      </div>
      </div>

      {report ? (
        <div className="mt-6 flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/50">
          <div className="flex shrink-0 items-baseline justify-between gap-3 border-b border-zinc-800 px-6 py-4">
            <h2 className="text-sm font-medium text-white">Last run</h2>
            <p className={`text-sm ${report.ok ? "text-emerald-400" : "text-red-400"}`}>
              {running ? "Updating…" : report.ok ? "Completed" : "Finished with errors"}
            </p>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            {report.results.length ? (
              <table className="w-full table-fixed border-collapse text-sm">
                <colgroup>
                  <col className="w-[46%]" />
                  <col className="w-[38%]" />
                  <col className="w-[16%]" />
                </colgroup>
                <thead>
                  <tr className="text-[11px] uppercase tracking-wider text-zinc-500">
                    <th className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950 px-6 py-2.5 text-left font-medium">
                      Collection
                    </th>
                    <th className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950 px-3 py-2.5 text-right font-medium">
                      Records
                    </th>
                    <th className="sticky top-0 z-10 border-b border-zinc-800 bg-zinc-950 px-6 py-2.5 text-right font-medium">
                      Elapsed
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {report.results.map((row) => (
                    <tr key={row.id} className="border-b border-zinc-800/70 last:border-b-0">
                      <td className="truncate px-6 py-2.5 text-left text-zinc-200" title={row.label}>
                        {row.label}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {row.error ? (
                          <span className="block truncate text-red-400" title={row.error}>
                            {row.error}
                          </span>
                        ) : (
                          <span className="font-mono tabular-nums text-zinc-300">{amountLabel(row)}</span>
                        )}
                      </td>
                      <td className="px-6 py-2.5 text-right font-mono tabular-nums text-zinc-400">
                        {row.elapsed}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="px-6 py-3 text-sm text-zinc-500">No collection results returned.</p>
            )}
            {report.lines.some((line) => line.kind === "err") ? (
              <ul className="space-y-1 border-t border-zinc-800 px-6 py-3 text-sm text-red-400">
                {report.lines
                  .filter((line) => line.kind === "err")
                  .map((line, index) => (
                    <li key={`${index}-${line.text}`}>{line.text}</li>
                  ))}
              </ul>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );

  return (
    <div
      className={
        bare
          ? "flex h-screen items-stretch justify-center overflow-hidden bg-zinc-950 p-6"
          : "flex h-full min-h-0 flex-1 flex-col overflow-hidden"
      }
    >
      {content}
      {running ? (
        <FetchTerminal
          request={running}
          autoSync
          closeOnComplete
          onClose={() => setRunning(null)}
          onResults={() => undefined}
          onComplete={(next) => {
            setReport(next);
            setRunning(null);
          }}
        />
      ) : null}
    </div>
  );
}
