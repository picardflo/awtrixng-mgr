/**
 * A window where a display is dimmed and its buzzer silenced.
 *
 * Kept by awtrixng-mgr, not by the clock: the firmware has no schedule of any
 * kind — only a manual brightness, one driven by the light sensor, and a deep
 * sleep that turns the matrix off entirely. Checked across the whole official
 * documentation before building this.
 *
 * Saving writes nothing to the display. The scheduler opens and closes the
 * window on its own pass, within a second of the change.
 */

import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { BedroomMode as Mode } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, Field, Input, Toggle } from "../../components/ui";
import { useI18n } from "../../i18n";

/** "22:00:00" -> "22:00", and back: the input works in minutes, the API in
 *  seconds. */
const toInput = (value: string) => value.slice(0, 5);
const toApi = (value: string) => `${value}:00`;

export function BedroomPanel({ deviceId }: { deviceId: number }) {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [draft, setDraft] = useState<Mode | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .bedroom(deviceId)
      .then(setDraft)
      .catch(() => setFailed(true));
  }, [deviceId]);

  if (failed) {
    return (
      <p className="text-xs text-[var(--color-text-faint)]">{t("common.unexpectedError")}</p>
    );
  }
  if (!draft) {
    return <p className="text-xs text-[var(--color-text-faint)]">{t("common.loading")}</p>;
  }

  const patch = (fields: Partial<Mode>) =>
    setDraft((previous) => (previous ? { ...previous, ...fields } : previous));

  const sameEnds = draft.start === draft.end;

  async function save() {
    if (!draft) return;
    setBusy(true);
    try {
      setDraft(await api.setBedroom(deviceId, draft));
      toast("success", t("device.bedroom.saved"));
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
    <div className="space-y-3">
      <p className="text-xs text-[var(--color-text-faint)]">{t("device.bedroom.help")}</p>

      <div className="flex items-center gap-3">
        <Toggle
          label={t("device.bedroom.enable")}
          checked={draft.enabled}
          onChange={(enabled) => patch({ enabled })}
        />
        {draft.active && (
          <span className="rounded-full border border-[var(--color-accent)]/40 bg-[var(--color-accent)]/10 px-2 py-0.5 text-[10px] text-[var(--color-accent)]">
            {t("device.bedroom.inEffect")}
          </span>
        )}
      </div>

      {draft.enabled && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("device.bedroom.from")}>
              <Input
                type="time"
                value={toInput(draft.start)}
                onChange={(event) => patch({ start: toApi(event.target.value) })}
              />
            </Field>
            <Field label={t("device.bedroom.to")} hint={t("device.bedroom.crossesMidnight")}>
              <Input
                type="time"
                value={toInput(draft.end)}
                onChange={(event) => patch({ end: toApi(event.target.value) })}
              />
            </Field>
          </div>

          {/* 0 is not "very dim": `setBrightness(0)` is exactly what the
              firmware's matrix-off state calls, and nothing clamps it. Read
              in the firmware source rather than assumed, and said here rather
              than hidden behind "low, not off". */}
          <Field
            label={
              draft.brightness === 0
                ? `${t("device.bedroom.brightness")} — ${t("device.bedroom.off")}`
                : `${t("device.bedroom.brightness")} — ${draft.brightness} / 255`
            }
            hint={
              draft.brightness === 0
                ? t("device.bedroom.offHint")
                : draft.brightness >= 2
                  ? t("device.bedroom.aboveTheFloor")
                  : t("device.bedroom.brightnessHint")
            }
          >
            <input
              type="range"
              min={0}
              max={40}
              value={Math.min(draft.brightness, 40)}
              onChange={(event) => patch({ brightness: Number(event.target.value) })}
              className="w-full accent-[var(--color-accent)]"
            />
          </Field>

          {sameEnds && (
            <p className="text-xs text-[var(--color-danger)]">
              {t("device.bedroom.sameEnds")}
            </p>
          )}
        </>
      )}

      <Button onClick={save} loading={busy} variant="primary" disabled={sameEnds && draft.enabled}>
        {t("device.settings.apply")}
      </Button>
    </div>
  );
}
