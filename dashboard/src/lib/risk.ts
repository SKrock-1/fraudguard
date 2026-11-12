import type { IconName } from "./icons";
import type { Alert, RiskFactors, RuleName } from "./types";

export type Severity = "low" | "elevated" | "high" | "critical";

export const SEVERITY: Record<
  Severity,
  { label: string; color: string; track: string; chip: string; icon: IconName }
> = {
  low: {
    label: "Low",
    icon: "verified_user",
    color: "var(--md-ext-color-success)",
    track: "var(--md-ext-color-success-container)",
    chip: "bg-success-container text-on-success-container",
  },
  elevated: {
    label: "Elevated",
    icon: "warning",
    color: "var(--md-ext-color-warning)",
    track: "var(--md-ext-color-warning-container)",
    chip: "bg-warning-container text-on-warning-container",
  },
  high: {
    label: "High",
    icon: "report",
    color: "var(--md-ext-color-serious)",
    track: "var(--md-ext-color-serious-container)",
    chip: "bg-serious-container text-on-serious-container",
  },
  critical: {
    label: "Critical",
    icon: "crisis_alert",
    color: "var(--md-sys-color-error)",
    track: "var(--md-sys-color-error-container)",
    chip: "bg-error-container text-on-error-container",
  },
};

export function severityOf(score: number): Severity {
  if (score >= 0.8) return "critical";
  if (score >= 0.6) return "high";
  if (score >= 0.3) return "elevated";
  return "low";
}

export type FactorKey = RuleName | "ml_anomaly";

/** Each signal keeps one hue (validated chart series) and one icon everywhere it appears. */
export const FACTOR_META: Record<FactorKey, { label: string; short: string; color: string; tint: string; ink: string; icon: IconName }> = {
  impossible_travel: { label: "Impossible travel", short: "Travel", color: "var(--md-ext-series-1)", tint: tint(1), ink: ink(1), icon: "flight_takeoff" },
  amount_anomaly: { label: "Amount anomaly", short: "Amount", color: "var(--md-ext-series-2)", tint: tint(2), ink: ink(2), icon: "payments" },
  velocity: { label: "Velocity burst", short: "Velocity", color: "var(--md-ext-series-3)", tint: tint(3), ink: ink(3), icon: "speed" },
  ml_anomaly: { label: "ML anomaly", short: "Model", color: "var(--md-ext-series-4)", tint: tint(4), ink: ink(4), icon: "neurology" },
};

/** Glyph color for use on the tint: pulled toward on-surface so it clears 3:1 on its own tint. */
function ink(slot: number) {
  return "color-mix(in srgb, var(--md-ext-series-" + slot + ") 78%, var(--md-sys-color-on-surface))";
}

function tint(slot: number) {
  return `color-mix(in srgb, var(--md-ext-series-${slot}) 16%, transparent)`;
}

export const FACTOR_ORDER: FactorKey[] = ["impossible_travel", "amount_anomaly", "velocity", "ml_anomaly"];

const num = (v: unknown) => (typeof v === "number" ? v : Number(v));
const km = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** Plain-language explanation of why a rule did (or didn't) fire. */
export function explainFactor(key: FactorKey, factors: RiskFactors, currency = "USD"): string {
  if (key === "ml_anomaly") {
    const s = factors.ml_score;
    if (s >= 0.7) return `Isolation Forest rates this ${Math.round(s * 100)}% anomalous versus normal spend patterns.`;
    if (s > 0) return `Model sees mild deviation (${Math.round(s * 100)}% anomalous).`;
    return "Consistent with this account's learned spending pattern.";
  }

  const factor = factors.rule_engine[key];
  const d = factor?.detail ?? ({} as RuleFactorDetail);
  if (d.error) return "Check unavailable: the velocity store could not be reached.";

  switch (key) {
    case "impossible_travel": {
      if (d.reason === "missing_account_baseline_location_or_timestamp")
        return "No prior location on file for this account yet.";
      if (d.reason === "missing_transaction_location_or_timestamp") return "Transaction has no location.";
      const dist = num(d.distance_km);
      const mins = Math.max(0, num(d.elapsed_seconds) / 60);
      if (d.reason === "instantaneous_displacement")
        return `${km.format(dist)} km from the last known location with no time elapsed.`;
      // Sub-minute gaps make the implied speed meaningless; say what happened instead
      if (factor.triggered && num(d.elapsed_seconds) < 60)
        return `${km.format(dist)} km from the last known location within seconds.`;
      if (factor.triggered)
        return `${km.format(dist)} km in ${formatMinutes(mins)}, which implies ${km.format(num(d.speed_kmh))} km/h (limit ${km.format(num(d.max_speed_kmh))}).`;
      return dist < 1 ? "Same location as the previous transaction." : `${km.format(dist)} km over ${formatMinutes(mins)}, a plausible journey.`;
    }
    case "amount_anomaly": {
      const avg = new Intl.NumberFormat("en-US", { style: "currency", currency }).format(num(d.avg_spend));
      if (d.reason === "zero_stddev_extreme_multiple") return `At least 5x the account's ${avg} average, with no spend variance on record.`;
      const z = d.z_score == null ? null : num(d.z_score);
      if (z == null) return `Compared against a ${avg} average.`;
      return factor.triggered
        ? `${z.toFixed(1)}σ above this account's ${avg} average (threshold ${num(d.threshold_z)}σ).`
        : `${z.toFixed(1)}σ from the ${avg} average, within the normal range.`;
    }
    case "velocity": {
      const c = num(d.count);
      return factor.triggered
        ? `${c} transactions within ${num(d.window_minutes)} min (limit ${num(d.max_count)}).`
        : `${c} of ${num(d.max_count)} allowed transactions in the last ${num(d.window_minutes)} min.`;
    }
  }
}

type RuleFactorDetail = Record<string, unknown> & { reason?: string; error?: string };

function formatMinutes(mins: number): string {
  if (mins < 1) return `${Math.round(mins * 60)} s`;
  if (mins < 120) return `${Math.round(mins)} min`;
  return `${(mins / 60).toFixed(1)} h`;
}

export function isTriggered(key: FactorKey, factors: RiskFactors): boolean {
  if (key === "ml_anomaly") return factors.ml_score >= 0.5;
  return Boolean(factors.rule_engine[key]?.triggered);
}

export function contributions(factors: RiskFactors) {
  return FACTOR_ORDER.map((key) => ({
    key,
    value: factors.composite_breakdown[key]?.contribution ?? 0,
    weight: factors.composite_breakdown[key]?.weight ?? 0,
  }));
}

export function primaryReason(alert: Alert): string {
  const rules = alert.risk_score.factors.triggered_rules;
  if (!rules.length) return "Model anomaly";
  return rules.map((r) => FACTOR_META[r].label).join(" + ");
}
