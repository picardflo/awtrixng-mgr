import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ConnectorDescriptor, ConnectorInstance, Device } from "../../api/client";
import { SchemaForm } from "../../components/SchemaForm";
import type { FormValues } from "../../components/SchemaForm";
import { useToast } from "../../components/Toast";
import { Button, Card, EmptyState, Field, Input, StatusBadge } from "../../components/ui";
import { useI18n } from "../../i18n";

/** What the form is working on: a type to create, or an instance to edit. */
interface Editing {
  descriptor: ConnectorDescriptor;
  instance?: ConnectorInstance;
}

export function ConnectorsPage() {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [types, setTypes] = useState<ConnectorDescriptor[]>([]);
  const [instances, setInstances] = useState<ConnectorInstance[] | null>(null);
  //: A `device` field picks from these, so the page loads them too.
  const [devices, setDevices] = useState<Device[]>([]);
  const [editing, setEditing] = useState<Editing | null>(null);
  const formRef = useRef<HTMLDivElement>(null);

  // The form opens above the list; without this it can open off-screen.
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
      const [descriptors, configured, displays] = await Promise.all([
        api.connectorTypes(),
        api.listConnectors(),
        api.listDevices(),
      ]);
      setTypes(descriptors);
      setInstances(configured);
      setDevices(displays);
    } catch (error) {
      fail(error);
      setInstances([]);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-5">
      <header>
        <h2 className="text-lg font-medium">{t("connectors.title")}</h2>
        <p className="text-sm text-[var(--color-text-muted)]">{t("connectors.subtitle")}</p>
      </header>

      {editing ? (
        <div ref={formRef}>
          <ConnectorForm
            // A new subject must give a new form, never the previous values.
            key={editing.instance?.id ?? editing.descriptor.id}
            descriptor={editing.descriptor}
            instance={editing.instance}
            devices={devices}
            onDone={() => {
              setEditing(null);
              void load();
            }}
            onCancel={() => setEditing(null)}
          />
        </div>
      ) : (
        <section className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-faint)]">
            {t("connectors.catalogue")}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {types.map((descriptor) => (
              <button
                key={descriptor.id}
                onClick={() => setEditing({ descriptor })}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-left
                  transition hover:border-[var(--color-accent)]/50 hover:bg-[var(--color-surface-2)]"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">
                    {tApi(`connector.${descriptor.id}.name`, undefined, descriptor.name)}
                  </span>
                  {!descriptor.requires_credentials && (
                    <span className="rounded-full border border-[var(--color-success)]/40 bg-[var(--color-success)]/10 px-2 py-0.5 text-[10px] text-[var(--color-success)]">
                      {t("connectors.noCredentials")}
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-xs text-[var(--color-text-muted)]">
                  {tApi(
                    `connector.${descriptor.id}.description`,
                    undefined,
                    descriptor.description,
                  )}
                </p>
                <p className="mt-2 font-mono text-[10px] text-[var(--color-text-faint)]">
                  {descriptor.widgets
                    .map((widget) =>
                      tApi(`widgetType.${widget.type}.name`, undefined, widget.name),
                    )
                    .join(" · ")}
                </p>
              </button>
            ))}
          </div>
        </section>
      )}

      {instances === null && (
        <p className="text-sm text-[var(--color-text-faint)]">{t("common.loading")}</p>
      )}

      {instances?.length === 0 && !editing && (
        <EmptyState
          title={t("connectors.emptyTitle")}
          description={t("connectors.emptyBody")}
        />
      )}

      <div className="space-y-3">
        {instances?.map((instance) => {
          const descriptor = types.find((type) => type.id === instance.type);
          return (
            <ConnectorCard
              key={instance.id}
              instance={instance}
              descriptor={descriptor}
              onChanged={load}
              onEdit={descriptor ? () => setEditing({ descriptor, instance }) : undefined}
              onError={fail}
            />
          );
        })}
      </div>
    </div>
  );
}

function ConnectorCard({
  instance,
  descriptor,
  onChanged,
  onEdit,
  onError,
}: {
  instance: ConnectorInstance;
  descriptor?: ConnectorDescriptor;
  onChanged: () => void;
  onEdit?: () => void;
  onError: (error: unknown) => void;
}) {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [testing, setTesting] = useState(false);

  async function test() {
    setTesting(true);
    try {
      const result = await api.testConnector(instance.id);
      toast(
        result.ok ? "success" : "error",
        `${instance.name} — ${tApi(result.code, result.params, result.message)}`,
      );
    } catch (error) {
      onError(error);
    } finally {
      setTesting(false);
      onChanged();
    }
  }

  async function remove() {
    if (!confirm(t("connectors.confirmDelete", { name: instance.name }))) return;
    try {
      await api.deleteConnector(instance.id);
      toast("success", t("connectors.deleted", { name: instance.name }));
      onChanged();
    } catch (error) {
      onError(error);
    }
  }

  const error = instance.last_error_code
    ? tApi(instance.last_error_code, undefined, instance.last_error ?? "")
    : instance.last_error;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate font-medium">{instance.name}</h3>
            <StatusBadge status={instance.enabled ? instance.status : "disabled"} />
          </div>
          <p className="mt-1 font-mono text-xs text-[var(--color-text-muted)]">
            {descriptor
              ? tApi(`connector.${descriptor.id}.name`, undefined, descriptor.name)
              : instance.type}
            {instance.last_success
              ? ` · ${new Date(instance.last_success).toLocaleString()}`
              : ` · ${t("connectors.neverTested")}`}
          </p>
        </div>
      </div>

      {error && (
        <p className="mx-4 mb-3 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]">
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-2 border-t border-[var(--color-border)] px-4 py-3">
        <Button onClick={test} loading={testing}>
          {t("connectors.test")}
        </Button>
        {onEdit && <Button onClick={onEdit}>{t("common.edit")}</Button>}
        <Button variant="danger" onClick={remove} className="ml-auto">
          {t("common.delete")}
        </Button>
      </div>
    </Card>
  );
}

function ConnectorForm({
  descriptor,
  instance,
  devices,
  onDone,
  onCancel,
}: {
  descriptor: ConnectorDescriptor;
  /** Present when editing rather than creating. */
  instance?: ConnectorInstance;
  devices: Device[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [name, setName] = useState(
    instance?.name ?? tApi(`connector.${descriptor.id}.name`, undefined, descriptor.name),
  );
  const [values, setValues] = useState<FormValues>(
    () =>
      instance?.config ??
      Object.fromEntries(
        descriptor.config_schema
          .filter((field) => field.default !== null && field.default !== undefined)
          .map((field) => [field.name, field.default]),
      ),
  );
  const [busy, setBusy] = useState(false);

  const secretNames = new Set(
    descriptor.config_schema.filter((field) => field.type === "secret").map((f) => f.name),
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const config: Record<string, unknown> = {};
      const secrets: Record<string, string> = {};
      for (const [key, value] of Object.entries(values)) {
        if (secretNames.has(key)) {
          // An untouched secret field is empty: leaving it out keeps the
          // stored value rather than clearing it.
          if (value) secrets[key] = String(value);
        } else {
          config[key] = value;
        }
      }

      const saved = instance
        ? await api.updateConnector(instance.id, { name: name.trim(), config, secrets })
        : await api.createConnector({
            type: descriptor.id,
            name: name.trim(),
            config,
            secrets,
          });

      // Test right away: nobody wants to discover a typo three screens later.
      const result = await api.testConnector(saved.id);
      toast(
        result.ok ? "success" : "error",
        tApi(result.code, result.params, result.message),
      );
      onDone();
    } catch (error) {
      toast(
        "error",
        error instanceof ApiError
          ? tApi(error.code, error.params, error.message)
          : t("common.unexpectedError"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-4">
      <form onSubmit={submit} className="space-y-4">
        <div>
          <h3 className="font-medium">
            {tApi(`connector.${descriptor.id}.name`, undefined, descriptor.name)}
          </h3>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            {tApi(`connector.${descriptor.id}.description`, undefined, descriptor.description)}
          </p>
        </div>

        <Field label={t("builder.name")}>
          <Input value={name} onChange={(event) => setName(event.target.value)} required />
        </Field>

        {/* Generated from the connector's own schema: no form is coded here. */}
        <SchemaForm
          fields={descriptor.config_schema}
          values={values}
          onChange={setValues}
          columns={1}
          namespace={descriptor.id}
          devices={devices}
          secretsSet={instance?.secrets_set ?? []}
          // A remote field asks the service itself for its options, which
          // only an already-saved service can answer: the list comes from its
          // own settings. Absent while creating one, and the field says so
          // rather than showing an empty list.
          connectorId={instance?.id}
        />

        <div className="flex gap-2">
          <Button type="submit" variant="primary" loading={busy}>
            {instance ? t("connectors.save") : t("connectors.add")}
          </Button>
          <Button type="button" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
