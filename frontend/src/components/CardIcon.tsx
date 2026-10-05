import { iconThumbnail } from "../api/client";

/**
 * The icon a card's subject shows on the matrix, as a small thumbnail.
 *
 * Three cases, and only one of them yields a picture:
 *
 * - a numeric LaMetric id — the gallery has an image for it;
 * - a file name typed by hand — the file lives on the clock, and there is
 *   nowhere to fetch it from, so a neutral square says "there is an icon, we
 *   just cannot show it" rather than implying there is none;
 * - nothing at all — the matrix shows no icon either, so neither do we.
 *
 * Shared between widgets and reminders: two lists that mean the same thing
 * should not render it twice, and differently.
 */
export function CardIcon({ icon, title }: { icon?: string | null; title?: string }) {
  if (!icon) return null;

  const common =
    "h-6 w-6 shrink-0 rounded border border-[var(--color-border)] bg-[var(--color-matrix-bg)]";

  if (!/^\d+$/.test(icon)) {
    return (
      <span
        className={`${common} flex items-center justify-center text-[9px] text-[var(--color-text-faint)]`}
        title={title ?? icon}
      >
        ▦
      </span>
    );
  }

  return (
    <img
      src={iconThumbnail(icon)}
      alt=""
      title={title ?? icon}
      // Pixel art: smoothing an 8x8 icon blurs it into a stain.
      className={`${common} [image-rendering:pixelated]`}
    />
  );
}
