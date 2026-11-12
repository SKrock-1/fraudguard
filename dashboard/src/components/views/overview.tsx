"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useAlerts } from "@/components/alert-stream";
import { ScorePill, StatusBadge } from "@/components/alerts/badges";
import { AreaChart, BarList, Legend, ScoreHistogram, Sparkline } from "@/components/charts/charts";
import { useAuth } from "@/components/providers";
import { PageHeader, scallop } from "@/components/shell";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Button, Card, CardHeader, ConnectedButtonGroup, Icon, Ripple, Skeleton, cn } from "@/components/ui/m3";
import type { IconName } from "@/lib/icons";
import { api } from "@/lib/api";
import { clock, count, day, displayName, money, percent, relativeTime } from "@/lib/format";
import { spatialDefault } from "@/lib/motion";
import { FACTOR_META, SEVERITY, primaryReason, severityOf } from "@/lib/risk";
import type { Alert, Stats, StatsWindow } from "@/lib/types";

const WINDOWS: { value: StatsWindow; label: string }[] = [
  { value: "1h", label: "1 hour" },
  { value: "24h", label: "24 hours" },
  { value: "7d", label: "7 days" },
];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function OverviewView() {
  const { user } = useAuth();
  const { alerts, version } = useAlerts();
  const router = useRouter();
  const [range, setRange] = useState<StatsWindow>("24h");
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api<Stats>(`/api/alerts/stats?window=${range}`)
        .then((s) => {
          if (cancelled) return;
          setStats(s);
          setError(null);
        })
        .catch((e) => !cancelled && setError(e.message));
    // Debounce socket-driven refreshes so a burst of alerts is one refetch
    const t = setTimeout(load, version ? 400 : 0);
    const poll = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearTimeout(t);
      clearInterval(poll);
    };
  }, [range, version]);

  const pending = alerts.filter((a) => a.status === "pending");
  const bySeverity = { critical: 0, high: 0, elevated: 0, low: 0 };
  for (const a of pending) bySeverity[severityOf(a.risk_score.composite_score)] += 1;
  const recent = alerts.slice(0, 6);
  const stale = !!stats && stats.window !== range;
  const sparkTx = useMemo(() => tail(stats?.series.map((b) => b.transactions) ?? [], 24), [stats]);
  const sparkAlerts = useMemo(() => tail(stats?.series.map((b) => b.alerts) ?? [], 24), [stats]);

  return (
    <div className="pb-10">
      <PageHeader
        title={`${greeting()}, ${displayName(user!.username).split(" ")[0]}`}
        description="Here's what the scoring pipeline has seen."
        actions={
          <ConnectedButtonGroup
            label="Time window"
            value={range}
            onChange={setRange}
            options={WINDOWS}
            className="w-full medium:w-auto"
          />
        }
      />

      {error && !stats && (
        <p className="m3-pane mb-4">
          <span className="block rounded-md bg-error-container px-4 py-3 text-body-medium text-on-error-container">{error}</span>
        </p>
      )}

      <div className={cn("m3-pane m3-grid transition-opacity duration-300", stale && "opacity-60")}>
        {/* Hero: the one number this view leads with */}
        <section className="relative col-span-4 overflow-hidden rounded-xl bg-primary-container p-6 text-on-primary-container medium:col-span-8 expanded:col-span-4 expanded:row-span-2">
          <svg aria-hidden viewBox="0 0 200 200" className="pointer-events-none absolute -right-14 -bottom-16 size-64 opacity-40">
            <path d={scallop(100, 100, 96, 0.07, 12)} fill="var(--md-sys-color-primary)" opacity={0.35} />
          </svg>
          <div className="relative flex h-full flex-col">
            <p className="text-title-medium">Awaiting review</p>
            <div className="emphasized mt-2 text-display-large tabular">
              {stats ? <AnimatedNumber value={pending.length} format={(n) => count(Math.round(n))} /> : <Skeleton className="h-16 w-24" />}
            </div>
            <p className="mt-1 text-body-large">
              {pending.length
                ? `${bySeverity.critical} critical, oldest ${relativeTime(pending[pending.length - 1].transaction.timestamp)}`
                : "The queue is clear"}
            </p>

            {pending.length > 0 && (
              <ul className="mt-5 flex flex-col gap-2.5" aria-label="Pending alerts by severity">
                {(["critical", "high", "elevated"] as const).map((sev) => (
                  <li key={sev} className="grid grid-cols-[100px_1fr_28px] items-center gap-3 text-body-medium">
                    <span className="flex items-center gap-2">
                      <Icon name={SEVERITY[sev].icon} filled size={18} />
                      {SEVERITY[sev].label}
                    </span>
                    <span className="h-2 overflow-hidden rounded-full bg-on-primary-container/15">
                      <motion.span
                        className="block h-full rounded-full"
                        style={{ background: SEVERITY[sev].color }}
                        initial={{ width: 0 }}
                        animate={{ width: `${(bySeverity[sev] / pending.length) * 100}%` }}
                        transition={spatialDefault}
                      />
                    </span>
                    <span className="text-right text-label-large tabular">{bySeverity[sev]}</span>
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-auto pt-6">
              <Button variant="filled" size="md" onClick={() => router.push("/alerts")} icon={<Icon name="arrow_forward" />}>
                Review queue
              </Button>
            </div>
          </div>
        </section>

        <StatCard
          className="col-span-2 medium:col-span-4"
          icon="monitoring"
          tone="bg-primary-container text-on-primary-container"
          label="Transactions scored"
          value={stats?.totals.scored}
          format={(n) => count(Math.round(n), true)}
          footer={stats && `Average score ${stats.totals.avg_score.toFixed(2)}`}
          spark={<Sparkline values={sparkTx} color="var(--md-ext-series-1)" />}
        />
        <StatCard
          className="col-span-2 medium:col-span-4"
          icon="notifications_active"
          tone="bg-error-container text-on-error-container"
          label="Alerts raised"
          value={stats?.totals.alerts}
          format={(n) => count(Math.round(n))}
          footer={stats && `${percent(stats.totals.alert_rate)} of transactions`}
          spark={<Sparkline values={sparkAlerts} color="var(--md-ext-series-2)" />}
        />
        <StatCard
          className="col-span-4 medium:col-span-8"
          icon="account_balance_wallet"
          tone="bg-tertiary-container text-on-tertiary-container"
          label="Fraud blocked"
          value={stats ? Number(stats.totals.blocked_amount) : undefined}
          format={(n) => money(n, "USD", n >= 10_000)}
          footer={stats && `${count(stats.totals.rejected)} confirmed of ${count(stats.totals.resolved)} resolved`}
          aside={stats && <ResolutionMeter approved={stats.totals.approved} rejected={stats.totals.rejected} pending={stats.totals.pending} />}
        />

        <Card className="col-span-4 medium:col-span-8 expanded:col-span-12 large:col-span-8">
          <CardHeader
            title="Scoring throughput"
            subtitle="Transactions scored and alerts raised per interval"
            action={
              <Legend
                items={[
                  { label: "Transactions", color: "var(--md-ext-series-1)", shape: "line" },
                  { label: "Alerts", color: "var(--md-ext-series-2)", shape: "line" },
                ]}
              />
            }
          />
          <div className="p-3 pt-4">
            {stats ? (
              <AreaChart
                data={stats.series.map((b) => ({ t: b.t, values: [b.transactions, b.alerts] }))}
                series={[
                  { label: "Transactions", color: "var(--md-ext-series-1)" },
                  { label: "Alerts", color: "var(--md-ext-series-2)" },
                ]}
                formatX={stats.window === "7d" ? day : clock}
                formatTooltipX={(t) => (stats.window === "7d" ? day(t) : `${day(t)}, ${clock(t)}`)}
                height={264}
              />
            ) : (
              <Skeleton className="h-[264px] w-full rounded-md" />
            )}
          </div>
        </Card>

        <Card className="col-span-4 medium:col-span-8 expanded:col-span-6 large:col-span-4">
          <CardHeader title="What's triggering alerts" subtitle="Share of scored transactions where each signal fired" />
          <div className="p-5 pt-6">
            {stats ? (
              <BarList
                total={stats.totals.scored}
                items={[...stats.rule_triggers]
                  .sort((a, b) => b.count - a.count)
                  .map((r) => ({
                    key: r.rule,
                    label: FACTOR_META[r.rule].label,
                    value: r.count,
                    color: FACTOR_META[r.rule].color,
                    icon: FACTOR_META[r.rule].icon,
                  }))}
              />
            ) : (
              <div className="flex flex-col gap-5">
                {[0, 1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-9 w-full" />
                ))}
              </div>
            )}
          </div>
        </Card>

        <Card className="col-span-4 medium:col-span-8 expanded:col-span-6 large:col-span-5">
          <CardHeader
            title="Risk score distribution"
            subtitle="Composite score per transaction (log scale)"
            action={
              <Legend
                items={[
                  { label: "Below threshold", color: "var(--md-ext-series-1)" },
                  { label: "Alerted", color: "var(--md-sys-color-error)" },
                ]}
              />
            }
          />
          <div className="p-3 pt-4">
            {stats ? (
              <ScoreHistogram bins={stats.score_histogram} threshold={stats.threshold} height={240} />
            ) : (
              <Skeleton className="h-[240px] w-full rounded-md" />
            )}
          </div>
        </Card>

        <Card className="col-span-4 medium:col-span-8 expanded:col-span-12 large:col-span-7">
          <CardHeader
            title="Latest alerts"
            subtitle="Streaming in as they're raised"
            action={
              <Link href="/alerts" className="state-layer relative inline-flex h-10 items-center rounded-full px-3 text-label-large text-primary">
                View all
              </Link>
            }
          />
          <ul className="px-2 pt-2 pb-3">
            {recent.length === 0 &&
              [0, 1, 2, 3].map((i) => (
                <li key={i} className="px-3 py-2">
                  <Skeleton className="h-14 w-full rounded-md" />
                </li>
              ))}
            {recent.map((a) => (
              <AlertListItem key={a.id} alert={a} />
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

function AlertListItem({ alert }: { alert: Alert }) {
  const sev = SEVERITY[severityOf(alert.risk_score.composite_score)];
  return (
    <motion.li layout transition={spatialDefault}>
      <Link
        href={`/alerts?id=${alert.id}`}
        className="state-layer relative flex min-h-[72px] items-center gap-4 overflow-hidden rounded-lg px-3 py-2"
      >
        <Ripple />
        <span className="relative flex size-10 shrink-0 items-center justify-center">
          <svg viewBox="0 0 40 40" className="absolute inset-0" aria-hidden>
            <path d={scallop(20, 20, 20, 0.1, 6)} fill={sev.track} />
          </svg>
          <Icon name={sev.icon} filled size={20} className="relative" style={{ color: sev.color }} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-body-large text-on-surface">{alert.transaction.merchant}</p>
          <p className="truncate text-body-medium text-on-surface-variant">
            {primaryReason(alert)} · {relativeTime(alert.transaction.timestamp)}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="text-title-small text-on-surface tabular">{money(alert.transaction.amount, alert.transaction.currency)}</span>
          <span className="hidden medium:block">
            <StatusBadge status={alert.status} compact />
          </span>
          <span className="medium:hidden">
            <ScorePill score={alert.risk_score.composite_score} showLabel={false} />
          </span>
        </div>
      </Link>
    </motion.li>
  );
}

function ResolutionMeter({ approved, rejected, pending }: { approved: number; rejected: number; pending: number }) {
  const total = Math.max(1, approved + rejected + pending);
  const parts = [
    { label: "Fraud", value: rejected, className: "bg-error" },
    { label: "Approved", value: approved, className: "bg-success" },
    { label: "Pending", value: pending, className: "bg-warning" },
  ];
  return (
    <div className="w-full max-w-[320px]">
      <div className="flex h-3 gap-[3px] overflow-hidden rounded-full">
        {parts.map((p) =>
          p.value ? (
            <motion.span
              key={p.label}
              className={cn("h-full rounded-[3px] first:rounded-l-full last:rounded-r-full", p.className)}
              initial={{ flexGrow: 0 }}
              animate={{ flexGrow: p.value / total }}
              transition={spatialDefault}
            />
          ) : null,
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-label-medium text-on-surface-variant">
        {parts.map((p) => (
          <span key={p.label} className="inline-flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", p.className)} />
            {p.label} <span className="text-on-surface tabular">{p.value}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function tail<T>(arr: T[], n: number) {
  return arr.slice(Math.max(0, arr.length - n));
}

function StatCard({
  icon,
  tone,
  label,
  value,
  format,
  footer,
  spark,
  aside,
  className,
}: {
  icon: IconName;
  tone: string;
  label: string;
  value: number | undefined;
  format: (n: number) => string;
  footer?: ReactNode;
  spark?: ReactNode;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <Card variant="filled" className={cn("card-lift p-5", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-label-large text-on-surface-variant">
            <span className={cn("flex size-9 items-center justify-center rounded-full", tone)}>
              <Icon name={icon} filled size={20} />
            </span>
            {label}
          </div>
          <div className="emphasized mt-4 text-headline-large text-on-surface medium:text-display-small">
            {value === undefined ? <Skeleton className="h-11 w-28" /> : <AnimatedNumber value={value} format={format} />}
          </div>
          <div className="mt-1 min-h-5 text-body-medium text-on-surface-variant">{footer}</div>
        </div>
        {spark && <div className="hidden w-28 shrink-0 medium:block">{spark}</div>}
        {aside}
      </div>
    </Card>
  );
}
