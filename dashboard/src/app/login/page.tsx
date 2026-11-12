"use client";

import { motion, useAnimationControls } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/components/providers";
import { BrandMark, scallop } from "@/components/shell";
import { Button, Icon, IconButton, LiveDot, Ripple, TextField } from "@/components/ui/m3";
import { ApiError } from "@/lib/api";
import { emphasizedDecelerate, spatialDefault, spatialSlow } from "@/lib/motion";

const DEMO_USERS = [
  { username: "maya.chen", role: "Analyst" },
  { username: "ops.admin", role: "Admin" },
];

export default function LoginPage() {
  const { login, logout, user, ready } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shake = useAnimationControls();

  useEffect(() => {
    if (ready && user) router.replace("/");
  }, [ready, user, router]);

  const fail = (message: string) => {
    setError(message);
    setBusy(false);
    shake.start({ x: [0, -8, 8, -5, 5, 0], transition: { duration: 0.4 } });
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const signedIn = await login(username.trim(), password);
      if (signedIn.role === "ingestion_client") {
        logout();
        fail("This is an API ingestion account and can't use the review console.");
        return;
      }
      router.replace("/");
    } catch (err) {
      fail(
        err instanceof ApiError && err.status === 401
          ? "That username and password don't match."
          : err instanceof Error
            ? err.message
            : "Sign-in failed.",
      );
    }
  };

  return (
    <main className="grid min-h-dvh bg-surface expanded:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] expanded:gap-4 expanded:p-4">
      <HeroPane />

      <section className="flex flex-col px-4 py-6 medium:px-12">
        <div className="flex items-center gap-3 expanded:hidden">
          <BrandMark className="size-9" />
          <span className="emphasized text-title-large">FraudGuard</span>
        </div>

        <div className="mx-auto flex w-full max-w-[420px] flex-1 flex-col justify-center py-10">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: emphasizedDecelerate }}
          >
            <h1 className="text-headline-large text-on-surface">Sign in</h1>
            <p className="mt-2 text-body-large text-on-surface-variant">
              Review flagged transactions as they happen. Every decision is written to a tamper-proof audit trail.
            </p>

            <motion.form animate={shake} onSubmit={submit} className="mt-8 flex flex-col gap-5" noValidate>
              <TextField
                label="Username"
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                leading={<Icon name="person" />}
                error={!!error}
                required
              />
              <TextField
                label="Password"
                type={reveal ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                leading={<Icon name="lock" />}
                error={!!error}
                supporting={
                  error ? (
                    <span role="alert" className="inline-flex items-center gap-1">
                      <Icon name="warning" filled size={16} /> {error}
                    </span>
                  ) : undefined
                }
                trailing={
                  <IconButton type="button" label={reveal ? "Hide password" : "Show password"} onClick={() => setReveal((r) => !r)}>
                    <Icon name={reveal ? "visibility_off" : "visibility"} />
                  </IconButton>
                }
                required
              />

              <Button
                type="submit"
                variant="filled"
                size="md"
                disabled={busy || !username || !password}
                className="mt-2 w-full"
                icon={busy ? <Icon name="progress_activity" className="animate-spin" /> : undefined}
              >
                {busy ? "Signing in" : "Continue"}
                {!busy && <Icon name="arrow_forward" />}
              </Button>
            </motion.form>

            <div className="mt-8 rounded-lg bg-surface-container p-4">
              <p className="text-title-small text-on-surface">Demo workspace</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {DEMO_USERS.map((d) => (
                  <button
                    key={d.username}
                    type="button"
                    onClick={() => setUsername(d.username)}
                    className="state-layer shape-morph relative inline-flex h-8 items-center gap-2 overflow-hidden rounded-sm border border-outline-variant px-3 text-label-large text-on-surface-variant active:rounded-md"
                  >
                    <Ripple />
                    <Icon name="person" filled size={18} className="text-primary" />
                    {d.username}
                    <span>· {d.role}</span>
                  </button>
                ))}
              </div>
              <p className="mt-3 text-body-small text-on-surface-variant">
                Seeded by <code className="font-mono">manage.py seed_demo</code>. The password is{" "}
                <code className="font-mono">DEMO_PASSWORD</code> in the backend&apos;s <code className="font-mono">.env</code>.
              </p>
            </div>
          </motion.div>
        </div>

        <p className="text-body-small text-on-surface-variant">Synthetic data only. No real cardholder information.</p>
      </section>
    </main>
  );
}

const SHAPES = [
  { x: 80, y: 16, r: 22, lobes: 9, depth: 0.08, fill: "var(--md-sys-color-tertiary-container)", delay: 0.1, opacity: 1 },
  { x: 14, y: 30, r: 18, lobes: 4, depth: 0.12, fill: "var(--md-sys-color-primary)", delay: 0.2, opacity: 0.16 },
  { x: 92, y: 60, r: 12, lobes: 6, depth: 0.1, fill: "var(--md-sys-color-secondary-container)", delay: 0.3, opacity: 1 },
];

function HeroPane() {
  return (
    <section className="relative hidden overflow-hidden rounded-xl-inc bg-primary-container text-on-primary-container expanded:flex">
      <svg aria-hidden viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 size-full">
        {SHAPES.map((s, i) => (
          <motion.path
            key={i}
            d={scallop(s.x, s.y, s.r, s.depth, s.lobes)}
            fill={s.fill}
            initial={{ scale: 0.6, rotate: -20, opacity: 0 }}
            animate={{ scale: 1, rotate: 0, opacity: s.opacity }}
            transition={{ ...spatialSlow, delay: s.delay }}
            style={{ transformOrigin: `${s.x}px ${s.y}px`, transformBox: "view-box" }}
          />
        ))}
      </svg>

      <div className="relative flex w-full flex-col p-10 large:p-14">
        <div className="flex items-center gap-3">
          <BrandMark className="size-10" />
          <span className="emphasized text-title-large">FraudGuard</span>
        </div>

        <div className="mt-auto max-w-[520px]">
          <p className="inline-flex h-8 items-center gap-2 rounded-sm bg-surface-container-lowest/70 px-3 text-label-large text-on-surface">
            <LiveDot /> Scoring every transaction in under a second
          </p>
          <h2 className="mt-6 text-display-medium large:text-display-large">Every flag comes with a reason.</h2>
          <p className="mt-4 max-w-[440px] text-body-large opacity-90">
            Rules and an Isolation Forest model score each transaction. Analysts see exactly which signals fired and how much
            each one added.
          </p>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...spatialDefault, delay: 0.35 }}
            className="mt-10 max-w-[440px] rounded-xl bg-surface-container-low p-5 text-on-surface shadow-elev-2"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-label-medium text-on-surface-variant">Alert · FG-4821-0007</p>
                <p className="mt-1 text-title-medium">CryptoXchange Ltd</p>
                <p className="text-body-small text-on-surface-variant">Tokyo, 31 min after a purchase in London</p>
              </div>
              <div className="text-right">
                <p className="text-title-medium tabular">$2,418.90</p>
                <span className="mt-1 inline-flex h-6 items-center gap-1 rounded-sm bg-error-container px-2 text-label-medium text-on-error-container">
                  <Icon name="crisis_alert" filled size={16} /> 0.95 Critical
                </span>
              </div>
            </div>
            <div className="mt-4 flex h-3 gap-[3px] overflow-hidden rounded-full">
              {[
                { w: 40, c: "var(--md-ext-series-1)" },
                { w: 30, c: "var(--md-ext-series-2)" },
                { w: 25, c: "var(--md-ext-series-4)" },
              ].map((s, i) => (
                <motion.span
                  key={i}
                  className="h-full origin-left rounded-[3px] first:rounded-l-full"
                  style={{ width: `${s.w}%`, background: s.c }}
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ ...spatialDefault, delay: 0.6 + i * 0.1 }}
                />
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-label-medium text-on-surface-variant">
              {[
                ["Travel", "+0.40", "var(--md-ext-series-1)"],
                ["Amount", "+0.30", "var(--md-ext-series-2)"],
                ["Model", "+0.25", "var(--md-ext-series-4)"],
              ].map(([label, value, color]) => (
                <span key={label} className="inline-flex items-center gap-1.5">
                  <span className="size-2 rounded-full" style={{ background: color }} />
                  {label} <span className="text-on-surface tabular">{value}</span>
                </span>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
