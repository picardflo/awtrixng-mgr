import { describe, expect, it } from "vitest";
import { GLYPH_HEIGHT, LETTER_SPACING, rasterize, textWidth } from "./pixelFont";

/** Render one string as rows of "#" and "." for readable assertions. */
function rows(text: string): string[] {
  const columns = rasterize(text);
  return Array.from({ length: GLYPH_HEIGHT }, (_, y) =>
    columns.map((mask) => (mask & (1 << y) ? "#" : ".")).join(""),
  );
}

describe("rasterize", () => {
  it("renders a known glyph exactly", () => {
    expect(rows("A")).toEqual([".#.", "#.#", "###", "#.#", "#.#"]);
  });

  it("gives every glyph five rows", () => {
    expect(rows("AWTRIX 3").length).toBe(GLYPH_HEIGHT);
  });

  it("uses variable width, as the firmware does", () => {
    // AWTRIX: "the font does not have a fixed size and I uses less space than W"
    expect(textWidth("I")).toBeLessThan(textWidth("W"));
  });

  it("inserts spacing between characters but not before the first", () => {
    expect(textWidth("II")).toBe(2 * textWidth("I") + LETTER_SPACING);
  });

  it("maps lowercase onto uppercase, like the firmware default", () => {
    expect(rasterize("awtrix")).toEqual(rasterize("AWTRIX"));
  });

  it("falls back to a visible glyph for unknown characters", () => {
    const unknown = rasterize("☃"); // snowman
    expect(unknown).toEqual(rasterize("?"));
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
    expect(textWidth("DUNE PART TWO")).toBeGreaterThan(32 - 9);
  });
});
