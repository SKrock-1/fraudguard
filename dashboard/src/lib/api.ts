import type { User } from "./types";

const ACCESS_KEY = "fg.access";
const REFRESH_KEY = "fg.refresh";
const USER_KEY = "fg.user";

export interface Session {
  access: string;
  refresh: string;
  user: User;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
  }
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function loadSession(): Session | null {
  const access = read(ACCESS_KEY);
  const refresh = read(REFRESH_KEY);
  const user = read(USER_KEY);
  if (!access || !refresh || !user) return null;
  try {
    return { access, refresh, user: JSON.parse(user) as User };
  } catch {
    return null;
  }
}

const sessionListeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cachedUser: User | null = null;

export function subscribeSession(listener: () => void) {
  sessionListeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key === USER_KEY || e.key === null) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    sessionListeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** Stable snapshot of the signed-in user for useSyncExternalStore. */
export function getSessionUser(): User | null {
  const raw = read(ACCESS_KEY) && read(REFRESH_KEY) ? read(USER_KEY) : null;
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try {
      cachedUser = raw ? (JSON.parse(raw) as User) : null;
    } catch {
      cachedUser = null;
    }
  }
  return cachedUser;
}

const emitSession = () => sessionListeners.forEach((l) => l());

export function saveSession(session: Session) {
  try {
    localStorage.setItem(ACCESS_KEY, session.access);
    localStorage.setItem(REFRESH_KEY, session.refresh);
    localStorage.setItem(USER_KEY, JSON.stringify(session.user));
  } catch {}
  emitSession();
}

export function clearSession() {
  try {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {}
  emitSession();
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

let refreshing: Promise<string | null> | null = null;

async function refreshAccess(): Promise<string | null> {
  const refresh = read(REFRESH_KEY);
  if (!refresh) return null;
  refreshing ??= (async () => {
    try {
      const res = await fetch("/api/auth/token/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });
      if (!res.ok) return null;
      const data = (await res.json()) as { access: string; refresh?: string };
      localStorage.setItem(ACCESS_KEY, data.access);
      if (data.refresh) localStorage.setItem(REFRESH_KEY, data.refresh);
      return data.access;
    } catch {
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

export function getAccessToken() {
  return read(ACCESS_KEY);
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const send = (token: string | null) =>
    fetch(path, {
      ...rest,
      headers: {
        Accept: "application/json",
        ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });

  let res = await send(getAccessToken());
  if (res.status === 401) {
    const token = await refreshAccess();
    if (token) res = await send(token);
    if (res.status === 401) {
      onUnauthorized?.();
      throw new ApiError(401, "Your session has expired. Sign in again.");
    }
  }

  const text = await res.text();
  const body = text ? safeJson(text) : undefined;
  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed (${res.status})`;
    throw new ApiError(res.status, detail, body);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function wsUrl(path: string): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL;
  if (configured) return `${configured.replace(/\/$/, "")}${path}`;
  const { protocol, hostname, port } = window.location;
  const scheme = protocol === "https:" ? "wss:" : "ws:";
  // In dev the dashboard runs on :3000 and Django on :8000
  const host = port === "3000" ? `${hostname}:8000` : window.location.host;
  return `${scheme}//${host}${path}`;
}
