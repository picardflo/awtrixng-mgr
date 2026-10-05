import { describe, expect, it } from "vitest";
import { resolveColour } from "./WidgetBuilder";

/** The preview resolves colours itself so it can draw without a round trip.
 *
 *  That means the rule lives twice — here and in `renderer.py` — and the bar
 *  is what happens when they drift: the matrix took the connector's colour
 *  while the preview kept firmware green, and the form still said so in its
 *  help text. Each case below is the behaviour the backend has.
 */
describe("resolveColour", () => {
  it("prefers what the user typed", () => {
    expect(resolveColour("#ff0000", "#4aa8ff", "#00ff00")).toBe("#ff0000");
  });

  it("falls back to what the connector proposes", () => {
    expect(resolveColour(null, "#4aa8ff", "#00ff00")).toBe("#4aa8ff");
  });

  it("falls back again when the connector proposes nothing", () => {
    expect(resolveColour(null, null, "#00ff00")).toBe("#00ff00");
  });

  it("treats an emptied field as unset", () => {
    // What the text input stores when someone clears it. `??` would have kept
    // the empty string and painted nothing at all.
    expect(resolveColour("", "#4aa8ff", "#00ff00")).toBe("#4aa8ff");
  });

  it("treats undefined as unset", () => {
    expect(resolveColour(undefined, "#4aa8ff", "#00ff00")).toBe("#4aa8ff");
  });

  it("applies the same chain whatever it colours", () => {
    // One function, two call sites: the text and the bar cannot diverge
    // again without this failing.
    const connector = "#ff7043";
    expect(resolveColour(null, connector, "#3ddc84")).toBe(connector);
    expect(resolveColour(null, connector, "#00ff00")).toBe(connector);
  });
});
