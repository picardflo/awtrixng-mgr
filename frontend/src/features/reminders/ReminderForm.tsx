import { useState } from "react";
import { api, ApiError, iconThumbnail } from "../../api/client";
import type { Device, Reminder, ReminderInput } from "../../api/client";
import { AwtrixMatrixPreview, MATRIX_WIDTH } from "../../components/AwtrixMatrixPreview";
import { MatrixTextFields } from "../../components/MatrixTextFields";
import { IconPicker } from "../../components/IconPicker";
import { useToast } from "../../components/Toast";
import { Button, Card, Field, Input, Toggle } from "../../components/ui";
import { textWidth } from "../../components/pixelFont";
import { useI18n } from "../../i18n";
import { MELODIES, looksLikeRtttl } from "./melodies";

/** The language the clocks speak, which is not the interface's. */
export type ClockLanguage = "en" | "fr";

/** Whole days from today to `target`. Negative once it is past. */
export function daysUntil(target: string, today: Date): number {
  const [y, m, d] = target.split("-").map(Number);
  const midnight = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((Date.UTC(y, m - 1, d) - midnight) / 86_400_000);
}

/** What `{{ countdown }}` says. Mirrors `countdown_values()` on the backend.
 *
 *  Two implementations is a cost, but the preview exists to show what the
 *  clock will show, and printing the braces back at someone is exactly the
 *  near-miss this form has produced before. A test pins the two together.
 */
const COUNTDOWN = {
  en: { before: "D-", day: "D-DAY", after: "D+" },
  fr: { before: "J-", day: "JOUR J", after: "J+" },
} as const;

export function countdownText(days: number, language: ClockLanguage = "en"): string {
  const words = COUNTDOWN[language] ?? COUNTDOWN.en;
  if (days === 0) return words.day;
  return days > 0 ? `${words.before}${days}` : `${words.after}${-days}`;
}

/** Substitute what a reminder may interpolate. Unknown names render empty,
 *  as the backend's engine does. */
export function renderMessage(
  message: string,
  countdownTo: string | null,
  today: Date = new Date(),
  language: ClockLanguage = "en",
): string {
  let values: Record<string, string> = {};
  if (countdownTo) {
    const days = daysUntil(countdownTo, today);
    values = {
      countdown: countdownText(days, language),
      days: String(days),
      date: countdownTo.split("-").reverse().join("/"),
    };
  }
  return message.replace(/\{\{([^{}]*)\}\}/g, (_, expression) =>
    values[expression.split("|")[0].trim()] ?? "",
  );
}

/** Monday first, as the week is written here and as Python counts it. */
const DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

const DURATIONS = [5, 10, 15, 30] as const;
const CYCLES = [1, 2, 3, 4] as const;
const REPEATS = [0, 1, 2, 3] as const;
const INTERVALS = [1, 2, 3, 5] as const;

/** An existing reminder's settings, without what identifies it.
 *
 *  Dropped by name rather than by spreading and hoping: an `id` reaching a
 *  POST body is the kind of thing that works until the day it does not.
 */
export function settingsOf(source: Reminder): ReminderInput {
  const { id: _id, last_fired_at: _fired, next_at: _next, ...fields } = source;
  return { ...fields, at: source.at.slice(0, 5) + ":00" };
}

function blank(): ReminderInput {
  return {
    name: "",
    message: "",
    icon: null,
    color: null,
    // The presentation block, on the same defaults `MatrixText` gives a
    // widget: five rows, the display's own letter case, still when it fits.
    background: null,
    effect: null,
    overlay: null,
    icon_mode: "fixed",
    text_case: "inherit",
    font: "small",
    scroll_mode: "wrap",
    scroll_speed: 100,
    scroll_when_fits: "static",
    at: "07:30:00",
    days: [0, 1, 2, 3, 4],
    every_weeks: 1,
    anchor: null,
    on_date: null,
    countdown_to: null,
    duration_seconds: 10,
    repeat_count: 0,
    repeat_every_minutes: 2,
    melody: null,
    rings_at_night: false,
    enabled: true,
    device_ids: [],
  };
}

export function ReminderForm({
  reminder,
  seed,
  devices,
  onSaved,
  onCancel,
}: {
  reminder: Reminder | null;
  /** A reminder to copy the settings of. The form still *creates* one — only
   *  the fields are borrowed — so nothing rings until it is saved. A copy
   *  made straight into the list would ring at the same time tomorrow, before
   *  anyone had adjusted what they duplicated it to change. */
  seed?: Reminder | null;
  devices: Device[];
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [draft, setDraft] = useState<ReminderInput>(() => {
    if (reminder) return settingsOf(reminder);
    if (seed) return { ...settingsOf(seed), name: t("common.copyOf", { name: seed.name }) };
    return blank();
  });
  const [saving, setSaving] = useState(false);
  const [listening, setListening] = useState(false);
  const [advanced, setAdvanced] = useState(false);

  const patch = (fields: Partial<ReminderInput>) =>
    setDraft((current) => ({ ...current, ...fields }));

  function toggleDay(day: number) {
    const days = draft.days.includes(day)
      ? draft.days.filter((d) => d !== day)
      : [...draft.days, day].sort((a, b) => a - b);
    patch({ days });
  }

  function toggleDevice(id: number) {
    const device_ids = draft.device_ids.includes(id)
      ? draft.device_ids.filter((d) => d !== id)
      : [...draft.device_ids, id].sort((a, b) => a - b);
    patch({ device_ids });
  }

  /** Play it on a chosen clock, so composing does not mean saving first and
   *  ringing afterwards. */
  async function listen() {
    const target = draft.device_ids[0];
    if (!draft.melody || target === undefined) return;
    setListening(true);
    try {
      await api.notifyDevice(target, {
        text: "\u266a",
        duration: 3,
        wakeup: true,
        melody: draft.melody,
      });
    } catch (error) {
      toast(
        "error",
        error instanceof ApiError
          ? tApi(error.code, error.params, error.message)
          : t("common.unexpectedError"),
      );
    } finally {
      setListening(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      if (reminder) await api.updateReminder(reminder.id, draft);
      else await api.createReminder(draft);
      toast("success", t("reminders.saved", { name: draft.name }));
      onSaved();
    } catch (error) {
      toast(
        "error",
        error instanceof ApiError
          ? tApi(error.code, error.params, error.message)
          : t("common.unexpectedError"),
      );
    } finally {
      setSaving(false);
    }
  }

  // Same reckoning as the widget builder: an 8x8 icon costs 9 of the 32
  // columns, and past what is left AWTRIX scrolls. Worth knowing before
  // saving — a scrolling alert takes longer to read than it stays up.
  const shown =
    renderMessage(draft.message, draft.countdown_to) || t("reminders.messagePlaceholder");
  // Upper-cased before measuring, because that is what the clock draws: a
  // stock display shows capitals unless `text_case` says otherwise, and "ne
  // pas oublier" measured as typed fits where "NE PAS OUBLIER" does not.
  const drawn = draft.text_case === "asTyped" ? shown : shown.toUpperCase();
  const columnsFree = MATRIX_WIDTH - (draft.icon ? 9 : 0);
  const columnsUsed = textWidth(drawn);
  const willScroll = columnsUsed > columnsFree && draft.scroll_mode !== "static";

  // Empty days or no display would be refused by the server; saying so here
  // saves a round trip and explains why the button is dark.
  const ready =
    draft.name.trim() !== "" &&
    draft.message.trim() !== "" &&
    (draft.on_date !== null || draft.days.length > 0) &&
    draft.device_ids.length > 0;

  return (
    <Card className="p-4">
      <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("reminders.name")}>
              <Input
                value={draft.name}
                onChange={(e) => patch({ name: e.target.value })}
                placeholder={t("reminders.namePlaceholder")}
              />
            </Field>
            <Field label={t("reminders.at")}>
              <Input
                type="time"
                value={draft.at.slice(0, 5)}
                onChange={(e) => patch({ at: `${e.target.value}:00` })}
              />
            </Field>
          </div>

          <Field label={t("reminders.message")} hint={t("reminders.messageHint")}>
            <Input
              value={draft.message}
              onChange={(e) => patch({ message: e.target.value })}
              placeholder={t("reminders.messagePlaceholder")}
            />
          </Field>

          <Field label={t("reminders.when")}>
            <div className="flex gap-1">
              {(["weekly", "once"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() =>
                    patch({
                      on_date:
                        mode === "once"
                          ? (draft.on_date ?? new Date().toISOString().slice(0, 10))
                          : null,
                    })
                  }
                  className={`rounded-lg border px-2.5 py-1 text-xs transition ${
                    (draft.on_date !== null) === (mode === "once")
                      ? "border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                      : "border-[var(--color-border)] text-[var(--color-text-muted)]"
                  }`}
                >
                  {t(`reminders.${mode}` as never)}
                </button>
              ))}
            </div>
          </Field>

          {draft.on_date !== null ? (
            <Field label={t("reminders.onDate")} hint={t("reminders.onDateHint")}>
              <Input
                type="date"
                value={draft.on_date}
                onChange={(e) =>
                  // Clearing the field would smuggle the reminder back into
                  // weekly mode without the buttons saying so.
                  patch({ on_date: e.target.value || draft.on_date })
                }
              />
            </Field>
          ) : (
            <>
              <Field label={t("reminders.days")}>
                <div className="flex flex-wrap gap-1">
                  {DAY_KEYS.map((key, day) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => toggleDay(day)}
                      className={`rounded-lg border px-2.5 py-1 text-xs transition ${
                        draft.days.includes(day)
                          ? "border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                          : "border-[var(--color-border)] text-[var(--color-text-muted)]"
                      }`}
                    >
                      {t(`day.${key}` as never)}
                    </button>
                  ))}
                </div>
              </Field>

              <div className="grid gap-3 sm:grid-cols-2">
                <Field label={t("reminders.cycle")}>
                  <select
                    value={draft.every_weeks}
                    onChange={(e) => patch({ every_weeks: Number(e.target.value) })}
                    className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5 text-sm"
                  >
                    {CYCLES.map((n) => (
                      <option key={n} value={n}>
                        {n === 1 ? t("reminders.everyWeek") : t("reminders.everyNWeeks", { n })}
                      </option>
                    ))}
                  </select>
                </Field>
                {draft.every_weeks > 1 && (
                  <Field label={t("reminders.anchor")} hint={t("reminders.anchorHint")}>
                    <Input
                      type="date"
                      value={draft.anchor ?? ""}
                      onChange={(e) => patch({ anchor: e.target.value || null })}
                    />
                  </Field>
                )}
              </div>
            </>
          )}

          <Field label="" hint={t("reminders.countdownHint")}>
            <div className="flex items-center gap-2">
              <Toggle
                label={t("reminders.countdown")}
                checked={draft.countdown_to !== null}
                onChange={(on) =>
                  patch({
                    countdown_to: on
                      ? (draft.countdown_to ?? new Date().toISOString().slice(0, 10))
                      : null,
                  })
                }
              />
              {draft.countdown_to !== null && (
                <Input
                  type="date"
                  value={draft.countdown_to}
                  onChange={(e) =>
                    patch({ countdown_to: e.target.value || draft.countdown_to })
                  }
                />
              )}
            </div>
          </Field>

          <Field label={t("reminders.devices")}>
            <div className="flex flex-wrap gap-1">
              {devices.map((device) => (
                <button
                  key={device.id}
                  type="button"
                  onClick={() => toggleDevice(device.id)}
                  className={`rounded-lg border px-2.5 py-1 text-xs transition ${
                    draft.device_ids.includes(device.id)
                      ? "border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                      : "border-[var(--color-border)] text-[var(--color-text-muted)]"
                  }`}
                >
                  {device.name}
                </button>
              ))}
            </div>
          </Field>

          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <Field label={t("builder.icon")} hint={t("reminders.iconHint")}>
              <IconPicker value={draft.icon} onChange={(icon) => patch({ icon })} />
            </Field>
            <Field label={t("builder.color")}>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={draft.color ?? "#3ddc84"}
                  onChange={(e) => patch({ color: e.target.value })}
                  className="h-8 w-10 shrink-0 cursor-pointer rounded border border-[var(--color-border)] bg-transparent"
                />
                <Input
                  value={draft.color ?? ""}
                  placeholder="#3ddc84"
                  onChange={(e) => patch({ color: e.target.value || null })}
                />
              </div>
            </Field>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <Field label={t("reminders.duration")}>
              <select
                value={draft.duration_seconds}
                onChange={(e) => patch({ duration_seconds: Number(e.target.value) })}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5 text-sm"
              >
                {DURATIONS.map((n) => (
                  <option key={n} value={n}>
                    {n} s
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("reminders.repeat")}>
              <select
                value={draft.repeat_count}
                onChange={(e) => patch({ repeat_count: Number(e.target.value) })}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5 text-sm"
              >
                {REPEATS.map((n) => (
                  <option key={n} value={n}>
                    {n === 0 ? t("reminders.repeatNone") : t("reminders.repeatTimes", { n })}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("reminders.every")}>
              <select
                value={draft.repeat_every_minutes}
                disabled={draft.repeat_count === 0}
                onChange={(e) => patch({ repeat_every_minutes: Number(e.target.value) })}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5 text-sm disabled:opacity-50"
              >
                {INTERVALS.map((n) => (
                  <option key={n} value={n}>
                    {n} min
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {/* The same block the widget builder offers, minus the options a
              reminder has no use for: it carries no data, so no progress bar
              and nothing to hide when a service returns none. */}
          <button
            type="button"
            onClick={() => setAdvanced(!advanced)}
            className="text-xs text-[var(--color-text-muted)] underline-offset-2 hover:underline"
          >
            {advanced ? "▾" : "▸"} {t("builder.advanced")}
          </button>

          {advanced && (
            <div className="space-y-4 rounded-lg bg-[var(--color-surface-2)] p-3">
              {/* The same block the widget builder shows, from the same
                  component: a reminder had three of these and a widget ten,
                  and nobody could say why the font was among the missing. */}
              <MatrixTextFields value={draft} onChange={patch} />
            </div>
          )}

          <Field label={t("reminders.melody")} hint={t("reminders.melodyHint")}>
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2">
                <select
                  value={
                    MELODIES.find((m) => m.rtttl === draft.melody)?.id ?? ""
                  }
                  onChange={(e) =>
                    patch({
                      melody:
                        MELODIES.find((m) => m.id === e.target.value)?.rtttl ?? null,
                    })
                  }
                  className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5 text-sm"
                >
                  <option value="">{t("reminders.melodyNone")}</option>
                  {MELODIES.map((melody) => (
                    <option key={melody.id} value={melody.id}>
                      {t(`melody.${melody.id}` as never)}
                    </option>
                  ))}
                </select>
                <Button
                  onClick={listen}
                  loading={listening}
                  disabled={!draft.melody || draft.device_ids.length === 0}
                >
                  {t("reminders.listen")}
                </Button>
              </div>
              <Input
                value={draft.melody ?? ""}
                onChange={(e) => patch({ melody: e.target.value || null })}
                placeholder="alert:d=4,o=5,b=120:c,e,g"
              />
              {/* A typo is swallowed in silence by the firmware, which is the
                  worst way to find out. */}
              {draft.melody && !looksLikeRtttl(draft.melody) && (
                <p className="text-xs text-[var(--color-warning,#f5a524)]">
                  {t("reminders.melodyInvalid")}
                </p>
              )}
            </div>
          </Field>

          {/* Beside the melody, because it is only about the melody: the
              reminder still appears on a dimmed display, it simply makes no
              sound unless this is ticked. */}
          {draft.melody && (
            <Toggle
              label={t("reminders.ringsAtNight")}
              hint={t("reminders.ringsAtNightHint")}
              checked={draft.rings_at_night}
              onChange={(rings_at_night) => patch({ rings_at_night })}
            />
          )}
        </div>

        <div className="space-y-3 lg:w-72">
          <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-faint)]">
            {t("builder.livePreview")}
          </p>
          <div className="flex justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-matrix-bg)] p-2">
            <AwtrixMatrixPreview
              text={drawn}
              icon={draft.icon}
              // Both are needed: `icon` only reserves the 8x8 slot, and
              // without the image the preview draws a checker to show where it
              // will go. Only a numeric id has a gallery image — a file name
              // typed by hand lives on the clock and nowhere we can fetch.
              iconUrl={
                draft.icon && /^\d+$/.test(draft.icon)
                  ? iconThumbnail(draft.icon)
                  : null
              }
              color={draft.color || "#3ddc84"}
              background={draft.background}
              font={draft.font}
              noScroll={draft.scroll_mode === "static"}
              scrollSpeed={draft.scroll_speed}
              scale={7}
            />
          </div>

          <p className="text-center text-xs text-[var(--color-text-faint)]">
            <span className="font-mono">
              {columnsUsed}/{columnsFree}
            </span>
          </p>

          {willScroll && (
            <p className="rounded-lg border border-[var(--color-info)]/30 bg-[var(--color-info)]/10 px-2 py-1.5 text-xs text-[var(--color-info)]">
              {t("builder.willScroll")}
            </p>
          )}
          <div className="flex gap-2">
            <Button variant="primary" onClick={save} loading={saving} disabled={!ready}>
              {reminder ? t("builder.update") : t("reminders.create")}
            </Button>
            <Button onClick={onCancel}>{t("common.cancel")}</Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
