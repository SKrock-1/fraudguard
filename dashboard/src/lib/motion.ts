/**
 * M3 Expressive motion scheme as Motion springs.
 * Motion takes absolute damping, so each M3 (dampingRatio ζ, stiffness k) pair
 * is converted with damping = 2ζ√k (mass 1). Mirrors the CSS tokens in globals.css.
 */
const spring = (dampingRatio: number, stiffness: number) => ({
  type: "spring" as const,
  stiffness,
  damping: 2 * dampingRatio * Math.sqrt(stiffness),
  mass: 1,
});

/** Position, size, shape: may overshoot slightly, which is the "expressive" part */
export const spatialFast = spring(0.6, 800);
export const spatialDefault = spring(0.8, 380);
export const spatialSlow = spring(0.8, 200);

/** Opacity and color: critically damped, never overshoot */
export const effectsFast = spring(1, 3800);
export const effectsDefault = spring(1, 1600);
export const effectsSlow = spring(1, 800);

export const emphasizedDecelerate = [0.05, 0.7, 0.1, 1] as const;
export const standard = [0.2, 0, 0, 1] as const;
