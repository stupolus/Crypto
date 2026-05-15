import { useState } from "react";

type Payload = Record<string, unknown>;

interface AgentSpec {
  title: string;
  /** Главный вывод агента одной строкой. */
  headline: (p: Payload) => string;
  /** Confidence 0..1 если есть. */
  confidence: (p: Payload) => number | null;
  /** Развёрнутое объяснение. */
  reasoning: (p: Payload) => string | null;
}

function s(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

function num(v: unknown): number | null {
  if (typeof v === "number" && isFinite(v)) return v;
  if (typeof v === "string") {
    const n = parseFloat(v);
    if (isFinite(n)) return n;
  }
  return null;
}

const SPECS: Record<string, AgentSpec> = {
  market_analyst: {
    title: "📊 Market Analyst",
    headline: (p) => `${s(p.state)} · vol ${s(p.volatility)} · liq ${s(p.liquidity)}`,
    confidence: () => null,
    reasoning: (p) => (p.notes ? s(p.notes) : null),
  },
  sentiment_analyst: {
    title: "🌐 Sentiment Analyst",
    headline: (p) => `score ${s(p.sentiment_score)}`,
    confidence: (p) => num(p.confidence),
    reasoning: (p) =>
      Array.isArray(p.key_events) && p.key_events.length
        ? (p.key_events as unknown[]).map(s).join("; ")
        : null,
  },
  risk_overseer: {
    title: "🛡️ Risk Overseer",
    headline: (p) =>
      p.approved === true
        ? `APPROVED · max ${s(p.max_risk_pct)}%`
        : p.approved === false
          ? "VETO"
          : "—",
    confidence: (p) => num(p.confidence),
    reasoning: (p) => {
      const r = p.reasoning ? s(p.reasoning) : "";
      const c =
        Array.isArray(p.concerns) && p.concerns.length
          ? ` | concerns: ${(p.concerns as unknown[]).map(s).join("; ")}`
          : "";
      return r || c ? `${r}${c}` : null;
    },
  },
  macro_analyst: {
    title: "🌍 Macro Analyst",
    headline: (p) =>
      `${s(p.regime)}${p.portfolio_hedge_recommended ? " · hedge recommended" : ""}`,
    confidence: (p) => num(p.confidence),
    reasoning: (p) => (p.rationale ? s(p.rationale) : null),
  },
  coordinator: {
    title: "⚖️ Coordinator — final decision",
    headline: (p) => `${s(p.action)} · risk ${s(p.size_risk_pct)}%`,
    confidence: (p) => num(p.composite_confidence),
    reasoning: (p) => (p.reasoning ? s(p.reasoning) : null),
  },
};

function confColor(c: number): string {
  return c >= 0.7 ? "text-gain" : c >= 0.5 ? "text-gold" : "text-loss";
}

export default function AgentCard({
  agent,
  payload,
}: {
  agent: keyof typeof SPECS;
  payload: Payload;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const spec = SPECS[agent];
  const empty = !payload || Object.keys(payload).length === 0;

  return (
    <div className="bg-bg-panel border border-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-bg-elevated">
        <h2 className="text-xs font-mono uppercase tracking-wider text-text-secondary">
          {spec.title}
        </h2>
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="text-xs font-mono text-text-muted hover:text-text-primary"
        >
          {showRaw ? "hide raw" : "raw json"}
        </button>
      </div>

      {empty ? (
        <div className="px-4 py-4 text-text-muted font-mono text-sm">пусто</div>
      ) : (
        <div className="p-4 space-y-2">
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-mono text-sm">{spec.headline(payload)}</span>
            {spec.confidence(payload) !== null && (
              <span
                className={`font-mono text-sm ${confColor(spec.confidence(payload)!)}`}
              >
                conf {(spec.confidence(payload)! * 100).toFixed(0)}%
              </span>
            )}
          </div>
          {spec.reasoning(payload) && (
            <div className="text-xs font-mono text-text-muted leading-relaxed">
              {spec.reasoning(payload)}
            </div>
          )}
        </div>
      )}

      {showRaw && (
        <pre className="px-4 py-3 text-xs font-mono text-text-secondary overflow-x-auto whitespace-pre-wrap leading-relaxed border-t border-border">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </div>
  );
}
