import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { usePolling, fmtTime, fmtDate, fmtNum, fmtPct } from "../hooks";
import { Section } from "./Overview";

export default function TradeDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, error } = usePolling(() => api.trade(id!), 10000, [id]);

  if (error) {
    return (
      <div className="px-6 py-8 text-loss font-mono">
        ⚠ {error.message}
        <div className="mt-4">
          <Link to="/trades" className="text-neutral underline">
            ← back to trades
          </Link>
        </div>
      </div>
    );
  }

  if (!data) return <div className="p-6 text-text-muted font-mono">Loading…</div>;

  const pnl = data.pnl_pct ? parseFloat(data.pnl_pct) : null;
  const pnlColor =
    pnl === null
      ? "text-text-muted"
      : pnl > 0
        ? "text-gain glow-gain"
        : pnl < 0
          ? "text-loss glow-loss"
          : "text-text-secondary";

  return (
    <div className="px-4 sm:px-6 py-6 max-w-5xl mx-auto space-y-4">
      <div>
        <Link to="/trades" className="text-text-muted text-sm hover:text-text-primary">
          ← Trades
        </Link>
      </div>

      <div className="bg-bg-panel border border-border rounded-lg p-4 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span
                className={`px-2 py-1 text-sm font-mono font-bold rounded ${
                  data.side === "BUY"
                    ? "bg-gain-bg text-gain"
                    : "bg-loss-bg text-loss"
                }`}
              >
                {data.side}
              </span>
              <span className="font-mono text-xl font-semibold">{data.symbol}</span>
              {!data.is_closed && (
                <span className="px-2 py-1 text-xs font-mono bg-neutral/10 text-neutral border border-neutral/30 rounded">
                  OPEN
                </span>
              )}
            </div>
            <div className="text-xs font-mono text-text-muted">
              {data.trade_id}
            </div>
          </div>
          <div className="text-right">
            <div className={`text-3xl font-mono font-bold ${pnlColor}`}>
              {data.pnl_pct ? fmtPct(data.pnl_pct) : "—"}
            </div>
            <div className="text-xs font-mono text-text-muted">
              {data.pnl_usd ? `${fmtNum(data.pnl_usd)} USD` : "open · no realised PnL"}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6 text-sm">
          <KV k="Entry" v={fmtNum(data.entry_price)} sub={fmtTime(data.entry_time_ms)} />
          <KV
            k="Exit"
            v={data.exit_price ? fmtNum(data.exit_price) : "—"}
            sub={data.exit_time_ms ? fmtTime(data.exit_time_ms) : "—"}
          />
          <KV k="Size" v={fmtNum(data.size, 4)} sub="contracts" />
          <KV
            k="Exit reason"
            v={data.exit_reason ?? "—"}
            sub={data.holding_time_min ? `${data.holding_time_min} min` : "—"}
          />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3 text-sm">
          <KV
            k="Decision latency"
            v={data.latency_decision_ms ? `${data.latency_decision_ms} ms` : "—"}
          />
          <KV
            k="Slippage"
            v={data.slippage_bps ? `${data.slippage_bps} bps` : "—"}
          />
          <KV k="Date" v={fmtDate(data.entry_time_ms)} />
        </div>
      </div>

      {/* LLM payloads */}
      <Section title="Signal Candidate">
        <Json data={data.signal_candidate} />
      </Section>
      <Section title="📊 Market Analyst (Sonnet 4.6)">
        <Json data={data.market_analyst} />
      </Section>
      <Section title="🌐 Sentiment Analyst (Haiku 4.5)">
        <Json data={data.sentiment_analyst} />
      </Section>
      <Section title="🛡️ Risk Overseer (Opus 4.7)">
        <Json data={data.risk_overseer} />
      </Section>
      <Section title="🌍 Macro Analyst (Sonnet 4.6)">
        <Json data={data.macro_analyst} />
      </Section>
      <Section title="⚖️ Coordinator (Opus 4.7) — final decision">
        <Json data={data.coordinator} />
      </Section>
    </div>
  );
}

function KV({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div>
      <div className="text-text-muted text-xs uppercase font-mono tracking-wider">
        {k}
      </div>
      <div className="font-mono tabular text-text-primary mt-0.5">{v}</div>
      {sub && <div className="text-xs font-mono text-text-muted">{sub}</div>}
    </div>
  );
}

function Json({ data }: { data: Record<string, unknown> }) {
  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="px-4 py-4 text-text-muted font-mono text-sm">пусто</div>
    );
  }
  return (
    <pre className="px-4 py-3 text-xs font-mono text-text-secondary overflow-x-auto whitespace-pre-wrap leading-relaxed">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
