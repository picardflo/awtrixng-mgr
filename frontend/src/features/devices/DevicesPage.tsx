import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Device } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, EmptyState } from "../../components/ui";
import { useI18n } from "../../i18n";
import { AddDeviceForm } from "./AddDeviceForm";
import { ClockLanguage } from "../../components/ClockLanguage";
import { DeviceCard } from "./DeviceCard";

export function DevicesPage() {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [adding, setAdding] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);

  // Same reason as everywhere else: with several displays listed, the button
  // sits below the form it opens.
  useEffect(() => {
    if (adding) formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [adding]);

  async function load() {
    try {
      setDevices(await api.listDevices());
    } catch (error) {
      toast(
        "error",
        error instanceof ApiError
          ? tApi(error.code, error.params, error.message)
          : t("common.unexpectedError"),
      );
      setDevices([]);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium">{t("devices.title")}</h2>
          <p className="text-sm text-[var(--color-text-muted)]">{t("devices.subtitle")}</p>
        </div>
        {!adding && devices && devices.length > 0 && (
          <Button variant="primary" onClick={() => setAdding(true)}>
            + {t("devices.add")}
          </Button>
        )}
      </header>

      {/* An installation setting, on the page about the things it governs.
          It sat in the header beside the interface picker, where two selects
          both reading "Français" looked like a duplicate. */}
      <ClockLanguage />

      {adding && (
        <div ref={formRef}>
          <AddDeviceForm
            onAdded={() => {
              setAdding(false);
              void load();
            }}
            onCancel={() => setAdding(false)}
          />
        </div>
      )}

      {devices === null && (
        <p className="text-sm text-[var(--color-text-faint)]">{t("common.loading")}</p>
      )}

      {devices?.length === 0 && !adding && (
        <EmptyState
          title={t("devices.welcomeTitle")}
          description={t("devices.welcomeBody")}
          action={
            <Button variant="primary" onClick={() => setAdding(true)}>
              {t("devices.add")}
            </Button>
          }
        />
      )}

      <div className="space-y-3">
        {devices?.map((device) => (
          <DeviceCard key={device.id} device={device} onChanged={load} />
        ))}
      </div>
    </div>
  );
}
