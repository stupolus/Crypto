import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";

interface Marker {
  time_sec: number;
  price: number;
  type: "entry" | "exit";
  side?: "BUY" | "SELL";
  label?: string;
}

interface Props {
  candles: Array<{ time: number; open: number; high: number; low: number; close: number }>;
  markers?: Marker[];
  height?: number;
}

export default function CandleChart({ candles, markers = [], height = 360 }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  // Setup chart once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#11151c" },
        textColor: "#8b949e",
        fontFamily: "JetBrains Mono, monospace",
      },
      grid: {
        vertLines: { color: "#21262d" },
        horzLines: { color: "#21262d" },
      },
      timeScale: {
        borderColor: "#30363d",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "#30363d",
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#00ff88",
      downColor: "#ff4d4d",
      borderUpColor: "#00ff88",
      borderDownColor: "#ff4d4d",
      wickUpColor: "#00ff88",
      wickDownColor: "#ff4d4d",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height]);

  // Update candles + markers when data changes
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return;
    const data = candles
      .map((c) => ({
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));
    seriesRef.current.setData(data);

    if (markers.length > 0) {
      seriesRef.current.setMarkers(
        markers.map((m) => ({
          time: m.time_sec as Time,
          position: m.type === "entry" ? "belowBar" : "aboveBar",
          color: m.type === "entry"
            ? m.side === "BUY"
              ? "#00ff88"
              : "#ff4d4d"
            : "#d4af37",
          shape: m.type === "entry" ? "arrowUp" : "arrowDown",
          text: m.label ?? `${m.type.toUpperCase()} ${m.price.toFixed(2)}`,
        })),
      );
    } else {
      seriesRef.current.setMarkers([]);
    }
    chartRef.current.timeScale().fitContent();
  }, [candles, markers]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height }}
      className="bg-bg-panel"
    />
  );
}
