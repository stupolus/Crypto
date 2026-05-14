// Тонкий клиент над FastAPI backend.
// В dev режиме vite проксирует /api → http://127.0.0.1:8081
// В production — same origin (через nginx).

export interface HealthInfo {
  status: "ok" | "stale" | "halted";
  uptime_s: number | null;
  runner_heartbeat_age_s: number | null;
  halt_active: boolean;
  halt_reason: Record<string, string> | null;
}

export interface TradeSummary {
  trade_id: string;
  symbol: string;
  side: string;
  entry_time_ms: number;
  entry_price: string;
  exit_time_ms: number | null;
  exit_price: string | null;
  pnl_pct: string | null;
  exit_reason: string | null;
  holding_time_min: number | null;
  is_closed: boolean;
  is_win: boolean;
  is_loss: boolean;
}

export interface AgentSnapshot {
  name: string;
  last_payload: Record<string, unknown>;
  last_trade_id: string;
  last_decision_at_ms: number;
}

export interface StatusResponse {
  health: HealthInfo;
  trades: {
    total: number;
    open: number;
    closed: number;
    wins: number;
    losses: number;
    win_rate_pct: number;
  };
  open_trades: TradeSummary[];
}

export interface TradeDetail {
  trade_id: string;
  symbol: string;
  side: string;
  entry_time_ms: number;
  entry_price: string;
  size: string;
  exit_time_ms: number | null;
  exit_price: string | null;
  pnl_usd: string | null;
  pnl_pct: string | null;
  exit_reason: string | null;
  holding_time_min: number | null;
  latency_decision_ms: number | null;
  latency_execution_ms: number | null;
  slippage_bps: string | null;
  is_closed: boolean;
  is_win: boolean;
  is_loss: boolean;
  signal_candidate: Record<string, unknown>;
  market_analyst: Record<string, unknown>;
  sentiment_analyst: Record<string, unknown>;
  risk_overseer: Record<string, unknown>;
  macro_analyst: Record<string, unknown>;
  coordinator: Record<string, unknown>;
}

export interface EquityPoint {
  timestamp_ms: number;
  cumulative_pnl_usd: string;
  pnl_usd: string;
  trade_id: string;
}

const API_BASE = ""; // same origin in prod, vite proxy in dev

async function json<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) {
    throw new Error(`${resp.status} ${resp.statusText}: ${path}`);
  }
  return resp.json();
}

export const api = {
  health: () => json<HealthInfo>("/api/health"),
  status: () => json<StatusResponse>("/api/status"),
  agents: () => json<{ agents: AgentSnapshot[] }>("/api/agents"),
  trades: (opts: { onlyOpen?: boolean; onlyClosed?: boolean; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (opts.onlyOpen) q.set("only_open", "true");
    if (opts.onlyClosed) q.set("only_closed", "true");
    if (opts.limit) q.set("limit", String(opts.limit));
    return json<{ trades: TradeSummary[] }>(`/api/trades?${q.toString()}`);
  },
  trade: (id: string) => json<TradeDetail>(`/api/trades/${encodeURIComponent(id)}`),
  equity: (limit = 100) => json<{ points: EquityPoint[] }>(`/api/equity?limit=${limit}`),
};
