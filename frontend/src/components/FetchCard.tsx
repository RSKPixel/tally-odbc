import { FormEvent, useEffect, useState } from "react";
import { api, CollectionInfo, FetchResult } from "../api";
import { Field } from "./Field";
import { FetchTerminal } from "./FetchTerminal";
import { RecordsModal } from "./RecordsModal";

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

function defaultToDate(tallyFrom?: string, tallyTo?: string) {
  return clampDate(todayIso(), tallyFrom, tallyTo);
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

function rangeForOption(
  option: "15days" | "period",
  tallyFrom?: string,
  tallyTo?: string,
): { from: string; to: string } {
  if (option === "period") {
    const from = tallyFrom || defaultToDate(tallyFrom, tallyTo);
    const to = tallyTo || defaultToDate(tallyFrom, tallyTo);
    return { from, to: to < from ? from : to };
  }
  const to = defaultToDate(tallyFrom, tallyTo);
  const from = clampDate(addDays(to, -14), tallyFrom, to);
  return { from, to };
}

function amountLabel(row: { id?: string; count: number; vouchers?: number; lines?: number }) {
  if (row.vouchers != null && row.lines != null && (row.id === "sales" || row.id === "purchase")) {
    const voucherWord = row.vouchers === 1 ? "voucher" : "vouchers";
    const lineWord = row.lines === 1 ? "line" : "lines";
    return `${row.vouchers} ${voucherWord} · ${row.lines} ${lineWord}`;
  }
  if (row.id === "inventory") {
    const word = row.count === 1 ? "item" : "items";
    return `${row.count} ${word}`;
  }
  if (row.id === "accounts") {
    const word = row.count === 1 ? "account" : "accounts";
    return `${row.count} ${word}`;
  }
  if (row.id === "costcentres") {
    const word = row.count === 1 ? "centre" : "centres";
    return `${row.count} ${word}`;
  }
  if (row.id === "receivables" || row.id === "payables") {
    const word = row.count === 1 ? "bill" : "bills";
    return `${row.count} ${word}`;
  }
  if (row.id === "daybook") {
    const word = row.count === 1 ? "line" : "lines";
    return `${row.count} ${word}`;
  }
  const word = row.count === 1 ? "line" : "lines";
  return `${row.count} ${word}`;
}

type Props = {
  online: boolean;
  fromDate?: string;
  toDate?: string;
  databaseReady: boolean;
  collections: CollectionInfo[];
  selected: Record<string, boolean>;
  fullFetch: boolean;
};

export function FetchCard({
  online,
  fromDate: tallyFrom,
  toDate: tallyTo,
  databaseReady,
  collections,
  selected,
  fullFetch,
}: Props) {
  const initial = rangeForOption("15days", tallyFrom, tallyTo);
  const [dateOption, setDateOption] = useState<"15days" | "period">("15days");
  const [fromDate, setFromDate] = useState(initial.from);
  const [toDate, setToDate] = useState(initial.to);
  const [results, setResults] = useState<FetchResult[]>([]);
  const [pending, setPending] = useState<FetchResult | null>(null);
  const [open, setOpen] = useState<FetchResult | null>(null);
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [terminal, setTerminal] = useState<{
    collections: string[];
    from_date: string;
    to_date: string;
    full_fetch: boolean;
  } | null>(null);

  function askForRecords(row: FetchResult) {
    setPending(row);
    setPassword("");
    setPasswordError("");
  }

  function closePassword() {
    if (checking) return;
    setPending(null);
    setPassword("");
    setPasswordError("");
  }

  async function confirmPassword(event: FormEvent) {
    event.preventDefault();
    if (!pending) return;
    setChecking(true);
    setPasswordError("");
    try {
      await api.verifyPassword(password);
      setOpen(pending);
      setPending(null);
      setPassword("");
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "Invalid admin password");
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    const next = rangeForOption(dateOption, tallyFrom, tallyTo);
    setFromDate(next.from);
    setToDate(next.to);
  }, [tallyFrom, tallyTo, dateOption]);

  function changeDateOption(option: "15days" | "period") {
    setDateOption(option);
    const next = rangeForOption(option, tallyFrom, tallyTo);
    setFromDate(next.from);
    setToDate(next.to);
  }

  function changeFrom(value: string) {
    const next = clampDate(value, tallyFrom, tallyTo);
    setFromDate(next);
    setToDate((prev) => (prev && next && next > prev ? next : prev));
  }

  function changeTo(value: string) {
    const next = clampDate(value, tallyFrom, tallyTo);
    setToDate(next);
    setFromDate((prev) => (prev && next && next < prev ? next : prev));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const names = collections
      .filter((row) => selected[row.id])
      .filter((row) => fullFetch || row.id !== "daybook")
      .map((row) => row.id);
    if (!names.length) {
      setError("Select a collection");
      return;
    }
    setError("");
    setResults([]);
    setTerminal({
      collections: names,
      from_date: fromDate,
      to_date: toDate,
      full_fetch: true,
    });
  }

  return (
    <>
      <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
        <form onSubmit={(event) => void submit(event)} autoComplete="off" className="shrink-0 space-y-6">
          <p className="text-sm text-zinc-500">{fullFetch ? "Full mode" : "Quick mode"}</p>
          <div>
            <p className="text-xs uppercase tracking-wider text-zinc-500">Dates</p>
            <div className="mt-3 grid max-w-md grid-cols-2 gap-2">
              {(
                [
                  ["15days", "15 days"],
                  ["period", "Full period"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => changeDateOption(id)}
                  className={`rounded-lg border px-3 py-2 text-sm ${
                    dateOption === id
                      ? "border-emerald-600 bg-emerald-600/15 text-emerald-300"
                      : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid max-w-md grid-cols-2 gap-4">
            <Field
              id="from_date"
              label="From"
              type="date"
              lang="en-IN"
              min={tallyFrom || undefined}
              max={toDate || tallyTo || undefined}
              value={fromDate}
              onChange={(e) => changeFrom(e.target.value)}
              required
            />
            <Field
              id="to_date"
              label="To"
              type="date"
              lang="en-IN"
              min={fromDate || tallyFrom || undefined}
              max={tallyTo || undefined}
              value={toDate}
              onChange={(e) => changeTo(e.target.value)}
              required
            />
          </div>
          {error ? <p className="text-sm text-red-400">{error}</p> : null}
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={!online || !databaseReady || Boolean(terminal)}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
              title={
                !databaseReady
                  ? "Save the MySQL database binding before fetching"
                  : undefined
              }
            >
              Fetch
            </button>
          </div>
        </form>
        {results.length ? (
          <div className="mt-6 min-h-0 flex-1 overflow-auto border-t border-zinc-800">
            <table className="mt-2 w-full text-left text-sm">
              <thead className="sticky top-0 bg-zinc-900/95">
                <tr className="text-zinc-500">
                  <th className="py-2 pr-4 font-medium">Collection</th>
                  <th className="py-2 pr-4 font-medium">Records</th>
                  <th className="py-2 font-medium">Elapsed</th>
                </tr>
              </thead>
              <tbody>
                {results.map((row) => (
                  <tr key={row.id} className="border-t border-zinc-800">
                    <td className="py-3 pr-4 text-zinc-300">{row.label}</td>
                    <td className="py-3 pr-4">
                      {row.error ? (
                        <span className="text-red-400">{row.error}</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => askForRecords(row)}
                          className="text-emerald-400 hover:text-emerald-300"
                        >
                          {amountLabel(row)}
                        </button>
                      )}
                    </td>
                    <td className="py-3 font-mono text-zinc-400">{row.elapsed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
      {pending ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={closePassword}
        >
          <form
            autoComplete="off"
            className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => void confirmPassword(event)}
          >
            <h2 className="text-sm font-medium text-white">View records</h2>
            <p className="mt-2 text-sm text-zinc-400">{pending.label}</p>
            <div className="mt-4">
              <Field
                id="records_admin_password"
                label="Admin password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {passwordError ? <p className="mt-3 text-sm text-red-400">{passwordError}</p> : null}
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                disabled={checking}
                className="text-sm text-zinc-400 hover:text-zinc-100"
                onClick={closePassword}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={checking}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
              >
                {checking ? "Checking…" : "Open"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
      {open ? <RecordsModal result={open} onClose={() => setOpen(null)} /> : null}
      {terminal ? (
        <FetchTerminal
          request={terminal}
          onClose={() => setTerminal(null)}
          onResults={setResults}
        />
      ) : null}
    </>
  );
}
