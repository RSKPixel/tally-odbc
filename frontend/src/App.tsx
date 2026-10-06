import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api, Me } from "./api";
import { Layout } from "./components/Layout";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Settings } from "./pages/Settings";

export default function App() {
  const [username, setUsername] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [ready, setReady] = useState(false);

  function applyMe(me: Me) {
    setUsername(me.username);
    setDisplayName(me.name);
  }

  useEffect(() => {
    api
      .me()
      .then(applyMe)
      .catch(() => {
        setUsername(null);
        setDisplayName("");
      })
      .finally(() => setReady(true));
  }, []);

  if (!ready) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-zinc-500">Loading…</div>;
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={
          username ? <Navigate to="/" replace /> : <Login onLoggedIn={applyMe} />
        }
      />
      <Route
        element={
          username ? (
            <Layout
              username={displayName || username}
              onLogout={() => {
                setUsername(null);
                setDisplayName("");
              }}
            />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      >
        <Route path="/" element={<Landing />} />
        <Route path="/settings" element={<Settings onProfileSaved={applyMe} />} />
      </Route>
      <Route path="*" element={<Navigate to={username ? "/" : "/login"} replace />} />
    </Routes>
  );
}
