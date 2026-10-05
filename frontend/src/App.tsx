import { useEffect, useState } from "react";
import { api } from "./api/client";
import { LocaleSwitcher } from "./components/LocaleSwitcher";
import { ToastProvider } from "./components/Toast";
import { Button } from "./components/ui";
import { AuthGate, useAuth } from "./features/auth/AuthGate";
import { BackupPage } from "./features/backup/BackupPage";
import { ConnectorsPage } from "./features/connectors/ConnectorsPage";
import { DevicesPage } from "./features/devices/DevicesPage";
import { RemindersPage } from "./features/reminders/RemindersPage";
import { WidgetsPage } from "./features/widgets/WidgetsPage";
import { useI18n } from "./i18n";
import type { MessageKey } from "./i18n/messages.en";
import { LOGO_PIXELS } from "./logo";
import { Dashboard } from "./pages/Dashboard";

/** Navigation.
 *
 * Only pages that exist. An earlier version listed Notifications and Settings
 * greyed out, to show where the product was going — but a disabled entry is a
 * promise, and two permanent ones read as unfinished rather than planned.
 * Settings had no content and no plan (the language picker lives in the
 * header, everything else belongs to a device or a service), and Notifications
 * lost its reason when Zabbix was dropped. Re-adding an entry costs one line.
 */
const NAV = [
  { id: "dashboard", label: "nav.dashboard" },
  { id: "devices", label: "nav.devices" },
  { id: "widgets", label: "nav.widgets" },
  { id: "reminders", label: "nav.reminders" },
  { id: "connectors", label: "nav.connectors" },
  { id: "backup", label: "nav.backup" },
] as const satisfies readonly { id: string; label: MessageKey }[];

type Route = (typeof NAV)[number]["id"];

function useHashRoute(): [Route, (route: Route) => void] {
  const read = (): Route => {
    const hash = window.location.hash.replace("#/", "");
    return (NAV.find((n) => n.id === hash)?.id ?? "dashboard") as Route;
  };
  const [route, setRoute] = useState<Route>(read);

  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return [route, (next: Route) => { window.location.hash = `#/${next}`; }];
}

function Logo() {
  // Original branding: a grid of RGB pixels, nothing borrowed from AWTRIX.
  return (
    <div className="flex items-center gap-2">
      <div className="grid grid-cols-3 gap-[2px]" aria-hidden>
        {LOGO_PIXELS.map((c, i) => (
          <span key={i} className="h-[5px] w-[5px] rounded-[1px]" style={{ background: c }} />
        ))}
      </div>
      <span className="font-medium tracking-tight">awtrixng-mgr</span>
    </div>
  );
}

function Shell() {
  const { t } = useI18n();
  const { required, signOut } = useAuth();
  const [route, go] = useHashRoute();
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    api.health().then((h) => setVersion(h.version)).catch(() => setVersion(null));
  }, []);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-[var(--color-border)] bg-[var(--color-bg)]/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <Logo />
          <nav className="flex flex-wrap gap-1 text-sm">
            {NAV.map((item) => (
              <button
                key={item.id}
                onClick={() => go(item.id)}
                className={`rounded-lg px-2.5 py-1 transition
                  ${route === item.id
                    ? "bg-[var(--color-surface-2)] text-[var(--color-text)]"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"}`}
              >
                {t(item.label)}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <LocaleSwitcher />
            {version && (
              <span className="font-mono text-xs text-[var(--color-text-faint)]">
                v{version}
              </span>
            )}
            {/* Only where there is something to sign out of: an installation
                without a password would show a button that does nothing. */}
            {required && <Button onClick={signOut}>{t("auth.signOut")}</Button>}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        {route === "dashboard" && <Dashboard />}
        {route === "devices" && <DevicesPage />}
        {route === "connectors" && <ConnectorsPage />}
        {route === "widgets" && <WidgetsPage />}
        {route === "reminders" && <RemindersPage />}
        {route === "backup" && <BackupPage />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AuthGate>
        <Shell />
      </AuthGate>
    </ToastProvider>
  );
}
