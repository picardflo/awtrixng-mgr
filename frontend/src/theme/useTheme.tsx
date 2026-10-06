/**
 * Light or dark, remembered.
 *
 * The attribute goes on `<html>`, which is where `tokens.css` looks for it —
 * the same mechanism AWTRIX NG's own interface uses (`:root[data-theme=…]`),
 * so the two switch the same way.
 *
 * **No choice is a choice too.** Until someone picks one, the page follows
 * the operating system, and keeps following it: an installation left alone
 * goes light in the morning and dark at night without anyone asking. Picking
 * one pins it, and that is what is stored — "light" or "dark", never "auto
 * resolved to dark on the evening it was clicked".
 *
 * The first paint is handled in `index.html`, not here: React runs after the
 * browser has drawn, so a dark page would flash white before this ever ran.
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

export type Theme = "light" | "dark";
/** What is stored. `null` means "follow the system", which is the default. */
export type ThemeChoice = Theme | null;

const STORAGE_KEY = "awtrixng-mgr.theme";

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function storedChoice(): ThemeChoice {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === "light" || saved === "dark" ? saved : null;
  } catch {
    // Private browsing refuses localStorage outright. Following the system is
    // a perfectly good fallback, and better than a blank screen.
    return null;
  }
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

interface ThemeApi {
  /** What is on screen now. */
  theme: Theme;
  /** What was chosen, or null while following the system. */
  choice: ThemeChoice;
  setChoice: (choice: ThemeChoice) => void;
  /** Light ⇄ dark. Pins the result, so a toggle always toggles. */
  toggle: () => void;
}

const Context = createContext<ThemeApi | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setStored] = useState<ThemeChoice>(storedChoice);
  const [system, setSystem] = useState<Theme>(systemTheme);
  const theme = choice ?? system;

  // Only while nothing is pinned. A listener left running would be harmless
  // but misleading: it would look as though the system still had a say.
  useEffect(() => {
    if (choice !== null) return;
    const query = window.matchMedia?.("(prefers-color-scheme: light)");
    if (!query) return;
    const onChange = () => setSystem(systemTheme());
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [choice]);

  useEffect(() => apply(theme), [theme]);

  const setChoice = useCallback((next: ThemeChoice) => {
    setStored(next);
    try {
      if (next === null) localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not stored is not broken: the page still switches for this visit.
    }
  }, []);

  const toggle = useCallback(() => {
    setStored((current) => {
      const next: Theme = (current ?? systemTheme()) === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* see above */
      }
      return next;
    });
  }, []);

  return (
    <Context.Provider value={{ theme, choice, setChoice, toggle }}>
      {children}
    </Context.Provider>
  );
}

export function useTheme(): ThemeApi {
  const api = useContext(Context);
  if (!api) throw new Error("useTheme outside ThemeProvider");
  return api;
}
