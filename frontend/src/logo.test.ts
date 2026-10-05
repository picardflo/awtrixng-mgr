import { describe, expect, it } from "vitest";
import favicon from "../public/favicon.svg?raw";
import { LOGO_BACKGROUND, LOGO_PIXELS } from "./logo";

describe("the mark", () => {
  it("has nine pixels", () => {
    expect(LOGO_PIXELS).toHaveLength(9);
  });

  it("is drawn identically in the tab and in the header", () => {
    // A favicon that drifts from the logo is the kind of detail nobody
    // notices and everybody feels.
    const painted = [...favicon.matchAll(/<rect[^>]*fill="(#[0-9a-f]{6})"/g)].map(
      (m) => m[1],
    );
    expect(painted).toEqual([LOGO_BACKGROUND, ...LOGO_PIXELS]);
  });

  it("uses the three channels and nothing else", () => {
    // Red, green, blue, amber — the mark says "pixel matrix" and borrows
    // nothing from AWTRIX.
    expect(new Set(LOGO_PIXELS).size).toBe(4);
  });
});
