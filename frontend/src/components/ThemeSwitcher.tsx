/**
 * Light ⇄ dark, beside the language picker.
 *
 * One button rather than three (light / dark / system): the third state is
 * what you get before touching it, and a control whose default value is also
 * one of its options reads as a question nobody asked. Following the system
 * is still reachable — it is what an installation does until someone clicks.
 */

import { useTheme } from "../theme/useTheme";
import { useI18n } from "../i18n";

export function ThemeSwitcher() {
  const { theme, toggle } = useTheme();
  const { t } = useI18n();
  // The button offers the *other* one, so the label names where it goes.
  const label = theme === "dark" ? t("theme.toLight") : t("theme.toDark");

  return (
    <button
      type="button"
      onClick={toggle}
      title={label}
      aria-label={label}
      className="flex h-7 w-7 items-center justify-center rounded-lg border
        border-[var(--color-border)] bg-[var(--color-surface)]
        text-[var(--color-text-muted)] transition
        hover:border-[var(--color-accent)] hover:text-[var(--color-text)]"
    >
      {theme === "dark" ? <Sun /> : <Moon />}
    </button>
  );
}

/* Drawn here rather than pulled from an icon set: two glyphs do not justify a
   dependency, and `currentColor` makes them follow the theme for free. */

function Sun() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function Moon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}
