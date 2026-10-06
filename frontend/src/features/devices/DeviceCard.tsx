import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Device, DeviceState, TestResult } from "../../api/client";
import { AwtrixMatrixPreview } from "../../components/AwtrixMatrixPreview";
import { useToast } from "../../components/Toast";
import { Button, Card, Stat, StatusBadge } from "../../components/ui";
import { deviceUrl } from "./deviceUrl";
import { QuietHoursPanel } from "./QuietHours";
import { DeviceSettingsPanel } from "./DeviceSettings";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages.en";

export function DeviceCard({
  device,
  onChanged,
}: {
  device: Device;
  onChanged: () => void;
}) {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [stats, setStats] = useState<DeviceState | null>(null);
  const [testing, setTesting] = useState(false);
  const [notifying, setNotifying] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showQuiet, setShowQuiet] = useState(false);

  function uptime(seconds?: number): string {
    if (seconds === undefined) return t("unit.none");
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const d = t("unit.day.short");
    const h = t("unit.hour.short");
    const min = t("unit.minute.short");
    if (days) return `${days} ${d} ${hours} ${h}`;
    if (hours) return `${hours} ${h} ${minutes} ${min}`;
    return `${minutes} ${min}`;
  }

  /** A reading, or the dash. Written once: six tiles spelling out the same
   *  `x !== undefined ? ... : t("unit.none")` is six chances to get it wrong,
   *  and the version that shipped got all six wrong at once. */
  function num(value?: number, unit = ""): string {
    return value === undefined || value === null ? t("unit.none") : `${value}${unit}`;
  }

  /** The unit, but only when there is a figure to attach it to. */
  function unitFor(value: number | undefined | null, unit: string): string | undefined {
    return value === undefined || value === null ? undefined : unit;
  }

  /** Wi-Fi quality in words: the raw RSSI means nothing to most people. */
  function wifiQuality(rssi?: number): string | undefined {
    if (rssi === undefined) return undefined;
    const key: MessageKey =
      rssi >= -55
        ? "device.wifi.excellent"
        : rssi >= -70
          ? "device.wifi.good"
          : "device.wifi.weak";
    return t(key);
  }

  async function run(
    setBusy: (value: boolean) => void,
    action: () => Promise<TestResult>,
  ) {
    setBusy(true);
    try {
      const result = await action();
      toast(
        result.ok ? "success" : "error",
        `${device.name} — ${tApi(result.code, result.params, result.message)}`,
      );
    } catch (error) {
      toast(
        "error",
        error instanceof ApiError
          ? tApi(error.code, error.params, error.message)
          : t("common.unexpectedError"),
      );
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  const test = () =>
    run(setTesting, async () => {
      const result = await api.testDevice(device.id);
      setStats(result.stats ?? null);
      return result;
    });

  const notify = () =>
    run(setNotifying, () =>
      api.notifyDevice(device.id, { text: "awtrixng-mgr", color: "#3ddc84", duration: 6 }),
    );

  async function remove() {
    if (!confirm(t("device.confirmDelete", { name: device.name }))) return;
    try {
      await api.deleteDevice(device.id);
      toast("success", t("device.deleted", { name: device.name }));
      onChanged();
    } catch (error) {
      toast(
        "error",
        error instanceof ApiError
          ? tApi(error.code, error.params, error.message)
          : t("common.unexpectedError"),
      );
    }
  }

  const error = device.last_error_code
    ? tApi(device.last_error_code, undefined, device.last_error ?? "")
    : device.last_error;

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 p-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate font-medium">{device.name}</h3>
            <StatusBadge status={device.enabled ? device.status : "disabled"} />
          </div>
          <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
            {/* The address is already written here, so it is the address that
                becomes clickable — a fifth button in the bar below would
                dilute the four that act on the display rather than leave it. */}
            <a
              href={deviceUrl(device)}
              target="_blank"
              rel="noreferrer"
              title={t("device.openInterface")}
              className="underline decoration-dotted underline-offset-2
                hover:text-[var(--color-accent)]"
            >
              {device.host}
              {device.port !== 80 && `:${device.port}`}
            </a>
            {device.firmware && ` · AWTRIX NG v${device.firmware}`}
          </p>
        </div>

        <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-matrix-bg)] p-1.5">
          {/* The device name, never the app reported by /api/stats: that one is
              captured at test time and goes stale immediately, so the card
              would claim "BATTERY" while the clock shows the time. The real
              screen belongs on the Device page (§9 quinquies), where a
              LiveView poll is expected — not on a list. */}
          <AwtrixMatrixPreview text={device.name} color="#3ddc84" scale={5} />
        </div>
      </div>

      {error && (
        <p className="mx-4 mb-3 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]">
          {error}
        </p>
      )}

      {/* The same six readings the display's own interface shows, in the same
          order, with the same second line under each. Someone comparing the
          two should not have to translate anything.

          AWTRIX 3 reported `bat`, `temp`, `hum`; NG reports `battery_percent`,
          `temperature`, `humidity`. Reading the old names compiled fine and
          put a dash in every tile — which is how this shipped. */}
      {stats && (
        <>
          <div className="mx-4 mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {/* The unit is passed apart from the figure, not glued to it:
                it is drawn small and muted so the digits stand alone. When
                there is no reading the dash takes the tile on its own — a
                lone "%" beside nothing reads as a measurement of zero. */}
            <Stat
              label={t("device.stat.battery")}
              value={num(stats.battery_percent)}
              unit={unitFor(stats.battery_percent, "%")}
              detail={num(stats.battery_voltage, " V")}
            />
            <Stat
              label={t("device.stat.wifi")}
              value={num(stats.wifi_rssi)}
              unit={unitFor(stats.wifi_rssi, "dBm")}
              detail={wifiQuality(stats.wifi_rssi)}
            />
            <Stat
              label={t("device.stat.light")}
              value={num(stats.light_level)}
              unit={unitFor(stats.light_level, "%")}
              detail={num(stats.ldr_raw, ` ${t("device.stat.raw")}`)}
            />
            <Stat
              label={t("device.stat.temperature")}
              value={num(stats.temperature)}
              unit={unitFor(stats.temperature, "°C")}
            />
            <Stat
              label={t("device.stat.humidity")}
              value={num(stats.humidity)}
              unit={unitFor(stats.humidity, "%")}
            />
            <Stat
              label={t("device.stat.fps")}
              value={num(stats.fps)}
              detail={num(stats.brightness, ` ${t("device.stat.brightnessShort")}`)}
            />
          </div>

          {/* The footer line of the clock's own dashboard. */}
          <p className="mx-4 mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs
            text-[var(--color-text-faint)]">
            <span>{t("device.stat.uptime")} {uptime(stats.uptime_seconds)}</span>
            {stats.free_heap_bytes !== undefined && (
              <span>
                {t("device.stat.freeRam")} {Math.round(stats.free_heap_bytes / 1024)} Ko
              </span>
            )}
            {stats.current_app && (
              <span>{t("device.stat.currentApp")} {stats.current_app}</span>
            )}
            {stats.matrix_power === false && (
              <span className="text-[var(--color-danger)]">{t("device.stat.panelOff")}</span>
            )}
          </p>
        </>
      )}

      {showSettings && (
        <div className="mx-4 mb-3 rounded-lg bg-[var(--color-surface-2)] p-3">
          <DeviceSettingsPanel deviceId={device.id} />
        </div>
      )}

      {showQuiet && (
        <div className="mx-4 mb-3 rounded-lg bg-[var(--color-surface-2)] p-3">
          <QuietHoursPanel deviceId={device.id} />
        </div>
      )}

      <div className="flex flex-wrap gap-2 border-t border-[var(--color-border)] px-4 py-3">
        <Button onClick={test} loading={testing}>
          {t("device.testConnection")}
        </Button>
        <Button onClick={notify} loading={notifying}>
          {t("device.sendNotification")}
        </Button>
        <Button onClick={() => setShowSettings(!showSettings)}>
          {t("device.settings.title")}
        </Button>
        <Button onClick={() => setShowQuiet(!showQuiet)}>
          {t("device.quietHours.title")}
        </Button>
        <Button variant="danger" onClick={remove} className="ml-auto">
          {t("common.delete")}
        </Button>
      </div>
    </Card>
  );
}
