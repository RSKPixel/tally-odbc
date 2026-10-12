import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";

type Props = {
  username: string;
  onLogout: () => void;
};

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm ${
    isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-100"
  }`;

export function Layout({ username, onLogout }: Props) {
  const navigate = useNavigate();

  async function logout() {
    await api.logout();
    onLogout();
    navigate("/login");
  }

  return (
    <div className="flex h-screen w-full flex-col bg-zinc-950">
      <header className="flex w-full items-center justify-between border-b border-zinc-800 px-[5%] py-3">
        <div className="flex items-center gap-6">
          <span className="text-sm font-semibold tracking-tight text-emerald-400">Tally sync</span>
          <nav className="flex gap-1">
            <NavLink to="/" className={linkClass} end>
              Home
            </NavLink>
            <NavLink to="/settings" className={linkClass}>
              Settings
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-zinc-500">{username}</span>
          <button
            type="button"
            onClick={() => void logout()}
            className="text-zinc-400 hover:text-zinc-100"
          >
            Log out
          </button>
        </div>
      </header>
      <main className="flex min-h-0 w-full flex-1 flex-col p-[5%]">
        <Outlet />
      </main>
    </div>
  );
}
