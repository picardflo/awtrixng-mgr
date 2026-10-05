/**
 * The display's own settings: brightness, buzzer volume, rotation, formats.
 *
 * The AWTRIX web interface exposes none of these — only Network, MQTT, Time,
 * Icons and Auth — and the paid mobile apps that do are the reason this panel
 * exists at all.
 *
 * Unlike the built-in apps next door, **none of this needs a restart**: the
 * firmware applies these immediately.
 */

import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  DATE_ORDERS,
  DATE_SEPARATORS,
  TIME_SEPARATORS,
  TRANSITION_EFFECTS,
  YEAR_MODES,
} from "../../api/client";
import type { DeviceSettings, DeviceSettings as Settings } from "../../api/client";
import type { MessageKey } from "../../i18n/messages.en";
import { useToast } from "../../components/Toast";
import { Button, Field, Input, Toggle } from "../../components/ui";
import { useI18n } from "../../i18n";

const SELECT =
  "w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5 text-sm";

export function DeviceSettingsPanel({ deviceId }: { deviceId: number }) {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [current, setCurrent] = useState<Settings | null>(null);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .deviceSettings(deviceId)
      .then((settings) => {
        setCurrent(settings);
        setDraft(settings);
      })
      .catch(() => setFailed(true));
  }, [deviceId]);

  if (failed) {
    return (
      <p className="text-xs text-[var(--color-text-faint)]">
        {t("device.settingsUnavailable")}
      </p>
    );
  }
  if (!draft || !current) {
    return <p className="text-xs text-[var(--color-text-faint)]">{t("common.loading")}</p>;
  }

  const patch = (fields: Partial<Settings>) =>
    setDraft((previous) => (previous ? { ...previous, ...fields } : previous));

  const changed = (Object.keys(current) as (keyof Settings)[]).some(
    (key) => draft[key] !== current[key],
  );

  async function apply() {
    if (!draft) return;
    setBusy(true);
    try {
      const result = await api.setDeviceSettings(deviceId, draft);
      toast(result.ok ? "success" : "error", tApi(result.code, undefined, result.message));
      if (result.ok) {
        // What took effect, not what was asked: the firmware clamps, and a
        // form showing the request rather than the result is a form that lies.
        setCurrent(result.settings);
        setDraft(result.settings);
      }
    } catch (error) {
      toast(
        "error",
        error instanceof ApiError
          ? tApi(error.code, error.params, error.message)
          : t("common.unexpectedError"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <section className="space-y-2">
        <h4 className="text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
          {t("device.settings.brightness")}
        </h4>
        <Toggle
          label={t("device.settings.autoBrightness")}
          checked={draft.auto_brightness}
          onChange={(auto_brightness) => patch({ auto_brightness })}
        />
        {/* Disabled rather than hidden while the sensor drives it: a slider
            that silently does nothing is worse than one that says why.

            And renamed: with the sensor in charge this number is a *reading*
            taken when the panel opened, not a setting. Calling it "level"
            beside a slider says it is your choice, and it is already out of
            date by the time you look at it. */}
        <Field
          label={`${
            draft.auto_brightness
              ? t("device.settings.measured")
              : t("device.settings.level")
          } — ${draft.brightness} / 255`}
          hint={draft.auto_brightness ? t("device.settings.autoWins") : undefined}
        >
          <input
            type="range"
            min={0}
            max={255}
            value={draft.brightness}
            disabled={draft.auto_brightness}
            onChange={(event) => patch({ brightness: Number(event.target.value) })}
            className="w-full accent-[var(--color-accent)] disabled:opacity-40"
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label={t("device.settings.minBrightness")}
            hint={t("device.settings.minBrightnessHint")}
          >
            <Input
              type="number"
              min={0}
              max={draft.max_brightness}
              value={draft.min_brightness}
              onChange={(event) => patch({ min_brightness: Number(event.target.value) })}
            />
          </Field>
          <Field label={t("device.settings.maxBrightness")}>
            <Input
              type="number"
              min={draft.min_brightness}
              max={255}
              value={draft.max_brightness}
              onChange={(event) => patch({ max_brightness: Number(event.target.value) })}
            />
          </Field>
        </div>
      </section>

      <section className="space-y-2">
        <h4 className="text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
          {t("device.settings.sound")}
        </h4>
        <Toggle
          label={t("device.settings.soundEnabled")}
          hint={t("device.settings.soundEnabledHint")}
          checked={draft.sound_enabled}
          onChange={(sound_enabled) => patch({ sound_enabled })}
        />
        <Field
          label={`${t("device.settings.volume")} — ${draft.buzzer_volume} %`}
          hint={t("device.settings.volumeHint")}
        >
          <input
            type="range"
            min={0}
            max={100}
            value={draft.buzzer_volume}
            disabled={!draft.sound_enabled}
            onChange={(event) => patch({ buzzer_volume: Number(event.target.value) })}
            className="w-full accent-[var(--color-accent)] disabled:opacity-40"
          />
        </Field>
      </section>

      <section className="space-y-2">
        <h4 className="text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
          {t("device.settings.rotation")}
        </h4>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("device.settings.appSeconds")} hint={t("device.settings.appSecondsHint")}>
            <Input
              type="number"
              min={1}
              max={120}
              value={draft.app_seconds}
              onChange={(event) => patch({ app_seconds: Number(event.target.value) })}
            />
          </Field>
          <Field label={t("device.settings.transitionMs")} hint="ms">
            <Input
              type="number"
              min={0}
              max={5000}
              value={draft.transition_ms}
              onChange={(event) => patch({ transition_ms: Number(event.target.value) })}
            />
          </Field>
          <Field label={t("device.settings.effect")}>
            {/* NG names its twenty-two transitions and refuses anything else
                by listing them in the 422. AWTRIX 3 took an integer 0-10 it
                documented nowhere, so this field asked for a figure with
                nothing to go on. */}
            <select
              className={SELECT}
              value={draft.transition_effect}
              onChange={(event) => patch({ transition_effect: event.target.value })}
            >
              {TRANSITION_EFFECTS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("device.settings.scrollSpeed")} hint={t("device.settings.scrollHint")}>
            <Input
              type="number"
              min={1}
              max={200}
              value={draft.scroll_speed}
              onChange={(event) => patch({ scroll_speed: Number(event.target.value) })}
            />
          </Field>
        </div>
        <Toggle
          label={t("device.settings.autoTransition")}
          checked={draft.auto_transition}
          onChange={(auto_transition) => patch({ auto_transition })}
        />
      </section>

      <section className="space-y-2">
        <h4 className="text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
          {t("device.settings.formats")}
        </h4>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("device.settings.timeSeparator")}>
            <select
              className={SELECT}
              value={draft.time_separator}
              onChange={(event) =>
                patch({ time_separator: event.target.value as DeviceSettings["time_separator"] })
              }
            >
              {TIME_SEPARATORS.map((value) => (
                <option key={value} value={value}>
                  {t(`device.settings.timeSeparator.${value}` as MessageKey)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("device.settings.dateOrder")}>
            <select
              className={SELECT}
              value={draft.date_order}
              onChange={(event) =>
                patch({ date_order: event.target.value as DeviceSettings["date_order"] })
              }
            >
              {DATE_ORDERS.map((value) => (
                <option key={value} value={value}>
                  {t(`device.settings.dateOrder.${value}` as MessageKey)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("device.settings.dateSeparator")}>
            <select
              className={SELECT}
              value={draft.date_separator}
              onChange={(event) =>
                patch({
                  date_separator: event.target.value as DeviceSettings["date_separator"],
                })
              }
            >
              {DATE_SEPARATORS.map((value) => (
                <option key={value} value={value}>
                  {t(`device.settings.dateSeparator.${value}` as MessageKey)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("device.settings.dateYear")}>
            <select
              className={SELECT}
              value={draft.date_year}
              onChange={(event) =>
                patch({ date_year: event.target.value as DeviceSettings["date_year"] })
              }
            >
              {YEAR_MODES.map((value) => (
                <option key={value} value={value}>
                  {t(`device.settings.dateYear.${value}` as MessageKey)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        {/* Each label's key is the field's own name in camelCase, and a test
            checks it. Twice now a toggle has carried a label describing some
            other setting — "Semaine dès lundi" switching the weekday on —
            which compiles, reads correctly, and does the wrong thing. Deriving
            the key from the field is what makes that a failing test rather
            than something to spot by eye. */}
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          <Toggle
            label={t("device.settings.uppercase")}
            checked={draft.uppercase}
            onChange={(uppercase) => patch({ uppercase })}
          />
          <Toggle
            label={t("device.settings.celsius")}
            checked={draft.celsius}
            onChange={(celsius) => patch({ celsius })}
          />
          <Toggle
            label={t("device.settings.dateShowWeekday")}
            checked={draft.date_show_weekday}
            onChange={(date_show_weekday) => patch({ date_show_weekday })}
          />
          <Toggle
            label={t("device.settings.dateMonthNames")}
            checked={draft.date_month_names}
            onChange={(date_month_names) => patch({ date_month_names })}
          />
          <Toggle
            label={t("device.settings.weekdayBar")}
            checked={draft.weekday_bar}
            onChange={(weekday_bar) => patch({ weekday_bar })}
          />
          <Toggle
            label={t("device.settings.weekStartsMonday")}
            checked={draft.week_starts_monday}
            onChange={(week_starts_monday) => patch({ week_starts_monday })}
          />
        </div>
      </section>

      {changed && (
        <Button onClick={apply} loading={busy} variant="primary">
          {t("device.settings.apply")}
        </Button>
      )}
    </div>
  );
}
