import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, Card, Field, Input } from "../../components/ui";
import { useI18n } from "../../i18n";

export function AddDeviceForm({
  onAdded,
  onCancel,
}: {
  onAdded: () => void;
  onCancel: () => void;
}) {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("80");
  const [withAuth, setWithAuth] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      // Create then immediately test: the user must know straight away whether
      // their AWTRIX answers (§24).
      const device = await api.createDevice({
        name: name.trim(),
        host: host.trim(),
        port: Number(port) || 80,
        username: withAuth ? username : null,
        password: withAuth ? password : null,
      });
      const result = await api.testDevice(device.id);
      toast(
        result.ok ? "success" : "error",
        tApi(result.code, result.params, result.message),
      );
      onAdded();
    } catch (error) {
      toast(
        "error",
        error instanceof ApiError
          ? tApi(error.code, error.params, error.message)
          : t("deviceForm.failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-4">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label={t("deviceForm.name")}>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("deviceForm.namePlaceholder")}
              required
              autoFocus
            />
          </Field>
          <Field label={t("deviceForm.address")} hint={t("deviceForm.addressHint")}>
            <Input
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder={t("deviceForm.addressPlaceholder")}
              required
            />
          </Field>
          <Field label={t("deviceForm.port")}>
            <Input
              type="number"
              value={port}
              onChange={(e) => setPort(e.target.value)}
              min={1}
              max={65535}
            />
          </Field>
        </div>

        <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
          <input
            type="checkbox"
            checked={withAuth}
            onChange={(e) => setWithAuth(e.target.checked)}
            className="accent-[var(--color-accent)]"
          />
          {t("deviceForm.needsAuth")}
        </label>

        {withAuth && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("deviceForm.username")}>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} />
            </Field>
            <Field label={t("deviceForm.password")} hint={t("deviceForm.passwordHint")}>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          </div>
        )}

        <div className="flex gap-2">
          <Button type="submit" variant="primary" loading={busy}>
            {t("deviceForm.submit")}
          </Button>
          <Button type="button" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
