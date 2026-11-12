"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useEffectEvent, useMemo, useState, type ReactNode } from "react";
import { api, getAccessToken, wsUrl } from "@/lib/api";
import { money } from "@/lib/format";
import type { Alert } from "@/lib/types";
import { useSnackbar } from "./providers";

export type Connection = "connecting" | "live" | "reconnecting" | "offline";

interface AlertStore {
  alerts: Alert[];
  loading: boolean;
  error: string | null;
  connection: Connection;
  /** IDs that arrived over the socket this session, for highlight treatment */
  freshIds: ReadonlySet<number>;
  /** Bumps whenever data changes, so aggregate views know to refetch */
  version: number;
  upsert: (alert: Alert) => void;
  reload: () => Promise<void>;
}

const AlertStoreContext = createContext<AlertStore | null>(null);

export function useAlerts() {
  const ctx = useContext(AlertStoreContext);
  if (!ctx) throw new Error("useAlerts outside AlertStreamProvider");
  return ctx;
}

const sortNewest = (a: Alert, b: Alert) =>
  new Date(b.transaction.timestamp).getTime() - new Date(a.transaction.timestamp).getTime() || b.id - a.id;

export function AlertStreamProvider({ children }: { children: ReactNode }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [freshIds, setFreshIds] = useState<ReadonlySet<number>>(new Set());
  const [version, setVersion] = useState(0);
  const snackbar = useSnackbar();
  const router = useRouter();

  const upsert = useCallback((alert: Alert) => {
    setAlerts((prev) => {
      const next = prev.filter((a) => a.id !== alert.id);
      next.push(alert);
      return next.sort(sortNewest);
    });
    setVersion((v) => v + 1);
  }, []);

  const reload = useCallback(async () => {
    try {
      const data = await api<Alert[]>("/api/alerts");
      setAlerts(data.sort(sortNewest));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load alerts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api<Alert[]>("/api/alerts")
      .then((data) => {
        setAlerts(data.sort(sortNewest));
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load alerts"))
      .finally(() => setLoading(false));
  }, []);

  // Reads the latest upsert/snackbar/router without reconnecting the socket
  const onAlertMessage = useEffectEvent(async (id: number) => {
    try {
      // The socket payload is a summary; fetch the full serializer shape
      const alert = await api<Alert>(`/api/alerts/${id}`);
      upsert(alert);
      setFreshIds((prev) => new Set(prev).add(alert.id));
      snackbar({
        tone: "alert",
        message: `New alert: ${alert.transaction.merchant}, ${money(alert.transaction.amount, alert.transaction.currency)} (score ${alert.risk_score.composite_score.toFixed(2)})`,
        action: { label: "Review", onClick: () => router.push(`/alerts?id=${alert.id}`) },
        long: true,
      });
    } catch {}
  });

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;

    const connect = () => {
      const token = getAccessToken();
      if (!token || disposed) return;
      setConnection(retry === 0 ? "connecting" : "reconnecting");
      socket = new WebSocket(wsUrl(`/ws/alerts/?token=${encodeURIComponent(token)}`));

      socket.onopen = () => {
        retry = 0;
        setConnection("live");
      };

      socket.onmessage = (event) => {
        try {
          const id = (JSON.parse(event.data) as { id?: number }).id;
          if (id) onAlertMessage(id);
        } catch {}
      };

      socket.onclose = async (event) => {
        if (disposed) return;
        if (event.code === 4003) {
          // Token likely expired: any authenticated call triggers a refresh
          try {
            await api("/api/auth/me");
          } catch {
            setConnection("offline");
            return;
          }
        }
        retry += 1;
        setConnection(retry > 6 ? "offline" : "reconnecting");
        timer = setTimeout(connect, Math.min(15000, 600 * 2 ** retry));
      };
    };

    connect();
    return () => {
      disposed = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, []);

  const value = useMemo(
    () => ({ alerts, loading, error, connection, freshIds, version, upsert, reload }),
    [alerts, loading, error, connection, freshIds, version, upsert, reload],
  );
  return <AlertStoreContext.Provider value={value}>{children}</AlertStoreContext.Provider>;
}
