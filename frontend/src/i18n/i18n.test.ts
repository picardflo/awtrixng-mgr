import { afterEach, describe, expect, it, vi } from "vitest";
import { detectLocale, interpolate, LOCALES } from "./index";
import { en } from "./messages.en";
import { fr } from "./messages.fr";

function stubBrowser(languages: string[], stored?: string) {
  vi.stubGlobal("navigator", { languages, language: languages[0] });
  vi.stubGlobal("window", {
    localStorage: {
      getItem: () => stored ?? null,
      setItem: () => {},
    },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("interpolate", () => {
  it("substitutes named placeholders", () => {
    expect(interpolate("firmware {v}.", { v: "0.98" })).toBe("firmware 0.98.");
  });

  it("substitutes the same placeholder twice", () => {
    expect(interpolate("{a} and {a}", { a: "x" })).toBe("x and x");
  });

  it("accepts numbers", () => {
    expect(interpolate("HTTP {status}", { status: 502 })).toBe("HTTP 502");
  });

  it("leaves a placeholder alone when no value is given", () => {
    expect(interpolate("hello {name}", {})).toBe("hello {name}");
  });

  it("returns the template untouched without params", () => {
    expect(interpolate("no placeholder")).toBe("no placeholder");
  });
});

describe("detectLocale", () => {
  it("prefers the stored choice over the browser", () => {
    stubBrowser(["en-US"], "fr");
    expect(detectLocale()).toBe("fr");
  });

  it("falls back to the browser preference", () => {
    stubBrowser(["fr-CA", "en"]);
    expect(detectLocale()).toBe("fr");
  });

  it("defaults to English for an unsupported language", () => {
    stubBrowser(["ja-JP"]);
    expect(detectLocale()).toBe("en");
  });

  it("ignores a stored value that is not a known locale", () => {
    stubBrowser(["de-DE"], "klingon");
    expect(detectLocale()).toBe("en");
  });

  it("survives blocked storage", () => {
    vi.stubGlobal("navigator", { languages: ["fr"], language: "fr" });
    vi.stubGlobal("window", {
      localStorage: {
        getItem: () => {
          throw new Error("blocked in private mode");
        },
        setItem: () => {},
      },
    });
    expect(detectLocale()).toBe("fr");
  });
});

describe("catalogues", () => {
  it("translates every key in every locale", () => {
    const keys = Object.keys(en);
    for (const [code, { messages }] of Object.entries(LOCALES)) {
      for (const key of keys) {
        expect(messages[key as keyof typeof en], `${code} is missing ${key}`).toBeTruthy();
      }
    }
  });

  it("keeps the same placeholders in every translation", () => {
    const placeholders = (text: string) =>
      [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

    for (const key of Object.keys(en) as (keyof typeof en)[]) {
      expect(placeholders(fr[key]), `placeholders differ for ${key}`).toEqual(
        placeholders(en[key]),
      );
    }
  });

  it("leaves no whole phrase untranslated", () => {
    // Single words often match across languages on purpose — "Port",
    // "Rotation", "Wi-Fi", "excellent" — so only multi-word phrases are
    // checked. Placeholders are excluded too: they hold examples, such as city
    // names, IP addresses or hex colours, which do not translate.
    const isPhrase = (text: string) => text.includes(" ") && text.length > 12;
    const untranslated = (Object.keys(en) as (keyof typeof en)[]).filter(
      (key) => !key.endsWith(".placeholder") && isPhrase(en[key]) && fr[key] === en[key],
    );
    expect(untranslated).toEqual([]);
  });
});
