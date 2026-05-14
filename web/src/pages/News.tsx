import { api } from "../api";
import { usePolling, fmtTime, fmtDate } from "../hooks";

export default function News() {
  const { data, error } = usePolling(() => api.news(40), 60_000);

  if (error)
    return <div className="p-6 text-loss font-mono">⚠ {error.message}</div>;

  if (!data)
    return <div className="p-6 text-text-muted font-mono">Loading…</div>;

  return (
    <div className="px-4 sm:px-6 py-6 max-w-4xl mx-auto space-y-3">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-lg font-bold uppercase tracking-wider">News Feed</h1>
        <span className="text-xs font-mono text-text-muted">
          обновляется каждые 60s
        </span>
      </div>

      {data.items.length === 0 ? (
        <div className="bg-bg-panel border border-border rounded-lg px-4 py-12 text-center text-text-muted font-mono text-sm">
          лента пуста · RSS-источники могут быть недоступны
        </div>
      ) : (
        <div className="space-y-2">
          {data.items.map((item, idx) => (
            <NewsCard key={`${item.link}-${idx}`} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function NewsCard({
  item,
}: {
  item: {
    title: string;
    link: string;
    source: string;
    pub_ts_ms: number;
    summary: string;
  };
}) {
  const sourceColors: Record<string, string> = {
    CoinDesk: "text-gold border-gold/30 bg-gold/5",
    Cointelegraph: "text-neutral border-neutral/30 bg-neutral/5",
    Decrypt: "text-gain border-gain/30 bg-gain/5",
  };
  const sc = sourceColors[item.source] ?? "text-text-muted border-border bg-bg-elevated";

  return (
    <a
      href={item.link}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-bg-panel border border-border rounded-lg p-4 hover:border-border-strong transition group"
    >
      <div className="flex items-start gap-3">
        <span
          className={`shrink-0 px-2 py-0.5 text-xs font-mono uppercase rounded border ${sc}`}
        >
          {item.source}
        </span>
        <div className="flex-1 min-w-0">
          <div className="font-semibold leading-snug group-hover:text-gold transition">
            {item.title}
          </div>
          {item.summary && (
            <div className="mt-1 text-sm text-text-secondary line-clamp-2">
              {item.summary}
            </div>
          )}
        </div>
        <span className="shrink-0 text-xs font-mono text-text-muted text-right whitespace-nowrap">
          {fmtTime(item.pub_ts_ms)}
          <div className="text-text-muted/60">{fmtDate(item.pub_ts_ms)}</div>
        </span>
      </div>
    </a>
  );
}
