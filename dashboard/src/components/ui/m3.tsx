"use client";

import { motion } from "motion/react";
import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { initials } from "@/lib/format";
import type { IconName } from "@/lib/icons";
import { spatialFast } from "@/lib/motion";

/**
 * Material Symbols Rounded glyph. `filled` switches the FILL axis (animated), used
 * for selected and emphasized states; size follows font-size, so parents can set it.
 */
export function Icon({
  name,
  filled,
  size,
  weight,
  label,
  className,
  style,
}: {
  name: IconName;
  filled?: boolean;
  size?: number;
  weight?: number;
  label?: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <span
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
      data-filled={filled ? "" : undefined}
      className={["icon", className].filter(Boolean).join(" ")}
      style={{ fontSize: size, ...(weight ? { ["--icon-wght" as string]: weight } : null), ...style }}
    >
      {name}
    </span>
  );
}

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/* ────────────────────────────────── Ripple ──────────────────────────────────
   Drop inside any `relative overflow-hidden` interactive element. Listens on the
   parent so the host element needs no wiring. */
export function Ripple() {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const host = ref.current?.parentElement;
    if (!host) return;
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || host.hasAttribute("disabled")) return;
      const rect = host.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const r = Math.hypot(Math.max(x, rect.width - x), Math.max(y, rect.height - y));
      const wave = document.createElement("span");
      wave.className = "m3-ripple";
      wave.style.cssText = `left:${x - r}px;top:${y - r}px;width:${r * 2}px;height:${r * 2}px`;
      ref.current?.appendChild(wave);
      const release = () => {
        wave.setAttribute("data-released", "");
        setTimeout(() => wave.remove(), 650);
        window.removeEventListener("pointerup", release);
        window.removeEventListener("pointercancel", release);
      };
      window.addEventListener("pointerup", release);
      window.addEventListener("pointercancel", release);
    };
    host.addEventListener("pointerdown", down);
    return () => host.removeEventListener("pointerdown", down);
  }, []);

  return <span ref={ref} aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]" />;
}

/* ────────────────────────────────── Buttons ────────────────────────────────── */

type ButtonVariant = "filled" | "tonal" | "outlined" | "text" | "elevated" | "error" | "success";
type ButtonSize = "xs" | "sm" | "md";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  filled: "bg-primary text-on-primary hover:shadow-elev-1",
  tonal: "bg-secondary-container text-on-secondary-container hover:shadow-elev-1",
  outlined: "border border-outline-variant text-on-surface-variant",
  text: "text-primary",
  elevated: "bg-surface-container-low text-primary shadow-elev-1 hover:shadow-elev-2",
  error: "bg-error text-on-error hover:shadow-elev-1",
  success: "bg-success text-on-success hover:shadow-elev-1",
};

// Expressive sizes: height, padding, type, and the corner the shape morphs to while pressed
const BUTTON_SIZE: Record<ButtonSize, string> = {
  xs: "h-8 px-3 gap-1 text-label-large active:rounded-[var(--md-sys-shape-corner-small)] [&_.icon]:text-[18px]",
  sm: "h-10 px-4 gap-2 text-label-large active:rounded-[var(--md-sys-shape-corner-small)] [&_.icon]:text-[18px]",
  md: "h-14 px-6 gap-2 text-title-medium active:rounded-[var(--md-sys-shape-corner-medium)] [&_.icon]:text-[24px]",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize; icon?: ReactNode }
>(function Button({ variant = "filled", size = "sm", icon, className, children, ...props }, ref) {
  return (
    <button
      ref={ref}
      className={cn(
        "state-layer shape-morph relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full whitespace-nowrap select-none",
        "disabled:pointer-events-none disabled:bg-on-surface/10 disabled:text-on-surface/40 disabled:shadow-none",
        BUTTON_SIZE[size],
        BUTTON_VARIANT[variant],
        className,
      )}
      {...props}
    >
      <Ripple />
      {icon}
      {children}
    </button>
  );
});

type IconButtonVariant = "standard" | "filled" | "tonal" | "outlined";

const ICON_VARIANT: Record<IconButtonVariant, string> = {
  standard: "text-on-surface-variant",
  filled: "bg-primary text-on-primary",
  tonal: "bg-secondary-container text-on-secondary-container",
  outlined: "border border-outline-variant text-on-surface-variant",
};

export const IconButton = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: IconButtonVariant; label: string; selected?: boolean }
>(function IconButton({ variant = "standard", label, selected, className, children, ...props }, ref) {
  return (
    <button
      ref={ref}
      aria-label={label}
      title={label}
      aria-pressed={selected}
      className={cn(
        "state-layer shape-morph relative inline-flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full",
        "active:rounded-[var(--md-sys-shape-corner-medium)] disabled:text-on-surface/40 [&_.icon]:text-[24px]",
        selected ? "bg-secondary-container text-on-secondary-container" : ICON_VARIANT[variant],
        className,
      )}
      {...props}
    >
      <Ripple />
      {children}
    </button>
  );
});

/** Extended FAB. `layoutId` lets it container-transform into a dialog. */
export const Fab = forwardRef<
  HTMLButtonElement,
  { icon: ReactNode; label?: string; layoutId?: string; onClick?: () => void; className?: string; disabled?: boolean }
>(function Fab({ icon, label, layoutId, onClick, className, disabled }, ref) {
  return (
    <motion.button
      ref={ref}
      layoutId={layoutId}
      onClick={onClick}
      disabled={disabled}
      aria-label={label ?? "Simulate traffic"}
      title={label ? undefined : "Simulate traffic"}
      transition={spatialFast}
      style={{ borderRadius: 16 }}
      className={cn(
        "state-layer relative inline-flex h-14 shrink-0 items-center justify-center gap-3 overflow-hidden",
        "bg-primary-container text-on-primary-container shadow-elev-3 transition-shadow hover:shadow-elev-4",
        "disabled:opacity-60 [&_.icon]:text-[24px]",
        label ? "px-4 pr-5" : "w-14",
        className,
      )}
    >
      <Ripple />
      {icon}
      {label && <span className="text-label-large">{label}</span>}
    </motion.button>
  );
});

/* ─────────────────────────────────── Cards ─────────────────────────────────── */

type CardVariant = "elevated" | "filled" | "outlined";

const CARD_VARIANT: Record<CardVariant, string> = {
  elevated: "bg-surface-container-low shadow-elev-1",
  filled: "bg-surface-container-highest",
  outlined: "bg-surface border border-outline-variant",
};

export function Card({
  variant = "filled",
  interactive,
  className,
  children,
  ...rest
}: { variant?: CardVariant; interactive?: boolean; className?: string; children: ReactNode } & React.HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn("rounded-lg", CARD_VARIANT[variant], interactive && "card-lift state-layer cursor-pointer", className)}
      {...rest}
    >
      {children}
    </section>
  );
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-5 pt-5">
      <div className="min-w-0">
        <h2 className="text-title-medium text-on-surface">{title}</h2>
        {subtitle && <p className="mt-0.5 text-body-medium text-on-surface-variant">{subtitle}</p>}
      </div>
      {action}
    </header>
  );
}

/* ─────────────────────────────────── Chips ─────────────────────────────────── */

export function FilterChip({
  selected,
  onClick,
  children,
  trailing,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
  trailing?: ReactNode;
}) {
  return (
    <button
      role="checkbox"
      aria-checked={selected}
      onClick={onClick}
      className={cn(
        "state-layer shape-morph relative inline-flex h-8 shrink-0 items-center gap-2 overflow-hidden rounded-sm text-label-large",
        selected
          ? "bg-secondary-container pr-4 pl-2 text-on-secondary-container"
          : "border border-outline-variant px-4 text-on-surface-variant",
      )}
    >
      <Ripple />
      {selected && (
        <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={spatialFast} className="inline-flex">
          <Icon name="check" size={18} weight={600} />
        </motion.span>
      )}
      {children}
      {trailing}
    </button>
  );
}

/** M3 Expressive connected button group: single-select, selected item morphs to full round. */
export function ConnectedButtonGroup<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("flex gap-0.5", className)}>
      {options.map((opt, i) => {
        const selected = opt.value === value;
        const first = i === 0;
        const last = i === options.length - 1;
        return (
          <button
            key={opt.value}
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(opt.value)}
            className={cn(
              "state-layer shape-morph relative inline-flex h-10 min-w-0 flex-1 items-center justify-center gap-1.5 overflow-hidden px-4 text-label-large whitespace-nowrap",
              selected
                ? "rounded-full bg-secondary-container text-on-secondary-container"
                : cn(
                    "bg-surface-container-high text-on-surface-variant",
                    first ? "rounded-l-full rounded-r-sm" : last ? "rounded-l-sm rounded-r-full" : "rounded-sm",
                  ),
            )}
          >
            <Ripple />
            {selected && <Icon name="check" size={18} weight={600} />}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

/* ──────────────────────────────── Text field ──────────────────────────────── */

export const TextField = forwardRef<
  HTMLInputElement,
  Omit<InputHTMLAttributes<HTMLInputElement>, "size"> & {
    label: string;
    leading?: ReactNode;
    trailing?: ReactNode;
    supporting?: ReactNode;
    error?: boolean;
  }
>(function TextField({ label, leading, trailing, supporting, error, className, value, ...props }, ref) {
  const id = useId();
  const [focused, setFocused] = useState(false);
  const floated = focused || (value !== undefined && String(value).length > 0);
  return (
    <div className={className}>
      <div
        className={cn(
          "relative flex h-14 items-center gap-3 rounded-xs px-4 transition-[box-shadow] duration-200",
          error
            ? "shadow-[inset_0_0_0_2px_var(--md-sys-color-error)]"
            : focused
              ? "shadow-[inset_0_0_0_2px_var(--md-sys-color-primary)]"
              : "shadow-[inset_0_0_0_1px_var(--md-sys-color-outline)] hover:shadow-[inset_0_0_0_1px_var(--md-sys-color-on-surface)]",
        )}
      >
        {leading && <span className="text-on-surface-variant [&_.icon]:text-[24px]">{leading}</span>}
        <div className="relative h-full flex-1">
          <label
            htmlFor={id}
            className={cn(
              "pointer-events-none absolute left-0 origin-left transition-all duration-200 ease-[var(--md-sys-motion-easing-standard)]",
              floated
                ? cn("top-0 -translate-y-1/2 bg-surface px-1 -ml-1 text-body-small", error ? "text-error" : focused ? "text-primary" : "text-on-surface-variant")
                : "top-1/2 -translate-y-1/2 text-body-large text-on-surface-variant",
              floated && !!leading && "-ml-10",
            )}
          >
            {label}
          </label>
          <input
            ref={ref}
            id={id}
            value={value}
            onFocus={(e) => {
              setFocused(true);
              props.onFocus?.(e);
            }}
            onBlur={(e) => {
              setFocused(false);
              props.onBlur?.(e);
            }}
            className="h-full w-full bg-transparent text-body-large text-on-surface caret-primary outline-none"
            {...props}
          />
        </div>
        {trailing && <span className="text-on-surface-variant">{trailing}</span>}
      </div>
      {supporting && (
        <p className={cn("mt-1 px-4 text-body-small", error ? "text-error" : "text-on-surface-variant")}>{supporting}</p>
      )}
    </div>
  );
});

/* ──────────────────────────────── Small parts ──────────────────────────────── */

export function Badge({ count, className }: { count?: number; className?: string }) {
  if (count === undefined) return <span className={cn("size-1.5 rounded-full bg-error", className)} />;
  return (
    <motion.span
      key={count}
      initial={{ scale: 0.6 }}
      animate={{ scale: 1 }}
      transition={spatialFast}
      className={cn(
        "inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-error px-1 text-label-small text-on-error tabular",
        className,
      )}
    >
      {count > 999 ? "999+" : count}
    </motion.span>
  );
}

const AVATAR_TONES = [
  "bg-primary-container text-on-primary-container",
  "bg-secondary-container text-on-secondary-container",
  "bg-tertiary-container text-on-tertiary-container",
];

export function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  const tone = AVATAR_TONES[[...name].reduce((h, c) => h + c.charCodeAt(0), 0) % AVATAR_TONES.length];
  return (
    <span
      aria-hidden
      className={cn("inline-flex shrink-0 items-center justify-center rounded-full text-label-large uppercase", tone)}
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {initials(name)}
    </span>
  );
}

/** `onColor` inherits the host's content color, for hints inside filled buttons. */
export function Kbd({ children, className, onColor }: { children: ReactNode; className?: string; onColor?: boolean }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-xs border px-1 font-mono text-label-small",
        onColor ? "border-current/50 text-current" : "border-outline-variant text-on-surface-variant",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton rounded-sm", className)} />;
}

export function LiveDot({ className }: { className?: string }) {
  return <span className={cn("live-dot relative inline-flex size-2 rounded-full bg-success text-success", className)} />;
}

/** M3 Expressive wavy indeterminate progress. */
export function WavyProgress({ className }: { className?: string }) {
  return (
    <span className={cn("block h-2 overflow-hidden", className)} role="progressbar" aria-label="In progress">
      <svg className="wave-travel h-2 w-[calc(100%+20px)]" preserveAspectRatio="none" viewBox="0 0 200 8">
        <path
          d={Array.from({ length: 11 }, (_, i) => `${i ? "" : "M0 4 "}q5 -4 10 0 t10 0`).join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

/** M3 switch: handle grows when on and while pressed. */
export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  const [pressed, setPressed] = useState(false);
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      onPointerDown={() => setPressed(true)}
      onPointerUp={() => setPressed(false)}
      onPointerLeave={() => setPressed(false)}
      className={cn(
        "relative inline-flex h-8 w-[52px] shrink-0 items-center rounded-full transition-colors duration-200",
        checked ? "bg-primary" : "border-2 border-outline bg-surface-container-highest",
      )}
    >
      <motion.span
        layout
        transition={spatialFast}
        className={cn("absolute rounded-full", checked ? "bg-on-primary" : "bg-outline")}
        style={{
          width: pressed ? 28 : checked ? 24 : 16,
          height: pressed ? 28 : checked ? 24 : 16,
          left: checked ? (pressed ? 22 : 24) : pressed ? 0 : 6,
        }}
      />
    </button>
  );
}

export function Divider({ className }: { className?: string }) {
  return <hr className={cn("border-0 border-t border-outline-variant", className)} />;
}
