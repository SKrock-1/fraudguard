"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { effectsDefault, spatialDefault } from "@/lib/motion";
import { Button, FilterChip, Icon } from "./ui/m3";

const COUNTS = [15, 30, 60];
const RATES = [0.1, 0.25, 0.5];
const DURATIONS = [20, 40, 90];

/**
 * Basic dialog that container-transforms out of the "Simulate" FAB: both share
 * a layoutId, so the FAB's surface grows into the dialog and shrinks back.
 */
export function SimulateDialog({
  open,
  layoutId,
  onClose,
  onStart,
}: {
  open: boolean;
  layoutId: string;
  onClose: () => void;
  onStart: (opts: { count: number; fraud_rate: number; duration_seconds: number }) => void;
}) {
  const [count, setCount] = useState(30);
  const [rate, setRate] = useState(0.25);
  const [duration, setDuration] = useState(40);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => confirmRef.current?.focus(), 200);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-6">
          <motion.div
            key="scrim"
            className="absolute inset-0 bg-scrim/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={effectsDefault}
            onClick={onClose}
          />
          <motion.div
            layoutId={layoutId}
            role="dialog"
            aria-modal="true"
            aria-labelledby="simulate-title"
            transition={spatialDefault}
            style={{ borderRadius: 28 }}
            className="relative w-full max-w-[400px] overflow-hidden bg-surface-container-high text-on-surface shadow-elev-3"
          >
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, transition: { ...effectsDefault, delay: 0.08 } }}
              exit={{ opacity: 0, transition: { duration: 0.08 } }}
              className="p-6"
            >
              <span className="flex size-10 items-center justify-center rounded-full bg-tertiary-container text-on-tertiary-container">
                <Icon name="bolt" filled />
              </span>
              <h2 id="simulate-title" className="mt-4 text-headline-small">
                Simulate live traffic
              </h2>
              <p className="mt-2 text-body-medium text-on-surface-variant">
                Streams synthetic transactions through the real scoring pipeline. Flagged ones arrive in the alert queue as they
                happen.
              </p>

              <Option label="Events">
                {COUNTS.map((c) => (
                  <FilterChip key={c} selected={count === c} onClick={() => setCount(c)}>
                    {c}
                  </FilterChip>
                ))}
              </Option>
              <Option label="Fraud share">
                {RATES.map((r) => (
                  <FilterChip key={r} selected={rate === r} onClick={() => setRate(r)}>
                    {Math.round(r * 100)}%
                  </FilterChip>
                ))}
              </Option>
              <Option label="Over">
                {DURATIONS.map((d) => (
                  <FilterChip key={d} selected={duration === d} onClick={() => setDuration(d)}>
                    {d}s
                  </FilterChip>
                ))}
              </Option>

              <div className="mt-6 flex justify-end gap-2">
                <Button variant="text" onClick={onClose}>
                  Cancel
                </Button>
                <Button
                  ref={confirmRef}
                  variant="filled"
                  onClick={() => onStart({ count, fraud_rate: rate, duration_seconds: duration })}
                >
                  Start stream
                </Button>
              </div>
            </motion.div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

function Option({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-5">
      <p className="mb-2 text-label-large text-on-surface-variant">{label}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
