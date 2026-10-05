import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ConnectorInstance, Device, WidgetInstance } from "../api/client";
import { AwtrixMatrixPreview } from "../components/AwtrixMatrixPreview";
import { Card, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/messages.en";

interface Failure {
  id: string;
  name: string;
  status: Device["status"];
  code: string | null;
  message: string | null;
}

function Counter({
  title,
  value,
  total,
}: {
  title: MessageKey;
  value: number;
  total: number;
}) {
  const { t } = useI18n();
  return (
    <Card className="p-4">
      <h3 className="text-sm font-medium text-[var(--color-text-muted)]">{t(title)}</h3>
      <p className="mt-2 font-mono text-2xl">
        {value}
        <span className="text-sm text-[var(--color-text-faint)]"> / {total}</span>
      </p>
      <p className="mt-1 text-xs text-[var(--color-text-faint)]">
        {t("dashboard.devicesOnline")}
      </p>
    </Card>
  );
}

export function Dashboard() {
  const { t, tApi } = useI18n();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [connectors, setConnectors] = useState<ConnectorInstance[] | null>(null);
  const [widgets, setWidgets] = useState<WidgetInstance[] | null>(null);

  useEffect(() => {
    api.listDevices().then(setDevices).catch(() => setDevices([]));
    api.listConnectors().then(setConnectors).catch(() => setConnectors([]));
    api.listWidgets().then(setWidgets).catch(() => setWidgets([]));
  }, []);

  const healthy = <T extends { status: Device["status"] }>(list: T[] | null) =>
    list?.filter((item) => item.status === "healthy").length ?? 0;

  // One list, whatever the thing: an error is an error (§18).
  const failing: Failure[] = [
    ...(devices ?? []).map((d) => ({ ...d, id: `device-${d.id}` })),
    ...(connectors ?? []).map((c) => ({ ...c, id: `connector-${c.id}` })),
    ...(widgets ?? []).map((w) => ({ ...w, id: `widget-${w.id}` })),
  ]
    .filter((item) => item.status === "error")
    .map((item) => ({
      id: item.id,
      name: item.name,
      status: item.status,
      code: item.last_error_code,
      message: item.last_error,
    }));

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center justify-between gap-6 p-5">
        <div>
          <h2 className="text-lg font-medium">awtrixng-mgr</h2>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            {t("dashboard.tagline")}
          </p>
        </div>
        <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-matrix-bg)] p-2">
          {/* 31 colonnes sur les 32 du panneau : il tient, donc il se lit à
              tout instant. Le texte précédent en faisait 58 et défilait, si
              bien qu'une capture d'écran le prenait en plein milieu et
              montrait "AWTRIXHI" — un bandeau qui a l'air cassé. */}
          <AwtrixMatrixPreview text="AWTRIXNG" color="#3ddc84" scale={6} />
        </div>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        <Counter
          title="dashboard.devices"
          value={healthy(devices)}
          total={devices?.length ?? 0}
        />
        <Counter
          title="dashboard.connectors"
          value={healthy(connectors)}
          total={connectors?.length ?? 0}
        />
        <Counter
          title="dashboard.activeWidgets"
          value={healthy(widgets)}
          total={widgets?.length ?? 0}
        />
      </div>

      {failing.length > 0 && (
        <Card className="p-4">
          <h3 className="mb-3 text-sm font-medium">{t("dashboard.recentErrors")}</h3>
          <ul className="space-y-2">
            {failing.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-3 text-sm">
                <StatusBadge status={item.status} />
                <span className="font-medium">{item.name}</span>
                <span className="text-[var(--color-text-muted)]">
                  {item.code ? tApi(item.code, undefined, item.message ?? "") : item.message}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
