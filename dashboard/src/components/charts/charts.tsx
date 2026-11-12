"use client";

import { motion } from "motion/react";
import { useMemo, useState, type ReactNode } from "react";
import { useElementSize } from "@/hooks/use-element-size";
import { count } from "@/lib/format";
import type { IconName } from "@/lib/icons";
import { Icon } from "../ui/m3";

/* ------------------------------- shared bits ------------------------------ */

function niceMax(value: number): number {
  if (value <= 4) return 4;
  const pow = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * pow * 4 >= value) ?? 10;
  return step * pow * 4;
}

function Tooltip({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
  const flip = x > width - 170;
  return (
    <div
      className="pointer-events-none absolute z-10 min-w-[150px] rounded-xs bg-inverse-surface px-3 py-2 text-body-small text-inverse-on-surface shadow-elev-2 [&_.text-on-surface]:text-inverse-on-surface [&_.text-on-surface-variant]:text-inverse-on-surface/80 [&_.text-error]:text-inverse-primary"
      style={{ left: x, top: y, transform: `translate(${flip ? "calc(-100% - 12px)" : "12px"}, -50%)` }}
    >
      {children}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; shape?: "line" | "square" }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-label-medium text-on-surface-variant">
      {items.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          {item.shape === "line" ? (
            <span className="h-[2px] w-3 rounded-full" style={{ background: item.color }} />
          ) : (
            <span className="size-2.5 rounded-[3px]" style={{ background: item.color }} />
          )}
          {item.label}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------- Area chart ------------------------------- */

export interface AreaPoint {
  t: string;
  values: number[];
}

export function AreaChart({
  data,
  series,
  height = 240,
  formatX,
  formatTooltipX,
}: {
  data: AreaPoint[];
  series: { label: string; color: string; fill?: boolean }[];
  height?: number;
  formatX: (iso: string) => string;
  formatTooltipX: (iso: string) => string;
}) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const pad = { top: 12, right: 12, bottom: 26, left: 36 };
  const innerW = Math.max(0, width - pad.left - pad.right);
  const innerH = height - pad.top - pad.bottom;

  const yMax = niceMax(Math.max(1, ...data.flatMap((d) => d.values)));
  const x = (i: number) => pad.left + (data.length <= 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
  const y = (v: number) => pad.top + innerH - (v / yMax) * innerH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax);

  const paths = useMemo(
    () =>
      series.map((_, s) => {
        const pts = data.map((d, i) => [x(i), y(d.values[s] ?? 0)] as const);
        const line = smoothPath(pts);
        const area = pts.length
          ? `${line} L${pts[pts.length - 1][0]},${pad.top + innerH} L${pts[0][0]},${pad.top + innerH} Z`
          : "";
        return { line, area };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, series.length, width, yMax],
  );

  const xTickEvery = Math.max(1, Math.ceil(data.length / Math.max(2, Math.floor(innerW / 90))));

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    const rel = (e.clientX - rect.left) / rect.width;
    setHover(Math.max(0, Math.min(data.length - 1, Math.round(rel * (data.length - 1)))));
  };

  return (
    <div ref={ref} className="relative w-full" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} className="overflow-visible" role="img" aria-label={series.map((s) => s.label).join(" and ") + " over time"}>
          <defs>
            {series.map((s, i) => (
              <linearGradient key={i} id={`area-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={s.color} stopOpacity={0.18} />
                <stop offset="1" stopColor={s.color} stopOpacity={0.01} />
              </linearGradient>
            ))}
          </defs>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--md-sys-color-outline)" : "var(--md-sys-color-outline-variant)"} />
              <text x={pad.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-[var(--md-sys-color-on-surface-variant)] text-label-small tabular">
                {count(t, true)}
              </text>
            </g>
          ))}
          {data.map((d, i) =>
            i % xTickEvery === 0 ? (
              <text key={d.t} x={x(i)} y={height - 6} textAnchor="middle" className="fill-[var(--md-sys-color-on-surface-variant)] text-label-small tabular">
                {formatX(d.t)}
              </text>
            ) : null,
          )}
          {paths.map((p, i) => (
            <g key={i}>
              {series[i].fill !== false && (
                <motion.path
                  d={p.area}
                  fill={`url(#area-${i})`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.5 }}
                />
              )}
              <motion.path
                d={p.line}
                fill="none"
                stroke={series[i].color}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.8, ease: [0.2, 0.7, 0.2, 1] }}
              />
            </g>
          ))}
          {hover !== null && (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + innerH} stroke="var(--md-sys-color-outline)" />
              {series.map((s, i) => (
                <circle
                  key={i}
                  cx={x(hover)}
                  cy={y(data[hover].values[i] ?? 0)}
                  r={4}
                  fill={s.color}
                  stroke="var(--md-sys-color-surface-container-low)"
                  strokeWidth={2}
                />
              ))}
            </g>
          )}
          <rect
            x={pad.left}
            y={pad.top}
            width={innerW}
            height={innerH}
            fill="transparent"
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
          />
        </svg>
      )}
      {hover !== null && data[hover] && (
        <Tooltip x={x(hover)} y={pad.top + innerH / 2} width={width}>
          <p className="mb-1.5 font-medium text-on-surface">{formatTooltipX(data[hover].t)}</p>
          {series.map((s, i) => (
            <p key={s.label} className="flex items-center gap-2 text-on-surface-variant">
              <span className="h-[2px] w-2.5 rounded-full" style={{ background: s.color }} />
              {s.label}
              <span className="ml-auto pl-4 font-medium tabular text-on-surface">{count(data[hover].values[i] ?? 0)}</span>
            </p>
          ))}
        </Tooltip>
      )}
    </div>
  );
}

function smoothPath(pts: readonly (readonly [number, number])[]): string {
  if (!pts.length) return "";
  if (pts.length < 3) return pts.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(" ");
  // Monotone-ish cubic: control points at 1/3 of the horizontal gap keep it from overshooting
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const dx = (x1 - x0) / 3;
    d += ` C${x0 + dx},${y0} ${x1 - dx},${y1} ${x1},${y1}`;
  }
  return d;
}

/* -------------------------------- Histogram ------------------------------- */

export function ScoreHistogram({
  bins,
  threshold,
  height = 200,
}: {
  bins: { start: number; end: number; count: number }[];
  threshold: number;
  height?: number;
}) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const pad = { top: 22, right: 16, bottom: 24, left: 16 };
  const innerW = Math.max(0, width - pad.left - pad.right);
  const innerH = height - pad.top - pad.bottom;
  // Log-ish scale: the benign mass near 0 would otherwise flatten the tail analysts care about
  const max = Math.max(1, ...bins.map((b) => b.count));
  const scale = (v: number) => (v <= 0 ? 0 : Math.log1p(v) / Math.log1p(max));
  const band = innerW / bins.length;
  const barW = Math.min(24, band - 2);
  const thresholdX = pad.left + threshold * innerW;

  return (
    <div ref={ref} className="relative w-full" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Distribution of composite risk scores">
          {[0, 0.5, 1].map((f) => (
            <line key={f} x1={pad.left} x2={width - pad.right} y1={pad.top + innerH * (1 - f)} y2={pad.top + innerH * (1 - f)} stroke={f === 0 ? "var(--md-sys-color-outline)" : "var(--md-sys-color-outline-variant)"} />
          ))}
          {bins.map((b, i) => {
            const h = scale(b.count) * innerH;
            const above = b.start >= threshold - 1e-9;
            const bx = pad.left + i * band + (band - barW) / 2;
            const r = Math.min(4, h / 2);
            return (
              <g key={i} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
                <rect x={pad.left + i * band} y={pad.top} width={band} height={innerH} fill="transparent" />
                {h > 0 && (
                  <motion.path
                    d={roundedTopBar(bx, pad.top + innerH - h, barW, h, r)}
                    fill={above ? "var(--md-sys-color-error)" : "var(--md-ext-series-1)"}
                    opacity={hover === null || hover === i ? 1 : 0.45}
                    style={{ transformOrigin: `0px ${pad.top + innerH}px`, transformBox: "view-box" }}
                    initial={{ scaleY: 0 }}
                    animate={{ scaleY: 1 }}
                    transition={{ duration: 0.5, delay: i * 0.015, ease: [0.2, 0.7, 0.2, 1] }}
                  />
                )}
              </g>
            );
          })}
          <line x1={thresholdX} x2={thresholdX} y1={pad.top - 6} y2={pad.top + innerH} stroke="var(--md-sys-color-on-surface-variant)" strokeWidth={1} />
          <text x={thresholdX + 6} y={pad.top - 8} className="fill-[var(--md-sys-color-on-surface-variant)] text-label-small font-medium">
            Alert threshold {threshold.toFixed(2)}
          </text>
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <text key={v} x={pad.left + v * innerW} y={height - 6} textAnchor={v === 0 ? "start" : v === 1 ? "end" : "middle"} className="fill-[var(--md-sys-color-on-surface-variant)] text-label-small tabular">
              {v.toFixed(2)}
            </text>
          ))}
        </svg>
      )}
      {hover !== null && bins[hover] && (
        <Tooltip x={pad.left + (hover + 0.5) * band} y={height / 2} width={width}>
          <p className="font-medium text-on-surface tabular">
            Score {bins[hover].start.toFixed(2)}–{bins[hover].end.toFixed(2)}
          </p>
          <p className="mt-1 flex text-on-surface-variant">
            Transactions <span className="ml-auto pl-4 font-medium tabular text-on-surface">{count(bins[hover].count)}</span>
          </p>
          {bins[hover].start >= threshold - 1e-9 && <p className="mt-1 text-[11px] text-error">Above threshold · alerted</p>}
        </Tooltip>
      )}
    </div>
  );
}

function roundedTopBar(x: number, y: number, w: number, h: number, r: number) {
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}

/* -------------------------------- Bar list -------------------------------- */

export function BarList({
  items,
  total,
}: {
  items: { key: string; label: string; value: number; color?: string; icon?: IconName; hint?: string }[];
  total: number;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="flex flex-col gap-3.5">
      {items.map((item, i) => (
        <li key={item.key} className="group">
          <div className="mb-2 flex items-baseline justify-between gap-3 text-body-medium">
            <span className="flex items-center gap-2 text-on-surface-variant">
              {item.icon ? (
                <Icon name={item.icon} filled size={18} style={{ color: item.color ?? "var(--md-ext-series-1)" }} />
              ) : (
                <span className="size-2 rounded-[3px]" style={{ background: item.color ?? "var(--md-ext-series-1)" }} />
              )}
              {item.label}
            </span>
            <span className="tabular">
              <span className="font-medium text-on-surface">{count(item.value)}</span>
              <span className="text-on-surface-variant"> · {total ? ((item.value / total) * 100).toFixed(1) : "0.0"}%</span>
            </span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-on-surface/8">
            <motion.div
              className="h-full origin-left rounded-full"
              style={{ background: item.color ?? "var(--md-ext-series-1)", width: `${(item.value / max) * 100}%` }}
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.6, delay: i * 0.06, ease: [0.2, 0.7, 0.2, 1] }}
            />
          </div>
          {item.hint && <p className="mt-1 text-[11px] text-on-surface-variant">{item.hint}</p>}
        </li>
      ))}
    </ul>
  );
}

/* -------------------------------- Sparkline ------------------------------- */

export function Sparkline({ values, color = "var(--md-ext-series-1)", height = 32 }: { values: number[]; color?: string; height?: number }) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const max = Math.max(1, ...values);
  const pts = values.map((v, i) => [values.length > 1 ? (i / (values.length - 1)) * width : 0, height - 2 - (v / max) * (height - 4)] as const);
  const line = smoothPath(pts);
  return (
    <div ref={ref} style={{ height }} className="w-full">
      {width > 0 && values.length > 1 && (
        <svg width={width} height={height} aria-hidden>
          <path d={`${line} L${width},${height} L0,${height} Z`} fill={color} opacity={0.1} />
          <path d={line} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
          <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r={2.5} fill={color} />
        </svg>
      )}
    </div>
  );
}

/* ---------------------------- Threshold sweep ----------------------------- */

export interface SweepPoint {
  threshold: number;
  precision: number;
  recall: number;
  f1: number;
}

const SWEEP_SERIES = [
  { key: "precision", label: "Precision", color: "var(--md-ext-series-1)" },
  { key: "recall", label: "Recall", color: "var(--md-ext-series-2)" },
  { key: "f1", label: "F1", color: "var(--md-ext-series-3)" },
] as const;

export const SWEEP_LEGEND = SWEEP_SERIES.map((s) => ({ label: s.label, color: s.color, shape: "line" as const }));

/** Precision, recall and F1 against the alert threshold, with the live threshold marked. */
export function ThresholdChart({ points, current, height = 260 }: { points: SweepPoint[]; current: number; height?: number }) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const pad = { top: 22, right: 16, bottom: 26, left: 36 };
  const innerW = Math.max(0, width - pad.left - pad.right);
  const innerH = height - pad.top - pad.bottom;
  const x = (t: number) => pad.left + t * innerW;
  const y = (v: number) => pad.top + innerH - v * innerH;

  const lines = SWEEP_SERIES.map((s) => points.map((p, i) => `${i ? "L" : "M"}${x(p.threshold)},${y(p[s.key])}`).join(" "));

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    const t = (e.clientX - rect.left) / rect.width;
    let best = 0;
    points.forEach((p, i) => {
      if (Math.abs(p.threshold - t) < Math.abs(points[best].threshold - t)) best = i;
    });
    setHover(best);
  };

  const hp = hover !== null ? points[hover] : null;

  return (
    <div ref={ref} className="relative w-full" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} className="overflow-visible" role="img" aria-label="Precision, recall and F1 by alert threshold">
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <g key={v}>
              <line x1={pad.left} x2={width - pad.right} y1={y(v)} y2={y(v)} stroke={v === 0 ? "var(--md-sys-color-outline)" : "var(--md-sys-color-outline-variant)"} />
              <text x={pad.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-[var(--md-sys-color-on-surface-variant)] text-label-small tabular">
                {v.toFixed(2)}
              </text>
            </g>
          ))}
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <text key={v} x={x(v)} y={height - 6} textAnchor={v === 0 ? "start" : v === 1 ? "end" : "middle"} className="fill-[var(--md-sys-color-on-surface-variant)] text-label-small tabular">
              {v.toFixed(2)}
            </text>
          ))}
          <line x1={x(current)} x2={x(current)} y1={pad.top - 6} y2={pad.top + innerH} stroke="var(--md-sys-color-on-surface-variant)" strokeDasharray="3 3" />
          <text x={x(current) + 6} y={pad.top - 8} className="fill-[var(--md-sys-color-on-surface-variant)] text-label-small font-medium">
            Live threshold {current.toFixed(2)}
          </text>
          {lines.map((d, i) => (
            <motion.path
              key={SWEEP_SERIES[i].key}
              d={d}
              fill="none"
              stroke={SWEEP_SERIES[i].color}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.8, delay: i * 0.08, ease: [0.2, 0.7, 0.2, 1] }}
            />
          ))}
          {hp && (
            <g>
              <line x1={x(hp.threshold)} x2={x(hp.threshold)} y1={pad.top} y2={pad.top + innerH} stroke="var(--md-sys-color-outline)" />
              {SWEEP_SERIES.map((s) => (
                <circle key={s.key} cx={x(hp.threshold)} cy={y(hp[s.key])} r={4} fill={s.color} stroke="var(--md-sys-color-surface-container-highest)" strokeWidth={2} />
              ))}
            </g>
          )}
          <rect x={pad.left} y={pad.top} width={innerW} height={innerH} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
        </svg>
      )}
      {hp && (
        <Tooltip x={x(hp.threshold)} y={pad.top + innerH / 2} width={width}>
          <p className="mb-1.5 font-medium text-on-surface tabular">Threshold {hp.threshold.toFixed(2)}</p>
          {SWEEP_SERIES.map((s) => (
            <p key={s.key} className="flex items-center gap-2 text-on-surface-variant">
              <span className="h-[2px] w-2.5 rounded-full" style={{ background: s.color }} />
              {s.label}
              <span className="ml-auto pl-4 font-medium tabular text-on-surface">{hp[s.key].toFixed(2)}</span>
            </p>
          ))}
        </Tooltip>
      )}
    </div>
  );
}

/* -------------------------- Labelled histogram ---------------------------- */

/** Score distribution stacked by label (log scale), so the overlap between classes is visible. */
export function LabelHistogram({
  bins,
  threshold,
  height = 220,
}: {
  bins: { start: number; end: number; fraud: number; legit: number }[];
  threshold: number;
  height?: number;
}) {
  const [ref, { width }] = useElementSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const pad = { top: 22, right: 16, bottom: 24, left: 16 };
  const innerW = Math.max(0, width - pad.left - pad.right);
  const innerH = height - pad.top - pad.bottom;
  const max = Math.max(1, ...bins.map((b) => b.fraud + b.legit));
  const scale = (v: number) => (v <= 0 ? 0 : Math.log1p(v) / Math.log1p(max));
  const band = innerW / Math.max(1, bins.length);
  const barW = Math.min(24, band - 2);
  const tx = pad.left + threshold * innerW;
  const base = pad.top + innerH;

  return (
    <div ref={ref} className="relative w-full" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label="Score distribution of fraudulent and legitimate transactions">
          {[0, 0.5, 1].map((f) => (
            <line key={f} x1={pad.left} x2={width - pad.right} y1={pad.top + innerH * (1 - f)} y2={pad.top + innerH * (1 - f)} stroke={f === 0 ? "var(--md-sys-color-outline)" : "var(--md-sys-color-outline-variant)"} />
          ))}
          {bins.map((b, i) => {
            const total = b.fraud + b.legit;
            const h = scale(total) * innerH;
            const fraudH = total ? (h * b.fraud) / total : 0;
            const bx = pad.left + i * band + (band - barW) / 2;
            return (
              <g key={i} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} opacity={hover === null || hover === i ? 1 : 0.45}>
                <rect x={pad.left + i * band} y={pad.top} width={band} height={innerH} fill="transparent" />
                {h > 0 && (
                  <motion.g
                    style={{ transformOrigin: `0px ${base}px`, transformBox: "view-box" }}
                    initial={{ scaleY: 0 }}
                    animate={{ scaleY: 1 }}
                    transition={{ duration: 0.5, delay: i * 0.015, ease: [0.2, 0.7, 0.2, 1] }}
                  >
                    {h - fraudH > 0 && <rect x={bx} y={base - (h - fraudH)} width={barW} height={h - fraudH} rx={2} fill="var(--md-ext-series-1)" />}
                    {fraudH > 0 && <rect x={bx} y={base - h} width={barW} height={fraudH} rx={2} fill="var(--md-sys-color-error)" />}
                  </motion.g>
                )}
              </g>
            );
          })}
          <line x1={tx} x2={tx} y1={pad.top - 6} y2={pad.top + innerH} stroke="var(--md-sys-color-on-surface-variant)" strokeDasharray="3 3" />
          <text x={tx + 6} y={pad.top - 8} className="fill-[var(--md-sys-color-on-surface-variant)] text-label-small font-medium">
            Threshold {threshold.toFixed(2)}
          </text>
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <text key={v} x={pad.left + v * innerW} y={height - 6} textAnchor={v === 0 ? "start" : v === 1 ? "end" : "middle"} className="fill-[var(--md-sys-color-on-surface-variant)] text-label-small tabular">
              {v.toFixed(2)}
            </text>
          ))}
        </svg>
      )}
      {hover !== null && bins[hover] && (
        <Tooltip x={pad.left + (hover + 0.5) * band} y={height / 2} width={width}>
          <p className="font-medium text-on-surface tabular">
            Score {bins[hover].start.toFixed(2)}–{bins[hover].end.toFixed(2)}
          </p>
          <p className="mt-1 flex text-on-surface-variant">
            Fraud <span className="ml-auto pl-4 font-medium tabular text-on-surface">{count(bins[hover].fraud)}</span>
          </p>
          <p className="flex text-on-surface-variant">
            Legitimate <span className="ml-auto pl-4 font-medium tabular text-on-surface">{count(bins[hover].legit)}</span>
          </p>
        </Tooltip>
      )}
    </div>
  );
}
