/**
 * Exporting and restoring the configuration.
 *
 * Everything lives in one SQLite file. Losing it means retyping every
 * template, icon, colour and position by hand.
 *
 * Restoring replaces rather than merges, so the file's contents are shown
 * against what is there now before anything happens — that is what stops the
 * wrong file from wiping a working configuration.
 *
 * The file carries credentials in clear text: a backup that cannot restore is
 * half a backup, and some API keys are only ever shown once by the service
 * that issues them. The warning is stated here, and again inside the file.
 */

import { useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { BackupSummary } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Button, Card } from "../../components/ui";
import { useI18n } from "../../i18n";

export function BackupPage() {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<unknown>(null);
  const [summary, setSummary] = useState<BackupSummary | null>(null);
  const [restoring, setRestoring] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  function fail(error: unknown) {
    toast(
      "error",
      error instanceof ApiError
        ? tApi(error.code, error.params, error.message)
        : t("common.unexpectedError"),
    );
  }

  async function download() {
    if (!confirm(t("backup.confirmExport"))) return;
    setBusy(true);
    try {
      const backup = await api.exportBackup();
      const stamp = new Date().toISOString().slice(0, 10);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `awtrixng-mgr-${stamp}.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast("success", t("backup.exported"));
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function choose(event: React.ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
    if (!chosen) return;
    setSummary(null);
    setFile(null);
    try {
      const parsed = JSON.parse(await chosen.text());
      // Validated server-side: the frontend should not hold a second copy of
      // the format's rules.
      const read = await api.inspectBackup(parsed);
      setSummary(read);
      if (read.ok) setFile(parsed);
    } catch (error) {
      if (error instanceof SyntaxError) toast("error", t("backup.notJson"));
      else fail(error);
    }
  }

  async function restore() {
    if (!file || !confirm(t("backup.confirmRestore"))) return;
    setRestoring(true);
    try {
      const result = await api.restoreBackup(file);
      toast("success", tApi(result.code, undefined, result.message));
      setFile(null);
      setSummary(null);
      if (input.current) input.current.value = "";
    } catch (error) {
      fail(error);
    } finally {
      setRestoring(false);
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-lg font-medium">{t("backup.title")}</h2>
        <p className="text-sm text-[var(--color-text-muted)]">{t("backup.subtitle")}</p>
      </header>

      <Card className="space-y-3 p-4">
        <h3 className="text-sm font-medium">{t("backup.export")}</h3>
        <p className="text-xs text-[var(--color-text-muted)]">{t("backup.exportHelp")}</p>
        <p className="rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 px-3 py-2 text-xs text-[var(--color-warning)]">
          {t("backup.credentialsWarning")}
        </p>
        <Button variant="primary" onClick={download} loading={busy}>
          {t("backup.download")}
        </Button>
      </Card>

      <Card className="space-y-3 p-4">
        <h3 className="text-sm font-medium">{t("backup.import")}</h3>
        <p className="text-xs text-[var(--color-text-muted)]">{t("backup.importHelp")}</p>

        <input
          ref={input}
          type="file"
          accept="application/json,.json"
          onChange={choose}
          className="block w-full text-xs text-[var(--color-text-muted)]
            file:mr-3 file:rounded-lg file:border file:border-[var(--color-border-strong)]
            file:bg-transparent file:px-3 file:py-1.5 file:text-sm file:text-[var(--color-text)]"
        />

        {summary && !summary.ok && (
          <p className="rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]">
            {tApi(summary.code, undefined, summary.message)}
          </p>
        )}

        {summary?.ok && (
          <div className="space-y-3 rounded-lg bg-[var(--color-surface-2)] p-3">
            <p className="text-xs text-[var(--color-text-muted)]">
              {t("backup.fileHolds", {
                devices: summary.devices,
                connectors: summary.connectors,
                widgets: summary.widgets,
              })}
              {summary.exported_at &&
                ` · ${new Date(summary.exported_at).toLocaleString()}`}
              {summary.app_version && ` · v${summary.app_version}`}
            </p>

            <p className="rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 px-3 py-2 text-xs text-[var(--color-warning)]">
              {t("backup.willReplace")}
            </p>

            {summary.secrets > 0 && (
              <p className="text-xs text-[var(--color-text-muted)]">
                {t("backup.fileCarriesSecrets", { count: summary.secrets })}
              </p>
            )}

            <Button variant="danger" onClick={restore} loading={restoring}>
              {t("backup.restore")}
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
