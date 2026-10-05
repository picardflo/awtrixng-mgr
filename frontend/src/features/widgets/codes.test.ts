import { describe, expect, it } from "vitest";
import { untranslatedCodes } from "./WidgetBuilder";

/** A clock showing LOW under a French interface, for an hour of diagnosis.
 *
 *  Nothing was broken: the template asked for `level_code`, which is the
 *  untranslated identifier and exists precisely so that a comparison keeps
 *  working whatever the language. But it sits beside `level` in the variable
 *  list, "code" reads as "the code for the level", and nothing said which was
 *  which at the point of choosing.
 */
const AIR = ["aqi", "quality", "quality_code", "pm2_5", "pm10"];
const UV = ["uv", "level", "level_code"];

describe("untranslatedCodes", () => {
  it("catches the one that cost an hour", () => {
    expect(untranslatedCodes("UV {{ uv | round }} - {{ level_code }}", UV)).toEqual([
      "level_code",
    ]);
  });

  it("says nothing when the words are used", () => {
    expect(untranslatedCodes("UV {{ uv }} {{ level }}", UV)).toEqual([]);
  });

  it("finds several at once", () => {
    const text = "{{ quality_code }} {{ pm10 }}";
    expect(untranslatedCodes(text, AIR)).toEqual(["quality_code"]);
  });

  it("ignores a code with no translated twin", () => {
    // `event_code` on a widget that offers no `event` would be the only way
    // to say it, so warning would be wrong.
    expect(untranslatedCodes("{{ event_code }}", ["event_code", "next"])).toEqual([]);
  });

  it("sees through a filter", () => {
    expect(untranslatedCodes("{{ level_code | upper }}", UV)).toEqual(["level_code"]);
  });

  it("does not warn twice for the same variable", () => {
    expect(untranslatedCodes("{{ level_code }} {{ level_code }}", UV)).toEqual([
      "level_code",
    ]);
  });

  it("is quiet on a template with no variables", () => {
    expect(untranslatedCodes("DEBOUT", UV)).toEqual([]);
  });

  it("is quiet when the widget declares nothing", () => {
    expect(untranslatedCodes("{{ level_code }}", [])).toEqual([]);
  });
});
