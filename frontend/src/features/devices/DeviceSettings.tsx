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
import { api, ApiError, DATE_FORMATS, TIME_FORMATS, TRANSITION_EFFECTS } from "../../api/client";
import type { DeviceSettings as Settings } from "../../api/client";
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
      </section>

      <section className="space-y-2">
        <h4 className="text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
          {t("device.settings.sound")}
        </h4>
        <Field
          label={`${t("device.settings.volume")} — ${draft.volume} / 30`}
          hint={t("device.settings.volumeHint")}
        >
          <input
            type="range"
            min={0}
            max={30}
            value={draft.volume}
            onChange={(event) => patch({ volume: Number(event.target.value) })}
            className="w-full accent-[var(--color-accent)]"
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
            {/* A named list, not a number. The firmware does name them — the
                official documentation lists all eleven — and this field asked
                for a figure between 0 and 10 with nothing to go on. */}
            <select
              className={SELECT}
              value={draft.transition_effect}
              onChange={(event) =>
                patch({ transition_effect: Number(event.target.value) })
              }
            >
              {TRANSITION_EFFECTS.map((name, code) => (
                <option key={name} value={code}>
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
        <p className="text-xs text-[var(--color-text-faint)]">
          {t("device.settings.formatsHint")}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("device.settings.timeFormat")}>
            <select
              className={SELECT}
              value={draft.time_format}
              onChange={(event) => patch({ time_format: event.target.value })}
            >
              {TIME_FORMATS.map((format) => (
                <option key={format} value={format}>
                  {format}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("device.settings.dateFormat")}>
            <select
              className={SELECT}
              value={draft.date_format}
              onChange={(event) => patch({ date_format: event.target.value })}
            >
              {DATE_FORMATS.map((format) => (
                <option key={format} value={format}>
                  {format}
                </option>
              ))}
            </select>
          </Field>
        </div>
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
            label={t("device.settings.mondayFirst")}
            checked={draft.week_starts_monday}
            onChange={(week_starts_monday) => patch({ week_starts_monday })}
          />
          <Toggle
            label={t("device.settings.showWeekday")}
            checked={draft.show_weekday}
            onChange={(show_weekday) => patch({ show_weekday })}
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
