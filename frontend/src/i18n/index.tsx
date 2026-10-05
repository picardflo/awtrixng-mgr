/**
 * Minimal i18n layer.
 *
 * No dependency: the browser already provides the hard parts through `Intl`,
 * and the §13 brief is explicit about not turning the frontend into a
 * machine. What remains is a catalogue lookup plus interpolation.
 *
 * Adding a language means two things and nothing else:
 *   1. create `messages.<tag>.ts` typed `Record<MessageKey, string>`;
 *   2. add one entry to `LOCALES` below.
 * TypeScript then refuses to build until every key is translated.
 *
 * Plural forms are deliberately absent: no string needs them yet, and the
 * rules differ enough between languages that guessing an API now would be
 * worse than adding `Intl.PluralRules` alongside the first plural string.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { en } from "./messages.en";
import type { MessageKey } from "./messages.en";
import { fr } from "./messages.fr";

export const LOCALES = {
  en: { label: "English", messages: en as Record<MessageKey, string> },
  fr: { label: "Français", messages: fr },
} as const;

export type Locale = keyof typeof LOCALES;

/** English is the default: it is the project's published language. */
const DEFAULT_LOCALE: Locale = "en";
const STORAGE_KEY = "awtrixng-mgr.locale";

export type Params = Record<string, string | number | null | undefined>;

function isLocale(value: string): value is Locale {
  return value in LOCALES;
}

/** Stored choice, else the browser's preference, else English. Exported for tests. */
export function detectLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && isLocale(stored)) return stored;
  } catch {
    // Private browsing or blocked storage: fall through to detection.
  }

  const preferences = navigator.languages ?? [navigator.language];
  for (const tag of preferences) {
    const base = tag.split("-")[0].toLowerCase();
    if (isLocale(base)) return base;
  }
  return DEFAULT_LOCALE;
}

/** Exported for tests. */
export function interpolate(template: string, params?: Params): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined || value === null ? match : String(value);
  });
}

interface I18n {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  /** Translate a known key. */
  t: (key: MessageKey, params?: Params) => string;
  /**
   * Translate a code coming from the API.
   *
   * The backend sends a stable `code` plus an English `message`. Unknown codes
   * fall back to that message, so a backend newer than the frontend degrades
   * to readable English instead of showing a raw key.
   */
  tApi: (code: string, params: Params | undefined, fallback: string) => string;
}

const I18nContext = createContext<I18n | null>(null);

export function useI18n(): I18n {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside <I18nProvider>");
  return context;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(detectLocale);

  useEffect(() => {
    // Screen readers and hyphenation rely on this being correct.
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not persisting a language preference is not worth failing over.
    }
  }, []);

  const value = useMemo<I18n>(() => {
    const messages = LOCALES[locale].messages;

    const t = (key: MessageKey, params?: Params) =>
      interpolate(messages[key] ?? en[key] ?? key, params);

    const tApi = (code: string, params: Params | undefined, fallback: string) =>
      code in en ? t(code as MessageKey, params) : fallback;

    return { locale, setLocale, t, tApi };
  }, [locale, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
