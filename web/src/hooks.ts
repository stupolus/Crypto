import { useCallback, useEffect, useRef, useState } from "react";

/**
 * SSE hook: подписывается на /stream/events и обновляет state при каждом
 * `event: <eventName>` от сервера. Auto-reconnect при разрыве (стандарт
 * EventSource).
 */
export function useSse<T>(
  url: string,
  eventName: string,
): { data: T | null; connected: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(url);
    es.addEventListener("open", () => setConnected(true));
    es.addEventListener("error", () => setConnected(false));
    es.addEventListener(eventName, (ev) => {
      try {
        const payload = JSON.parse((ev as MessageEvent).data);
        setData(payload as T);
      } catch {
        // ignore malformed
      }
    });
    return () => {
      es.close();
    };
  }, [url, eventName]);

  return { data, connected };
}

/**
 * Polling hook: вызывает loader каждые intervalMs миллисекунд.
 * Возвращает {data, error, loading}. Hot-swap: первый запрос показывает loading,
 * последующие — silent refresh (loading остаётся false если data уже есть).
 */
export function usePolling<T>(
  loader: () => Promise<T>,
  intervalMs: number,
  deps: ReadonlyArray<unknown> = [],
): { data: T | null; error: Error | null; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);

  const run = useCallback(async () => {
    try {
      const result = await loader();
      if (mountedRef.current) {
        setData(result);
        setError(null);
        setLoading(false);
      }
    } catch (e) {
      if (mountedRef.current) {
        setError(e as Error);
        setLoading(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    mountedRef.current = true;
    void run();
    const id = setInterval(run, intervalMs);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [run, intervalMs]);

  return { data, error, loading, reload: run };
}

/**
 * Форматтер времени UTC ms → 'HH:MM:SS' (UTC).
 */
export function fmtTime(ms: number): string {
  if (!ms) return "—";
  const d = new Date(ms);
  return d.toISOString().slice(11, 19);
}

export function fmtDate(ms: number): string {
  if (!ms) return "—";
  const d = new Date(ms);
  return d.toISOString().slice(0, 10);
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h${m}m`;
  if (m > 0) return `${m}m${sec.toString().padStart(2, "0")}s`;
  return `${sec}s`;
}

export function fmtNum(s: string | null | undefined, fractionDigits = 2): string {
  if (s == null || s === "") return "—";
  const n = parseFloat(s);
  if (!isFinite(n)) return s;
  return n.toLocaleString("en-US", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

export function fmtPct(s: string | null | undefined): string {
  if (s == null || s === "") return "—";
  const n = parseFloat(s);
  if (!isFinite(n)) return s;
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}
