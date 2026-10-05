import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError, setUnauthorizedHandler } from "../../api/client";
import { Button, Card, Field, Input } from "../../components/ui";
import { useI18n } from "../../i18n";

/**
 * Stands in front of the application.
 *
 * Nothing is rendered until the server has said whether a password is
 * configured: showing the dashboard first and the login screen a moment later
 * would flash content that the visitor may not be entitled to. The check is
 * cheap — one open route — so the wait is imperceptible.
 *
 * This is a convenience, not the protection: every route is guarded on the
 * server, and removing this component would hide nothing but reveal nothing
 * either.
 */
interface Auth {
  /** False when no password is configured: there is nothing to sign out of. */
  required: boolean;
  signOut: () => void;
}

const AuthContext = createContext<Auth>({ required: false, signOut: () => {} });

export function useAuth(): Auth {
  return useContext(AuthContext);
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { t, tApi } = useI18n();
  const [state, setState] = useState<"checking" | "in" | "out" | "unreachable">(
    "checking",
  );
  const [required, setRequired] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const check = useCallback(async () => {
    try {
      const status = await api.authStatus();
      setRequired(status.required);
      setState(!status.required || status.authenticated ? "in" : "out");
    } catch {
      setState("unreachable");
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  useEffect(() => {
    // A session that ends while the page is open — expired, or signed out from
    // another tab — puts the login screen back without a reload.
    setUnauthorizedHandler(() => {
      setState("out");
      setRequired(true);
      setError(t("auth.required"));
    });
    return () => setUnauthorizedHandler(null);
  }, [t]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.login(password);
      if (result.ok) {
        setPassword("");
        setState("in");
      } else {
        setError(tApi(result.code, undefined, result.message));
      }
    } catch (failure) {
      setError(
        failure instanceof ApiError
          ? tApi(failure.code, failure.params, failure.message)
          : t("common.unexpectedError"),
      );
    } finally {
      setBusy(false);
    }
  }

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setState("out");
      setError(null);
    }
  }, []);

  if (state === "checking") {
    return (
      <p className="p-8 text-center text-sm text-[var(--color-text-muted)]">
        {t("auth.checking")}
      </p>
    );
  }

  if (state === "unreachable") {
    return (
      <p className="p-8 text-center text-sm text-[var(--color-danger)]">
        {t("auth.unreachable")}
      </p>
    );
  }

  if (state === "out") {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <Card className="w-full max-w-sm p-6">
          <h1 className="text-lg font-medium">{t("auth.title")}</h1>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            {t("auth.intro")}
          </p>
          <form onSubmit={submit} className="mt-5 space-y-4">
            <Field label={t("auth.password")}>
              <Input
                type="password"
                value={password}
                autoFocus
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
            {error && (
              <p className="rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]">
                {error}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              loading={busy}
              disabled={!password}
              className="w-full"
            >
              {t("auth.signIn")}
            </Button>
          </form>
        </Card>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ required, signOut }}>{children}</AuthContext.Provider>
  );
}
