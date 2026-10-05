import { describe, expect, it } from "vitest";
import cases from "./countdown-cases.json";
import { countdownText, daysUntil, renderMessage } from "./ReminderForm";

/** The preview computes the countdown itself so it can show it without asking
 *  the server. That means two implementations of one rule, and the only way
 *  that stays true is a table both suites read. The backend reads this same
 *  file in `test_reminders.py`.
 *
 *  It lives here rather than in a shared/ directory at the repository root:
 *  the frontend image builds with `frontend/` as its context, so an import
 *  reaching above it passes locally and fails the Docker build. */
describe("the preview agrees with the matrix", () => {
  for (const c of cases.cases) {
    for (const language of ["en", "fr"] as const) {
      it(`on ${c.today} in ${language} says ${c[language]}`, () => {
        // Local midnight, as a person reading a clock in their own timezone.
        const [y, m, d] = c.today.split("-").map(Number);
        const today = new Date(y, m - 1, d);

        expect(daysUntil(cases.target, today)).toBe(c.days);
        expect(countdownText(c.days, language)).toBe(c[language]);
        expect(
          renderMessage("PRET {{ countdown }}", cases.target, today, language),
        ).toBe(`PRET ${c[language]}`);
      });
    }
  }
});

describe("rendering a message", () => {
  const today = new Date(2026, 9, 3);

  it("leaves an unknown name empty rather than printing the braces", () => {
    expect(renderMessage("A {{ nope }} B", "2027-11-15", today)).toBe("A  B");
  });

  it("interpolates nothing when there is no target", () => {
    expect(renderMessage("DEBOUT {{ countdown }}", null, today)).toBe("DEBOUT ");
  });

  it("writes the date the French way", () => {
    expect(renderMessage("{{ date }}", "2027-11-15", today)).toBe("15/11/2027");
  });

  it("counts in days in French and in D-Days in English", () => {
    // "J-406" was hard-coded in an application whose default display language
    // is English, which is the mirror of the bug that prompted this.
    expect(countdownText(406, "fr")).toBe("J-406");
    expect(countdownText(406, "en")).toBe("D-406");
    expect(countdownText(0, "fr")).toBe("JOUR J");
    expect(countdownText(0, "en")).toBe("D-DAY");
  });

  it("survives a DST boundary", () => {
    // 28/03/2027 is the spring change in Paris: a naive hour-based diff
    // loses a day here, and the count is off by one for seven months.
    expect(
      renderMessage("{{ countdown }}", "2027-11-15", new Date(2027, 2, 28), "fr"),
    ).toBe("J-232");
  });
});
