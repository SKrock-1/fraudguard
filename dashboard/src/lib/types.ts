export type Role = "ingestion_client" | "analyst" | "admin";
export type AlertStatus = "pending" | "approved" | "rejected";
export type RuleName = "velocity" | "impossible_travel" | "amount_anomaly";

export interface User {
  id: number;
  username: string;
  email: string;
  role: Role;
}

export interface Transaction {
  id: number;
  account_number: string;
  amount: string;
  currency: string;
  merchant: string;
  lat: string | null;
  lng: string | null;
  timestamp: string;
  idempotency_key: string;
  status: "pending" | "scored";
  created_at: string;
}

export interface RuleFactor {
  triggered: boolean;
  detail: Record<string, unknown> & { rule: string; reason?: string; error?: string };
}

export interface BreakdownEntry {
  weight: number;
  triggered?: boolean;
  contribution: number;
  score?: number;
}

export interface RiskFactors {
  rule_engine: Record<RuleName, RuleFactor>;
  triggered_rules: RuleName[];
  ml_score: number;
  ml_contribution: number;
  composite_breakdown: Record<RuleName | "ml_anomaly", BreakdownEntry>;
}

export interface RiskScore {
  id: number;
  composite_score: number;
  model_version: string;
  factors: RiskFactors;
  created_at: string;
}

export interface Alert {
  id: number;
  transaction: Transaction;
  risk_score: RiskScore;
  status: AlertStatus;
  assigned_to: number | null;
  assigned_to_username: string | null;
  notes: string;
  created_at: string;
  resolved_at: string | null;
}

export interface StatsBucket {
  t: string;
  transactions: number;
  alerts: number;
}

export interface Stats {
  window: StatsWindow;
  generated_at: string;
  threshold: number;
  totals: {
    transactions: number;
    scored: number;
    alerts: number;
    pending: number;
    approved: number;
    rejected: number;
    avg_score: number;
    alert_rate: number;
    flagged_amount: string;
    blocked_amount: string;
    resolved: number;
  };
  series: StatsBucket[];
  score_histogram: { start: number; end: number; count: number }[];
  rule_triggers: { rule: RuleName | "ml_anomaly"; count: number }[];
}

export type StatsWindow = "1h" | "24h" | "7d";

export interface AuditEntry {
  id: number;
  actor: number | null;
  actor_username: string | null;
  action: string;
  target: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface ThresholdMetrics {
  threshold: number;
  tp: number;
  fp: number;
  fn: number;
  tn: number;
  precision: number;
  recall: number;
  f1: number;
  accuracy: number;
}

export interface BacktestResult {
  source: "analyst" | "synthetic";
  samples: number;
  fraud?: number;
  legit?: number;
  reviewed?: number;
  average_precision?: number | null;
  current_threshold?: number;
  current?: ThresholdMetrics;
  best_f1?: ThresholdMetrics;
  thresholds?: ThresholdMetrics[];
  histogram?: { start: number; end: number; fraud: number; legit: number }[];
  note: string;
}

export interface ModelEval {
  average_precision: number;
  precision: number;
  recall: number;
  roc_auc: number | null;
}

export interface ModelRun {
  id: number;
  version: string;
  trained_at: string;
  trigger: "manual" | "api" | "scheduled";
  promoted: boolean;
  train_samples: number;
  labeled_fraud: number;
  labeled_legit: number;
  contamination: number;
  metrics: {
    holdout_size: number;
    holdout_fraud: number;
    challenger: ModelEval;
    champion: ModelEval | null;
    champion_version: string | null;
    challenger_beats_champion: boolean;
  };
  notes: string;
  created_by: string | null;
}

export interface ModelList {
  production_version: string | null;
  runs: ModelRun[];
}

export interface RetrainResult {
  status: "promoted" | "kept_champion" | "skipped" | "dry_run";
  version?: string;
  notes?: string;
  reason?: string;
  samples: number;
  labeled_fraud: number;
  labeled_legit: number;
}
