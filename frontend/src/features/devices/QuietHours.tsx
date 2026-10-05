/**
 * A window of the day where this display's reminders ring without a melody.
 *
 * **It used to dim the display as well, and no longer does.** That was its
 * reason to exist on AWTRIX 3, whose automatic brightness clamped at 2 — too
 * bright for a bedroom, and the floor could not be changed. So the window
 * turned the sensor off, forced a lower level, remembered what it had
 * overwritten and restored it at dawn.
 *
 * NG makes `minBrightness` a setting, which now lives in the clock's own
 * settings panel. It reads the room rather than the hour, so it dims when
 * someone actually goes to bed — which a window fixed at 22:00 cannot know.
 *
 * What is left is the half a light sensor cannot do, because silence is a
 * matter of time. Saving writes nothing to the display: there is nothing to
 * write, and nothing to be left behind if this application stops.
 */

import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { QuietHours as Mode } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, Field, Input, Toggle } from "../../components/ui";
import { useI18n } from "../../i18n";

/** "22:00:00" -> "22:00", and back: the input works in minutes, the API in
 *  seconds. */
const toInput = (value: string) => value.slice(0, 5);
const toApi = (value: string) => `${value}:00`;

export function QuietHoursPanel({ deviceId }: { deviceId: number }) {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [draft, setDraft] = useState<Mode | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .quietHours(deviceId)
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
      setDraft(await api.setQuietHours(deviceId, draft));
      toast("success", t("device.quietHours.saved"));
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
      <p className="text-xs text-[var(--color-text-faint)]">{t("device.quietHours.help")}</p>

      <Toggle
        label={t("device.quietHours.enable")}
        checked={draft.enabled}
        onChange={(enabled) => patch({ enabled })}
      />

      {draft.enabled && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("device.quietHours.from")}>
              <Input
                type="time"
                value={toInput(draft.start)}
                onChange={(event) => patch({ start: toApi(event.target.value) })}
              />
            </Field>
            <Field label={t("device.quietHours.to")} hint={t("device.quietHours.crossesMidnight")}>
              <Input
                type="time"
                value={toInput(draft.end)}
                onChange={(event) => patch({ end: toApi(event.target.value) })}
              />
            </Field>
          </div>

          {sameEnds && (
            <p className="text-xs text-[var(--color-danger)]">
              {t("device.quietHours.sameEnds")}
            </p>
          )}

          {/* Where the dimming went. Said here rather than left for someone to
              discover the feature is missing. */}
          <p className="text-xs text-[var(--color-text-faint)]">
            {t("device.quietHours.dimmingMoved")}
          </p>
        </>
      )}

      <Button onClick={save} loading={busy} disabled={draft.enabled && sameEnds}>
        {t("device.settings.apply")}
      </Button>
    </div>
  );
}
