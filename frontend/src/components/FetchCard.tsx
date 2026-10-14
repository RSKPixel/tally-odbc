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

function amountLabel(row: { id?: string; count: number; vouchers?: number; lines?: number }) {
  if (row.vouchers != null && row.lines != null && (row.id === "sales" || row.id === "purchase")) {
    const voucherWord = row.vouchers === 1 ? "voucher" : "vouchers";
    const lineWord = row.lines === 1 ? "line" : "lines";
    return `${row.vouchers} ${voucherWord} · ${row.lines} ${lineWord}`;
  }
  const word = row.count === 1 ? "line" : "lines";
  return `${row.count} ${word}`;
}

type Props = { online: boolean; fromDate?: string; toDate?: string; databaseReady: boolean };

export function FetchCard({ online, fromDate: tallyFrom, toDate: tallyTo }: Props) {
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [fromDate, setFromDate] = useState(() => clampDate(tallyFrom || todayIso(), tallyFrom, tallyTo));
  const [toDate, setToDate] = useState(() => defaultToDate(tallyFrom, tallyTo));
  const [fullFetch, setFullFetch] = useState(false);
  const [results, setResults] = useState<FetchResult[]>([]);
  const [open, setOpen] = useState<FetchResult | null>(null);
  const [error, setError] = useState("");
  const [terminal, setTerminal] = useState<{
    collections: string[];
    from_date: string;
    to_date: string;
    full_fetch: boolean;
  } | null>(null);

  useEffect(() => {
    api
      .collections()
      .then((rows) => {
        setCollections(rows);
        setSelected(Object.fromEntries(rows.map((row) => [row.id, true])));
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load collections"));
  }, []);

  useEffect(() => {
    if (tallyFrom) setFromDate((prev) => clampDate(prev || tallyFrom, tallyFrom, tallyTo));
    if (tallyFrom || tallyTo) setToDate(defaultToDate(tallyFrom, tallyTo));
  }, [tallyFrom, tallyTo]);

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

  const shownFrom = fullFetch ? fromDate : clampDate(toDate ? addDays(toDate, -14) : fromDate, tallyFrom, toDate);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const names = collections.filter((row) => selected[row.id]).map((row) => row.id);
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
      full_fetch: fullFetch,
    });
  }

  return (
    <>
      <div className="flex h-full flex-col rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
        <form onSubmit={(event) => void submit(event)} autoComplete="off" className="space-y-6">
          <div className="flex flex-wrap gap-4">
            {collections.map((row) => (
              <label key={row.id} className="flex items-center gap-2 text-sm text-zinc-300">
                <input
                  type="checkbox"
                  checked={Boolean(selected[row.id])}
                  onChange={(event) => setSelected((prev) => ({ ...prev, [row.id]: event.target.checked }))}
                  autoComplete="new-password"
                  data-1p-ignore
                  data-lpignore="true"
                  className="size-4 rounded border-zinc-600 bg-zinc-900 text-emerald-600"
                />
                {row.label}
              </label>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={fullFetch}
              onChange={(event) => setFullFetch(event.target.checked)}
              autoComplete="new-password"
              data-1p-ignore
              data-lpignore="true"
              className="size-4 rounded border-zinc-600 bg-zinc-900 text-emerald-600"
            />
            Full fetch
          </label>
          <p className="text-sm text-zinc-500">
            {fullFetch ? "Selected period, 15 days at a time." : "Last 15 days through the To date."}
          </p>
          <div className="grid max-w-md grid-cols-2 gap-4">
            <Field
              id="from_date"
              label="From"
              type="date"
              lang="en-IN"
              min={tallyFrom || undefined}
              max={toDate || tallyTo || undefined}
              value={shownFrom}
              onChange={(e) => changeFrom(e.target.value)}
              disabled={!fullFetch}
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
              disabled={!online || Boolean(terminal)}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              Fetch
            </button>
          </div>
        </form>
        {results.length ? (
          <div className="mt-6 overflow-x-auto border-t border-zinc-800">
            <table className="mt-2 w-full text-left text-sm">
              <thead>
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
                          onClick={() => setOpen(row)}
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
