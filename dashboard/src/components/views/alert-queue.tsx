"use client";

import { AnimatePresence, motion } from "motion/react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertDetail } from "@/components/alerts/alert-detail";
import { ScorePill } from "@/components/alerts/badges";
import { useAlerts } from "@/components/alert-stream";
import { PageHeader, scallop } from "@/components/shell";
import { FilterChip, Icon, Kbd, Ripple, Skeleton, cn } from "@/components/ui/m3";
import { api } from "@/lib/api";
import { money, relativeTime } from "@/lib/format";
import { effectsDefault, spatialDefault } from "@/lib/motion";
import { FACTOR_META, SEVERITY, severityOf } from "@/lib/risk";
import type { Alert, AlertStatus, Stats } from "@/lib/types";

type Filter = AlertStatus | "all";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "rejected", label: "Fraud" },
  { value: "approved", label: "Approved" },
  { value: "all", label: "All" },
];

export function AlertQueueView() {
  return (
    <Suspense fallback={<QueueSkeleton />}>
      <AlertQueue />
    </Suspense>
  );
}

function useTwoPane() {
  const [two, setTwo] = useState(true);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 840px)");
    const sync = () => setTwo(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return two;
}

function AlertQueue() {
  const { alerts, loading, freshIds } = useAlerts();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const twoPane = useTwoPane();
  const [filter, setFilter] = useState<Filter>("pending");
  const [query, setQuery] = useState("");
  const [threshold, setThreshold] = useState(0.6);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selectedId = Number(params.get("id")) || null;
  const select = useCallback(
    (id: number | null) => router.replace(id ? `${pathname}?id=${id}` : pathname, { scroll: false }),
    [router, pathname],
  );

  useEffect(() => {
    api<Stats>("/api/alerts/stats?window=1h")
      .then((s) => setThreshold(s.threshold))
      .catch(() => {});
  }, []);

  const counts = useMemo(() => {
    const c = { pending: 0, approved: 0, rejected: 0, all: alerts.length };
    for (const a of alerts) c[a.status] += 1;
    return c;
  }, [alerts]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return alerts.filter(
      (a) =>
        (filter === "all" || a.status === filter) &&
        (!q ||
          a.transaction.merchant.toLowerCase().includes(q) ||
          a.transaction.account_number.toLowerCase().includes(q) ||
          String(a.id).includes(q)),
    );
  }, [alerts, filter, query]);

  const selected = alerts.find((a) => a.id === selectedId) ?? null;

  // A deep link to an alert outside the current filter widens the filter to show
  // it. Only on selection change, so reviewing an alert doesn't flip the filter.
  const selectionKey = `${selectedId}:${selected ? 1 : 0}`;
  const [seenSelection, setSeenSelection] = useState(selectionKey);
  if (selectionKey !== seenSelection) {
    setSeenSelection(selectionKey);
    if (selected && filter !== "all" && selected.status !== filter) setFilter("all");
  }

  // Two-pane layouts always show something in the detail pane
  useEffect(() => {
    if (twoPane && !selectedId && visible.length) select(visible[0].id);
  }, [twoPane, selectedId, visible, select]);

  const move = useCallback(
    (delta: number) => {
      if (!visible.length) return;
      const idx = visible.findIndex((a) => a.id === selectedId);
      const next = visible[Math.max(0, Math.min(visible.length - 1, (idx < 0 ? -1 : idx) + delta))];
      select(next.id);
      listRef.current?.querySelector(`[data-id="${next.id}"]`)?.scrollIntoView({ block: "nearest" });
    },
    [visible, selectedId, select],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        move(1);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        move(-1);
      } else if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "Escape" && !twoPane && selectedId) {
        select(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [move, twoPane, selectedId, select]);

  // After a review, keep the analyst moving: jump to the next pending alert
  const onReviewed = (reviewed: Alert) => {
    if (filter !== "pending") return;
    const idx = visible.findIndex((a) => a.id === reviewed.id);
    const rest = visible.filter((a) => a.id !== reviewed.id);
    const next = rest[Math.min(idx, rest.length - 1)];
    select(twoPane && next ? next.id : null);
  };

  const singlePaneDetail = !twoPane && selected;

  return (
    <div className="flex flex-col expanded:h-dvh">
      <PageHeader
        title="Alert queue"
        description="Transactions scored above the alert threshold, newest first."
        actions={
          <div className="hidden items-center gap-4 text-body-small text-on-surface-variant large:flex">
            <Shortcut keys={["J", "K"]} label="Move" />
            <Shortcut keys={["A"]} label="Approve" />
            <Shortcut keys={["R"]} label="Fraud" />
            <Shortcut keys={["/"]} label="Search" />
          </div>
        }
      />

      <div className="m3-pane flex min-h-0 flex-1 gap-[var(--md-layout-gutter)] pb-6">
        <section className="flex min-h-0 w-full flex-col expanded:w-[380px] expanded:shrink-0 xlarge:w-[440px]">
          <label className="flex h-14 shrink-0 items-center gap-3 rounded-full bg-surface-container-high px-4 text-on-surface-variant focus-within:shadow-[inset_0_0_0_2px_var(--md-sys-color-primary)]">
            <Icon name="search" />
            <span className="sr-only">Search alerts</span>
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search merchant, account or ID"
              className="h-full min-w-0 flex-1 bg-transparent text-body-large text-on-surface outline-none placeholder:text-on-surface-variant"
            />
            <span className="hidden expanded:inline-flex">
              <Kbd>/</Kbd>
            </span>
          </label>

          <div className="-mx-1 mt-3 flex shrink-0 gap-2 overflow-x-auto px-1 pb-1" role="group" aria-label="Filter by status">
            {FILTERS.map((f) => (
              <FilterChip
                key={f.value}
                selected={filter === f.value}
                onClick={() => setFilter(f.value)}
                trailing={<span className="text-label-medium tabular">{counts[f.value]}</span>}
              >
                {f.label}
              </FilterChip>
            ))}
          </div>

          <ul
            ref={listRef}
            role="listbox"
            aria-label="Alerts"
            className="relative mt-3 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pb-2 expanded:pr-1"
          >
            {loading &&
              [0, 1, 2, 3, 4].map((i) => (
                <li key={i}>
                  <Skeleton className="h-[104px] w-full rounded-lg" />
                </li>
              ))}
            <AnimatePresence initial={false} mode="popLayout">
              {visible.map((a) =>
                singlePaneDetail && a.id === selected.id ? (
                  <li key={a.id} className="h-[104px]" aria-hidden />
                ) : (
                  <AlertRow
                    key={a.id}
                    alert={a}
                    active={twoPane && a.id === selectedId}
                    fresh={freshIds.has(a.id)}
                    morphId={twoPane ? undefined : `alert-card-${a.id}`}
                    onSelect={() => select(a.id)}
                  />
                ),
              )}
            </AnimatePresence>
            {!loading && visible.length === 0 && <EmptyState filter={filter} query={query} />}
          </ul>
        </section>

        {twoPane && (
          <section className="hidden min-h-0 flex-1 overflow-hidden rounded-xl bg-surface-container-low expanded:block">
            <AnimatePresence mode="wait">
              {selected ? (
                <AlertDetail key={selected.id} alert={selected} threshold={threshold} onReviewed={onReviewed} />
              ) : (
                <motion.div
                  key="none"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex h-full flex-col items-center justify-center gap-3 text-center"
                >
                  <Icon name="gpp_maybe" size={40} weight={300} className="text-on-surface-variant" />
                  <p className="text-body-large text-on-surface-variant">Select an alert to review</p>
                </motion.div>
              )}
            </AnimatePresence>
          </section>
        )}
      </div>

      {/* Single pane: the tapped card container-transforms into the full-screen detail */}
      <AnimatePresence>
        {singlePaneDetail && (
          <motion.div
            key={selected.id}
            layoutId={`alert-card-${selected.id}`}
            transition={spatialDefault}
            style={{ borderRadius: 0 }}
            className="fixed inset-0 z-40 overflow-hidden bg-surface-container-low"
          >
            <motion.div
              className="h-full"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, transition: { ...effectsDefault, delay: 0.06 } }}
              exit={{ opacity: 0, transition: { duration: 0.06 } }}
            >
              <AlertDetail alert={selected} threshold={threshold} onReviewed={onReviewed} onClose={() => select(null)} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Shortcut({ keys, label }: { keys: string[]; label: string }) {
  return (
    <span className="flex items-center gap-1">
      {keys.map((k) => (
        <Kbd key={k}>{k}</Kbd>
      ))}
      <span className="ml-0.5">{label}</span>
    </span>
  );
}

function AlertRow({
  alert,
  active,
  fresh,
  morphId,
  onSelect,
}: {
  alert: Alert;
  active: boolean;
  fresh: boolean;
  morphId?: string;
  onSelect: () => void;
}) {
  const score = alert.risk_score.composite_score;
  const sev = SEVERITY[severityOf(score)];
  const rules = alert.risk_score.factors.triggered_rules;

  return (
    <motion.li
      layout
      data-id={alert.id}
      initial={{ opacity: 0, y: -16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: -24, transition: effectsDefault }}
      transition={spatialDefault}
      role="option"
      aria-selected={active}
    >
      <motion.button
        layoutId={morphId}
        transition={spatialDefault}
        onClick={onSelect}
        style={{ borderRadius: 16 }}
        className={cn(
          "state-layer relative flex w-full gap-4 overflow-hidden p-4 text-left transition-colors duration-200",
          active ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container text-on-surface",
        )}
      >
        <Ripple />
        {fresh && (
          <motion.span
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-error-container"
            initial={{ opacity: 1 }}
            animate={{ opacity: 0 }}
            transition={{ duration: 2.4, ease: "easeOut" }}
          />
        )}
        <span className="relative mt-0.5 flex size-10 shrink-0 items-center justify-center">
          <svg viewBox="0 0 40 40" className="absolute inset-0" aria-hidden>
            <path d={scallop(20, 20, 20, 0.1, 6)} fill={sev.track} />
          </svg>
          <Icon name={sev.icon} filled size={20} className="relative" style={{ color: sev.color }} />
        </span>
        <div className="relative min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <p className="truncate text-body-large">{alert.transaction.merchant}</p>
            <p className="shrink-0 text-title-small tabular">{money(alert.transaction.amount, alert.transaction.currency)}</p>
          </div>
          <div className={cn("mt-0.5 flex items-center justify-between gap-3 text-body-small", !active && "text-on-surface-variant")}>
            <p className="truncate font-mono">{alert.transaction.account_number}</p>
            <p className="shrink-0">{relativeTime(alert.transaction.timestamp)}</p>
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <ScorePill score={score} showLabel={false} />
            {rules.map((r) => (
              <span
                key={r}
                className="inline-flex h-6 items-center gap-1 rounded-sm border border-outline-variant pr-2 pl-1 text-label-medium"
              >
                <Icon name={FACTOR_META[r].icon} filled size={16} style={{ color: FACTOR_META[r].color }} />
                {FACTOR_META[r].short}
              </span>
            ))}
            {alert.status !== "pending" && (
              <span className={cn("ml-auto text-label-medium", !active && "text-on-surface-variant")}>
                {alert.status === "rejected" ? "Fraud" : "Approved"}
              </span>
            )}
          </div>
        </div>
      </motion.button>
    </motion.li>
  );
}

function EmptyState({ filter, query }: { filter: Filter; query: string }) {
  const clear = filter === "pending" && !query;
  return (
    <motion.li
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1, transition: spatialDefault }}
      className="flex flex-col items-center justify-center gap-4 px-6 py-16 text-center"
    >
      <span className="relative flex size-20 items-center justify-center text-on-tertiary-container">
        <svg viewBox="0 0 80 80" className="absolute inset-0" aria-hidden>
          <path d={scallop(40, 40, 40, 0.08, 9)} fill="var(--md-sys-color-tertiary-container)" />
        </svg>
        <Icon name={clear ? "done_all" : "inbox"} size={32} className="relative" />
      </span>
      <div>
        <p className="text-title-medium text-on-surface">{clear ? "Queue clear" : "No matching alerts"}</p>
        <p className="mt-1 text-body-medium text-on-surface-variant">
          {clear ? "New alerts stream in here the moment they're raised." : "Try another filter or search."}
        </p>
      </div>
    </motion.li>
  );
}

function QueueSkeleton() {
  return (
    <div className="m3-pane pt-8">
      <Skeleton className="h-9 w-56" />
      <Skeleton className="mt-6 h-[70vh] w-full rounded-xl" />
    </div>
  );
}
