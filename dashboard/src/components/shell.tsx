"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { displayName } from "@/lib/format";
import { SEEDS } from "@/lib/m3-theme";
import { effectsDefault, spatialDefault } from "@/lib/motion";
import { AlertStreamProvider, useAlerts, type Connection } from "./alert-stream";
import { CommandMenuProvider, useCommandMenu } from "./command-menu";
import { useAuth, useSnackbar, useTheme } from "./providers";
import { SimulateDialog } from "./simulate-dialog";
import type { IconName } from "@/lib/icons";
import { Avatar, Badge, Fab, Icon, IconButton, Kbd, LiveDot, Ripple, Switch, WavyProgress, cn } from "./ui/m3";

const NAV: { href: string; label: string; icon: IconName; badge?: boolean }[] = [
  { href: "/", label: "Overview", icon: "space_dashboard" },
  { href: "/alerts", label: "Alerts", icon: "gpp_maybe", badge: true },
  { href: "/audit", label: "Audit", icon: "receipt_long" },
];

const FAB_LAYOUT_ID = "simulate-fab";

export function ConsoleShell({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);

  if (!ready || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <BrandMark className="size-10 animate-pulse" />
      </div>
    );
  }

  return (
    <AlertStreamProvider>
      <ShellFrame>{children}</ShellFrame>
    </AlertStreamProvider>
  );
}

/* ───────────────────────────── Simulation state ───────────────────────────── */

type SimState = { enabled: boolean; running: boolean } | null;

function useSimulation() {
  const [state, setState] = useState<SimState>(null);
  useEffect(() => {
    api<SimState>("/api/demo/simulate").then(setState).catch(() => setState(null));
  }, []);
  useEffect(() => {
    if (!state?.running) return;
    const t = setInterval(() => {
      api<SimState>("/api/demo/simulate").then(setState).catch(() => {});
    }, 3000);
    return () => clearInterval(t);
  }, [state?.running]);
  return [state, setState] as const;
}

function useMediaQuery(query: string) {
  const [match, setMatch] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const sync = () => setMatch(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, [query]);
  return match;
}

function ShellFrame({ children }: { children: ReactNode }) {
  const [expandedPref, setExpandedPref] = useState(true);
  const isLarge = useMediaQuery("(min-width: 1200px)");
  const isMedium = useMediaQuery("(min-width: 600px)");
  const expanded = expandedPref && isLarge;
  const [dialog, setDialog] = useState(false);
  const [sim, setSim] = useSimulation();
  const snackbar = useSnackbar();

  const start = async (opts: { count: number; fraud_rate: number; duration_seconds: number }) => {
    setDialog(false);
    setSim({ enabled: true, running: true });
    try {
      await api("/api/demo/simulate", { method: "POST", json: opts });
      snackbar({ message: `Streaming ${opts.count} synthetic events over ${opts.duration_seconds} seconds` });
    } catch (e) {
      snackbar({ message: e instanceof Error ? e.message : "Simulation could not start" });
      setSim({ enabled: true, running: false });
    }
  };

  const fab = sim?.enabled ? { running: sim.running, open: () => setDialog(true) } : null;

  return (
    <CommandMenuProvider onSimulate={fab && !fab.running ? fab.open : undefined}>
      <LayoutGroup>
        <div className="flex min-h-dvh bg-surface" style={{ ["--rail-width" as string]: expanded ? "256px" : "96px" }}>
          <NavRail
            expanded={expanded}
            canExpand={isLarge}
            onToggle={() => setExpandedPref((e) => !e)}
            fab={isMedium ? fab : null}
            dialogOpen={dialog}
          />

          <div className="flex min-w-0 flex-1 flex-col pb-20 medium:pb-0">
            <TopAppBar />
            <main className="min-w-0 flex-1">{children}</main>
          </div>

          <NavigationBar />
          {fab && !isMedium && (
            <div className="fixed right-4 bottom-[calc(80px+16px)] z-30 medium:hidden">
              {fab.running ? (
                <StreamingPill />
              ) : (
                !dialog && <Fab layoutId={FAB_LAYOUT_ID} icon={<Icon name="bolt" filled />} label="Simulate" onClick={fab.open} />
              )}
            </div>
          )}
        </div>

        <SimulateDialog open={dialog} layoutId={FAB_LAYOUT_ID} onClose={() => setDialog(false)} onStart={start} />
      </LayoutGroup>
    </CommandMenuProvider>
  );
}

/* ───────────────────────────── Navigation rail ─────────────────────────────
   Hidden on compact. 96dp rail on medium/expanded; on large+ it expands into the
   labelled expanded rail with an extended FAB. */

function NavRail({
  expanded,
  canExpand,
  onToggle,
  fab,
  dialogOpen,
}: {
  expanded: boolean;
  canExpand: boolean;
  onToggle: () => void;
  fab: { running: boolean; open: () => void } | null;
  dialogOpen: boolean;
}) {
  const pathname = usePathname();
  const { alerts, connection } = useAlerts();
  const { open: openCommand } = useCommandMenu();
  const pending = alerts.filter((a) => a.status === "pending").length;

  return (
    <motion.nav
      aria-label="Primary"
      initial={false}
      animate={{ width: expanded ? 256 : 96 }}
      transition={spatialDefault}
      className="sticky top-0 z-20 hidden h-dvh shrink-0 flex-col overflow-x-hidden overflow-y-auto bg-surface-container medium:flex"
    >
      <div className={cn("flex flex-col pt-4", expanded ? "px-4" : "items-center")}>
        <div className={cn("flex h-12 items-center gap-3", expanded && "pl-2")}>
          {canExpand ? (
            <IconButton label={expanded ? "Collapse navigation" : "Expand navigation"} onClick={onToggle}>
              <Icon name={expanded ? "menu_open" : "menu"} />
            </IconButton>
          ) : (
            <BrandMark className="size-9" />
          )}
          {expanded && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={effectsDefault}
              className="emphasized text-title-large whitespace-nowrap text-on-surface"
            >
              FraudGuard
            </motion.span>
          )}
        </div>

        <div className={cn("mt-4 mb-4 h-14", !expanded && "flex justify-center")}>
          {fab &&
            (fab.running ? (
              <StreamingPill compact={!expanded} />
            ) : (
              !dialogOpen && (
                <Fab
                  layoutId={FAB_LAYOUT_ID}
                  icon={<Icon name="bolt" filled />}
                  label={expanded ? "Simulate traffic" : undefined}
                  onClick={fab.open}
                />
              )
            ))}
        </div>

        <div className={cn("mb-4", !expanded && "flex justify-center")}>
          {expanded ? (
            <button
              onClick={openCommand}
              className="state-layer relative flex h-12 w-full items-center gap-3 overflow-hidden rounded-full bg-surface-container-high px-4 text-on-surface-variant"
            >
              <Ripple />
              <Icon name="search" />
              <span className="flex-1 text-left text-body-large whitespace-nowrap">Search</span>
              <Kbd className="whitespace-nowrap">Ctrl K</Kbd>
            </button>
          ) : (
            <IconButton label="Search (Ctrl K)" onClick={openCommand}>
              <Icon name="search" />
            </IconButton>
          )}
        </div>
      </div>

      <ul className={cn("flex flex-col", expanded ? "gap-1 px-3" : "items-center gap-3")}>
        {NAV.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const count = item.badge && pending ? pending : undefined;
          return (
            <li key={item.href} className="w-full">
              {expanded ? (
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "state-layer relative flex h-14 items-center gap-3 overflow-hidden rounded-full pr-6 pl-4 text-label-large",
                    active ? "text-on-secondary-container" : "text-on-surface-variant",
                  )}
                >
                  {active && (
                    <motion.span
                      layoutId="rail-indicator"
                      transition={spatialDefault}
                      className="absolute inset-0 -z-10 rounded-full bg-secondary-container"
                    />
                  )}
                  <Ripple />
                  <Icon name={item.icon} filled={active} />
                  <span className="flex-1 whitespace-nowrap">{item.label}</span>
                  {count !== undefined && <span className="text-label-large tabular">{count}</span>}
                </Link>
              ) : (
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className="flex flex-col items-center gap-1 text-label-medium"
                >
                  <span
                    className={cn(
                      "state-layer relative flex h-8 w-14 items-center justify-center rounded-full",
                      active ? "text-on-secondary-container" : "text-on-surface-variant",
                    )}
                  >
                    {active && (
                      <motion.span
                        layoutId="rail-indicator"
                        transition={spatialDefault}
                        className="absolute inset-0 -z-10 rounded-full bg-secondary-container"
                      />
                    )}
                    <Icon name={item.icon} filled={active} />
                    {count !== undefined && <Badge count={count} className="absolute -top-0.5 left-[30px]" />}
                  </span>
                  <span className={active ? "text-on-surface" : "text-on-surface-variant"}>{item.label}</span>
                </Link>
              )}
            </li>
          );
        })}
      </ul>

      <div className={cn("mt-auto flex flex-col gap-3 pt-6 pb-5", expanded ? "px-4" : "items-center")}>
        <ConnectionStatus connection={connection} compact={!expanded} />
        <AccountMenu placement="rail" showName={expanded} />
      </div>
    </motion.nav>
  );
}

function StreamingPill({ compact }: { compact?: boolean }) {
  return (
    <div
      role="status"
      aria-label="Streaming simulated traffic"
      className={cn(
        "flex h-14 flex-col justify-center gap-1.5 rounded-lg bg-tertiary-container text-on-tertiary-container shadow-elev-1",
        compact ? "w-14 items-center px-2" : "min-w-[176px] px-4",
      )}
    >
      {!compact && <span className="text-label-large">Streaming traffic</span>}
      <WavyProgress className={compact ? "w-10" : "w-full"} />
    </div>
  );
}

/* ─────────────────────────────── Top app bar ─────────────────────────────── */

function TopAppBar() {
  const { connection } = useAlerts();
  const { open: openCommand } = useCommandMenu();
  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-2 bg-surface px-4 medium:hidden">
      <BrandMark className="size-8" />
      <span className="emphasized ml-1 flex-1 text-title-large">FraudGuard</span>
      <ConnectionStatus connection={connection} compact />
      <IconButton label="Search" onClick={openCommand}>
        <Icon name="search" />
      </IconButton>
      <AccountMenu placement="top" />
    </header>
  );
}

/* ───────────────────────────── Navigation bar ───────────────────────────── */

function NavigationBar() {
  const pathname = usePathname();
  const { alerts } = useAlerts();
  const pending = alerts.filter((a) => a.status === "pending").length;
  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-30 flex h-20 bg-surface-container pb-[env(safe-area-inset-bottom)] medium:hidden"
    >
      {NAV.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className="flex flex-1 flex-col items-center justify-center gap-1 text-label-medium"
          >
            <span
              className={cn(
                "state-layer relative flex h-8 w-16 items-center justify-center rounded-full",
                active ? "text-on-secondary-container" : "text-on-surface-variant",
              )}
            >
              {active && (
                <motion.span
                  layoutId="bar-indicator"
                  transition={spatialDefault}
                  className="absolute inset-0 -z-10 rounded-full bg-secondary-container"
                />
              )}
              <Icon name={item.icon} filled={active} />
              {item.badge && pending > 0 && <Badge count={pending} className="absolute -top-0.5 left-[34px]" />}
            </span>
            <span className={active ? "text-on-surface" : "text-on-surface-variant"}>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/* ───────────────────────────── Connection status ───────────────────────────── */

const CONNECTION_META: Record<Connection, { label: string; dot: string }> = {
  live: { label: "Live", dot: "bg-success" },
  connecting: { label: "Connecting", dot: "bg-warning" },
  reconnecting: { label: "Reconnecting", dot: "bg-warning" },
  offline: { label: "Offline", dot: "bg-error" },
};

function ConnectionStatus({ connection, compact }: { connection: Connection; compact?: boolean }) {
  const meta = CONNECTION_META[connection];
  return (
    <div
      role="status"
      title={`Alert stream: ${meta.label}`}
      className={cn(
        "flex items-center gap-2 text-label-medium text-on-surface-variant",
        !compact && "h-8 rounded-sm bg-surface-container-high px-3",
      )}
    >
      {connection === "live" ? <LiveDot /> : <span className={cn("size-2 rounded-full", meta.dot)} />}
      <span className={compact ? "sr-only" : "whitespace-nowrap"}>Alert stream {meta.label.toLowerCase()}</span>
    </div>
  );
}

/* ─────────────────────────────── Account menu ─────────────────────────────── */

function AccountMenu({ placement, showName }: { placement: "rail" | "top"; showName?: boolean }) {
  const { user, logout } = useAuth();
  const { mode, toggleMode, seed, setSeed } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className={cn("relative", showName && "w-full")}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label="Account and appearance"
        className={cn(
          "state-layer relative flex items-center gap-3 overflow-hidden rounded-full text-left",
          showName ? "w-full p-2 pr-4" : "p-1",
        )}
      >
        <Ripple />
        <Avatar name={user!.username} size={showName ? 40 : 32} />
        {showName && (
          <span className="min-w-0 flex-1">
            <span className="block truncate text-title-small text-on-surface">{displayName(user!.username)}</span>
            <span className="block text-body-small text-on-surface-variant capitalize">{user!.role.replace("_", " ")}</span>
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            id={menuId}
            role="menu"
            initial={{ opacity: 0, scale: 0.92, y: placement === "rail" ? 8 : -8 }}
            animate={{ opacity: 1, scale: 1, y: 0, transition: spatialDefault }}
            exit={{ opacity: 0, scale: 0.96, transition: effectsDefault }}
            className={cn(
              "fixed z-50 w-[300px] rounded-lg bg-surface-container-high p-2 text-on-surface shadow-elev-2",
              placement === "rail"
                ? "bottom-4 left-[calc(var(--rail-width)+8px)] origin-bottom-left"
                : "top-16 right-3 origin-top-right",
            )}
          >
            <div className="flex items-center gap-3 px-3 py-3">
              <Avatar name={user!.username} size={40} />
              <div className="min-w-0">
                <p className="truncate text-title-medium">{displayName(user!.username)}</p>
                <p className="truncate text-body-medium text-on-surface-variant">{user!.email || user!.role}</p>
              </div>
            </div>

            <div className="my-1 h-px bg-outline-variant" />

            <div className="flex items-center gap-3 px-3 py-2">
              <Icon name={mode === "dark" ? "dark_mode" : "light_mode"} className="text-on-surface-variant" />
              <span className="flex-1 text-body-large">Dark theme</span>
              <Switch checked={mode === "dark"} onChange={toggleMode} label="Dark theme" />
            </div>

            <div className="px-3 pt-2 pb-3">
              <p className="flex items-center gap-3 text-body-large">
                <Icon name="palette" className="text-on-surface-variant" /> Dynamic color
              </p>
              <div className="mt-3 flex gap-2 pl-9" role="radiogroup" aria-label="Theme seed color">
                {SEEDS.map((s) => {
                  const selected = s.hex === seed;
                  return (
                    <button
                      key={s.hex}
                      role="radio"
                      aria-checked={selected}
                      aria-label={s.name}
                      title={s.name}
                      onClick={() => setSeed(s.hex)}
                      className={cn(
                        "shape-morph flex size-10 items-center justify-center text-white",
                        selected ? "rounded-md" : "rounded-full hover:rounded-lg",
                      )}
                      style={{ background: s.hex }}
                    >
                      {selected && <Icon name="check" size={20} weight={700} />}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="my-1 h-px bg-outline-variant" />

            <button
              role="menuitem"
              onClick={logout}
              className="state-layer relative flex h-12 w-full items-center gap-3 overflow-hidden rounded-md px-3 text-body-large"
            >
              <Ripple />
              <Icon name="logout" className="text-on-surface-variant" /> Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ─────────────────────────────────── Brand ─────────────────────────────────── */

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden>
      <path d={scallop(20, 20, 19.5, 0.08, 8)} fill="var(--md-sys-color-primary)" />
      <path
        d="M20 10.5 12.5 13.4v6.4c0 4.7 3.2 8.8 7.5 10.2 4.3-1.4 7.5-5.5 7.5-10.2v-6.4L20 10.5Z"
        fill="none"
        stroke="var(--md-sys-color-on-primary)"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="m16.3 20 2.6 2.6 4.9-5.2"
        fill="none"
        stroke="var(--md-sys-color-on-primary)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Rounded scalloped outline: the family of M3 Expressive "cookie" shapes. */
export function scallop(cx: number, cy: number, r: number, depth: number, lobes: number, rotate = 0, steps = 120): string {
  let d = "";
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2;
    const rr = r * (1 - depth + depth * Math.cos(lobes * t));
    const a = t + rotate;
    d += `${i ? "L" : "M"}${(cx + rr * Math.cos(a)).toFixed(2)},${(cy + rr * Math.sin(a)).toFixed(2)}`;
  }
  return d + "Z";
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="m3-pane flex flex-wrap items-end justify-between gap-4 pt-4 pb-6 medium:pt-8">
      <div className="min-w-0">
        <h1 className="text-headline-medium text-on-surface expanded:text-headline-large">{title}</h1>
        {description && <p className="mt-1 text-body-large text-on-surface-variant">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
