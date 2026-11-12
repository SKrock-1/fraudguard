const currencyCache = new Map<string, Intl.NumberFormat>();

export function money(value: string | number, currency = "USD", compact = false): string {
  const key = `${currency}-${compact}`;
  let fmt = currencyCache.get(key);
  if (!fmt) {
    fmt = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      notation: compact ? "compact" : "standard",
      maximumFractionDigits: compact ? 1 : 2,
      minimumFractionDigits: compact ? 0 : 2,
    });
    currencyCache.set(key, fmt);
  }
  return fmt.format(Number(value));
}

const compactFmt = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const intFmt = new Intl.NumberFormat("en-US");

export function count(value: number, compact = false): string {
  return compact && Math.abs(value) >= 10_000 ? compactFmt.format(value) : intFmt.format(value);
}

export function percent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function score(value: number): string {
  return value.toFixed(2);
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto", style: "short" });

export function relativeTime(iso: string, now = Date.now()): string {
  const diff = (new Date(iso).getTime() - now) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

const timeFmt = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });
const dateTimeFmt = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
});
const dayFmt = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" });

export const clock = (iso: string) => timeFmt.format(new Date(iso));
export const dateTime = (iso: string) => dateTimeFmt.format(new Date(iso));
export const day = (iso: string) => dayFmt.format(new Date(iso));

export function initials(name: string): string {
  const parts = name.split(/[.\s_-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "");
}

export function displayName(username: string): string {
  return username
    .split(/[.\s_-]+/)
    .filter(Boolean)
    .map((p) => p[0].toUpperCase() + p.slice(1))
    .join(" ");
}
