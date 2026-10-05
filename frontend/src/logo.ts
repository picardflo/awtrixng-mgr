/**
 * The nine pixels of the awtrixng-mgr mark.
 *
 * Original: a grid of RGB pixels, nothing borrowed from AWTRIX. Shared rather
 * than written twice — the header draws them from here, `public/favicon.svg`
 * carries the same values, and a test refuses the day the two drift apart.
 */
export const LOGO_PIXELS = [
  "#3ddc84", "#4aa8ff", "#f5a524",
  "#4aa8ff", "#3ddc84", "#f4526b",
  "#f5a524", "#f4526b", "#3ddc84",
] as const;

/** The matrix behind them, so the mark reads on a pale tab bar too. */
export const LOGO_BACKGROUND = "#0b0f14";
