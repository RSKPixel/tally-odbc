import { FormEvent, useEffect, useState } from "react";
import { api, TallyStatus } from "../api";
import { FetchCard } from "../components/FetchCard";
import { Field, SelectField } from "../components/Field";
import { formatDate } from "../dates";

export function Landing() {
  const [status, setStatus] = useState<TallyStatus | null>(null);
  const [error, setError] = useState("");
  const [databases, setDatabases] = useState<string[]>([]);
  const [database, setDatabase] = useState("");
  const [savedDatabase, setSavedDatabase] = useState("");
  const [askPassword, setAskPassword] = useState(false);
  const [password, setPassword] = useState("");
  const [saveError, setSaveError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .tallyStatus()
      .then((row) => {
        if (!cancelled) setStatus(row);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load Tally status");
      });
    api
      .mysqlDatabases()
      .then((row) => {
        if (!cancelled) setDatabases(row.databases);
      })
      .catch((err: unknown) => {
        if (!cancelled) setSaveError(err instanceof Error ? err.message : "Could not load MySQL databases");
      });
    api
      .mysqlBinding()
      .then((row) => {
        if (cancelled) return;
        setSavedDatabase(row.database);
        if (row.database) setDatabase(row.database);
      })
      .catch(() => {
        /* Tally offline or extra companies */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const extraCompanies = (status?.companies?.length ?? 0) > 1;
  const extras = (status?.companies ?? []).filter((name) => name !== status?.company);
  const canSave = Boolean(status?.online && status.company && !extraCompanies && database);
  const databaseReady = Boolean(savedDatabase && database === savedDatabase);
  const databaseOptions = databases.includes(database) || !database ? databases : [database, ...databases];

  function openSave() {
    if (!database.trim()) {
      setSaveError("Select a MySQL database");
      return;
    }
    setSaveError("");
    setSaveMessage("");
    setPassword("");
    setAskPassword(true);
  }

  async function saveBinding(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setSaveError("");
    try {
      const saved = await api.saveMysqlBinding({ database: database.trim(), password });
      setSavedDatabase(saved.database);
      setDatabase(saved.database);
      setPassword("");
      setAskPassword(false);
      setSaveMessage(`Saved ${saved.database} for ${saved.company}`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save database");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      {error ? <p className="text-sm text-red-400">{error}</p> : null}
      {!status && !error ? <p className="text-sm text-zinc-500">Checking Tally…</p> : null}
      {status ? (
        <>
          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8">
            <p className="text-xs uppercase tracking-wider text-zinc-500">Tally server</p>
            <p className="mt-1 font-mono text-sm text-zinc-300">{status.url}</p>
            {status.online ? (
              <>
                <p className="mt-6 text-xs uppercase tracking-wider text-emerald-600">Loaded company</p>
                <p className="mt-2 text-2xl font-medium text-white">{status.company}</p>
                {extraCompanies ? (
                  <p className="mt-3 text-sm text-amber-400">
                    Close extra companies in Tally and keep only one open
                    {extras.length ? `: ${extras.join(", ")}` : ""}.
                  </p>
                ) : null}
                {status.from_date && status.to_date ? (
                  <p className="mt-3 font-mono text-sm text-zinc-400">
                    {formatDate(status.from_date)} – {formatDate(status.to_date)}
                  </p>
                ) : null}
                <div className="mt-6 flex max-w-md items-end gap-3">
                  <div className="min-w-0 flex-1">
                    <SelectField
                      id="mysql_database"
                      label="MySQL database"
                      value={database}
                      onChange={(e) => {
                        setDatabase(e.target.value);
                        setSaveMessage("");
                      }}
                    >
                      <option value="">Select database</option>
                      {databaseOptions.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </SelectField>
                  </div>
                  <button
                    type="button"
                    disabled={!canSave || saving}
                    onClick={openSave}
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
                  >
                    Save
                  </button>
                </div>
                {saveError ? <p className="mt-3 text-sm text-red-400">{saveError}</p> : null}
                {saveMessage ? <p className="mt-3 text-sm text-emerald-400">{saveMessage}</p> : null}
              </>
            ) : (
              <>
                <p className="mt-6 text-sm text-amber-400">Tally is not reachable</p>
                <p className="mt-2 text-sm text-zinc-400">{status.error}</p>
              </>
            )}
          </div>
          <FetchCard
            online={status.online && !extraCompanies}
            fromDate={status.from_date}
            toDate={status.to_date}
            databaseReady={databaseReady}
          />
        </>
      ) : null}
      {askPassword ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => !saving && setAskPassword(false)}
        >
          <form
            autoComplete="off"
            className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => void saveBinding(event)}
          >
            <h2 className="text-sm font-medium text-white">Save MySQL database</h2>
            <p className="mt-2 text-sm text-zinc-400">
              {status?.company} → {database.trim()}
            </p>
            <div className="mt-4">
              <Field
                id="superuser_password"
                label="Super user password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {saveError ? <p className="mt-3 text-sm text-red-400">{saveError}</p> : null}
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                disabled={saving}
                className="text-sm text-zinc-400 hover:text-zinc-100"
                onClick={() => setAskPassword(false)}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
