import { describe, expect, it } from "vitest";
import { dim } from "./AwtrixMatrixPreview";

/** The preview draws the progress track; the backend sends it. Two
 *  implementations of one rule, and a preview that disagreed with the clock
 *  would be worse than no preview — it is consulted precisely when something
 *  looks wrong.
 *
 *  Every expected value below was produced by `app.connectors.weather.wmo.dim`
 *  in Python. A matching table is pinned on that side, so a drift fails here
 *  or there rather than on the matrix. */
describe("the progress track", () => {
  it.each([
    ["#4aa8ff", "#0d1e2e"],
    ["#3ddc84", "#0b2818"],
    ["#f5a524", "#2c1e06"],
    ["#7e6bff", "#17132e"],
    ["#ffffff", "#2e2e2e"],
    ["#000000", "#000000"],
  ])("washes %s to %s, as the backend does", (colour, expected) => {
    expect(dim(colour)).toBe(expected);
  });

  it("stays dark enough never to read as a full bar", () => {
    // The whole reason the firmware's own white track was refused: at 2 % it
    // lights the bottom row and looks like 100 %.
    const channels = dim("#ffffff")
      .slice(1)
      .match(/../g)!
      .map((c) => parseInt(c, 16));
    expect(Math.max(...channels)).toBeLessThanOrEqual(60);
  });

  it("gives black back for something that is not a colour", () => {
    expect(dim("rouge")).toBe("#000000");
  });
});
