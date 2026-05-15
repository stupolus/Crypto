import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { usePolling, fmtTime, fmtNum, fmtPct } from "../hooks";

type FilterMode = "all" | "open" | "closed";

export default function Trades() {
  const [filter, setFilter] = useState<FilterMode>("all");
  const [symbol, setSymbol] = useState<string>("");
  const { data, error } = usePolling(
    () =>
      api.trades({
        onlyOpen: filter === "open",
        onlyClosed: filter === "closed",
        symbol: symbol || undefined,
        limit: 100,
      }),
    7000,
    [filter, symbol],
  );
  const { data: symbolsData } = usePolling(() => api.symbols(), 60000);

  return (
    <div className="px-4 sm:px-6 py-6 max-w-7xl mx-auto space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-bold uppercase tracking-wider">Trade Journal</h1>
        <div className="flex flex-wrap gap-2 items-center">
          {symbolsData && symbolsData.symbols.length > 1 && (
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-bg-panel border border-border rounded-md px-3 py-1 text-xs font-mono text-text-primary"
            >
              <option value="">all symbols</option>
              {symbolsData.symbols.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          )}
          <div className="flex gap-1 bg-bg-panel border border-border rounded-md p-1">
            {(["all", "open", "closed"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setFilter(mode)}
                className={`px-3 py-1 text-xs font-mono uppercase rounded transition ${
                  filter === mode
                    ? "bg-bg-elevated text-gold border border-border-strong"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <div className="text-loss font-mono">⚠ {error.message}</div>}

      {data && (
        <div className="bg-bg-panel border border-border rounded-lg overflow-hidden">
          {data.trades.length === 0 ? (
            <div className="px-4 py-12 text-center text-text-muted font-mono text-sm">
              нет сделок в этой выборке
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-bg-elevated border-b border-border text-xs font-mono text-text-muted uppercase">
                <tr>
                  <th className="text-left px-4 py-2 font-normal">Trade</th>
                  <th className="text-left px-4 py-2 font-normal hidden sm:table-cell">
                    Time
                  </th>
                  <th className="text-right px-4 py-2 font-normal">Entry</th>
                  <th className="text-right px-4 py-2 font-normal hidden md:table-cell">
                    Exit
                  </th>
                  <th className="text-right px-4 py-2 font-normal">PnL</th>
                  <th className="text-right px-4 py-2 font-normal hidden sm:table-cell">
                    Reason
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.trades.map((t) => {
                  const pnl = t.pnl_pct ? parseFloat(t.pnl_pct) : null;
                  const pnlColor =
                    pnl === null
                      ? "text-text-muted"
                      : pnl > 0
                        ? "text-gain"
                        : pnl < 0
                          ? "text-loss"
                          : "text-text-secondary";
                  return (
                    <tr
                      key={t.trade_id}
                      className="border-b border-border last:border-0 hover:bg-bg-elevated transition"
                    >
                      <td className="px-4 py-2.5">
                        <Link
                          to={`/trades/${t.trade_id}`}
                          className="flex items-center gap-2 hover:text-gold"
                        >
                          <span
                            className={`px-1.5 py-0.5 text-xs font-mono font-bold rounded ${
                              t.side === "BUY"
                                ? "bg-gain-bg text-gain"
                                : "bg-loss-bg text-loss"
                            }`}
                          >
                            {t.side}
                          </span>
                          <span className="font-mono">{t.symbol}</span>
                          {!t.is_closed && (
                            <span className="text-neutral text-xs font-mono">●</span>
                          )}
                        </Link>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-text-muted hidden sm:table-cell">
                        {fmtTime(t.entry_time_ms)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular">
                        {fmtNum(t.entry_price)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular hidden md:table-cell">
                        {t.exit_price ? fmtNum(t.exit_price) : "—"}
                      </td>
                      <td
                        className={`px-4 py-2.5 text-right font-mono tabular font-semibold ${pnlColor}`}
                      >
                        {t.pnl_pct ? fmtPct(t.pnl_pct) : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-right text-xs font-mono text-text-muted hidden sm:table-cell">
                        {t.exit_reason ?? "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
