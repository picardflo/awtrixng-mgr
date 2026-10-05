import { describe, expect, it } from "vitest";
import { barGeometry, MATRIX_WIDTH } from "./AwtrixMatrixPreview";

/** Measured on the hardware, not derived from this code.
 *
 *  One app, captured on a v0.98 Ulanzi and on the official simulator: the
 *  icon's lit pixels at x=3..4, the bar's first lit pixel at x=8 in both. The
 *  preview drew it from x=0, which hid part of it under the icon and spread
 *  the fill over 32 columns instead of 24 — so a bar always looked emptier in
 *  the builder than on the clock.
 */
describe("barGeometry", () => {
  it("starts after the icon when there is one", () => {
    expect(barGeometry(50, true).left).toBe(8);
  });

  it("starts at the edge when there is none", () => {
    expect(barGeometry(50, false).left).toBe(0);
  });

  it("spreads the fill over what is left, not over the whole matrix", () => {
    // The defect, as a number: 50 % with an icon is 12 columns, not 16.
    expect(barGeometry(50, true)).toMatchObject({ width: 24, filled: 12 });
    expect(barGeometry(50, false)).toMatchObject({ width: 32, filled: 16 });
  });

  it("matches what the clock showed", () => {
    // The captured bar ran x=8 to x=16: nine lit columns out of twenty-four.
    const { left, filled } = barGeometry(37.5, true);
    expect(left).toBe(8);
    expect(filled).toBe(9);
  });

  it("never runs past the right edge", () => {
    const { left, filled } = barGeometry(100, true);
    expect(left + filled).toBe(MATRIX_WIDTH);
  });

  it("clamps a value outside 0-100 rather than drawing nonsense", () => {
    expect(barGeometry(-20, true).filled).toBe(0);
    expect(barGeometry(140, false).filled).toBe(MATRIX_WIDTH);
  });

  it("shows nothing at zero", () => {
    expect(barGeometry(0, true).filled).toBe(0);
  });
});
