/**
 * Renders a connector's declared fields as a form (§10).
 *
 * This is the piece that keeps the frontend free of any connector knowledge:
 * adding Tautulli or Zabbix adds Python, never a form. Every branch below is a
 * field *type*, never a connector name.
 */

import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Device, FieldOption, FormField, PlaceValue } from "../api/client";
import { useI18n } from "../i18n";
import { PlaceField } from "./PlaceField";
import { Field, Input } from "./ui";

export type FormValues = Record<string, unknown>;

interface Props {
  fields: FormField[];
  values: FormValues;
  onChange: (values: FormValues) => void;
  /** Secret fields that already hold a value, so we can say so without
   *  ever receiving it. */
  secretsSet?: string[];
  /** Needed by remote_select fields, which ask the connector for options. */
  connectorId?: number;
  /** Needed by `device` fields, which pick one of the configured displays. */
  devices?: Device[];
  columns?: 1 | 2 | 3;
  /**
   * Prefix for translation lookups, e.g. "weather" or "weather.current".
   *
   * Connectors declare their labels in English, in Python. Rather than teach
   * the backend about locales, the frontend looks up
   * `field.<namespace>.<field>.label` and falls back to the English string —
   * the same pattern as API error codes (ADR-012). A connector with no
   * translation simply shows English.
   */
  namespace?: string;
}

const COLUMNS = { 1: "", 2: "sm:grid-cols-2", 3: "sm:grid-cols-3" } as const;

export function SchemaForm({
  fields,
  values,
  onChange,
  secretsSet = [],
  connectorId,
  devices = [],
  columns = 2,
  namespace,
}: Props) {
  const set = (name: string, value: unknown) => onChange({ ...values, [name]: value });

  return (
    <div className={`grid gap-4 ${COLUMNS[columns]}`}>
      {fields.map((field) => (
        <SchemaField
          key={field.name}
          field={field}
          value={values[field.name]}
          onChange={(value) => set(field.name, value)}
          hasSecret={secretsSet.includes(field.name)}
          connectorId={connectorId}
          devices={devices}
          values={values}
          namespace={namespace}
        />
      ))}
    </div>
  );
}

function SchemaField({
  field,
  value,
  onChange,
  hasSecret,
  connectorId,
  devices,
  values,
  namespace,
}: {
  field: FormField;
  value: unknown;
  onChange: (value: unknown) => void;
  hasSecret: boolean;
  connectorId?: number;
  devices?: Device[];
  values: FormValues;
  namespace?: string;
}) {
  const { t, tApi } = useI18n();
  const translate = (part: string, fallback: string | null | undefined) =>
    namespace && fallback
      ? tApi(`field.${namespace}.${field.name}.${part}`, undefined, fallback)
      : (fallback ?? undefined);
  const label = translate("label", field.label) ?? field.label;

  if (field.type === "boolean") {
    return (
      <label className="flex items-center gap-2 self-end pb-1.5 text-sm text-[var(--color-text-muted)]">
        <input
          type="checkbox"
          checked={Boolean(value ?? field.default)}
          onChange={(event) => onChange(event.target.checked)}
          className="accent-[var(--color-accent)]"
        />
        {label}
      </label>
    );
  }

  const hint = translate("help", field.help) ?? (field.unit ? `${field.unit}` : undefined);

  return (
    <Field
      label={label + (field.required ? " *" : "")}
      hint={
        field.type === "secret" && hasSecret
          ? t("form.secretStored")
          : hint ?? undefined
      }
    >
      <Control
        field={field}
        value={value}
        onChange={onChange}
        hasSecret={hasSecret}
        connectorId={connectorId}
        devices={devices}
        values={values}
        namespace={namespace}
        placeholder={translate("placeholder", field.placeholder)}
      />
    </Field>
  );
}

function Control({
  field,
  value,
  onChange,
  hasSecret,
  connectorId,
  devices = [],
  values,
  namespace,
  placeholder,
}: {
  field: FormField;
  value: unknown;
  onChange: (value: unknown) => void;
  hasSecret: boolean;
  connectorId?: number;
  devices?: Device[];
  values: FormValues;
  namespace?: string;
  placeholder?: string;
}) {
  const { t, tApi } = useI18n();
  const asString = value === undefined || value === null ? "" : String(value);

  switch (field.type) {
    case "device":
      // The displays are already loaded by the page, so no discover() call —
      // which matters, since the choice happens before the connector exists.
      return (
        <Select
          options={devices.map((device) => ({
            value: String(device.id),
            label: device.name,
          }))}
          value={asString}
          required={field.required}
          onChange={(chosen) => onChange(chosen ? Number(chosen) : null)}
        />
      );

    case "place":
      return (
        <PlaceField
          value={(value as PlaceValue | null) ?? null}
          onChange={onChange}
          placeholder={placeholder}
        />
      );

    case "number":
    case "duration": {
      return (
        <div className="flex items-center gap-2">
          <Input
            type="number"
            value={asString}
            placeholder={placeholder}
            min={field.min ?? undefined}
            max={field.max ?? undefined}
            step="any"
            required={field.required}
            onChange={(event) =>
              onChange(event.target.value === "" ? null : Number(event.target.value))
            }
          />
          {field.unit && (
            <span className="shrink-0 text-xs text-[var(--color-text-faint)]">
              {field.unit}
            </span>
          )}
        </div>
      );
    }

    case "secret":
      return (
        <Input
          type="password"
          value={asString}
          // A stored secret is never sent back, so the box stays empty and the
          // placeholder says it is set. Typing replaces it; leaving it blank
          // keeps it.
          placeholder={hasSecret ? "••••••••" : (placeholder)}
          autoComplete="new-password"
          required={field.required && !hasSecret}
          onChange={(event) => onChange(event.target.value)}
        />
      );

    case "select":
      return (
        <Select
          // Option labels come from the connector, in English. Same lookup as
          // everything else it declares, with the English text as fallback.
          options={(field.options ?? []).map((option) => ({
            ...option,
            label: namespace
              ? tApi(
                  `option.${namespace}.${field.name}.${option.value}`,
                  undefined,
                  option.label,
                )
              : option.label,
          }))}
          value={asString}
          required={field.required}
          onChange={onChange}
        />
      );

    case "remote_select":
      return (
        <RemoteSelect
          field={field}
          value={asString}
          onChange={onChange}
          connectorId={connectorId}
          values={values}
        />
      );

    case "multiselect":
      return (
        <Pills
          options={field.options ?? []}
          selected={Array.isArray(value) ? (value as string[]) : []}
          onChange={onChange}
        />
      );

    case "remote_multiselect":
      return (
        <RemotePills
          field={field}
          selected={Array.isArray(value) ? (value as string[]) : []}
          onChange={onChange}
          connectorId={connectorId}
          values={values}
        />
      );

    case "color":
      return (
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={/^#[0-9a-f]{6}$/i.test(asString) ? asString : "#3ddc84"}
            onChange={(event) => onChange(event.target.value)}
            className="h-8 w-10 shrink-0 cursor-pointer rounded border border-[var(--color-border)] bg-transparent"
          />
          <Input
            value={asString}
            placeholder="#3ddc84"
            onChange={(event) => onChange(event.target.value || null)}
          />
        </div>
      );

    case "template":
      return (
        <textarea
          value={asString}
          rows={2}
          placeholder={placeholder ?? "{{ value }}"}
          onChange={(event) => onChange(event.target.value)}
          className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]
            px-3 py-1.5 font-mono text-sm text-[var(--color-text)]
            focus:border-[var(--color-accent)] focus:outline-none"
        />
      );

    default:
      return (
        <Input
          type={field.type === "url" ? "url" : "text"}
          value={asString}
          placeholder={placeholder}
          required={field.required}
          onChange={(event) => onChange(event.target.value)}
          aria-label={t("form.value")}
        />
      );
  }
}

function Select({
  options,
  value,
  required,
  onChange,
  disabled,
  placeholder,
}: {
  options: FieldOption[];
  value: string;
  required?: boolean;
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  return (
    <select
      value={value}
      required={required}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]
        px-3 py-1.5 text-sm text-[var(--color-text)] disabled:opacity-50
        focus:border-[var(--color-accent)] focus:outline-none"
    >
      <option value="">{placeholder ?? "—"}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
          {option.hint ? ` · ${option.hint}` : ""}
        </option>
      ))}
    </select>
  );
}

/** Options come from the connector, e.g. the hosts of a Zabbix server. */
function Pills({
  options,
  selected,
  onChange,
}: {
  options: FieldOption[];
  selected: string[];
  onChange: (value: unknown) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const on = selected.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            title={option.hint ?? undefined}
            onClick={() =>
              onChange(
                on ? selected.filter((v) => v !== option.value) : [...selected, option.value],
              )
            }
            className={`rounded-full border px-2.5 py-1 text-xs transition ${
              on
                ? "border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            }`}
          >
            {option.label}
            {option.hint && (
              <span className="ml-1.5 text-[var(--color-text-faint)]">{option.hint}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** The same pills, over options the connector lists.
 *
 *  Separate from RemoteSelect rather than folded into it: that one falls back
 *  to a free text input when the listing fails, which makes sense for one
 *  value and none at all for a list of them. Here a failed listing says so
 *  and changes nothing — the stored choices are kept, not silently dropped.
 */
function RemotePills({
  field,
  selected,
  onChange,
  connectorId,
  values,
}: {
  field: FormField;
  selected: string[];
  onChange: (value: unknown) => void;
  connectorId?: number;
  values: FormValues;
}) {
  const { t } = useI18n();
  const [options, setOptions] = useState<FieldOption[] | null>(null);
  const [failed, setFailed] = useState(false);

  const dependencies = (field.depends_on ?? []).map((name) => values[name]).join("|");

  useEffect(() => {
    if (!connectorId || !field.source) return;
    let cancelled = false;
    setFailed(false);
    api
      .discover(connectorId, field.source)
      .then((result) => !cancelled && setOptions(result))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [connectorId, field.source, dependencies]);

  if (!connectorId) {
    // Before the service exists there is nothing to list: it is the saved
    // place and radius that decide which stations are nearby.
    return (
      <p className="text-xs text-[var(--color-text-faint)]">{t("form.saveFirst")}</p>
    );
  }
  if (failed) {
    return (
      <p className="text-xs text-[var(--color-text-faint)]">{t("form.optionsUnavailable")}</p>
    );
  }
  if (options === null) {
    return <p className="text-xs text-[var(--color-text-faint)]">{t("common.loading")}</p>;
  }
  if (options.length === 0) {
    return <p className="text-xs text-[var(--color-text-faint)]">{t("form.nothingToList")}</p>;
  }

  return <Pills options={options} selected={selected} onChange={onChange} />;
}

function RemoteSelect({
  field,
  value,
  onChange,
  connectorId,
  values,
}: {
  field: FormField;
  value: string;
  onChange: (value: unknown) => void;
  connectorId?: number;
  values: FormValues;
}) {
  const { t } = useI18n();
  const [options, setOptions] = useState<FieldOption[] | null>(null);
  const [failed, setFailed] = useState(false);

  // Re-fetch when a field this one depends on changes, e.g. items after host.
  const dependencies = (field.depends_on ?? []).map((name) => values[name]).join("|");

  useEffect(() => {
    if (!connectorId || !field.source) return;
    let cancelled = false;
    setFailed(false);
    api
      .discover(connectorId, field.source)
      .then((result) => !cancelled && setOptions(result))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [connectorId, field.source, dependencies]);

  if (!connectorId) {
    return (
      <p className="text-xs text-[var(--color-text-faint)]">
        {t("form.selectConnectorFirst")}
      </p>
    );
  }
  if (failed) {
    // A field that cannot list its options must still be fillable by hand.
    return (
      <Input
        value={value}
        placeholder={t("form.optionsUnavailable")}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  return (
    <Select
      options={options ?? []}
      value={value}
      required={field.required}
      disabled={options === null}
      placeholder={options === null ? t("common.loading") : undefined}
      onChange={onChange}
    />
  );
}
