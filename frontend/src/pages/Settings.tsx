import { FormEvent, useEffect, useState } from "react";
import { api, Me } from "../api";
import { Field } from "../components/Field";

type Tab = "tally" | "profile";
type Props = { onProfileSaved: (me: Me) => void };

export function Settings({ onProfileSaved }: Props) {
  const [tab, setTab] = useState<Tab>("tally");
  const [host, setHost] = useState("officehq");
  const [port, setPort] = useState("9000");
  const [username, setUsername] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then((row) => {
        setHost(row.tally_host);
        setPort(String(row.tally_port));
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load settings"));
    api
      .profile()
      .then((row) => {
        setUsername(row.username);
        setName(row.name);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load profile"));
  }, []);

  function switchTab(next: Tab) {
    setTab(next);
    setMessage("");
    setError("");
  }

  async function saveTally(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const saved = await api.saveSettings({
        tally_host: host.trim(),
        tally_port: Number(port),
      });
      setHost(saved.tally_host);
      setPort(String(saved.tally_port));
      setMessage("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const saved = await api.saveProfile({
        username: username.trim(),
        name: name.trim(),
        password,
      });
      setUsername(saved.username);
      setName(saved.name);
      setPassword("");
      onProfileSaved(saved);
      setMessage("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  const tabClass = (id: Tab) =>
    `px-4 py-2.5 text-sm ${
      tab === id ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-100"
    }`;

  return (
    <div>
      <h1 className="text-2xl font-semibold text-white">Settings</h1>
      <div className="mt-8 overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/40">
        <div role="tablist" className="flex border-b border-zinc-800">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "tally"}
            className={tabClass("tally")}
            onClick={() => switchTab("tally")}
          >
            Tally settings
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "profile"}
            className={tabClass("profile")}
            onClick={() => switchTab("profile")}
          >
            Profile
          </button>
        </div>
        {tab === "tally" ? (
          <form
            role="tabpanel"
            onSubmit={(event) => void saveTally(event)}
            autoComplete="off"
            className="max-w-md space-y-4 p-6"
          >
            <Field
              id="tally_host"
              label="Tally host"
              type="text"
              inputMode="text"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              required
            />
            <Field
              id="tally_port"
              label="Port"
              type="text"
              inputMode="numeric"
              value={port}
              onChange={(e) => setPort(e.target.value)}
              required
            />
            {error ? <p className="text-sm text-red-400">{error}</p> : null}
            {message ? <p className="text-sm text-emerald-400">{message}</p> : null}
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {busy ? "Saving…" : "Save"}
            </button>
          </form>
        ) : (
          <form
            role="tabpanel"
            onSubmit={(event) => void saveProfile(event)}
            autoComplete="off"
            className="max-w-md space-y-4 p-6"
          >
            <Field
              id="profile_username"
              label="Username"
              type="text"
              inputMode="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
            <Field
              id="profile_name"
              label="Name"
              type="text"
              inputMode="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Field
              id="profile_password"
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {error ? <p className="text-sm text-red-400">{error}</p> : null}
            {message ? <p className="text-sm text-emerald-400">{message}</p> : null}
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {busy ? "Saving…" : "Save"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
