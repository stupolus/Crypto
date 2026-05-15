import { Link } from "react-router-dom";
import { api, type AgentSnapshot } from "../api";
import { usePolling, fmtTime, fmtDate } from "../hooks";

const AGENT_META: Record<
  string,
  { displayName: string; model: string; tagline: string; emoji: string }
> = {
  market_analyst: {
    displayName: "Market Analyst",
    model: "Sonnet 4.6",
    tagline: "Технические уровни, режим рынка",
    emoji: "📊",
  },
  sentiment_analyst: {
    displayName: "Sentiment Analyst",
    model: "Haiku 4.5",
    tagline: "Twitter sentiment, новостной фон",
    emoji: "🌐",
  },
  risk_overseer: {
    displayName: "Risk Overseer",
    model: "Opus 4.7",
    tagline: "Veto power, риск-метрики",
    emoji: "🛡️",
  },
  macro_analyst: {
    displayName: "Macro Analyst",
    model: "Sonnet 4.6",
    tagline: "DXY, VIX, regime",
    emoji: "🌍",
  },
  coordinator: {
    displayName: "Coordinator",
    model: "Opus 4.7",
    tagline: "Синтез финального TradeProposal",
    emoji: "⚖️",
  },
};

export default function Agents() {
  const { data, error } = usePolling(() => api.agents(), 10000);

  if (error) return <div className="p-6 text-loss font-mono">⚠ {error.message}</div>;
  if (!data) return <div className="p-6 text-text-muted font-mono">Loading…</div>;

  return (
    <div className="px-4 sm:px-6 py-6 max-w-7xl mx-auto space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {data.agents.map((agent) => (
          <AgentCard key={agent.name} agent={agent} />
        ))}
      </div>
    </div>
  );
}

function AgentCard({ agent }: { agent: AgentSnapshot }) {
  const meta = AGENT_META[agent.name] ?? {
    displayName: agent.name,
    model: "?",
    tagline: "",
    emoji: "•",
  };
  const hasData = agent.last_trade_id !== "";
  const decision = extractDecisionLine(agent);
  const confidence = extractConfidence(agent);

  return (
    <div className="bg-bg-panel border border-border rounded-lg overflow-hidden hover:border-border-strong transition">
      <div className="p-4 border-b border-border flex items-start gap-3">
        <div className="text-3xl">{meta.emoji}</div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold truncate">{meta.displayName}</div>
          <div className="text-xs text-text-muted font-mono mt-0.5">{meta.tagline}</div>
        </div>
        <span className="text-xs font-mono text-gold px-2 py-0.5 bg-bg-elevated border border-border-strong rounded">
          {meta.model}
        </span>
      </div>

      <div className="p-4 space-y-3">
        {!hasData ? (
          <div className="text-text-muted text-sm font-mono">
            нет данных · ждём первой сделки
          </div>
        ) : (
          <>
            <div className="text-sm">
              <div className="text-text-muted text-xs uppercase font-mono mb-1">
                Last decision
              </div>
              <div className="font-mono">{decision}</div>
            </div>

            {confidence !== null && (
              <div>
                <div className="flex justify-between text-xs font-mono mb-1">
                  <span className="text-text-muted uppercase">Confidence</span>
                  <span
                    className={
                      confidence >= 0.7
                        ? "text-gain"
                        : confidence >= 0.5
                          ? "text-gold"
                          : "text-loss"
                    }
                  >
                    {(confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all ${
                      confidence >= 0.7
                        ? "bg-gain"
                        : confidence >= 0.5
                          ? "bg-gold"
                          : "bg-loss"
                    }`}
                    style={{ width: `${confidence * 100}%` }}
                  />
                </div>
              </div>
            )}

            <ConfidenceHistory agentName={agent.name} />

            <div className="flex justify-between text-xs font-mono text-text-muted pt-2 border-t border-border">
              <Link
                to={`/trades/${agent.last_trade_id}`}
                className="hover:text-text-primary truncate max-w-[60%]"
              >
                ↗ {agent.last_trade_id.slice(0, 12)}
              </Link>
              <span>
                {fmtDate(agent.last_decision_at_ms)} {fmtTime(agent.last_decision_at_ms)}
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ConfidenceHistory({ agentName }: { agentName: string }) {
  const { data } = usePolling(() => api.agentHistory(agentName, 30), 20000, [agentName]);
  if (!data || data.points.length < 2) return null;
  // DESC time → ASC для отрисовки слева-направо
  const values = [...data.points].reverse().map((p) => p.value);
  return (
    <div>
      <div className="flex justify-between text-xs font-mono text-text-muted mb-1">
        <span className="uppercase">History (last {values.length})</span>
        <span>0..1</span>
      </div>
      <MicroSparkline values={values} height={36} />
    </div>
  );
}

function MicroSparkline({ values, height = 32 }: { values: number[]; height?: number }) {
  const w = 280;
  const h = height;
  const pad = 2;
  const min = 0;
  const max = 1;
  const xs = values.map((_, i) => pad + (i * (w - pad * 2)) / Math.max(1, values.length - 1));
  const ys = values.map((v) => h - pad - ((v - min) / (max - min)) * (h - pad * 2));
  const path = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x},${ys[i]}`).join(" ");
  const last = values[values.length - 1];
  const stroke = last >= 0.7 ? "#00ff88" : last >= 0.5 ? "#d4af37" : "#ff4d4d";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full">
      <line
        x1={pad}
        y1={h / 2}
        x2={w - pad}
        y2={h / 2}
        stroke="#21262d"
        strokeDasharray="2,3"
      />
      <path d={path} fill="none" stroke={stroke} strokeWidth="1.5" />
      <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r="2" fill={stroke} />
    </svg>
  );
}

function extractDecisionLine(agent: AgentSnapshot): string {
  const p = agent.last_payload;
  if (agent.name === "coordinator") {
    const action = (p.action as string) ?? "?";
    return `${action}`;
  }
  if (agent.name === "market_analyst") {
    return (p.state as string) ?? "?";
  }
  if (agent.name === "sentiment_analyst") {
    const score = p.sentiment_score;
    return score !== undefined ? `score ${score}` : "?";
  }
  if (agent.name === "risk_overseer") {
    return p.approved === true ? "APPROVED" : p.approved === false ? "VETO" : "?";
  }
  if (agent.name === "macro_analyst") {
    return (p.regime as string) ?? "?";
  }
  return JSON.stringify(p).slice(0, 60);
}

function extractConfidence(agent: AgentSnapshot): number | null {
  const p = agent.last_payload;
  const candidates = [p.composite_confidence, p.confidence];
  for (const c of candidates) {
    if (typeof c === "number" && isFinite(c)) return Math.max(0, Math.min(1, c));
  }
  return null;
}
