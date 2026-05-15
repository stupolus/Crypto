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

export interface EquitySnapshot {
  timestamp_ms: number;
  equity: string;
  source: string;
}

export interface NewsItem {
  title: string;
  link: string;
  source: string;
  pub_ts_ms: number;
  summary: string;
}

export interface CandleBar {
  time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface CandlesResponse {
  symbol: string;
  interval: string;
  candles: CandleBar[];
}

export interface StrategyStat {
  strategy: string;
  symbol: string | null;
  total: number;
  open: number;
  closed: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  profit_factor: string | null;
  total_pnl_usd: string;
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
  trades: (
    opts: {
      onlyOpen?: boolean;
      onlyClosed?: boolean;
      symbol?: string;
      limit?: number;
    } = {},
  ) => {
    const q = new URLSearchParams();
    if (opts.onlyOpen) q.set("only_open", "true");
    if (opts.onlyClosed) q.set("only_closed", "true");
    if (opts.symbol) q.set("symbol", opts.symbol);
    if (opts.limit) q.set("limit", String(opts.limit));
    return json<{ trades: TradeSummary[] }>(`/api/trades?${q.toString()}`);
  },
  symbols: () => json<{ symbols: string[] }>("/api/symbols"),
  trade: (id: string) => json<TradeDetail>(`/api/trades/${encodeURIComponent(id)}`),
  strategyStats: () => json<{ strategies: StrategyStat[] }>("/api/strategy_stats"),
  equity: (limit = 100) => json<{ points: EquityPoint[] }>(`/api/equity?limit=${limit}`),
  equitySnapshots: (limit = 500) =>
    json<{ points: EquitySnapshot[] }>(`/api/equity_snapshots?limit=${limit}`),
  news: (limit = 30) => json<{ items: NewsItem[] }>(`/api/news?limit=${limit}`),
  candles: (symbol = "BTC-USDT", interval = "15m", limit = 100) =>
    json<CandlesResponse>(
      `/api/candles?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=${limit}`,
    ),
  agentHistory: (name: string, limit = 30) =>
    json<{
      agent: string;
      points: Array<{ trade_id: string; timestamp_ms: number; value: number }>;
    }>(`/api/agents/${encodeURIComponent(name)}/history?limit=${limit}`),
};
