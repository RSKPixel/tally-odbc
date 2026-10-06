import { FormEvent, useEffect, useState } from "react";
import { api, CollectionInfo, FetchResult } from "../api";
import { Field } from "./Field";
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

type Props = { online: boolean; fromDate?: string; toDate?: string; databaseReady: boolean };

export function FetchCard({ online, fromDate: tallyFrom, toDate: tallyTo, databaseReady }: Props) {
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [fromDate, setFromDate] = useState(() => clampDate(tallyFrom || todayIso(), tallyFrom, tallyTo));
  const [toDate, setToDate] = useState(() => clampDate(tallyTo || todayIso(), tallyFrom, tallyTo));
  const [results, setResults] = useState<FetchResult[]>([]);
  const [open, setOpen] = useState<FetchResult | null>(null);
  const [error, setError] = useState("");
  const [syncNote, setSyncNote] = useState("");
  const [busy, setBusy] = useState<"fetch" | "sync" | "">("");

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
    if (tallyTo) setToDate((prev) => clampDate(prev || tallyTo, tallyFrom, tallyTo));
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

  async function submit(event: FormEvent) {
    event.preventDefault();
    const names = collections.filter((row) => selected[row.id]).map((row) => row.id);
    if (!names.length) {
      setError("Select a collection");
      return;
    }
    setBusy("fetch");
    setError("");
    setSyncNote("");
    setResults([]);
    try {
      const body = await api.fetchCollections({
        collections: names,
        from_date: fromDate,
        to_date: toDate,
      });
      setResults(body.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fetch failed");
    } finally {
      setBusy("");
    }
  }

  async function sync() {
    const names = collections.filter((row) => selected[row.id]).map((row) => row.id);
    if (!names.length) {
      setError("Select a collection");
      return;
    }
    if (!databaseReady) {
      setError("Save a MySQL database first");
      return;
    }
    setBusy("sync");
    setError("");
    setSyncNote("");
    try {
      const body = await api.syncCollections({
        collections: names,
        from_date: fromDate,
        to_date: toDate,
      });
      const failed = body.results.find((row) => row.error);
      if (failed) {
        setError(failed.error);
      }
      setSyncNote(
        body.results
          .map((row) => (row.error ? `${row.label}: ${row.error}` : `${row.label} ${row.count} lines (${row.elapsed})`))
          .join(" · "),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8">
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
          {syncNote ? <p className="text-sm text-emerald-400">{syncNote}</p> : null}
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={Boolean(busy) || !online}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {busy === "fetch" ? "Fetching…" : "Fetch"}
            </button>
            <button
              type="button"
              disabled={Boolean(busy) || !online || !results.length || !databaseReady}
              title={
                !databaseReady
                  ? "Select and save a MySQL database first"
                  : !results.length
                    ? "Fetch records first"
                    : undefined
              }
              onClick={() => void sync()}
              className="rounded-lg border border-emerald-600 px-4 py-2 text-sm font-medium text-emerald-300 hover:bg-emerald-600/10 disabled:opacity-60"
            >
              {busy === "sync" ? "Syncing…" : "Sync"}
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
                          {row.count} {row.count === 1 ? "record" : "records"}
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
    </>
  );
}
