import { LOCALES, useI18n } from "../i18n";
import type { Locale } from "../i18n";

export function LocaleSwitcher() {
  const { locale, setLocale, t } = useI18n();

  return (
    <label className="flex items-center gap-1.5">
      <span className="sr-only">{t("common.language")}</span>
      <select
        value={locale}
        onChange={(event) => setLocale(event.target.value as Locale)}
        aria-label={t("common.language")}
        className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]
          px-2 py-1 text-xs text-[var(--color-text-muted)]
          hover:text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none"
      >
        {Object.entries(LOCALES).map(([code, { label }]) => (
          <option key={code} value={code}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}
