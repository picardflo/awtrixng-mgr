import { describe, expect, it } from "vitest";
import { GLYPH_HEIGHT, GLYPH_HEIGHT_LARGE, LETTER_SPACING, rasterize, textWidth } from "./pixelFont";

/** Render one string as rows of "#" and "." for readable assertions.
 *
 *  Every expectation below is a transcription of what a TC001 on NG 1.1.2
 *  actually drew, read back out of its framebuffer — not a drawing made from
 *  a screenshot. The previous version of this font was the latter, and its
 *  "A" was wrong.
 */
function rows(text: string, font: "small" | "large" = "small"): string[] {
  const columns = rasterize(text, font);
  const height = font === "large" ? GLYPH_HEIGHT_LARGE : GLYPH_HEIGHT;
  return Array.from({ length: height }, (_, y) =>
    columns.map((mask) => (mask & (1 << y) ? "#" : ".")).join(""),
  );
}

describe("the small font", () => {
  it("draws the glyph the firmware draws", () => {
    // Measured. The hand-drawn version had "010" on the top row.
    expect(rows("A")).toEqual(["##.", "#.#", "###", "#.#", "#.#"]);
  });

  it("is five rows tall", () => {
    expect(rows("AWTRIX 3").length).toBe(GLYPH_HEIGHT);
  });

  it("uses variable width, as the firmware does", () => {
    expect(textWidth("i")).toBeLessThan(textWidth("W"));
  });

  it("inserts spacing between characters but not before the first", () => {
    expect(textWidth("ii")).toBe(2 * textWidth("i") + LETTER_SPACING);
  });
});

describe("the large font", () => {
  it("is seven rows tall", () => {
    expect(rows("65%", "large").length).toBe(GLYPH_HEIGHT_LARGE);
  });

  it("draws the glyph the firmware draws", () => {
    expect(rows("A", "large")).toEqual([
      "###", "#.#", "#.#", "###", "#.#", "#.#", "#.#",
    ]);
  });

  it("costs nothing horizontally for most characters", () => {
    // The measurement that made the font rule possible: large fills the panel
    // vertically without pushing anything off the right-hand edge.
    for (const text of ["65%", "19:27", "21°", "UV 3"]) {
      expect(textWidth(text, "large")).toBe(textWidth(text, "small"));
    }
  });
});

describe("accents", () => {
  it("draws them, because the display does", () => {
    // AWTRIX 3 had no accented glyph and drew "?", which is why this project
    // used to strip them before sending. NG draws all of them.
    expect(rows("é")).not.toEqual(rows("?"));
    expect(rows("ç")).not.toEqual(rows("?"));
    expect(rows("É", "large")).not.toEqual(rows("?", "large"));
  });

  it("keeps an accented word the same width as the display gives it", () => {
    expect(textWidth("Dégradé")).toBeGreaterThan(0);
    expect(textWidth("Dégradé")).toBeLessThanOrEqual(32);
  });
});

describe("the rest", () => {
  it("falls back to a question mark for a character the display lacks", () => {
    expect(rasterize("☃")).toEqual(rasterize("?"));
  });

  it("returns nothing for an empty string", () => {
    expect(rasterize("")).toEqual([]);
  });

  it("renders a space as blank columns", () => {
    expect(rasterize(" ").every((mask) => mask === 0)).toBe(true);
  });

  it("keeps a typical widget line inside the 32-column matrix", () => {
    expect(textWidth("18.5°C")).toBeLessThanOrEqual(32);
  });

  it("detects that a long line will overflow and scroll", () => {
    expect(textWidth("Lune gibbeuse décroissante")).toBeGreaterThan(32 - 9);
  });
});
