"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { useAlerts } from "@/components/alert-stream";
import { PageHeader } from "@/components/shell";
import { Avatar, Card, Icon, Ripple, Skeleton, cn } from "@/components/ui/m3";
import { api } from "@/lib/api";
import { clock, dateTime, day, displayName, money } from "@/lib/format";
import { spatialDefault, spatialFast } from "@/lib/motion";
import type { AuditEntry } from "@/lib/types";

export function AuditView() {
  const { version } = useAlerts();
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    api<AuditEntry[]>("/api/audit?limit=300")
      .then((e) => {
        setEntries(e);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, [version]);

  const groups = useMemo(() => {
    const out: { day: string; items: AuditEntry[] }[] = [];
    for (const e of entries ?? []) {
      const d = day(e.timestamp);
      if (out.at(-1)?.day !== d) out.push({ day: d, items: [] });
      out.at(-1)!.items.push(e);
    }
    return out;
  }, [entries]);

  return (
    <div className="pb-10">
      <PageHeader
        title="Audit trail"
        description="Every analyst decision, newest first. Database triggers make these records insert-only."
        actions={
          <span className="inline-flex h-8 items-center gap-2 rounded-sm bg-tertiary-container px-3 text-label-large text-on-tertiary-container">
            <Icon name="lock" filled size={18} /> Immutable
          </span>
        }
      />

      <div className="m3-pane m3-grid">
        <div className="col-span-full large:col-span-10 large:col-start-2 xlarge:col-span-8 xlarge:col-start-3">
          {error && (
            <p className="mb-4 rounded-md bg-error-container px-4 py-3 text-body-medium text-on-error-container">{error}</p>
          )}

          {!entries && !error && (
            <Card className="flex flex-col gap-2 p-3">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className="h-16 w-full rounded-md" />
              ))}
            </Card>
          )}

          {entries?.length === 0 && (
            <Card className="px-6 py-16 text-center text-body-large text-on-surface-variant">No decisions recorded yet.</Card>
          )}

          <div className="flex flex-col gap-6">
            {groups.map((g) => (
              <section key={g.day} aria-label={g.day}>
                <h2 className="px-4 pb-2 text-title-small text-primary">{g.day}</h2>
                <Card className="overflow-hidden p-1.5">
                  <ul className="flex flex-col divide-y divide-outline-variant">
                    {g.items.map((e) => (
                      <AuditItem key={e.id} entry={e} expanded={open === e.id} onToggle={() => setOpen(open === e.id ? null : e.id)} />
                    ))}
                  </ul>
                </Card>
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function AuditItem({ entry: e, expanded, onToggle }: { entry: AuditEntry; expanded: boolean; onToggle: () => void }) {
  const fraud = e.action.endsWith("rejected");
  const p = e.payload as Record<string, string | number | boolean | undefined>;
  const alertId = e.target.startsWith("Alert:") ? e.target.slice(6) : null;

  return (
    <li className={cn("rounded-md transition-colors duration-300", expanded && "bg-surface-container-high")}>
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        className="state-layer relative flex min-h-[72px] w-full items-center gap-4 overflow-hidden rounded-md px-3 py-2 text-left"
      >
        <Ripple />
        <span
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-full",
            fraud ? "bg-error-container text-on-error-container" : "bg-success-container text-on-success-container",
          )}
        >
          <Icon name={fraud ? "block" : "check_circle"} filled size={20} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-body-large text-on-surface">
            {fraud ? "Fraud confirmed" : "Approved"}
            {p.amount && <span className="text-on-surface-variant tabular"> · {money(String(p.amount))}</span>}
          </p>
          <p className="flex items-center gap-1.5 truncate text-body-medium text-on-surface-variant">
            {e.actor_username ? displayName(e.actor_username) : "System"}
            <span aria-hidden>·</span>
            <span className="font-mono text-body-small">{e.target}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="hidden text-body-small text-on-surface-variant tabular medium:block">#{e.id}</span>
          <span className="text-label-medium text-on-surface-variant tabular" title={dateTime(e.timestamp)}>
            {clock(e.timestamp)}
          </span>
          <motion.span animate={{ rotate: expanded ? 180 : 0 }} transition={spatialFast} className="text-on-surface-variant">
            <Icon name="expand_more" />
          </motion.span>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="payload"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={spatialDefault}
            style={{ overflow: "hidden" }}
          >
            <div className="px-3 pb-3 medium:pl-[68px]">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-body-medium text-on-surface-variant">
                {e.actor_username && (
                  <span className="flex items-center gap-2">
                    <Avatar name={e.actor_username} size={24} />
                    {displayName(e.actor_username)}
                  </span>
                )}
                <span>
                  {String(p.previous_status)} → <span className="text-on-surface">{String(p.new_status)}</span>
                </span>
                <span className="tabular">score {Number(p.composite_score ?? 0).toFixed(2)}</span>
                <span className="tabular">{dateTime(e.timestamp)}</span>
                {alertId && (
                  <Link
                    href={`/alerts?id=${alertId}`}
                    className="state-layer relative ml-auto inline-flex h-10 items-center rounded-full px-3 text-label-large text-primary"
                  >
                    Open alert
                  </Link>
                )}
              </div>
              {p.notes && <p className="mt-3 text-body-large text-on-surface">“{String(p.notes)}”</p>}
              <pre className="mt-3 overflow-x-auto rounded-md bg-surface-container-lowest p-4 font-mono text-body-small text-on-surface-variant">
                {JSON.stringify(e.payload, null, 2)}
              </pre>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}
