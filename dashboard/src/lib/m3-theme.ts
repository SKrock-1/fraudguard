/**
 * Material 3 dynamic color: derives every color role from one seed color with
 * Google's material-color-utilities (2025 / Expressive spec), plus harmonized
 * custom colors for states M3 has no role for (success, warning, serious).
 *
 * Used by scripts/generate-tokens.ts for the default static tokens and at
 * runtime by the color picker.
 */
import {
  Blend,
  Hct,
  MaterialDynamicColors,
  SchemeExpressive,
  TonalPalette,
  argbFromHex,
  hexFromArgb,
  type DynamicColor,
  type DynamicScheme,
} from "@material/material-color-utilities";

export const DEFAULT_SEED = "#3d6dd8";

export const SEEDS = [
  { name: "Sapphire", hex: DEFAULT_SEED },
  { name: "Lagoon", hex: "#00838f" },
  { name: "Iris", hex: "#6750a4" },
  { name: "Orchid", hex: "#a33f7a" },
  { name: "Moss", hex: "#4f6a2a" },
];

const ROLES: [string, keyof typeof MaterialDynamicColors][] = [
  ["primary", "primary"],
  ["on-primary", "onPrimary"],
  ["primary-container", "primaryContainer"],
  ["on-primary-container", "onPrimaryContainer"],
  ["inverse-primary", "inversePrimary"],
  ["secondary", "secondary"],
  ["on-secondary", "onSecondary"],
  ["secondary-container", "secondaryContainer"],
  ["on-secondary-container", "onSecondaryContainer"],
  ["tertiary", "tertiary"],
  ["on-tertiary", "onTertiary"],
  ["tertiary-container", "tertiaryContainer"],
  ["on-tertiary-container", "onTertiaryContainer"],
  ["error", "error"],
  ["on-error", "onError"],
  ["error-container", "errorContainer"],
  ["on-error-container", "onErrorContainer"],
  ["background", "background"],
  ["on-background", "onBackground"],
  ["surface", "surface"],
  ["surface-dim", "surfaceDim"],
  ["surface-bright", "surfaceBright"],
  ["surface-container-lowest", "surfaceContainerLowest"],
  ["surface-container-low", "surfaceContainerLow"],
  ["surface-container", "surfaceContainer"],
  ["surface-container-high", "surfaceContainerHigh"],
  ["surface-container-highest", "surfaceContainerHighest"],
  ["surface-variant", "surfaceVariant"],
  ["on-surface", "onSurface"],
  ["on-surface-variant", "onSurfaceVariant"],
  ["inverse-surface", "inverseSurface"],
  ["inverse-on-surface", "inverseOnSurface"],
  ["outline", "outline"],
  ["outline-variant", "outlineVariant"],
  ["shadow", "shadow"],
  ["scrim", "scrim"],
  ["surface-tint", "surfaceTint"],
];

/** Fixed hues for states M3 doesn't model, nudged toward the seed so they belong to the scheme. */
const CUSTOM = [
  { name: "success", hex: "#2e7d32" },
  { name: "warning", hex: "#b88200" },
  { name: "serious", hex: "#c97000" },
];

export type Tokens = Record<string, string>;

export function buildScheme(seedHex: string, isDark: boolean): Tokens {
  const seed = argbFromHex(seedHex);
  const scheme: DynamicScheme = new SchemeExpressive(Hct.fromInt(seed), isDark, 0, "2025");
  const tokens: Tokens = {};

  for (const [css, key] of ROLES) {
    const color = MaterialDynamicColors[key] as unknown as DynamicColor;
    tokens[`--md-sys-color-${css}`] = hexFromArgb(color.getArgb(scheme));
  }

  for (const custom of CUSTOM) {
    const palette = TonalPalette.fromInt(Blend.harmonize(argbFromHex(custom.hex), seed));
    const [c, on, container, onContainer] = isDark ? [80, 20, 30, 90] : [40, 100, 90, 30];
    tokens[`--md-ext-color-${custom.name}`] = hexFromArgb(palette.tone(c));
    tokens[`--md-ext-color-on-${custom.name}`] = hexFromArgb(palette.tone(on));
    tokens[`--md-ext-color-${custom.name}-container`] = hexFromArgb(palette.tone(container));
    tokens[`--md-ext-color-on-${custom.name}-container`] = hexFromArgb(palette.tone(onContainer));
  }
  return tokens;
}

export function schemeCss(seedHex: string): string {
  const block = (tokens: Tokens) =>
    Object.entries(tokens)
      .map(([k, v]) => `  ${k}: ${v};`)
      .join("\n");
  return [
    `:root {\n${block(buildScheme(seedHex, false))}\n}`,
    `:root[data-theme="dark"] {\n${block(buildScheme(seedHex, true))}\n}`,
  ].join("\n\n");
}
