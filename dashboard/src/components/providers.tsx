"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import {
  api,
  clearSession,
  getSessionUser,
  saveSession,
  setUnauthorizedHandler,
  subscribeSession,
  type Session,
} from "@/lib/api";
import { DEFAULT_SEED } from "@/lib/m3-theme";
import { Icon } from "./ui/m3";
import { effectsDefault, spatialDefault } from "@/lib/motion";
import type { User } from "@/lib/types";

/* ───────────────────────────── Theme (mode + seed) ───────────────────────────── */

type Mode = "dark" | "light";

interface ThemeState {
  mode: Mode;
  seed: string;
  toggleMode: () => void;
  setSeed: (hex: string) => void;
}

const ThemeContext = createContext<ThemeState>({
  mode: "light",
  seed: DEFAULT_SEED,
  toggleMode: () => {},
  setSeed: () => {},
});
export const useTheme = () => useContext(ThemeContext);

const themeListeners = new Set<() => void>();
const subscribeTheme = (l: () => void) => {
  themeListeners.add(l);
  return () => themeListeners.delete(l);
};
const emitTheme = () => themeListeners.forEach((l) => l());
const readMode = (): Mode => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");
const readSeed = () => {
  try {
    return localStorage.getItem("fg.seed.v3") ?? DEFAULT_SEED;
  } catch {
    return DEFAULT_SEED;
  }
};

function ThemeProvider({ children }: { children: ReactNode }) {
  const mode = useSyncExternalStore(subscribeTheme, readMode, () => "light" as Mode);
  const seed = useSyncExternalStore(subscribeTheme, readSeed, () => DEFAULT_SEED);

  const toggleMode = useCallback(() => {
    const next = readMode() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("fg.theme", next);
    } catch {}
    emitTheme();
  }, []);

  const setSeed = useCallback(async (hex: string) => {
    // Loaded on demand: the default scheme ships as static CSS
    const { schemeCss } = await import("@/lib/m3-theme");
    let style = document.getElementById("m3-dynamic") as HTMLStyleElement | null;
    try {
      if (hex === DEFAULT_SEED) {
        style?.remove();
        localStorage.removeItem("fg.schemeCss.v3");
        localStorage.removeItem("fg.seed.v3");
      } else {
        const css = schemeCss(hex);
        if (!style) {
          style = document.createElement("style");
          style.id = "m3-dynamic";
          document.head.appendChild(style);
        }
        style.textContent = css;
        localStorage.setItem("fg.schemeCss.v3", css);
        localStorage.setItem("fg.seed.v3", hex);
      }
    } catch {}
    emitTheme();
  }, []);

  const value = useMemo(() => ({ mode, seed, toggleMode, setSeed }), [mode, seed, toggleMode, setSeed]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

const noopSubscribe = () => () => {};

/* ─────────────────────────────────── Auth ─────────────────────────────────── */

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

function AuthProvider({ children }: { children: ReactNode }) {
  const user = useSyncExternalStore(subscribeSession, getSessionUser, () => null);
  // False during SSR and the hydration pass, true once localStorage is readable
  const ready = useSyncExternalStore(noopSubscribe, () => true, () => false);

  const logout = useCallback(() => clearSession(), []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = useCallback(async (username: string, password: string) => {
    const session = await api<Session>("/api/auth/token", { method: "POST", json: { username, password } });
    saveSession(session);
    return session.user;
  }, []);

  const value = useMemo(() => ({ user, ready, login, logout }), [user, ready, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/* ──────────────────────────────── Snackbars ────────────────────────────────
   M3: one at a time, inverse-surface, bottom-anchored (above the nav bar on compact). */

interface Snack {
  id: number;
  message: string;
  /** Accepted for call-site clarity; M3 snackbars carry no icon */
  tone?: "info" | "success" | "alert";
  action?: { label: string; onClick: () => void };
  long?: boolean;
}

const SnackContext = createContext<(snack: Omit<Snack, "id">) => void>(() => {});
export const useSnackbar = () => useContext(SnackContext);

function SnackbarProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<Snack[]>([]);
  const nextId = useRef(1);
  const current = queue[0];

  const push = useCallback((snack: Omit<Snack, "id">) => {
    const id = nextId.current++;
    // Keep the queue short: a burst of live alerts shouldn't back up for minutes
    setQueue((q) => [...q.slice(0, 2), { ...snack, id }]);
  }, []);

  const dismiss = useCallback((id: number) => setQueue((q) => q.filter((s) => s.id !== id)), []);

  useEffect(() => {
    if (!current) return;
    const t = setTimeout(() => dismiss(current.id), current.long ? 6000 : 4000);
    return () => clearTimeout(t);
  }, [current, dismiss]);

  return (
    <SnackContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-[calc(80px+16px)] z-[60] flex justify-center px-4 medium:bottom-6 medium:justify-start medium:pl-[calc(96px+24px)] large:pl-[calc(var(--rail-width,96px)+24px)]"
      >
        <AnimatePresence mode="wait">
          {current && (
            <motion.div
              key={current.id}
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1, transition: spatialDefault }}
              exit={{ opacity: 0, y: 8, transition: effectsDefault }}
              className="pointer-events-auto flex min-h-12 w-full max-w-[560px] items-center gap-2 rounded-xs bg-inverse-surface py-1.5 pr-2 pl-4 text-inverse-on-surface shadow-elev-3 medium:w-auto medium:min-w-[344px]"
            >
              <p className="flex-1 py-2 text-body-medium">{current.message}</p>
              {current.action && (
                <button
                  onClick={() => {
                    current.action!.onClick();
                    dismiss(current.id);
                  }}
                  className="state-layer relative h-9 shrink-0 rounded-full px-3 text-label-large text-inverse-primary"
                >
                  {current.action.label}
                </button>
              )}
              <button
                onClick={() => dismiss(current.id)}
                aria-label="Dismiss"
                className="state-layer relative inline-flex size-9 shrink-0 items-center justify-center rounded-full"
              >
                <Icon name="close" size={20} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </SnackContext.Provider>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <ThemeProvider>
        <AuthProvider>
          <SnackbarProvider>{children}</SnackbarProvider>
        </AuthProvider>
      </ThemeProvider>
    </MotionConfig>
  );
}
