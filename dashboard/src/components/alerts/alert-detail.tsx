"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { api } from "@/lib/api";
import { dateTime, displayName, money, relativeTime } from "@/lib/format";
import { effectsDefault, spatialDefault } from "@/lib/motion";
import type { Alert, AuditEntry } from "@/lib/types";
import { useAlerts } from "../alert-stream";
import { useSnackbar } from "../providers";
import { Avatar, Button, Icon, IconButton, Kbd, cn } from "../ui/m3";
import { StatusBadge } from "./badges";
import { ContributionBar, FactorList, ScoreGauge } from "./explain";

export function AlertDetail({
  alert,
  threshold,
  onReviewed,
  onClose,
}: {
  alert: Alert;
  threshold: number;
  onReviewed: (alert: Alert) => void;
  onClose?: () => void;
}) {
  const tx = alert.transaction;
  const factors = alert.risk_score.factors;

  return (
    <motion.article
      key={alert.id}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0, transition: spatialDefault }}
      exit={{ opacity: 0, transition: effectsDefault }}
      className="@container flex h-full flex-col"
    >
      <header className="flex flex-col gap-5 px-5 pt-4 pb-6 @md:flex-row @md:items-center @md:px-6 @md:pt-6">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {onClose && (
              <IconButton label="Back to queue" onClick={onClose} className="-ml-2 expanded:hidden">
                <Icon name="arrow_back" />
              </IconButton>
            )}
            <StatusBadge status={alert.status} />
            <span className="font-mono text-label-medium text-on-surface-variant">
              ALT-{String(alert.id).padStart(5, "0")} · {relativeTime(tx.timestamp)}
            </span>
          </div>
          <h2 className="mt-3 text-title-large text-on-surface">{tx.merchant}</h2>
          <p className="emphasized mt-1 text-display-small text-on-surface tabular">{money(tx.amount, tx.currency)}</p>
        </div>
        <div className="self-start rounded-xl bg-surface-container-high px-5 pt-4 pb-3 @md:self-auto">
          <ScoreGauge score={alert.risk_score.composite_score} threshold={threshold} />
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 pb-6 @md:px-6">
        <section aria-labelledby="why-title">
          <SectionTitle id="why-title">Why this was flagged</SectionTitle>
          <div className="mt-4">
            <ContributionBar factors={factors} threshold={threshold} />
          </div>
          <div className="mt-4">
            <FactorList factors={factors} currency={tx.currency} />
          </div>
        </section>

        <section className="mt-8" aria-labelledby="tx-title">
          <SectionTitle id="tx-title">Transaction</SectionTitle>
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-4 rounded-lg border border-outline-variant p-4 @sm:grid-cols-2">
            <Detail label="Account">
              <span className="font-mono">{tx.account_number}</span>
            </Detail>
            <Detail label="Occurred">{dateTime(tx.timestamp)}</Detail>
            <Detail label="Location">
              {tx.lat && tx.lng ? (
                <span className="inline-flex items-center gap-1 tabular">
                  <Icon name="location_on" filled size={18} className="text-primary" />
                  {Number(tx.lat).toFixed(3)}, {Number(tx.lng).toFixed(3)}
                </span>
              ) : (
                <span className="text-on-surface-variant">Not provided</span>
              )}
            </Detail>
            <Detail label="Model">
              <span className="font-mono">{alert.risk_score.model_version}</span>
            </Detail>
            <div className="@sm:col-span-2">
              <Detail label="Idempotency key">
                <CopyValue value={tx.idempotency_key} />
              </Detail>
            </div>
          </dl>
        </section>

        <AuditHistory alertId={alert.id} status={alert.status} />
      </div>

      <AnimatePresence mode="wait" initial={false}>
        {alert.status === "pending" ? (
          <ReviewBar key="review" alert={alert} onReviewed={onReviewed} />
        ) : (
          <Resolution key="resolved" alert={alert} />
        )}
      </AnimatePresence>
    </motion.article>
  );
}

function SectionTitle({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h3 id={id} className="text-title-small text-on-surface-variant">
      {children}
    </h3>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-label-medium text-on-surface-variant">{label}</dt>
      <dd className="mt-1 truncate text-body-medium text-on-surface">{children}</dd>
    </div>
  );
}

function CopyValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard?.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        });
      }}
      aria-label="Copy idempotency key"
      className="state-layer relative inline-flex max-w-full items-center gap-2 rounded-sm bg-surface-container-high px-2.5 py-1.5 font-mono text-body-small text-on-surface-variant"
    >
      <span className="truncate">{value}</span>
      {copied ? <Icon name="check" size={18} className="text-success" /> : <Icon name="content_copy" size={18} />}
    </button>
  );
}

function ReviewBar({ alert, onReviewed }: { alert: Alert; onReviewed: (alert: Alert) => void }) {
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState<"approved" | "rejected" | null>(null);
  const snackbar = useSnackbar();
  const { upsert } = useAlerts();
  const notesRef = useRef<HTMLTextAreaElement>(null);

  const review = async (decision: "approved" | "rejected") => {
    if (busy) return;
    setBusy(decision);
    try {
      const res = await api<{ alert: Alert; audit_log_id: number }>(`/api/alerts/${alert.id}/review`, {
        method: "POST",
        json: { decision, notes },
      });
      upsert(res.alert);
      snackbar({
        tone: "success",
        message: `${decision === "rejected" ? "Marked as fraud" : "Approved"}: ${alert.transaction.merchant}. Audit entry #${res.audit_log_id}`,
      });
      onReviewed(res.alert);
    } catch (e) {
      snackbar({ tone: "alert", message: e instanceof Error ? `Review failed: ${e.message}` : "Review failed" });
      setBusy(null);
    }
  };

  const onKey = useEffectEvent((e: KeyboardEvent) => {
    const target = e.target as HTMLElement;
    if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") {
      if (e.key === "Escape") target.blur();
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "a") review("approved");
    if (e.key === "r") review("rejected");
    if (e.key === "n") {
      e.preventDefault();
      notesRef.current?.focus();
    }
  });

  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <motion.footer
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0, transition: spatialDefault }}
      exit={{ opacity: 0, y: 16, transition: effectsDefault }}
      className="border-t border-outline-variant bg-surface-container px-5 py-4 @md:px-6"
    >
      <label className="block">
        <span className="sr-only">Review note</span>
        <textarea
          ref={notesRef}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="Add a note for the audit record (optional)"
          className="w-full resize-none rounded-xs bg-surface-container-highest px-4 py-3 text-body-large text-on-surface shadow-[inset_0_-1px_0_var(--md-sys-color-on-surface-variant)] outline-none placeholder:text-on-surface-variant focus:shadow-[inset_0_-2px_0_var(--md-sys-color-primary)]"
        />
      </label>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="success"
          size="sm"
          onClick={() => review("approved")}
          disabled={!!busy}
          icon={<Icon name={busy === "approved" ? "progress_activity" : "verified_user"} filled className={busy === "approved" ? "animate-spin" : undefined} />}
          className="flex-1 @md:flex-none"
        >
          Approve
          <span className="hidden expanded:inline-flex"><Kbd onColor>A</Kbd></span>
        </Button>
        <Button
          variant="error"
          size="sm"
          onClick={() => review("rejected")}
          disabled={!!busy}
          icon={<Icon name={busy === "rejected" ? "progress_activity" : "block"} className={busy === "rejected" ? "animate-spin" : undefined} />}
          className="flex-1 @md:flex-none"
        >
          Confirm fraud
          <span className="hidden expanded:inline-flex"><Kbd onColor>R</Kbd></span>
        </Button>
        <p className="ml-auto hidden items-center gap-1.5 text-body-small text-on-surface-variant @lg:flex">
          <Icon name="lock" filled size={16} /> Permanent and audited
        </p>
      </div>
    </motion.footer>
  );
}

function Resolution({ alert }: { alert: Alert }) {
  const fraud = alert.status === "rejected";
  return (
    <motion.footer
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0, transition: spatialDefault }}
      exit={{ opacity: 0, transition: effectsDefault }}
      className={cn(
        "px-5 py-4 @md:px-6",
        fraud ? "bg-error-container text-on-error-container" : "bg-success-container text-on-success-container",
      )}
    >
      <div className="flex items-start gap-3">
        {alert.assigned_to_username && <Avatar name={alert.assigned_to_username} size={36} />}
        <div className="min-w-0 flex-1 text-body-medium">
          <p>
            <span className="text-title-small">
              {alert.assigned_to_username ? displayName(alert.assigned_to_username) : "An analyst"}
            </span>{" "}
            {fraud ? "confirmed this as fraud" : "approved this as legitimate"}
            {alert.resolved_at && <span className="opacity-80"> · {relativeTime(alert.resolved_at)}</span>}
          </p>
          {alert.notes && <p className="mt-1 opacity-90">“{alert.notes}”</p>}
        </div>
        <Icon name="lock" filled size={20} label="Locked decision" className="mt-0.5 opacity-80" />
      </div>
    </motion.footer>
  );
}

function AuditHistory({ alertId, status }: { alertId: number; status: Alert["status"] }) {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<AuditEntry[]>(`/api/audit?target=Alert:${alertId}`)
      .then((e) => !cancelled && setEntries(e))
      .catch(() => !cancelled && setEntries([]));
    return () => {
      cancelled = true;
    };
  }, [alertId, status]);

  if (!entries?.length) return null;
  return (
    <section className="mt-8" aria-labelledby="audit-title">
      <SectionTitle id="audit-title">Audit record</SectionTitle>
      <ol className="mt-3 flex flex-col gap-2">
        {entries.map((e) => (
          <li key={e.id} className="flex items-center gap-3 rounded-md bg-surface-container-high px-4 py-3 text-body-medium">
            <Icon name="fingerprint" size={20} className="text-primary" />
            <span className="font-mono text-label-medium text-on-surface-variant">#{e.id}</span>
            <span className={cn("text-label-large", e.action.endsWith("rejected") ? "text-error" : "text-success")}>
              {e.action.endsWith("rejected") ? "Fraud" : "Approved"}
            </span>
            <span className="truncate text-on-surface-variant">by {e.actor_username ?? "system"}</span>
            <span className="ml-auto shrink-0 text-body-small text-on-surface-variant tabular">{dateTime(e.timestamp)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
