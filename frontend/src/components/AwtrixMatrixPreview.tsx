import { useEffect, useRef } from "react";
import { useI18n } from "../i18n";
import { GLYPH_HEIGHT, rasterize } from "./pixelFont";

export const MATRIX_WIDTH = 32;
export const MATRIX_HEIGHT = 8;
const ICON_SIZE = 8;

/** Where the progress bar sits, and how much of it is lit.
 *
 *  **The bar starts after the icon, never under it.** Measured twice on the
 *  same app — once on a v0.98 device, once on the official simulator — and
 *  both put the icon's own pixels at x=3..4 and the first lit bar pixel at
 *  x=8.
 *
 *  Drawing it from x=0 was wrong twice over: it ran under an icon that hides
 *  it anyway, and it shared the fill over 32 columns where the firmware uses
 *  24, so every bar in the preview read lower than the clock showed.
 */
export function barGeometry(
  progress: number,
  hasIcon: boolean,
): { left: number; width: number; filled: number } {
  const left = hasIcon ? ICON_SIZE : 0;
  const width = MATRIX_WIDTH - left;
  const share = Math.max(0, Math.min(100, progress)) / 100;
  return { left, width, filled: Math.round(share * width) };
}

export interface MatrixPreviewProps {
  text?: string;
  /** AWTRIX icon id or file name. Only reserves the 8x8 slot. */
  icon?: string | null;
  /** Image for that icon. Passing LaMetric's URL shows the **animated** GIF,
   *  which a canvas could not do — drawImage only takes the first frame. */
  iconUrl?: string | null;
  color?: string;
  background?: string | null;
  noScroll?: boolean;
  scrollSpeed?: number;
  progress?: number | null;
  progressColor?: string;
  progressBackground?: string;
  indicators?: [boolean, boolean, boolean];
  /** Size of one LED in screen pixels. */
  scale?: number;
  className?: string;
}

const OFF = "#15171d";
const MATRIX_BG = "#05060a";

/** Reference scroll speed, in columns per second. */
const BASE_SCROLL_COLUMNS_PER_SECOND = 9;

export function AwtrixMatrixPreview({
  text = "",
  icon = null,
  iconUrl = null,
  color = "#3ddc84",
  background = null,
  noScroll = false,
  scrollSpeed = 100,
  progress = null,
  // Firmware defaults, measured on a v0.98 device: the filled part is pure
  // green and the track is WHITE — which is why awtrixng-mgr forces it to black
  // (see DisplayOptions.progress_background). The preview must show what the
  // device will show, not a prettier version of it.
  progressColor = "#00ff00",
  progressBackground = "#000000",
  indicators = [false, false, false],
  scale = 6,
  className = "",
}: MatrixPreviewProps) {
  const { t } = useI18n();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = MATRIX_WIDTH * scale * dpr;
    canvas.height = MATRIX_HEIGHT * scale * dpr;
    canvas.style.width = `${MATRIX_WIDTH * scale}px`;
    canvas.style.height = `${MATRIX_HEIGHT * scale}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const columns = rasterize(text);
    const textLeft = icon ? ICON_SIZE + 1 : 0;
    const available = MATRIX_WIDTH - textLeft;
    const overflows = columns.length > available;
    const scrolls = overflows && !noScroll;

    // Rows 1 to 5. Measured on the device: the progress bar does not move the
    // text, it only takes row 7.
    const textTop = 1;

    const dot = (x: number, y: number, fill: string) => {
      if (x < 0 || x >= MATRIX_WIDTH || y < 0 || y >= MATRIX_HEIGHT) return;
      ctx.fillStyle = fill;
      // A small gap between LEDs gives the matrix look.
      ctx.fillRect(x * scale + 0.5, y * scale + 0.5, scale - 1, scale - 1);
    };

    const draw = (elapsedMs: number) => {
      ctx.fillStyle = MATRIX_BG;
      ctx.fillRect(0, 0, MATRIX_WIDTH * scale, MATRIX_HEIGHT * scale);

      for (let y = 0; y < MATRIX_HEIGHT; y += 1) {
        for (let x = 0; x < MATRIX_WIDTH; x += 1) {
          dot(x, y, background ?? OFF);
        }
      }

      // With a URL, an <img> overlays this area so the GIF actually animates.
      // Without one, a discreet checker shows the icon's real footprint rather
      // than pretending to display it.
      if (icon && !iconUrl) {
        for (let y = 0; y < ICON_SIZE; y += 1) {
          for (let x = 0; x < ICON_SIZE; x += 1) {
            const edge = x === 0 || y === 0 || x === ICON_SIZE - 1 || y === ICON_SIZE - 1;
            if (edge || (x + y) % 2 === 0) dot(x, y, edge ? "#2c3240" : "#20242e");
          }
        }
      }

      let offset: number;
      if (scrolls) {
        const speed = BASE_SCROLL_COLUMNS_PER_SECOND * (scrollSpeed / 100);
        const cycle = columns.length + available;
        const travelled = (elapsedMs / 1000) * speed;
        offset = available - (travelled % cycle);
      } else if (!overflows) {
        // Measured on a TC001 running NG 1.1.2: text that fits is centred by
        // the firmware, always. "A" landed at columns 14-16, "ABC" at 10-20,
        // each exactly where centring puts it. AWTRIX 3 made this an option;
        // NG has no centring key at all, so the preview follows the firmware
        // rather than offering a switch that changes nothing.
        offset = Math.floor((available - columns.length) / 2);
      } else {
        offset = 0;
      }

      for (let i = 0; i < columns.length; i += 1) {
        const x = textLeft + Math.round(offset) + i;
        if (x < textLeft || x >= MATRIX_WIDTH) continue;
        const mask = columns[i];
        const fill = color;
        for (let y = 0; y < GLYPH_HEIGHT; y += 1) {
          if (mask & (1 << y)) dot(x, textTop + y, fill);
        }
      }

      if (progress !== null) {
        const { left, filled } = barGeometry(progress, Boolean(icon));
        for (let x = left; x < MATRIX_WIDTH; x += 1) {
          dot(x, MATRIX_HEIGHT - 1, x - left < filled ? progressColor : progressBackground);
        }
      }

      // indicator1 top-right, indicator2 mid-right, indicator3 bottom-right.
      const [i1, i2, i3] = indicators;
      if (i1) dot(MATRIX_WIDTH - 1, 0, "#f4526b");
      if (i2) dot(MATRIX_WIDTH - 1, 3, "#f5a524");
      if (i3) dot(MATRIX_WIDTH - 1, MATRIX_HEIGHT - 1, "#4aa8ff");
    };

    if (!scrolls) {
      draw(0);
      return;
    }

    const started = performance.now();
    const tick = () => {
      draw(performance.now() - started);
      frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [
    text, icon, iconUrl, color, background, noScroll,
    scrollSpeed, progress, progressColor, progressBackground, indicators, scale,
  ]);

  return (
    <div
      className={`relative ${className}`}
      style={{ width: MATRIX_WIDTH * scale, height: MATRIX_HEIGHT * scale }}
      role="img"
      aria-label={text ? t("matrix.previewOf", { text }) : t("matrix.previewEmpty")}
    >
      <canvas ref={canvasRef} className="rounded-[3px]" />
      {icon && iconUrl && (
        <img
          src={iconUrl}
          alt=""
          aria-hidden
          // The device draws one LED per pixel with a gap; nearest-neighbour
          // scaling is the closest a browser gets to that.
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: ICON_SIZE * scale,
            height: ICON_SIZE * scale,
            imageRendering: "pixelated",
          }}
        />
      )}
    </div>
  );
}
