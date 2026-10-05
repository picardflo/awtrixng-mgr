/**
 * The language the clocks speak, which is not the one this page is in.
 *
 * They sit side by side on purpose. The distinction is real — a browser has a
 * reader to ask, a matrix pushed at three in the morning does not — but it is
 * invisible unless both choices are offered together. Switching the interface
 * to French and finding the clock still saying "Moderate" is exactly what
 * happened before this existed.
 */

import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AppSettings } from "../api/client";
import { useToast } from "./Toast";
import { useI18n } from "../i18n";

const CHOICES: { code: AppSettings["language"]; label: string }[] = [
  { code: "en", label: "English" },
  { code: "fr", label: "Français" },
];

export function ClockLanguage() {
  const { t, tApi, locale } = useI18n();
  const toast = useToast();
  const [language, setLanguage] = useState<AppSettings["language"] | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((settings) => setLanguage(settings.language))
      // Silent: a header control that cannot load must not shout. It simply
      // does not appear.
      .catch(() => setLanguage(null));
  }, []);

  if (!language) return null;

  async function choose(code: AppSettings["language"]) {
    const previous = language;
    setLanguage(code);
    try {
      await api.setSettings({ language: code });
      toast("success", t("settings.clockLanguageSaved"));
    } catch (error) {
      setLanguage(previous);
      toast(
        "error",
        error instanceof ApiError
          ? tApi(error.code, error.params, error.message)
          : t("common.unexpectedError"),
      );
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border
      border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
      <label className="flex items-center gap-2 text-sm">
        {t("settings.clockLanguage")}
        <select
          value={language}
          onChange={(event) => choose(event.target.value as AppSettings["language"])}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]
            px-2 py-1 text-sm focus:border-[var(--color-accent)] focus:outline-none"
        >
          {CHOICES.map(({ code, label }) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <p className="text-xs text-[var(--color-text-faint)]">
        {t("settings.clockLanguageHelp")}
      </p>
      {/* Said out loud when the two differ. Nothing announced it before, so a
          French interface sat quietly above clocks reading "MODERATE" and the
          setting looked broken rather than unset. */}
      {language !== locale && (
        <p className="w-full text-xs text-[var(--color-warning,var(--color-text-muted))]">
          {t("settings.clockLanguageDiffers")}
        </p>
      )}
    </div>
  );
}
