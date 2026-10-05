import { describe, expect, it } from "vitest";
import { supportsProgress } from "./WidgetBuilder";

/** Ticking "show a progress bar" on a Temperature widget did nothing at all.
 *
 *  The renderer only sends a bar when the connector supplied a value, and
 *  most supply none — the switch promised something the engine could not
 *  keep. Each case below is one of the widgets this repository ships.
 */
describe("supportsProgress", () => {
  it("allows it when the widget type declares one", () => {
    // school.week, weather.rain, weather.sun, moon.phase all do.
    expect(supportsProgress(60, null)).toBe(true);
  });

  it("allows it when only the live value has one", () => {
    // device.metric declares none, because it depends on the metric picked:
    // a battery reads out of 100, the same display's temperature does not.
    expect(supportsProgress(null, 87)).toBe(true);
  });

  it("keeps it available when the live value is legitimately absent", () => {
    // The sun widget after dark: the bar does not apply right now, but the
    // widget still has one. Greying the switch out at night would be wrong.
    expect(supportsProgress(62, null)).toBe(true);
  });

  it("refuses it when neither has one", () => {
    // weather.current, fuel.cheapest, and device.metric on a temperature.
    expect(supportsProgress(null, null)).toBe(false);
  });

  it("treats an absent descriptor as no", () => {
    expect(supportsProgress(undefined, undefined)).toBe(false);
  });

  it("counts zero as a value", () => {
    // A bar at 0 % is a measurement — Friday evening, nothing left of the
    // school week. `!sample` would have dropped it.
    expect(supportsProgress(0, null)).toBe(true);
    expect(supportsProgress(null, 0)).toBe(true);
  });
});
