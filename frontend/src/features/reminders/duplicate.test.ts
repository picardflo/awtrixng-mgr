import { describe, expect, it } from "vitest";
import { settingsOf } from "./ReminderForm";
import type { Reminder } from "../../api/client";

const SOURCE: Reminder = {
  id: 7,
  name: "Poubelles noires",
  message: "NOIRES",
  icon: "1901",
  color: null,
  at: "19:45:00",
  days: [6],
  every_weeks: 1,
  anchor: "2026-10-11",
  on_date: null,
  countdown_to: null,
  duration_seconds: 15,
  // The presentation block. Not all on their defaults on purpose: a copy
  // that quietly reset the font would be exactly the kind of loss this test
  // is here to catch.
  background: null,
  effect: "TwinklingStars",
  overlay: null,
  icon_mode: "push",
  text_case: "asTyped",
  font: "large",
  scroll_mode: "wrap",
  scroll_speed: 100,
  scroll_when_fits: "scroll",
  repeat_count: 1,
  repeat_every_minutes: 3,
  melody: "bip:d=16,o=6,b=140:c,p,c",
  rings_at_night: false,
  enabled: true,
  device_ids: [2],
  last_fired_at: "2026-09-27T17:45:00Z",
  next_at: "2026-10-04T17:45:00Z",
};

/** Duplicating opens the form on a copy rather than creating one outright.
 *
 *  What the copy must not carry is identity: an `id` reaching a POST body is
 *  the kind of thing that works until the day it does not, and `last_fired_at`
 *  would make a brand-new reminder claim it had already rung.
 */
describe("settingsOf", () => {
  it("drops what identifies the original", () => {
    const copy = settingsOf(SOURCE);
    expect(copy).not.toHaveProperty("id");
    expect(copy).not.toHaveProperty("last_fired_at");
    expect(copy).not.toHaveProperty("next_at");
  });

  it("keeps everything someone would otherwise retype", () => {
    const copy = settingsOf(SOURCE);
    expect(copy.message).toBe("NOIRES");
    expect(copy.days).toEqual([6]);
    expect(copy.every_weeks).toBe(1);
    expect(copy.anchor).toBe("2026-10-11");
    expect(copy.melody).toBe("bip:d=16,o=6,b=140:c,p,c");
    expect(copy.repeat_count).toBe(1);
    expect(copy.icon).toBe("1901");
  });

  it("carries whether it rings through bedroom mode", () => {
    // A copy of an alarm must still be an alarm: losing this quietly turns a
    // duplicated wake-up into one that never makes a sound.
    expect(settingsOf({ ...SOURCE, rings_at_night: true }).rings_at_night).toBe(true);
  });

  it("keeps the displays it rings on", () => {
    // Forgetting these makes a duplicate that rings nowhere, and the list
    // says "0 displays" in small grey text nobody reads.
    expect(settingsOf(SOURCE).device_ids).toEqual([2]);
  });

  it("carries the one-off date and the countdown", () => {
    const dated = { ...SOURCE, on_date: "2027-03-15", countdown_to: "2027-11-15" };
    const copy = settingsOf(dated);
    expect(copy.on_date).toBe("2027-03-15");
    expect(copy.countdown_to).toBe("2027-11-15");
  });

  it("normalises the time the way the form expects it", () => {
    // The time input works in HH:MM and the API in HH:MM:SS.
    expect(settingsOf({ ...SOURCE, at: "07:30:00" }).at).toBe("07:30:00");
  });
});
