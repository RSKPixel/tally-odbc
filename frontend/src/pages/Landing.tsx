import { FormEvent, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api, CollectionInfo } from "../api";
import { FetchCard } from "../components/FetchCard";
import { Field, SelectField } from "../components/Field";
import { LayoutContext } from "../components/Layout";

export function Landing() {
  const { status, statusError } = useOutletContext<LayoutContext>();
  const [databases, setDatabases] = useState<string[]>([]);
  const [database, setDatabase] = useState("");
  const [savedDatabase, setSavedDatabase] = useState("");
  const [askPassword, setAskPassword] = useState(false);
  const [password, setPassword] = useState("");
  const [saveError, setSaveError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [collectionsError, setCollectionsError] = useState("");
  const [mode, setMode] = useState<"quick" | "full">("quick");

  useEffect(() => {
    let cancelled = false;
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
    api
      .collections()
      .then((rows) => {
        if (cancelled) return;
        setCollections(rows);
        setSelected(
          Object.fromEntries(rows.map((row) => [row.id, row.id !== "daybook"])),
        );
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setCollectionsError(err instanceof Error ? err.message : "Could not load collections");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function changeMode(next: "quick" | "full") {
    setMode(next);
    setSelected((prev) => ({
      ...prev,
      daybook: next === "full" ? true : false,
    }));
  }

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
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
      {statusError ? <p className="shrink-0 text-sm text-red-400">{statusError}</p> : null}
      {!status && !statusError ? <p className="shrink-0 text-sm text-zinc-500">Checking Tally…</p> : null}
      {status ? (
        <>
          <div className="grid min-h-0 flex-1 grid-cols-2 items-stretch gap-6 overflow-hidden">
            <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6">
              <p className="text-xs uppercase tracking-wider text-zinc-500">MySQL binding</p>
              {status.online ? (
                <>
                  {extraCompanies ? (
                    <p className="mt-3 text-sm text-amber-400">
                      Close extra companies in Tally and keep only one open
                      {extras.length ? `: ${extras.join(", ")}` : ""}.
                    </p>
                  ) : null}
                  <div className="mt-4 flex max-w-md items-end gap-3">
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
                  {savedDatabase && database === savedDatabase ? (
                    <p className="mt-3 text-sm text-zinc-500">Saved database: {savedDatabase}</p>
                  ) : null}
                  <div className="mt-6 flex min-h-0 flex-1 flex-col overflow-hidden border-t border-zinc-800 pt-4">
                    <p className="shrink-0 text-xs uppercase tracking-wider text-zinc-500">Mode</p>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      {(
                        [
                          ["quick", "Quick"],
                          ["full", "Full"],
                        ] as const
                      ).map(([id, label]) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() => changeMode(id)}
                          className={`rounded-lg border px-3 py-2 text-sm ${
                            mode === id
                              ? "border-emerald-600 bg-emerald-600/15 text-emerald-300"
                              : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <p className="mt-4 shrink-0 text-xs uppercase tracking-wider text-zinc-500">Collections</p>
                    {collectionsError ? <p className="mt-3 shrink-0 text-sm text-red-400">{collectionsError}</p> : null}
                    <div className="mt-3 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
                      {collections.map((row) => {
                        const daybookLocked = mode === "quick" && row.id === "daybook";
                        return (
                          <label
                            key={row.id}
                            className={`flex items-center gap-2 text-sm ${
                              daybookLocked ? "text-zinc-600" : "text-zinc-300"
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={daybookLocked ? false : Boolean(selected[row.id])}
                              disabled={daybookLocked}
                              onChange={(event) =>
                                setSelected((prev) => ({ ...prev, [row.id]: event.target.checked }))
                              }
                              autoComplete="new-password"
                              data-1p-ignore
                              data-lpignore="true"
                              className="size-4 shrink-0 rounded border-zinc-600 bg-zinc-900 text-emerald-600 disabled:opacity-40"
                            />
                            <span className="min-w-0 truncate" title={row.label}>
                              {row.label}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
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
              collections={collections}
              selected={selected}
              fullFetch={mode === "full"}
            />
          </div>
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
