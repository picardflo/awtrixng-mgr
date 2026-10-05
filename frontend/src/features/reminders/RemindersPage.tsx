import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Device, Reminder } from "../../api/client";
import { useToast } from "../../components/Toast";
import { CardIcon } from "../../components/CardIcon";
import { Button, Card, EmptyState, StatusBadge } from "../../components/ui";
import { useI18n } from "../../i18n";
import { ReminderForm, renderMessage } from "./ReminderForm";

const DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

export function RemindersPage() {
  const { t, tApi, locale } = useI18n();
  const toast = useToast();
  const [reminders, setReminders] = useState<Reminder[] | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  // `seed` is a reminder to copy the settings of while still creating a new
  // one. Kept apart from `reminder` on purpose: that field is what the form
  // reads to decide between PATCH and POST, and a copy must never PATCH the
  // thing it was copied from.
  const [editing, setEditing] = useState<{
    reminder: Reminder | null;
    seed?: Reminder;
  } | null>(null);
  const [ringing, setRinging] = useState<number | null>(null);
  const formRef = useRef<HTMLDivElement>(null);

  // The form opens above the list. Editing a reminder near the bottom would
  // otherwise look like nothing happened — the same oversight the widget
  // builder had, and the reason this is now checked on every such page.
  useEffect(() => {
    if (editing) formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [editing]);

  function fail(error: unknown) {
    toast(
      "error",
      error instanceof ApiError
        ? tApi(error.code, error.params, error.message)
        : t("common.unexpectedError"),
    );
  }

  async function load() {
    try {
      const [list, clocks] = await Promise.all([api.listReminders(), api.listDevices()]);
      setReminders(list);
      setDevices(clocks);
    } catch (error) {
      fail(error);
      setReminders([]);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function ring(reminder: Reminder) {
    setRinging(reminder.id);
    try {
      const result = await api.fireReminder(reminder.id);
      toast(
        result.ok ? "success" : "error",
        tApi(result.code, result.params, result.message),
      );
    } catch (error) {
      fail(error);
    } finally {
      setRinging(null);
    }
  }

  async function remove(reminder: Reminder) {
    if (!confirm(t("reminders.confirmDelete", { name: reminder.name }))) return;
    try {
      await api.deleteReminder(reminder.id);
      toast("success", t("reminders.deleted", { name: reminder.name }));
      void load();
    } catch (error) {
      fail(error);
    }
  }

  async function toggle(reminder: Reminder) {
    try {
      await api.updateReminder(reminder.id, { enabled: !reminder.enabled });
      void load();
    } catch (error) {
      fail(error);
    }
  }

  /** "Wed 18:00" is enough for a weekly reminder and misleading for any
   *  other: a fortnightly one can be eleven days away and still read as the
   *  Wednesday that is coming. The date appears as soon as the next ring is
   *  not within the week. */
  function nextLabel(reminder: Reminder): string {
    if (!reminder.enabled || !reminder.next_at) return t("reminders.never");
    const at = new Date(reminder.next_at);
    const withinTheWeek = at.getTime() - Date.now() < 7 * 24 * 3600 * 1000;
    return at.toLocaleString(locale, {
      weekday: "short",
      ...(withinTheWeek ? {} : { day: "2-digit", month: "2-digit" }),
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  if (reminders === null) return null;

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium">{t("reminders.title")}</h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            {t("reminders.subtitle")}
          </p>
        </div>
        {!editing && devices.length > 0 && reminders.length > 0 && (
          <Button variant="primary" onClick={() => setEditing({ reminder: null })}>
            + {t("reminders.add")}
          </Button>
        )}
      </header>

      {editing && (
        <div ref={formRef}>
          <ReminderForm
          // Remounted per reminder: without this the form keeps the previous
          // one's fields and writes them into the next. The copied id is part
          // of the key too — otherwise duplicating one reminder and then
          // another both read "new", and the second form would open on the
          // first one's settings.
          key={
            editing.reminder?.id ??
            (editing.seed ? `copy-${editing.seed.id}` : "new")
          }
          reminder={editing.reminder}
          seed={editing.seed}
          devices={devices}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
            onCancel={() => setEditing(null)}
          />
        </div>
      )}

      {reminders.length === 0 && !editing && (
        <EmptyState
          title={t("reminders.empty")}
          description={t("reminders.emptyBody")}
          action={
            devices.length === 0 ? (
              <p className="text-sm text-[var(--color-text-muted)]">
                {t("reminders.needsDevice")}
              </p>
            ) : (
              <Button variant="primary" onClick={() => setEditing({ reminder: null })}>
                + {t("reminders.add")}
              </Button>
            )
          }
        />
      )}

      {reminders.map((reminder) => (
        <Card key={reminder.id} className="overflow-hidden">
          <div className="flex flex-wrap items-start justify-between gap-3 p-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <CardIcon icon={reminder.icon} />
                <h3 className="truncate font-medium">{reminder.name}</h3>
                <span className="font-mono text-sm text-[var(--color-accent)]">
                  {reminder.at.slice(0, 5)}
                </span>
                {!reminder.enabled && (
                  <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] uppercase text-[var(--color-text-faint)]">
                    {t("status.disabled")}
                  </span>
                )}
                {reminder.device_ids.length > 0 && (
                  <span className="text-xs text-[var(--color-text-faint)]">
                    {t("reminders.onDisplays", {
                      count: reminder.device_ids.length,
                    })}
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                {/* What the clock will say, not what was typed: a countdown
                    reading "PRET {{ countdown }}" in the list tells nobody
                    how long is left. */}
                {renderMessage(reminder.message, reminder.countdown_to)}
              </p>
              <p className="mt-1 flex flex-wrap gap-1 text-[10px] text-[var(--color-text-faint)]">
                {reminder.on_date ? (
                  <span className="text-[var(--color-text)]">
                    {new Date(`${reminder.on_date}T00:00:00`).toLocaleDateString(locale, {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })}
                  </span>
                ) : (
                  DAY_KEYS.map((key, day) => (
                    <span
                      key={key}
                      className={
                        reminder.days.includes(day)
                          ? "text-[var(--color-text)]"
                          : "opacity-30"
                      }
                    >
                      {t(`day.${key}` as never)}
                    </span>
                  ))
                )}
                <span className="ml-2">
                  {!reminder.on_date &&
                    reminder.every_weeks > 1 &&
                    `· ${t("reminders.everyNWeeks", { n: reminder.every_weeks })} `}
                  · {reminder.duration_seconds} s
                  {reminder.repeat_count > 0 &&
                    ` · ${t("reminders.repeatTimes", { n: reminder.repeat_count })} / ${reminder.repeat_every_minutes} min`}
                </span>
              </p>
            </div>
            <p className="text-right text-xs text-[var(--color-text-muted)]">
              <span className="block text-[10px] uppercase tracking-wide text-[var(--color-text-faint)]">
                {t("reminders.next")}
              </span>
              {nextLabel(reminder)}
              {reminder.last_fired_at && (
                <span className="mt-1 block font-mono text-[10px] text-[var(--color-text-faint)]">
                  {t("reminders.lastFired", {
                    at: new Date(reminder.last_fired_at).toLocaleTimeString(locale),
                  })}
                </span>
              )}
            </p>
          </div>

          {/* One line per clock, like a widget — but the badge is the clock's
              own state, not the reminder's. A notification is sent and
              forgotten, so awtrixng-mgr holds no per-display result to show, and
              a green badge here would be an invention. What it can say is
              useful enough: a reminder pointed at an offline clock will not
              ring. */}
          <ul className="mx-4 mb-3 space-y-1">
            {reminder.device_ids.map((id) => {
              const device = devices.find((d) => d.id === id);
              return (
                <li
                  key={id}
                  className="flex flex-wrap items-center gap-2 rounded-lg bg-[var(--color-surface-2)] px-3 py-1.5 text-xs"
                >
                  <StatusBadge
                    status={
                      device ? (device.enabled ? device.status : "disabled") : "unknown"
                    }
                  />
                  <span>{device?.name ?? `#${id}`}</span>
                </li>
              );
            })}
            {reminder.device_ids.length === 0 && (
              <li className="rounded-lg bg-[var(--color-surface-2)] px-3 py-1.5 text-xs text-[var(--color-text-muted)]">
                {t("reminders.noDisplay")}
              </li>
            )}
          </ul>

          <div className="flex flex-wrap gap-2 border-t border-[var(--color-border)] px-4 py-3">
            <Button onClick={() => toggle(reminder)}>
              {reminder.enabled ? t("widgets.disable") : t("widgets.enable")}
            </Button>
            <Button onClick={() => ring(reminder)} loading={ringing === reminder.id}>
              {t("reminders.fire")}
            </Button>
            <Button onClick={() => setEditing({ reminder: null, seed: reminder })}>
              {t("common.duplicate")}
            </Button>
            <Button onClick={() => setEditing({ reminder })}>{t("common.edit")}</Button>
            <Button variant="danger" onClick={() => remove(reminder)} className="ml-auto">
              {t("common.delete")}
            </Button>
          </div>
        </Card>
      ))}
    </div>
  );
}
