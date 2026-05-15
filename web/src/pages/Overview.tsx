import { Link } from "react-router-dom";
import { api, type StatusResponse } from "../api";
import { useSse, usePolling, fmtNum, fmtPct, fmtTime } from "../hooks";

export default function Overview() {
  // SSE для realtime (5s server-pushed) + polling fallback на случай
  // что EventSource заблокирован proxy.
  const { data: sseData } = useSse<StatusResponse>("/stream/events", "status");
  const { data: pollData, error } = usePolling(() => api.status(), 10000);
  const data = sseData ?? pollData;
  const { data: equity } = usePolling(() => api.equity(50), 30000);

  if (error) {
    return (
      <div className="p-6 text-loss font-mono">
        ⚠ {error.message}
      </div>
    );
  }

  if (!data) {
    return <div className="p-6 text-text-muted font-mono">Loading…</div>;
  }

  const winRateColor =
    data.trades.win_rate_pct >= 50
      ? "text-gain glow-gain"
      : data.trades.win_rate_pct >= 35
        ? "text-gold"
        : "text-loss";

  return (
    <div className="px-4 sm:px-6 py-6 max-w-7xl mx-auto space-y-6">
      {/* Top stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="TOTAL"
          value={String(data.trades.total)}
          accent="text-text-primary"
        />
        <StatCard
          label="OPEN"
          value={String(data.trades.open)}
          accent="text-neutral"
        />
        <StatCard
          label="WIN RATE"
          value={`${data.trades.win_rate_pct.toFixed(1)}%`}
          accent={winRateColor}
          sub={`${data.trades.wins}W / ${data.trades.losses}L`}
        />
        <StatCard
          label="STATUS"
          value={data.health.status.toUpperCase()}
          accent={
            data.health.status === "ok"
              ? "text-gain"
              : data.health.status === "halted"
                ? "text-loss"
                : "text-gold"
          }
          sub={
            data.health.runner_heartbeat_age_s != null
              ? `hb ${Math.floor(data.health.runner_heartbeat_age_s)}s`
              : undefined
          }
        />
      </div>

      {/* Open positions */}
      <Section title="Open Positions">
        {data.open_trades.length === 0 ? (
          <div className="px-4 py-8 text-center text-text-muted font-mono text-sm">
            нет открытых позиций · ждём сигнала
          </div>
        ) : (
          <div className="divide-y divide-border">
            {data.open_trades.map((t) => (
              <Link
                key={t.trade_id}
                to={`/trades/${t.trade_id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-bg-elevated transition"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`px-2 py-0.5 text-xs font-mono font-bold rounded ${
                      t.side === "BUY"
                        ? "bg-gain-bg text-gain"
                        : "bg-loss-bg text-loss"
                    }`}
                  >
                    {t.side}
                  </span>
                  <span className="font-mono font-semibold">{t.symbol}</span>
                  <span className="text-text-muted text-xs font-mono hidden sm:inline">
                    {fmtTime(t.entry_time_ms)} UTC
                  </span>
                </div>
                <div className="text-right">
                  <div className="font-mono tabular text-sm">{fmtNum(t.entry_price)}</div>
                  <div className="text-xs text-text-muted font-mono">entry</div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </Section>

      {/* Equity curve */}
      <Section title="Cumulative PnL Curve">
        {!equity || equity.points.length === 0 ? (
          <div className="px-4 py-8 text-center text-text-muted font-mono text-sm">
            нет закрытых сделок · {data.trades.total === 0 ? "ждём первого сигнала" : "все позиции открыты"}
          </div>
        ) : (
          <Sparkline
            points={equity.points.map((p) => parseFloat(p.cumulative_pnl_usd))}
            height={160}
          />
        )}
      </Section>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  accent = "text-text-primary",
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="bg-bg-panel border border-border rounded-lg p-3">
      <div className="text-xs text-text-muted font-mono uppercase tracking-wider">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-mono font-bold ${accent}`}>{value}</div>
      {sub && <div className="text-xs text-text-muted font-mono mt-1">{sub}</div>}
    </div>
  );
}

export function Section({
  title,
  right,
  children,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-bg-panel border border-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-bg-elevated">
        <h2 className="text-xs font-mono uppercase tracking-wider text-text-secondary">
          {title}
        </h2>
        {right}
      </div>
      {children}
    </div>
  );
}

function Sparkline({ points, height = 100 }: { points: number[]; height?: number }) {
  if (points.length < 2) {
    return (
      <div className="p-4 text-text-muted font-mono text-sm">
        точек: {points.length} · нужно ≥2 для графика
      </div>
    );
  }
  const w = 800;
  const h = height;
  const pad = 16;
  const min = Math.min(...points, 0);
  const max = Math.max(...points, 0);
  const range = Math.max(max - min, 1);
  const xs = points.map((_, i) => pad + (i * (w - pad * 2)) / (points.length - 1));
  const ys = points.map(
    (v) => h - pad - ((v - min) / range) * (h - pad * 2),
  );
  const path = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x},${ys[i]}`).join(" ");
  const last = points[points.length - 1];
  const isUp = last >= 0;
  const stroke = isUp ? "#00ff88" : "#ff4d4d";
  const zeroY = h - pad - ((0 - min) / range) * (h - pad * 2);

  // Fade area under curve
  const areaPath =
    `M${xs[0]},${zeroY} ` +
    xs.map((x, i) => `L${x},${ys[i]}`).join(" ") +
    ` L${xs[xs.length - 1]},${zeroY} Z`;

  return (
    <div className="p-4">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full">
        <defs>
          <linearGradient id="grad" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.3" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Zero line */}
        <line
          x1={pad}
          y1={zeroY}
          x2={w - pad}
          y2={zeroY}
          stroke="#30363d"
          strokeDasharray="3,3"
        />
        <path d={areaPath} fill="url(#grad)" />
        <path d={path} fill="none" stroke={stroke} strokeWidth="2" />
        {/* Last point dot */}
        <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r="3" fill={stroke} />
      </svg>
      <div className="flex justify-between mt-2 text-xs font-mono text-text-muted">
        <span>min: {fmtNum(String(min))}</span>
        <span className={isUp ? "text-gain" : "text-loss"}>
          {fmtPct(((last / (Math.abs(min) || 1)) * 100).toFixed(2))} · last {fmtNum(String(last))}
        </span>
        <span>max: {fmtNum(String(max))}</span>
      </div>
    </div>
  );
}
