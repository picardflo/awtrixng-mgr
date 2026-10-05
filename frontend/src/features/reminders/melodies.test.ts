import { describe, expect, it } from "vitest";
import { MELODIES, looksLikeRtttl } from "./melodies";

describe("melodies", () => {
  it("ships melodies that pass its own check", () => {
    for (const melody of MELODIES) {
      expect(looksLikeRtttl(melody.rtttl), melody.id).toBe(true);
    }
  });

  it("gives each one its own id and tune", () => {
    expect(new Set(MELODIES.map((m) => m.id)).size).toBe(MELODIES.length);
    expect(new Set(MELODIES.map((m) => m.rtttl)).size).toBe(MELODIES.length);
  });

  it("keeps them short, which is the whole point", () => {
    // A phone ringtone runs to hundreds of characters; a reminder should not.
    for (const melody of MELODIES) {
      expect(melody.rtttl.length, melody.id).toBeLessThan(60);
    }
  });
});

describe("looksLikeRtttl", () => {
  it("accepts a well-formed tune", () => {
    expect(looksLikeRtttl("x:d=4,o=5,b=120:c,e,g")).toBe(true);
    expect(looksLikeRtttl("x:d=16,o=7,b=160:8c#6,p,4a.")).toBe(true);
  });

  it("refuses what is plainly not one", () => {
    expect(looksLikeRtttl("")).toBe(false);
    expect(looksLikeRtttl("no colons at all")).toBe(false);
    expect(looksLikeRtttl(":d=4,o=5,b=120:c")).toBe(false); // nameless
    expect(looksLikeRtttl("x:tempo=120:c")).toBe(false);
    expect(looksLikeRtttl("x:d=4,o=5,b=120:h")).toBe(false); // no note H
  });
});
