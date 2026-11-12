"use client";

import { motion } from "motion/react";
import { useCallback, useEffect, useState } from "react";
import { LabelHistogram, Legend, SWEEP_LEGEND, ThresholdChart } from "@/components/charts/charts";
import { useAuth, useSnackbar } from "@/components/providers";
import { PageHeader } from "@/components/shell";
import { Button, Card, CardHeader, ConnectedButtonGroup, Icon, Skeleton, cn } from "@/components/ui/m3";
import { ApiError, api } from "@/lib/api";
import { count, dateTime, displayName, percent } from "@/lib/format";
import { spatialDefault } from "@/lib/motion";
import type { BacktestResult, ModelList, ModelRun, RetrainResult, ThresholdMetrics } from "@/lib/types";

type Source = "analyst" | "synthetic";

const SOURCES: { value: Source; label: string }[] = [
  { value: "analyst", label: "Analyst labels" },
  { value: "synthetic", label: "Synthetic set" },
];

const TRIGGER_LABEL: Record<ModelRun["trigger"], string> = { manual: "Command line", api: "Dashboard", scheduled: "Weekly job" };

export function ModelsView() {
  const { user } = useAuth();
  const snackbar = useSnackbar();
  const [source, setSource] = useState<Source>("analyst");
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [models, setModels] = useState<ModelList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [training, setTraining] = useState(false);
  const [reload, setReload] = useState(0);

  const loadModels = useCallback(() => api<ModelList>("/api/ml/models").then(setModels), []);

  useEffect(() => {
    let cancelled = false;
    api<BacktestResult>(`/api/ml/backtest?source=${source}`)
      .then((b) => !cancelled && (setBacktest(b), setError(null)))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [source, reload]);

  useEffect(() => {
    loadModels().catch((e) => setError(e.message));
  }, [loadModels]);

  const retrain = async () => {
    setTraining(true);
    try {
      const r = await api<RetrainResult>("/api/ml/retrain", { method: "POST", json: {} });
      snackbar({
        message: r.status === "promoted" ? `New model ${r.version} promoted` : `Kept current model: ${r.notes ?? ""}`,
        tone: "success",
        long: true,
      });
      await loadModels();
      setReload((n) => n + 1);
    } catch (e) {
      const body = e instanceof ApiError ? (e.body as Partial<RetrainResult> | undefined) : undefined;
      snackbar({ message: body?.reason ?? (e as Error).message, tone: "alert", long: true });
    } finally {
      setTraining(false);
    }
  };

  const stale = !!backtest && backtest.source !== source;
  const ready = backtest && backtest.samples > 0 && backtest.current && backtest.thresholds && backtest.histogram;

  return (
    <div className="pb-10">
      <PageHeader
        title="Model performance"
        description="How well the scoring pipeline separates fraud from legitimate traffic, and the history of retrained models."
        actions={
          <ConnectedButtonGroup label="Evaluation data" value={source} onChange={setSource} options={SOURCES} className="w-full medium:w-auto" />
        }
      />

      {error && (
        <p className="m3-pane mb-4">
          <span className="block rounded-md bg-error-container px-4 py-3 text-body-medium text-on-error-container">{error}</span>
        </p>
      )}

      <div className={cn("m3-pane m3-grid transition-opacity duration-300", stale && "opacity-60")}>
        {!backtest && !error && (
          <>
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="col-span-2 h-28 rounded-lg medium:col-span-2 expanded:col-span-3" />
            ))}
            <Skeleton className="col-span-4 h-80 rounded-lg medium:col-span-8 expanded:col-span-12" />
          </>
        )}

        {backtest && !ready && (
          <Card className="col-span-full px-6 py-16 text-center text-body-large text-on-surface-variant">{backtest.note}</Card>
        )}

        {ready && (
          <>
            <Kpi label="Precision" value={percent(backtest.current!.precision, 0)} hint={`${count(backtest.current!.tp)} of ${count(backtest.current!.tp + backtest.current!.fp)} alerts were fraud`} />
            <Kpi label="Recall" value={percent(backtest.current!.recall, 0)} hint={`${count(backtest.current!.tp)} of ${count(backtest.fraud ?? 0)} fraud cases caught`} />
            <Kpi label="F1 score" value={backtest.current!.f1.toFixed(2)} hint={`at threshold ${backtest.current_threshold!.toFixed(2)}`} />
            <Kpi
              label="Best F1"
              value={backtest.best_f1!.f1.toFixed(2)}
              hint={`at threshold ${backtest.best_f1!.threshold.toFixed(2)}`}
              accent={backtest.best_f1!.threshold !== backtest.current_threshold}
            />

            <Card className="col-span-4 medium:col-span-8 expanded:col-span-12 large:col-span-8">
              <CardHeader
                title="Threshold trade-off"
                subtitle="Raising the threshold buys precision with recall"
                action={<Legend items={SWEEP_LEGEND} />}
              />
              <div className="px-3 pt-2 pb-4">
                <ThresholdChart points={backtest.thresholds!} current={backtest.current_threshold!} />
              </div>
            </Card>

            <Card className="col-span-4 medium:col-span-8 expanded:col-span-6 large:col-span-4">
              <CardHeader title="At the live threshold" subtitle={`${count(backtest.samples)} transactions evaluated`} />
              <div className="p-5 pt-4">
                <Confusion m={backtest.current!} />
                {backtest.average_precision != null && (
                  <p className="mt-4 flex items-baseline justify-between text-body-medium text-on-surface-variant">
                    Average precision (PR-AUC)
                    <span className="text-title-medium tabular text-on-surface">{backtest.average_precision.toFixed(2)}</span>
                  </p>
                )}
              </div>
            </Card>

            <Card className="col-span-4 medium:col-span-8 expanded:col-span-6 large:col-span-6">
              <CardHeader
                title="Score separation"
                subtitle="Composite score by true label (log scale)"
                action={
                  <Legend
                    items={[
                      { label: "Legitimate", color: "var(--md-ext-series-1)" },
                      { label: "Fraud", color: "var(--md-sys-color-error)" },
                    ]}
                  />
                }
              />
              <div className="px-3 pt-2 pb-4">
                <LabelHistogram bins={backtest.histogram!} threshold={backtest.current_threshold!} />
              </div>
            </Card>
          </>
        )}

        <Card className={cn("col-span-4 medium:col-span-8 expanded:col-span-12", ready && "large:col-span-6")}>
          <CardHeader
            title="Model versions"
            subtitle={
              models?.production_version ? (
                <>
                  In production: <span className="font-mono text-body-small text-on-surface">{models.production_version}</span>
                </>
              ) : (
                "Rules only, no ML model loaded"
              )
            }
            action={
              user?.role === "admin" && (
                <Button
                  variant="tonal"
                  onClick={retrain}
                  disabled={training}
                  icon={<Icon name={training ? "progress_activity" : "model_training"} className={training ? "animate-spin" : undefined} />}
                >
                  {training ? "Training…" : "Retrain now"}
                </Button>
              )
            }
          />
          <div className="p-2 pt-3">
            {!models && <Skeleton className="m-3 h-20 rounded-md" />}
            {models?.runs.length === 0 && (
              <p className="px-3 py-8 text-center text-body-medium text-on-surface-variant">
                No retraining runs yet. A run needs at least 5 alerts confirmed as fraud.
              </p>
            )}
            <ul className="flex flex-col gap-1">
              {models?.runs.map((r, i) => <RunRow key={r.id} run={r} index={i} />)}
            </ul>
          </div>
        </Card>

        {backtest?.note && ready && <p className="col-span-full px-1 text-body-small text-on-surface-variant">{backtest.note}</p>}
      </div>
    </div>
  );
}

function Kpi({ label, value, hint, accent }: { label: string; value: string; hint: string; accent?: boolean }) {
  return (
    <Card className={cn("col-span-2 p-5 medium:col-span-2 expanded:col-span-3", accent && "bg-tertiary-container text-on-tertiary-container")}>
      <p className={cn("text-title-small", accent ? "text-on-tertiary-container" : "text-on-surface-variant")}>{label}</p>
      <p className="emphasized mt-2 text-display-small tabular">{value}</p>
      <p className={cn("mt-1 text-body-small", accent ? "text-on-tertiary-container/80" : "text-on-surface-variant")}>{hint}</p>
    </Card>
  );
}

function Confusion({ m }: { m: ThresholdMetrics }) {
  const cells = [
    { label: "Caught fraud", sub: "true positive", v: m.tp, cls: "bg-error-container text-on-error-container" },
    { label: "False alarm", sub: "false positive", v: m.fp, cls: "bg-warning-container text-on-warning-container" },
    { label: "Missed fraud", sub: "false negative", v: m.fn, cls: "bg-serious-container text-on-serious-container" },
    { label: "Cleared", sub: "true negative", v: m.tn, cls: "bg-success-container text-on-success-container" },
  ];
  return (
    <div className="grid grid-cols-2 gap-2">
      {cells.map((c, i) => (
        <motion.div
          key={c.label}
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ ...spatialDefault, delay: i * 0.05 }}
          className={cn("rounded-md p-4", c.cls)}
        >
          <p className="emphasized text-headline-small tabular">{count(c.v)}</p>
          <p className="mt-1 text-label-large">{c.label}</p>
          <p className="text-body-small opacity-80">{c.sub}</p>
        </motion.div>
      ))}
    </div>
  );
}

function RunRow({ run: r, index }: { run: ModelRun; index: number }) {
  const ch = r.metrics.challenger;
  const champ = r.metrics.champion;
  return (
    <motion.li
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: index * 0.04 }}
      className="flex items-start gap-4 rounded-md px-3 py-3"
    >
      <span
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-full",
          r.promoted ? "bg-success-container text-on-success-container" : "bg-surface-container-high text-on-surface-variant",
        )}
      >
        <Icon name={r.promoted ? "verified_user" : "neurology"} filled={r.promoted} size={20} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-x-2 text-body-large text-on-surface">
          <span className="font-mono text-body-medium">{r.version}</span>
          <span className={cn("rounded-sm px-2 text-label-medium", r.promoted ? "bg-success-container text-on-success-container" : "bg-surface-container-high text-on-surface-variant")}>
            {r.promoted ? "Promoted" : "Kept champion"}
          </span>
        </p>
        <p className="mt-0.5 text-body-medium text-on-surface-variant">
          {dateTime(r.trained_at)} · {TRIGGER_LABEL[r.trigger]}
          {r.created_by && ` · ${displayName(r.created_by)}`}
        </p>
        <p className="mt-1 text-body-small text-on-surface-variant tabular">
          {count(r.labeled_fraud)} fraud / {count(r.labeled_legit)} approved labels · holdout AP {ch.average_precision.toFixed(2)}
          {champ ? ` vs ${champ.average_precision.toFixed(2)} before` : " (no previous model)"}
        </p>
      </div>
    </motion.li>
  );
}
