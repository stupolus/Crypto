import { NavLink, Outlet } from "react-router-dom";
import { usePolling, fmtDuration } from "./hooks";
import { api } from "./api";

const navItems = [
  { to: "/", label: "Overview", end: true },
  { to: "/agents", label: "Agents" },
  { to: "/trades", label: "Trades" },
];

export default function Layout() {
  const { data: health } = usePolling(() => api.health(), 5000);

  const statusColor =
    health?.status === "ok"
      ? "text-gain"
      : health?.status === "halted"
        ? "text-loss"
        : "text-gold";
  const statusDot =
    health?.status === "ok"
      ? "bg-gain"
      : health?.status === "halted"
        ? "bg-loss"
        : "bg-gold";

  return (
    <div className="min-h-screen bg-bg text-text-primary flex flex-col">
      {/* Top bar */}
      <header className="safe-pt border-b border-border bg-bg-elevated/80 backdrop-blur sticky top-0 z-30">
        <div className="px-4 sm:px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-gold glow-gold font-mono font-bold tracking-wider text-lg">◆</span>
            <span className="font-bold tracking-wide hidden sm:inline">CRYPTO TERMINAL</span>
            <span className="font-bold tracking-wide sm:hidden">TERMINAL</span>
          </div>
          <nav className="flex items-center gap-1 ml-2 sm:ml-6 text-sm">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded transition ${
                    isActive
                      ? "bg-bg-panel text-gold border border-border-strong"
                      : "text-text-secondary hover:text-text-primary"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex-1" />
          <div className="flex items-center gap-2 text-xs">
            <span className={`inline-block w-2 h-2 rounded-full ${statusDot} animate-pulse`} />
            <span className={`font-mono uppercase ${statusColor}`}>
              {health?.status ?? "loading"}
            </span>
            <span className="text-text-muted hidden sm:inline font-mono">
              · {fmtDuration(health?.uptime_s)}
            </span>
          </div>
        </div>
      </header>

      {/* Halt banner */}
      {health?.halt_active && (
        <div className="bg-loss-bg border-b border-loss/40 px-4 sm:px-6 py-2 text-sm text-loss font-mono">
          ⛔ HALT ACTIVE · source={health.halt_reason?.source ?? "unknown"} · note=
          {health.halt_reason?.note ?? "—"}
        </div>
      )}

      {/* Content */}
      <main className="flex-1 bg-grid">
        <Outlet />
      </main>

      {/* Footer ticker */}
      <footer className="safe-pb border-t border-border bg-bg-elevated text-text-muted text-xs px-4 sm:px-6 py-2 font-mono flex items-center justify-between">
        <span>BingX VST · Layer 3 LLM Composite + Layer 6 Post-Mortem</span>
        <span className="hidden sm:inline">v0.1.0</span>
      </footer>
    </div>
  );
}
