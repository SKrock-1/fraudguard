"use client";

import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { money } from "@/lib/format";
import { effectsDefault, spatialDefault } from "@/lib/motion";
import { SEVERITY, severityOf } from "@/lib/risk";
import { useAlerts } from "./alert-stream";
import { useAuth, useTheme } from "./providers";
import type { IconName } from "@/lib/icons";
import { Icon, Kbd, cn } from "./ui/m3";

interface Command {
  id: string;
  group: "Navigate" | "Actions" | "Alerts";
  label: string;
  hint?: string;
  icon: IconName;
  iconClass?: string;
  keywords?: string;
  run: () => void;
}

const CommandMenuContext = createContext<{ open: () => void }>({ open: () => {} });
export const useCommandMenu = () => useContext(CommandMenuContext);

export function CommandMenuProvider({ children, onSimulate }: { children: ReactNode; onSimulate?: () => void }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo(() => ({ open: () => setOpen(true) }), []);

  return (
    <CommandMenuContext.Provider value={value}>
      {children}
      <AnimatePresence>{open && <CommandPalette onClose={() => setOpen(false)} onSimulate={onSimulate} />}</AnimatePresence>
    </CommandMenuContext.Provider>
  );
}

function CommandPalette({ onClose, onSimulate }: { onClose: () => void; onSimulate?: () => void }) {
  const router = useRouter();
  const { alerts } = useAlerts();
  const { mode, toggleMode } = useTheme();
  const { logout } = useAuth();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const go = useCallback(
    (fn: () => void) => () => {
      onClose();
      fn();
    },
    [onClose],
  );

  const commands = useMemo<Command[]>(() => {
    const base: Command[] = [
      { id: "nav-overview", group: "Navigate", label: "Overview", icon: "space_dashboard", keywords: "home dashboard", run: go(() => router.push("/")) },
      { id: "nav-alerts", group: "Navigate", label: "Alert queue", icon: "gpp_maybe", keywords: "review pending", run: go(() => router.push("/alerts")) },
      { id: "nav-audit", group: "Navigate", label: "Audit trail", icon: "receipt_long", keywords: "log history decisions", run: go(() => router.push("/audit")) },
      ...(onSimulate
        ? [{ id: "act-sim", group: "Actions", label: "Simulate live traffic", icon: "bolt", keywords: "demo stream", run: go(onSimulate) } satisfies Command]
        : []),
      {
        id: "act-theme",
        group: "Actions",
        label: mode === "dark" ? "Switch to light theme" : "Switch to dark theme",
        icon: (mode === "dark" ? "light_mode" : "dark_mode") satisfies IconName,
        keywords: "appearance mode",
        run: go(toggleMode),
      },
      { id: "act-logout", group: "Actions", label: "Sign out", icon: "logout", run: go(logout) },
    ];
    const q = query.trim().toLowerCase();
    const alertMatches: Command[] = (q ? alerts : alerts.filter((a) => a.status === "pending"))
      .filter(
        (a) =>
          !q ||
          a.transaction.merchant.toLowerCase().includes(q) ||
          a.transaction.account_number.toLowerCase().includes(q) ||
          String(a.id).includes(q),
      )
      .slice(0, 6)
      .map((a) => {
        const sev = SEVERITY[severityOf(a.risk_score.composite_score)];
        return {
          id: `alert-${a.id}`,
          group: "Alerts" as const,
          label: a.transaction.merchant,
          hint: `${money(a.transaction.amount, a.transaction.currency)} · ${a.risk_score.composite_score.toFixed(2)} ${sev.label.toLowerCase()} · ${a.status}`,
          icon: sev.icon,
          iconClass: sev.chip,
          run: go(() => router.push(`/alerts?id=${a.id}`)),
        };
      });
    const filtered = q
      ? base.filter((c) => `${c.label} ${c.keywords ?? ""}`.toLowerCase().includes(q))
      : base;
    return [...filtered, ...alertMatches];
  }, [query, alerts, mode, toggleMode, logout, onSimulate, router, go]);

  const index = Math.min(active, Math.max(0, commands.length - 1));

  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: "nearest" });
  }, [index]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % Math.max(1, commands.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + commands.length) % Math.max(1, commands.length));
    } else if (e.key === "Enter") {
      e.preventDefault();
      commands[index]?.run();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  let lastGroup = "";

  return (
    <div className="fixed inset-0 z-[80] flex items-start justify-center px-3 pt-[12vh]">
      <motion.div
        className="absolute inset-0 bg-scrim/40"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={effectsDefault}
        onClick={onClose}
      />
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="Command menu"
        initial={{ opacity: 0, scale: 0.97, y: -8 }}
        animate={{ opacity: 1, scale: 1, y: 0, transition: spatialDefault }}
        exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.12 } }}
        className="relative w-full max-w-[600px] overflow-hidden rounded-xl bg-surface-container-high text-on-surface shadow-elev-3"
        onKeyDown={onKeyDown}
      >
        <div className="flex h-14 items-center gap-4 border-b border-outline-variant px-5">
          <Icon name="search" className="text-on-surface-variant" />
          <input
            autoFocus
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Search alerts or jump to…"
            aria-label="Search commands and alerts"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-list"
            aria-activedescendant={commands[index] ? `cmd-${commands[index].id}` : undefined}
            className="h-full flex-1 bg-transparent text-body-large text-on-surface outline-none placeholder:text-on-surface-variant"
          />
          <Kbd>Esc</Kbd>
        </div>

        <div ref={listRef} id="command-list" role="listbox" className="max-h-[min(440px,60vh)] overflow-y-auto p-2">
          {commands.length === 0 && (
            <p className="px-3 py-10 text-center text-body-medium text-on-surface-variant">No results for “{query}”</p>
          )}
          {commands.map((c, i) => {
            const header = c.group !== lastGroup ? c.group : null;
            lastGroup = c.group;
            const selected = i === index;
            return (
              <div key={c.id}>
                {header && (
                  <p className="px-4 pt-3 pb-2 text-title-small text-primary">
                    {header === "Alerts" && !query ? "Pending alerts" : header}
                  </p>
                )}
                <div
                  id={`cmd-${c.id}`}
                  role="option"
                  aria-selected={selected}
                  data-index={i}
                  onMouseMove={() => setActive(i)}
                  onClick={c.run}
                  className={cn(
                    "flex h-12 cursor-pointer items-center gap-4 rounded-full px-4 transition-colors duration-150",
                    selected ? "bg-secondary-container text-on-secondary-container" : "text-on-surface",
                  )}
                >
                  <span
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center rounded-full",
                      c.iconClass ?? (c.group === "Navigate" ? "bg-secondary-container text-on-secondary-container" : "bg-tertiary-container text-on-tertiary-container"),
                    )}
                  >
                    <Icon name={c.icon} size={20} filled={selected} />
                  </span>
                  <span className="min-w-0 flex-1 truncate text-body-large">{c.label}</span>
                  {c.hint && <span className={cn("hidden truncate text-body-small medium:block", !selected && "text-on-surface-variant")}>{c.hint}</span>}
                  {selected &&
                    (c.group === "Navigate" ? (
                      <Icon name="arrow_forward" size={20} />
                    ) : (
                      <Icon name="keyboard_return" size={20} />
                    ))}
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex items-center gap-4 border-t border-outline-variant px-5 py-2.5 text-label-small text-on-surface-variant">
          <span className="flex items-center gap-1.5">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> Navigate
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>↵</Kbd> Open
          </span>
          <span className="ml-auto flex items-center gap-1.5">
            <Kbd>Ctrl</Kbd>
            <Kbd>K</Kbd> Toggle
          </span>
        </div>
      </motion.div>
    </div>
  );
}
