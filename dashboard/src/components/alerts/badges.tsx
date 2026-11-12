import type { IconName } from "@/lib/icons";
import { SEVERITY, severityOf } from "@/lib/risk";
import type { AlertStatus } from "@/lib/types";
import { Icon, cn } from "../ui/m3";

/** Score + severity, always icon + text so color never carries meaning alone. */
export function ScorePill({ score, showLabel = true, className }: { score: number; showLabel?: boolean; className?: string }) {
  const meta = SEVERITY[severityOf(score)];
  return (
    <span
      className={cn("inline-flex h-6 items-center gap-1 rounded-sm pr-2 pl-1.5 text-label-medium tabular", meta.chip, className)}
      title={`${meta.label} risk`}
    >
      <Icon name={meta.icon} filled size={16} />
      {score.toFixed(2)}
      {showLabel && <span>· {meta.label}</span>}
    </span>
  );
}

const STATUS_META: Record<AlertStatus, { label: string; short: string; icon: IconName; chip: string }> = {
  pending: { label: "Pending review", short: "Pending", icon: "pending", chip: "bg-warning-container text-on-warning-container" },
  approved: { label: "Approved", short: "Approved", icon: "check_circle", chip: "bg-success-container text-on-success-container" },
  rejected: { label: "Fraud confirmed", short: "Fraud", icon: "block", chip: "bg-error-container text-on-error-container" },
};

export function StatusBadge({ status, compact }: { status: AlertStatus; compact?: boolean }) {
  const meta = STATUS_META[status];
  return (
    <span className={cn("inline-flex h-6 items-center gap-1 rounded-full pr-2.5 pl-1.5 text-label-medium", meta.chip)}>
      <Icon name={meta.icon} filled size={16} />
      {compact ? meta.short : meta.label}
    </span>
  );
}
