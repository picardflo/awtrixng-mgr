/**
 * Browse the LaMetric gallery and pick an animated icon.
 *
 * Only animated icons are offered: on a 32x8 matrix a moving 8x8 icon carries
 * what a word cannot fit (ADR-007). The thumbnails are the real GIFs, served
 * by LaMetric, so what you see here is what the matrix will show.
 *
 * Nothing needs installing by hand — awtrixng-mgr copies the icon onto the device
 * the first time a widget uses it.
 */

import { useEffect, useRef, useState } from "react";
import { api, iconThumbnail } from "../api/client";
import type { Icon } from "../api/client";
import { useI18n } from "../i18n";
import { Button, Input } from "./ui";

export function IconPicker({
  value,
  onChange,
  autoIcon = null,
}: {
  value: string | null;
  onChange: (icon: string | null) => void;
  /** What the connector would pick on its own. Shown when nothing is chosen,
   *  because "no icon" in the box does not mean no icon on the matrix. */
  autoIcon?: string | null;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [icons, setIcons] = useState<Icon[] | null>(null);
  const [failed, setFailed] = useState(false);
  const debounce = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!open) return;
    window.clearTimeout(debounce.current);
    // The catalogue is searched server-side on every keystroke otherwise.
    debounce.current = window.setTimeout(() => {
      setFailed(false);
      api
        .searchIcons(query)
        .then(setIcons)
        .catch(() => setFailed(true));
    }, 250);
    return () => window.clearTimeout(debounce.current);
  }, [open, query]);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        {value || autoIcon ? (
          <img
            src={iconThumbnail(value ?? autoIcon!)}
            alt=""
            aria-hidden
            className="h-8 w-8 shrink-0 rounded border border-[var(--color-border)] bg-[var(--color-matrix-bg)]"
            style={{ imageRendering: "pixelated" }}
          />
        ) : (
          <div className="h-8 w-8 shrink-0 rounded border border-dashed border-[var(--color-border)]" />
        )}
        <Input
          value={value ?? ""}
          placeholder={autoIcon ? t("iconPicker.automatic") : t("iconPicker.none")}
          onChange={(event) => onChange(event.target.value || null)}
          aria-label={t("builder.icon")}
        />
        <Button type="button" onClick={() => setOpen(!open)} className="shrink-0">
          {open ? t("iconPicker.close") : t("iconPicker.browse")}
        </Button>
      </div>

      {open && (
        <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
          <Input
            value={query}
            autoFocus
            placeholder={t("iconPicker.search")}
            onChange={(event) => setQuery(event.target.value)}
          />

          {failed && (
            <p className="text-xs text-[var(--color-danger)]">
              {t("iconPicker.unavailable")}
            </p>
          )}
          {!failed && icons === null && (
            <p className="text-xs text-[var(--color-text-faint)]">{t("common.loading")}</p>
          )}
          {icons?.length === 0 && (
            <p className="text-xs text-[var(--color-text-faint)]">
              {t("iconPicker.noResults")}
            </p>
          )}

          {icons && icons.length > 0 && (
            <div className="grid max-h-64 grid-cols-6 gap-2 overflow-y-auto sm:grid-cols-8">
              {icons.map((icon) => (
                <button
                  key={icon.id}
                  type="button"
                  title={`${icon.title} · ${icon.id}`}
                  onClick={() => {
                    onChange(String(icon.id));
                    setOpen(false);
                  }}
                  className={`flex aspect-square items-center justify-center rounded border transition ${
                    value === String(icon.id)
                      ? "border-[var(--color-accent)] bg-[var(--color-accent)]/15"
                      : "border-[var(--color-border)] bg-[var(--color-matrix-bg)] hover:border-[var(--color-border-strong)]"
                  }`}
                >
                  <img
                    src={icon.thumbnail || iconThumbnail(icon.id)}
                    alt={icon.title}
                    className="h-6 w-6"
                    style={{ imageRendering: "pixelated" }}
                    loading="lazy"
                  />
                </button>
              ))}
            </div>
          )}

          <p className="text-xs text-[var(--color-text-faint)]">
            {t("iconPicker.autoInstall")}
          </p>
        </div>
      )}
    </div>
  );
}
