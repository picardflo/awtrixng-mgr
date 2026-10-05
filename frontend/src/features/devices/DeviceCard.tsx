import { useState } from "react";
import { api, ApiError } from "../../api/client";
import type { AwtrixStats, Device, TestResult } from "../../api/client";
import { AwtrixMatrixPreview } from "../../components/AwtrixMatrixPreview";
import { useToast } from "../../components/Toast";
import { Button, Card, Stat, StatusBadge } from "../../components/ui";
import { deviceUrl } from "./deviceUrl";
import { BedroomPanel } from "./BedroomMode";
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
  const [stats, setStats] = useState<AwtrixStats | null>(null);
  const [testing, setTesting] = useState(false);
  const [notifying, setNotifying] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showBedroom, setShowBedroom] = useState(false);

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

  /** Wi-Fi quality: the raw RSSI means nothing to most people. */
  function wifi(rssi?: number): string {
    if (rssi === undefined) return t("unit.none");
    const key: MessageKey =
      rssi >= -55
        ? "device.wifi.excellent"
        : rssi >= -70
          ? "device.wifi.good"
          : "device.wifi.weak";
    return `${rssi} dBm · ${t(key)}`;
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
            {device.firmware && ` · AWTRIX 3 v${device.firmware}`}
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

      {stats && (
        <div className="mx-4 mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <Stat
            label={t("device.stat.battery")}
            value={stats.bat !== undefined ? `${stats.bat} %` : t("unit.none")}
          />
          <Stat label={t("device.stat.wifi")} value={wifi(stats.wifi_signal)} />
          <Stat
            label={t("device.stat.temperature")}
            value={stats.temp !== undefined ? `${stats.temp} °C` : t("unit.none")}
          />
          <Stat
            label={t("device.stat.humidity")}
            value={stats.hum !== undefined ? `${stats.hum} %` : t("unit.none")}
          />
          <Stat label={t("device.stat.brightness")} value={stats.bri ?? t("unit.none")} />
          <Stat label={t("device.stat.uptime")} value={uptime(stats.uptime)} />
        </div>
      )}

      {showSettings && (
        <div className="mx-4 mb-3 rounded-lg bg-[var(--color-surface-2)] p-3">
          <DeviceSettingsPanel deviceId={device.id} />
        </div>
      )}

      {showBedroom && (
        <div className="mx-4 mb-3 rounded-lg bg-[var(--color-surface-2)] p-3">
          <BedroomPanel deviceId={device.id} />
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
        <Button onClick={() => setShowBedroom(!showBedroom)}>
          {t("device.bedroom.title")}
        </Button>
        <Button variant="danger" onClick={remove} className="ml-auto">
          {t("common.delete")}
        </Button>
      </div>
    </Card>
  );
}
