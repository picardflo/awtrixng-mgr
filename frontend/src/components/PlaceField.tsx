/**
 * Pick a place by name.
 *
 * Asking someone for their latitude is asking them to go and look it up
 * somewhere else. The search does it for them; the exact coordinates stay
 * reachable for anyone who does have them.
 */

import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Place, PlaceValue } from "../api/client";
import { useI18n } from "../i18n";
import { Button, Input } from "./ui";

export function PlaceField({
  value,
  onChange,
  placeholder,
}: {
  value: PlaceValue | null;
  onChange: (value: PlaceValue | null) => void;
  placeholder?: string;
}) {
  const { t, locale } = useI18n();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [manual, setManual] = useState(false);
  const debounce = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(debounce.current);
    if (query.trim().length < 2) {
      setResults(null);
      return;
    }
    // Debounced, so typing "Bordeaux" is one request, not eight.
    debounce.current = window.setTimeout(() => {
      setFailed(false);
      api
        .searchPlaces(query, locale)
        .then(setResults)
        .catch(() => setFailed(true));
    }, 300);
    return () => window.clearTimeout(debounce.current);
  }, [query, locale]);

  if (value && !manual) {
    return (
      <div className="flex items-center gap-2">
        <div className="flex-1 truncate rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-sm">
          {value.name}
          <span className="ml-2 font-mono text-xs text-[var(--color-text-faint)]">
            {value.latitude.toFixed(4)}, {value.longitude.toFixed(4)}
          </span>
        </div>
        <Button
          type="button"
          className="shrink-0"
          onClick={() => {
            onChange(null);
            setQuery("");
          }}
        >
          {t("place.change")}
        </Button>
      </div>
    );
  }

  if (manual) {
    return (
      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="number"
            step="any"
            min={-90}
            max={90}
            value={value?.latitude ?? ""}
            aria-label={t("place.latitude")}
            placeholder={t("place.latitude")}
            onChange={(event) =>
              onChange({
                name: value?.name ?? t("place.custom"),
                latitude: Number(event.target.value),
                longitude: value?.longitude ?? 0,
              })
            }
          />
          <Input
            type="number"
            step="any"
            min={-180}
            max={180}
            value={value?.longitude ?? ""}
            aria-label={t("place.longitude")}
            placeholder={t("place.longitude")}
            onChange={(event) =>
              onChange({
                name: value?.name ?? t("place.custom"),
                latitude: value?.latitude ?? 0,
                longitude: Number(event.target.value),
              })
            }
          />
        </div>
        <button
          type="button"
          onClick={() => setManual(false)}
          className="text-xs text-[var(--color-text-muted)] underline-offset-2 hover:underline"
        >
          {t("place.backToSearch")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <Input
        value={query}
        placeholder={placeholder ?? t("place.search")}
        onChange={(event) => setQuery(event.target.value)}
        autoComplete="off"
      />

      {failed && (
        <p className="text-xs text-[var(--color-danger)]">{t("place.unavailable")}</p>
      )}
      {results?.length === 0 && (
        <p className="text-xs text-[var(--color-text-faint)]">{t("place.noResults")}</p>
      )}

      {results && results.length > 0 && (
        <ul className="max-h-48 overflow-y-auto rounded-lg border border-[var(--color-border)]">
          {results.map((place) => (
            <li key={`${place.latitude},${place.longitude}`}>
              <button
                type="button"
                onClick={() =>
                  onChange({
                    name: place.label,
                    latitude: place.latitude,
                    longitude: place.longitude,
                  })
                }
                className="flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left text-sm
                  transition hover:bg-[var(--color-surface-2)]"
              >
                <span className="truncate">{place.label}</span>
                <span className="shrink-0 font-mono text-[10px] text-[var(--color-text-faint)]">
                  {place.latitude.toFixed(2)}, {place.longitude.toFixed(2)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={() => setManual(true)}
        className="text-xs text-[var(--color-text-muted)] underline-offset-2 hover:underline"
      >
        {t("place.exact")}
      </button>
    </div>
  );
}
