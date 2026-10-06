/**
 * The nine pixels of the awtrixng-mgr mark.
 *
 * Original: a grid of RGB pixels. The shape is ours and stays ours — AWTRIX
 * NG's mark is a specific glyph, and copying it would be passing this off as
 * theirs rather than aligning with it.
 *
 * What did change with the 0.14.0 charter is the four inks. They were the old
 * palette's — a cold green, a cold blue — and on a page of warm greys they
 * read as something left behind rather than something chosen. They are now
 * the page's own state colours, which is why the mark belongs to it.
 *
 * Shared rather than written twice — the header draws them from here,
 * `public/favicon.svg` carries the same values, and a test refuses the day
 * the two drift apart.
 */
export const LOGO_PIXELS = [
  "#6ee7a0", "#79c0ff", "#f5a568",
  "#79c0ff", "#6ee7a0", "#ff8f80",
  "#f5a568", "#ff8f80", "#6ee7a0",
] as const;

/** The matrix behind them, so the mark reads on a pale tab bar too. */
export const LOGO_BACKGROUND = "#10100f";
