"use client";

import { motion } from "motion/react";
import { contributions, explainFactor, FACTOR_META, FACTOR_ORDER, isTriggered, SEVERITY, severityOf } from "@/lib/risk";
import type { RiskFactors } from "@/lib/types";
import { Icon, cn } from "../ui/m3";

const EASE = [0.2, 0.7, 0.2, 1] as const;

/** Half-ring meter: fill carries severity, the track is a quieter step of the same hue. */
export function ScoreGauge({ score, threshold }: { score: number; threshold: number }) {
  const sev = severityOf(score);
  const meta = SEVERITY[sev];
  const r = 52;
  const len = Math.PI * r;
  const angle = Math.PI * (1 - threshold);

  return (
    <div className="relative w-[148px]" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={score} aria-label="Composite risk score">
      <svg viewBox="0 0 128 74" className="w-full overflow-visible">
        <path d={`M12 64 A${r} ${r} 0 0 1 116 64`} fill="none" stroke={meta.track} strokeWidth={12} strokeLinecap="round" />
        <motion.path
          d={`M12 64 A${r} ${r} 0 0 1 116 64`}
          fill="none"
          stroke={meta.color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={len}
          initial={{ strokeDashoffset: len }}
          animate={{ strokeDashoffset: len * (1 - score) }}
          transition={{ duration: 0.7, ease: EASE }}
        />
        <line
          x1={64 + Math.cos(angle) * (r - 9)}
          y1={64 - Math.sin(angle) * (r - 9)}
          x2={64 + Math.cos(angle) * (r + 9)}
          y2={64 - Math.sin(angle) * (r + 9)}
          stroke="var(--md-sys-color-on-surface)"
          strokeWidth={1.5}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <p className="emphasized text-headline-medium leading-none tabular">{score.toFixed(2)}</p>
        <p className="mt-1 text-label-medium text-on-surface-variant">
          {meta.label} risk
        </p>
      </div>
    </div>
  );
}

/** Stacked contribution bar on a fixed 0–1 scale with the alert threshold marked. */
export function ContributionBar({ factors, threshold }: { factors: RiskFactors; threshold: number }) {
  const parts = contributions(factors).filter((p) => p.value > 0);
  return (
    <div>
      <div className="relative">
        <div className="flex h-4 w-full overflow-hidden rounded-full bg-surface-container-highest">
          {parts.map((p, i) => (
            <motion.div
              key={p.key}
              title={`${FACTOR_META[p.key].label}: +${p.value.toFixed(2)}`}
              className={cn("h-full origin-left", i > 0 && "border-l-2 border-surface-container-low")}
              style={{ width: `${p.value * 100}%`, background: FACTOR_META[p.key].color }}
              initial={{ scaleX: 0, opacity: 0 }}
              animate={{ scaleX: 1, opacity: 1 }}
              transition={{ duration: 0.45, delay: 0.1 + i * 0.1, ease: EASE }}
            />
          ))}
        </div>
        <div className="absolute -top-1.5 -bottom-1.5 w-px bg-on-surface" style={{ left: `${threshold * 100}%` }} />
      </div>
      <div className="mt-2 flex justify-between text-label-small text-on-surface-variant tabular">
        <span>0.00</span>
        <span style={{ marginLeft: `${threshold * 100 - 50}%` }} className="text-on-surface-variant">
          threshold {threshold.toFixed(2)}
        </span>
        <span>1.00</span>
      </div>
    </div>
  );
}

export function FactorList({ factors, currency }: { factors: RiskFactors; currency: string }) {
  const byContribution = [...FACTOR_ORDER].sort(
    (a, b) => (factors.composite_breakdown[b]?.contribution ?? 0) - (factors.composite_breakdown[a]?.contribution ?? 0),
  );
  return (
    <ul className="flex flex-col gap-2">
      {byContribution.map((key, i) => {
        const fired = isTriggered(key, factors);
        const contribution = factors.composite_breakdown[key]?.contribution ?? 0;
        const weight = factors.composite_breakdown[key]?.weight ?? 0;
        const meta = FACTOR_META[key];
        return (
          <motion.li
            key={key}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: 0.05 + i * 0.04 }}
            className={cn(
              "flex gap-3 rounded-md border p-4",
              fired || contribution > 0 ? "border-transparent bg-surface-container-high" : "border-outline-variant bg-transparent",
            )}
          >
            <span
              className="flex size-10 shrink-0 items-center justify-center rounded-full"
              style={
                fired || contribution > 0
                  ? { background: meta.tint, color: meta.ink }
                  : { background: "var(--md-sys-color-surface-container-highest)", color: "var(--md-sys-color-on-surface-variant)" }
              }
            >
              <Icon name={meta.icon} filled={fired || contribution > 0} size={22} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-3">
                <p className={cn("text-title-small", !(fired || contribution > 0) && "text-on-surface-variant")}>{meta.label}</p>
                <p className="shrink-0 text-label-large tabular">
                  <span className={contribution > 0 ? "font-semibold text-on-surface" : "text-on-surface-variant"}>+{contribution.toFixed(2)}</span>
                  <span className="text-on-surface-variant"> / {weight.toFixed(2)}</span>
                </p>
              </div>
              <p className="mt-0.5 text-body-medium text-on-surface-variant">{explainFactor(key, factors, currency)}</p>
            </div>
          </motion.li>
        );
      })}
    </ul>
  );
}
