import {
  ArcElement, BarElement, CategoryScale, Chart as ChartJS, Filler, Legend, LinearScale, LineElement, PointElement, Tooltip,
  type Chart, type ChartOptions, type Plugin,
} from "chart.js";
import ChartDataLabels from "chartjs-plugin-datalabels";
import { useMemo } from "react";
import { Bar, Doughnut, Line } from "react-chartjs-2";
import { palette, useTheme } from "../lib/theme";

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, LineElement, PointElement, Tooltip, Legend, Filler, ChartDataLabels);
ChartJS.defaults.plugins.datalabels = { display: false };

/* ---------- gauge (v2 renderGauge) ---------- */
export function Gauge({ value, max = 100, target, suffix = "", small = false }: {
  value: number | null; max?: number; target: number; suffix?: string; small?: boolean;
}) {
  const { theme } = useTheme();
  const pal = palette(theme);
  const v = value === null ? 0 : Math.max(0, Math.min(max, value));
  const color = value === null ? pal.faint : value >= target ? pal.green : value >= target * 0.7 ? pal.amber : pal.red;
  const targetLine: Plugin<"doughnut"> = useMemo(() => ({
    id: "targetLine",
    afterDraw(chart: Chart<"doughnut">) {
      const { ctx } = chart;
      const arc = chart.getDatasetMeta(0).data[0] as unknown as { x: number; y: number; outerRadius: number } | undefined;
      if (!arc) return;
      const frac = Math.max(0, Math.min(1, target / max));
      const angle = Math.PI + frac * Math.PI;
      ctx.save();
      ctx.strokeStyle = palette(theme).ink;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(arc.x + Math.cos(angle) * arc.outerRadius * 0.62, arc.y + Math.sin(angle) * arc.outerRadius * 0.62);
      ctx.lineTo(arc.x + Math.cos(angle) * arc.outerRadius * 1.02, arc.y + Math.sin(angle) * arc.outerRadius * 1.02);
      ctx.stroke();
      ctx.restore();
    },
  }), [target, max, theme]);
  return (
    <>
      <div className={"gauge-wrap" + (small ? " sm" : "")}>
        <Doughnut
          key={theme}
          data={{ datasets: [{ data: [v, max - v], backgroundColor: [color, pal.track], borderWidth: 0, circumference: 180, rotation: 270 }] }}
          options={{ responsive: true, maintainAspectRatio: false, cutout: "74%",
            plugins: { legend: { display: false }, tooltip: { enabled: false }, datalabels: { display: false } } }}
          plugins={[targetLine]}
        />
        <div className="gauge-val">{value === null ? "–" : `${value}${suffix}`}</div>
      </div>
      <div className="gauge-target">Target: {target}{suffix}</div>
    </>
  );
}

/* ---------- horizontal category bars (v2 renderCatChart) ---------- */
export function CatChart({ entries, color, total }: { entries: [string, number][]; color: string; total: number }) {
  const { theme } = useTheme();
  if (!entries.length) return null;
  const pal = palette(theme);
  const options: ChartOptions<"bar"> = {
    indexAxis: "y", responsive: true, maintainAspectRatio: false, layout: { padding: { right: 58 } },
    plugins: {
      legend: { display: false },
      datalabels: { display: true, anchor: "end", align: "end", clamp: true, color: pal.ink, font: { weight: "bold", size: 11 },
        formatter: (v: number) => (total ? `${v} (${Math.round((v / total) * 1000) / 10}%)` : `${v}`) },
      tooltip: { backgroundColor: pal.tooltipBg, padding: 10, cornerRadius: 8, displayColors: false, titleColor: pal.ink, bodyColor: pal.ink },
    },
    scales: { x: { grid: { color: pal.grid }, border: { display: false }, ticks: { color: pal.tick } },
              y: { grid: { display: false }, border: { display: false }, ticks: { color: pal.tick } } },
  };
  return (
    <Bar key={theme} options={options}
      data={{ labels: entries.map((e) => e[0]), datasets: [{ data: entries.map((e) => e[1]), backgroundColor: color, borderRadius: 7, borderSkipped: false, maxBarThickness: 30 }] }} />
  );
}

/* ---------- generic charts for the manager pages ---------- */
export interface Series { label: string; data: (number | null)[]; color: string; dashed?: boolean; fill?: boolean }

function baseScales(pal: ReturnType<typeof palette>, yTitle?: string) {
  return {
    x: { grid: { display: false }, border: { display: false }, ticks: { color: pal.tick } },
    y: { grid: { color: pal.grid }, border: { display: false }, ticks: { color: pal.tick },
         title: yTitle ? { display: true, text: yTitle, color: pal.faint } : undefined },
  };
}

export function LineChart({ labels, series, yTitle, refLine }: { labels: string[]; series: Series[]; yTitle?: string; refLine?: { value: number; label: string } }) {
  const { theme } = useTheme();
  const pal = palette(theme);
  const datasets = series.map((s) => ({
    label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.color, borderWidth: 2.4, pointRadius: 2.5,
    borderDash: s.dashed ? [6, 5] : undefined, tension: 0.25, spanGaps: true,
  }));
  if (refLine) {
    datasets.push({ label: refLine.label, data: labels.map(() => refLine.value), borderColor: pal.faint, backgroundColor: pal.faint,
      borderWidth: 1.4, pointRadius: 0, borderDash: [2, 4], tension: 0, spanGaps: true });
  }
  return (
    <Line key={theme} data={{ labels, datasets }}
      options={{ responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { labels: { color: pal.muted, boxWidth: 12 } }, datalabels: { display: false },
          tooltip: { backgroundColor: pal.tooltipBg, titleColor: pal.ink, bodyColor: pal.ink } },
        scales: baseScales(pal, yTitle) }} />
  );
}

export function BarChart({ labels, series, stacked = false, yTitle, showValues = false }: {
  labels: string[]; series: Series[]; stacked?: boolean; yTitle?: string; showValues?: boolean;
}) {
  const { theme } = useTheme();
  const pal = palette(theme);
  const scales = baseScales(pal, yTitle);
  return (
    <Bar key={theme}
      data={{ labels, datasets: series.map((s) => ({ label: s.label, data: s.data, backgroundColor: s.color, borderRadius: 5, maxBarThickness: 46 })) }}
      options={{ responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: series.length > 1, labels: { color: pal.muted, boxWidth: 12 } },
          datalabels: showValues ? { display: true, anchor: "end", align: "end", color: pal.ink, font: { weight: "bold", size: 11 } } : { display: false },
          tooltip: { backgroundColor: pal.tooltipBg, titleColor: pal.ink, bodyColor: pal.ink } },
        scales: { x: { ...scales.x, stacked }, y: { ...scales.y, stacked } } }} />
  );
}
