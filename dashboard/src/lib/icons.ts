/**
 * Material Symbols Rounded, subset to the glyphs this app uses.
 *
 * The list types <Icon name> (an unlisted name is a compile error) and builds
 * the Google Fonts URL, so the font subset and the code can't drift apart.
 */
export const ICON_NAMES = [
  "account_balance_wallet",
  "arrow_back",
  "arrow_forward",
  "bolt",
  "block",
  "check",
  "check_circle",
  "close",
  "content_copy",
  "crisis_alert",
  "dark_mode",
  "done_all",
  "expand_more",
  "fingerprint",
  "flight_takeoff",
  "gpp_maybe",
  "inbox",
  "keyboard_return",
  "light_mode",
  "location_on",
  "lock",
  "logout",
  "menu",
  "menu_open",
  "monitoring",
  "neurology",
  "notifications_active",
  "palette",
  "payments",
  "pending",
  "person",
  "progress_activity",
  "receipt_long",
  "remove",
  "report",
  "search",
  "space_dashboard",
  "speed",
  "verified_user",
  "visibility",
  "visibility_off",
  "warning",
] as const;

export type IconName = (typeof ICON_NAMES)[number];

/** Google Fonts requires icon_names in alphabetical order. */
export const ICON_FONT_HREF =
  "https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" +
  `&icon_names=${[...ICON_NAMES].sort().join(",")}&display=block`;
