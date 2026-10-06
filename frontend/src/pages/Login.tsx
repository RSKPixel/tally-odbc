import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Me } from "../api";
import { Field } from "../components/Field";

type Props = { onLoggedIn: (me: Me) => void };

export function Login({ onLoggedIn }: Props) {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const me = await api.login(username, password);
      onLoggedIn(me);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <form
        onSubmit={(event) => void submit(event)}
        autoComplete="off"
        className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-900/70 p-8 shadow-xl shadow-black/40"
      >
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-emerald-500">Tally sync</p>
        <h1 className="mt-2 text-2xl font-semibold text-white">Sign in</h1>
        <div className="mt-6 space-y-4">
          <Field
            id="username"
            label="Username"
            type="text"
            inputMode="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <Field
            id="password"
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}
        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
