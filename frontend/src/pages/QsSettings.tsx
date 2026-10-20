import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Field, SelectField } from "../components/Field";

export function QsSettings() {
  const [company, setCompany] = useState("");
  const [database, setDatabase] = useState("");
  const [days, setDays] = useState("1");
  const [autoMinutes, setAutoMinutes] = useState("0");
  const [databases, setDatabases] = useState<string[]>([]);
  const [tallyCompany, setTallyCompany] = useState("");
  const [askPassword, setAskPassword] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .qsSettings()
      .then((row) => {
        if (cancelled) return;
        setCompany(row.company || "");
        setDatabase(row.database || "");
        setDays(String(row.days || 1));
        setAutoMinutes(String(row.auto_minutes ?? 0));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load settings");
      });
    api
      .mysqlDatabases()
      .then((row) => {
        if (!cancelled) setDatabases(row.databases);
      })
      .catch(() => undefined);
    api
      .tallyStatus()
      .then((row) => {
        if (!cancelled && row.online) setTallyCompany(row.company || "");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const databaseOptions =
    databases.includes(database) || !database ? databases : [database, ...databases];

  function openSave(event: FormEvent) {
    event.preventDefault();
    const n = Number(days);
    const auto = Number(autoMinutes);
    if (!company.trim()) {
      setError("Company name is required");
      return;
    }
    if (!database.trim()) {
      setError("Select a MySQL database");
      return;
    }
    if (!Number.isInteger(n) || n < 1 || n > 366) {
      setError("Days must be a whole number from 1 to 366");
      return;
    }
    if (!Number.isInteger(auto) || auto < 0 || auto > 24 * 60) {
      setError("Auto timer must be 0 (off) or minutes from 1 to 1440");
      return;
    }
    setError("");
    setMessage("");
    setPassword("");
    setAskPassword(true);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const n = Number(days);
    const auto = Number(autoMinutes);
    setBusy(true);
    setError("");
    try {
      const saved = await api.saveQsSettings({
        company: company.trim(),
        database: database.trim(),
        days: n,
        auto_minutes: auto,
        password,
      });
      setCompany(saved.company);
      setDatabase(saved.database);
      setDays(String(saved.days));
      setAutoMinutes(String(saved.auto_minutes ?? 0));
      setPassword("");
      setAskPassword(false);
      setMessage("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-start justify-center bg-zinc-950 p-6">
      <div className="w-full max-w-lg">
        <div className="flex items-center justify-between gap-3">
          <span
            className="text-xl font-bold tracking-[0.18em]"
            style={{ fontFamily: '"IBM Plex Sans", sans-serif' }}
          >
            <span className="text-[#f3efe6]">TALLY</span>
            <span className="text-[#e2c08a]">SYNC</span>
          </span>
          <Link to="/qs" className="text-sm text-zinc-400 hover:text-zinc-100">
            Back
          </Link>
        </div>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">Quick sync settings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Company, database, period, and optional auto sync while this page stays open.
        </p>

        <form
          onSubmit={openSave}
          autoComplete="off"
          className="mt-6 space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6"
        >
          <Field
            id="qs_company"
            label="Company name"
            type="text"
            inputMode="text"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            required
          />
          {tallyCompany ? (
            <p className="text-xs text-zinc-500">
              Currently loaded in Tally:{" "}
              <button
                type="button"
                className="text-emerald-400 hover:text-emerald-300"
                onClick={() => setCompany(tallyCompany)}
              >
                {tallyCompany}
              </button>
            </p>
          ) : null}
          <SelectField
            id="qs_database"
            label="MySQL database"
            value={database}
            onChange={(e) => setDatabase(e.target.value)}
            required
          >
            <option value="">Select database</option>
            {databaseOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </SelectField>
          <Field
            id="qs_days"
            label="Number of days"
            type="text"
            inputMode="numeric"
            value={days}
            onChange={(e) => setDays(e.target.value)}
            required
          />
          <Field
            id="qs_auto_minutes"
            label="Auto sync every (minutes)"
            type="text"
            inputMode="numeric"
            value={autoMinutes}
            onChange={(e) => setAutoMinutes(e.target.value)}
            required
          />
          <p className="text-xs text-zinc-500">
            Set to 0 to turn off. Countdown runs only while the Quick sync page is open in the browser.
          </p>
          {error && !askPassword ? <p className="text-sm text-red-400">{error}</p> : null}
          {message ? <p className="text-sm text-emerald-400">{message}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
          >
            Save
          </button>
        </form>
      </div>

      {askPassword ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => !busy && setAskPassword(false)}
        >
          <form
            autoComplete="off"
            className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => void save(event)}
          >
            <h2 className="text-sm font-medium text-white">Save quick sync settings</h2>
            <p className="mt-2 text-sm text-zinc-400">
              {company.trim()} → {database.trim()} · {days} day{days === "1" ? "" : "s"}
              {Number(autoMinutes) > 0 ? ` · every ${autoMinutes} min` : ""}
            </p>
            <div className="mt-4">
              <Field
                id="qs_superuser_password"
                label="Super user password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                disabled={busy}
                className="text-sm text-zinc-400 hover:text-zinc-100"
                onClick={() => setAskPassword(false)}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busy}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
              >
                {busy ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
