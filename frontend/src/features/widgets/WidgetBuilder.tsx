/**
 * Two panels: what you choose on the left, what the matrix will show on the
 * right (§9 quater). The preview is served by the backend, which renders the
 * real AWTRIX payload — so it cannot drift from what gets pushed.
 *
 * It falls back to the widget's sample data when the service is unreachable,
 * so editing never stalls on a service being down.
 */

import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  FONTS,
  ICON_MODES,
  iconThumbnail,
  SCROLL_MODES,
  TEXT_CASES,
} from "../../api/client";
import type { Font, IconMode, ScrollMode, TextCase } from "../../api/client";
import type { MessageKey } from "../../i18n/messages.en";

/** The six the firmware draws, as it lists them in its capabilities. Kept
 *  here as a fallback; the display's own list is authoritative. */
const OVERLAYS = ["rain", "snow", "drizzle", "storm", "thunder", "frost"];
import type {
  ConnectorInstance,
  Device,
  DisplayOptions,
  PreviewResponse,
  WidgetDescriptor,
  WidgetInstance,
} from "../../api/client";
import {
  AwtrixMatrixPreview,
  MATRIX_WIDTH,
} from "../../components/AwtrixMatrixPreview";
import { textWidth } from "../../components/pixelFont";
import { IconPicker } from "../../components/IconPicker";
import { SchemaForm } from "../../components/SchemaForm";
import type { FormValues } from "../../components/SchemaForm";
import { useToast } from "../../components/Toast";
import { Button, Card, Field, Input, NativeSelect, Toggle } from "../../components/ui";
import { useI18n } from "../../i18n";

interface Props {
  connectors: ConnectorInstance[];
  devices: Device[];
  widgetTypes: WidgetDescriptor[];
  /** Present when editing rather than creating. */
  widget?: WidgetInstance;
  /** A widget to copy the settings of while still creating a new one. Kept
   *  apart from `widget`, which is what decides between PATCH and POST: a
   *  copy must never write over the thing it was copied from. */
  seed?: WidgetInstance;
  onSaved: () => void;
  onCancel: () => void;
}

/** The values a widget's fields declare as their defaults.
 *
 * Exported for tests: a required field arriving empty makes the form look
 * broken and blocks saving, which is exactly what happened to the metric
 * select of the display connector.
 */
export function defaultsOf(descriptor?: WidgetDescriptor): FormValues {
  return Object.fromEntries(
    (descriptor?.fields ?? [])
      .filter((field) => field.default !== null && field.default !== undefined)
      .map((field) => [field.name, field.default]),
  );
}

/** The `*_code` variables a template shows that have a translated twin.
 *
 *  `level_code` renders "low" and never changes with the display language —
 *  that is the point of it: a template compares against it, and a value that
 *  changed name with the language would break every widget in silence.
 *
 *  But the two sit side by side in the variable list, "code" reads as "the
 *  code for the level", and a clock then shows LOW under a French interface.
 *  It cost an hour to diagnose, on a matrix that was doing exactly what it
 *  was asked.
 */
export function untranslatedCodes(text: string, available: string[]): string[] {
  const used = new Set(
    [...text.matchAll(/\{\{([^{}]*)\}\}/g)].map((m) => m[1].split("|")[0].trim()),
  );
  return [...used].filter(
    (name) => name.endsWith("_code") && available.includes(name.slice(0, -5)),
  );
}

/** Whether a progress bar can do anything for this widget.
 *
 *  A bar needs a value out of 100, and most widgets carry none: a temperature
 *  or a price is not a fraction of anything. The switch was offered all the
 *  same, so ticking it on a Temperature widget did nothing at all — no
 *  message, no explanation.
 *
 *  Both sources are consulted, and each covers a case the other misses. The
 *  sample declares the *capability*, which keeps the switch available for the
 *  sun widget at night, when the real value is legitimately absent. The live
 *  value covers `device.metric`, whose answer depends on the metric picked: a
 *  battery has a bar, the same display's temperature has none.
 */
export function supportsProgress(
  sample: number | null | undefined,
  live: number | null | undefined,
): boolean {
  return sample != null || live != null;
}

/** Resolve a colour the way the renderer does.
 *
 *  An empty string counts as unset, which is what the text input stores when
 *  someone clears it — `??` would have kept it and painted nothing.
 */
export function resolveColour(
  typed: string | null | undefined,
  fromConnector: string | null | undefined,
  fallback: string,
): string {
  return typed || fromConnector || fallback;
}

export function WidgetBuilder({
  connectors,
  devices,
  widgetTypes,
  widget,
  seed,
  onSaved,
  onCancel,
}: Props) {
  const { t, tApi } = useI18n();
  const toast = useToast();

  // Where every field starts: the widget being edited, or the one being
  // copied. Only `widget` decides what the Save button does.
  const source = widget ?? seed;

  const [connectorId, setConnectorId] = useState<number | null>(
    source?.connector_id ?? connectors[0]?.id ?? null,
  );
  const connector = connectors.find((c) => c.id === connectorId);

  // Only the widgets the chosen service actually offers.
  const available = widgetTypes.filter((type) => type.type.startsWith(`${connector?.type}.`));
  const [widgetType, setWidgetType] = useState<string>(
    source?.widget_type ?? available[0]?.type ?? "",
  );
  const descriptor = widgetTypes.find((type) => type.type === widgetType);

  const [name, setName] = useState(
    widget ? widget.name : seed ? t("common.copyOf", { name: seed.name }) : "",
  );
  // A widget can appear on several clocks. The data is collected once and the
  // rendering computed once; only the push repeats.
  const [deviceIds, setDeviceIds] = useState<number[]>(
    source?.targets.map((target) => target.device_id) ?? (devices[0] ? [devices[0].id] : []),
  );
  const [refresh, setRefresh] = useState(
    source?.refresh_seconds ?? descriptor?.default_refresh ?? 60,
  );
  const [config, setConfig] = useState<FormValues>(
    source?.config ?? defaultsOf(descriptor),
  );
  // Initialised from the descriptor, not left null: otherwise the first render
  // shows "add a service first" although everything is ready.
  const [display, setDisplay] = useState<DisplayOptions | null>(
    source?.display ?? descriptor?.default_display ?? null,
  );
  const [advanced, setAdvanced] = useState(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const debounce = useRef<number | undefined>(undefined);

  // Switching service or widget type resets what belongs to the old one.
  useEffect(() => {
    if (!descriptor) return;
    // `source`, not `widget`: on mount this effect would otherwise overwrite
    // every field a copy had just borrowed with the descriptor's defaults.
    if (source) return;
    setDisplay(descriptor.default_display);
    setRefresh(descriptor.default_refresh);
    // A field that declares a default must arrive filled in. Leaving a
    // required select empty makes the form look broken and blocks saving.
    setConfig(defaultsOf(descriptor));
    setName((current) => current || descriptor.name);
  }, [widgetType, descriptor, source]);

  useEffect(() => {
    if (available.length && !available.some((type) => type.type === widgetType)) {
      setWidgetType(available[0].type);
    }
  }, [connectorId, available, widgetType]);

  // Debounced so typing in the text field does not fire a request per keystroke.
  useEffect(() => {
    if (!descriptor || !display) return;
    window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      api
        .previewWidget({
          widget_type: descriptor.type,
          display,
          config,
          connector_id: connectorId,
        })
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 300);
    return () => window.clearTimeout(debounce.current);
  }, [descriptor, display, config, connectorId]);

  function patch(changes: Partial<DisplayOptions>) {
    setDisplay((current) => (current ? { ...current, ...changes } : current));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!descriptor || !display || connectorId === null || deviceIds.length === 0) return;
    setBusy(true);
    try {
      const body = {
        name: name.trim() || descriptor.name,
        connector_id: connectorId,
        device_ids: deviceIds,
        widget_type: descriptor.type,
        config,
        display,
        refresh_seconds: refresh,
      };
      if (widget) {
        await api.updateWidget(widget.id, body);
      } else {
        await api.createWidget(body);
      }
      toast("success", t("builder.saved", { name: body.name }));
      onSaved();
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

  if (!display || !descriptor) {
    return (
      <Card className="p-4">
        <p className="text-sm text-[var(--color-text-muted)]">
          {t("widgets.needsPrerequisites")}
        </p>
      </Card>
    );
  }

  const icon = display.show_icon
    ? display.icon || preview?.data.hint_icon || null
    : null;

  // An 8x8 icon costs 9 of the 32 columns. Beyond what is left, AWTRIX
  // scrolls — which is fine, but it monopolises the app's slot, so it is
  // worth knowing before saving.
  const columnsFree = MATRIX_WIDTH - (icon ? 9 : 0);
  const columnsUsed = textWidth(preview?.text ?? "");
  const willScroll =
    columnsUsed > columnsFree && display.scroll_mode !== "static";

  // Asking for the identifier rather than the words is legitimate — it is
  // what a comparison needs — but it is almost never what someone typing a
  // display template means.
  const shownAsCode = untranslatedCodes(
    display.text ?? "",
    (descriptor?.variables ?? []).map((variable) => variable.name),
  );
  // What you typed, else what the connector proposes, else a default. The
  // backend applies exactly this chain, for the text and now for the bar —
  // one function rather than two copies, because the bar had drifted: the
  // matrix took the connector's colour while the preview kept firmware green.
  const colour = resolveColour(display.color, preview?.data.hint_color, "#3ddc84");
  const barColour = resolveColour(display.progress_color, preview?.data.hint_color, "#00ff00");

  const canShowProgress = supportsProgress(
    descriptor?.sample_data.progress,
    preview?.data.progress,
  );

  return (
    <form onSubmit={save} className="grid gap-4 lg:grid-cols-[1fr_20rem]">
      {/* ---------------- Configuration ---------------- */}
      <Card className="space-y-4 p-4">
        <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-faint)]">
          {t("builder.configuration")}
        </h3>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("builder.service")}>
            <NativeSelect
              value={String(connectorId ?? "")}
              onChange={(value) => setConnectorId(Number(value))}
              options={connectors.map((c) => ({ value: String(c.id), label: c.name }))}
            />
          </Field>
          <Field
            label={t("builder.widgetType")}
            hint={tApi(
              `widgetType.${descriptor.type}.description`,
              undefined,
              descriptor.description,
            )}
          >
            <NativeSelect
              value={widgetType}
              onChange={setWidgetType}
              options={available.map((type) => ({
                value: type.type,
                label: tApi(`widgetType.${type.type}.name`, undefined, type.name),
              }))}
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label={t("builder.name")}>
            <Input value={name} onChange={(event) => setName(event.target.value)} required />
          </Field>
          <Field label={t("builder.devices")} hint={t("builder.devicesHelp")}>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {devices.map((device) => {
                const on = deviceIds.includes(device.id);
                return (
                  <button
                    key={device.id}
                    type="button"
                    onClick={() =>
                      setDeviceIds(
                        on
                          ? deviceIds.filter((id) => id !== device.id)
                          : [...deviceIds, device.id],
                      )
                    }
                    className={`rounded-full border px-2.5 py-1 text-xs transition ${
                      on
                        ? "border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                        : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                    }`}
                  >
                    {device.name}
                  </button>
                );
              })}
            </div>
          </Field>
          <Field label={t("builder.refresh")} hint={t("builder.seconds")}>
            <Input
              type="number"
              min={5}
              max={86400}
              value={refresh}
              onChange={(event) => setRefresh(Number(event.target.value) || 60)}
            />
          </Field>
        </div>

        {descriptor.fields.length > 0 && (
          <SchemaForm
            fields={descriptor.fields}
            values={config}
            onChange={setConfig}
            connectorId={connectorId ?? undefined}
            devices={devices}
            namespace={descriptor.type}
          />
        )}

        <hr className="border-[var(--color-border)]" />

        <Field label={t("builder.text")} hint={t("builder.textHelp")}>
          <Input
            value={display.text}
            onChange={(event) => patch({ text: event.target.value })}
            className="font-mono"
          />
        </Field>

        <div className="space-y-2">
          <Toggle
            label={t("builder.showIcon")}
            checked={display.show_icon}
            onChange={(show_icon) => patch({ show_icon })}
          />
          {display.show_icon && (
            <Field label={t("builder.icon")} hint={t("builder.iconHelp")}>
              <IconPicker
                value={display.icon}
                autoIcon={preview?.data.hint_icon ?? null}
                onChange={(value) => patch({ icon: value })}
              />
            </Field>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("builder.color")} hint={t("builder.colorHelp")}>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={colour}
                onChange={(event) => patch({ color: event.target.value })}
                className="h-8 w-10 shrink-0 cursor-pointer rounded border border-[var(--color-border)] bg-transparent"
              />
              <Input
                value={display.color ?? ""}
                placeholder={preview?.data.hint_color ?? "#3ddc84"}
                onChange={(event) => patch({ color: event.target.value || null })}
              />
              {display.color && (
                <Button
                  type="button"
                  className="shrink-0"
                  title={t("builder.colorAutoHint")}
                  onClick={() => patch({ color: null })}
                >
                  {t("builder.colorAuto")}
                </Button>
              )}
            </div>
          </Field>
          <Field label={t("builder.duration")} hint={t("builder.seconds")}>
            <Input
              type="number"
              min={1}
              max={120}
              value={display.duration}
              onChange={(event) => patch({ duration: Number(event.target.value) || 7 })}
            />
          </Field>
        </div>

        <button
          type="button"
          onClick={() => setAdvanced(!advanced)}
          className="text-xs text-[var(--color-text-muted)] underline-offset-2 hover:underline"
        >
          {advanced ? "▾" : "▸"} {t("builder.advanced")}
        </button>

        {advanced && (
          <div className="space-y-4 rounded-lg bg-[var(--color-surface-2)] p-3">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("builder.scrollMode")} hint={t("builder.scrollModeHelp")}>
                <NativeSelect
                  value={display.scroll_mode}
                  onChange={(value) => patch({ scroll_mode: value as ScrollMode })}
                  options={SCROLL_MODES.map((mode) => ({
                    value: mode,
                    label: t(`builder.scrollMode.${mode}`),
                  }))}
                />
              </Field>
              <Field label={t("builder.scrollSpeed")} hint="%">
                <Input
                  type="number"
                  min={0}
                  max={500}
                  value={display.scroll_speed}
                  onChange={(event) =>
                    patch({ scroll_speed: Number(event.target.value) || 100 })
                  }
                />
              </Field>
              <Field label={t("builder.iconMode")} hint={t("builder.iconModeHelp")}>
                <NativeSelect
                  value={display.icon_mode}
                  onChange={(value) => patch({ icon_mode: value as IconMode })}
                  options={ICON_MODES.map((mode) => ({
                    value: mode,
                    label: t(`builder.iconMode.${mode}`),
                  }))}
                />
              </Field>
              <Field label={t("builder.font")} hint={t("builder.fontHelp")}>
                <NativeSelect
                  value={display.font}
                  onChange={(value) => patch({ font: value as Font })}
                  options={FONTS.map((name) => ({
                    value: name,
                    label: t(`builder.font.${name}`),
                  }))}
                />
              </Field>
              <Field label={t("builder.textCase")}>
                <NativeSelect
                  value={display.text_case}
                  onChange={(value) => patch({ text_case: value as TextCase })}
                  options={TEXT_CASES.map((mode) => ({
                    value: mode,
                    label: t(`builder.textCase.${mode}`),
                  }))}
                />
              </Field>
              <Field label={t("builder.overlay")} hint={t("builder.overlayHelp")}>
                <NativeSelect
                  value={display.overlay ?? ""}
                  onChange={(value) => patch({ overlay: value || null })}
                  options={[
                    // Empty means "whatever the service proposes", the same
                    // rule the icon and the colour already follow. The weather
                    // connector reads it off the WMO code; the others propose
                    // nothing, and nothing is drawn.
                    { value: "", label: t("builder.overlayAuto") },
                    ...OVERLAYS.map((name) => ({
                      value: name,
                      label: t(`builder.overlay.${name}` as MessageKey),
                    })),
                  ]}
                />
              </Field>
              <Field label={t("builder.background")}>
                <Input
                  value={display.background ?? ""}
                  placeholder="#000000"
                  onChange={(event) => patch({ background: event.target.value || null })}
                />
              </Field>
            </div>
            {display.show_progress && canShowProgress && (
              <Field label={t("builder.progressColor")} hint={t("builder.progressColorHelp")}>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={barColour}
                    onChange={(event) => patch({ progress_color: event.target.value })}
                    className="h-8 w-10 shrink-0 cursor-pointer rounded border border-[var(--color-border)] bg-transparent"
                  />
                  <Input
                    value={display.progress_color ?? ""}
                    placeholder={preview?.data.hint_color ?? "#00ff00"}
                    onChange={(event) =>
                      patch({ progress_color: event.target.value || null })
                    }
                  />
                </div>
              </Field>
            )}

            <div className="flex flex-wrap gap-4 text-sm text-[var(--color-text-muted)]">
              <Toggle
                label={t("builder.showOverlay")}
                hint={t("builder.showOverlayHelp")}
                checked={display.show_overlay}
                onChange={(show_overlay) => patch({ show_overlay })}
              />
              <Toggle
                label={t("builder.showProgress")}
                disabled={!canShowProgress}
                hint={canShowProgress ? undefined : t("builder.noProgressHere")}
                checked={display.show_progress}
                onChange={(show_progress) => patch({ show_progress })}
              />
              <Toggle
                label={t("builder.hideWhenEmpty")}
                checked={display.hide_when_empty}
                onChange={(hide_when_empty) => patch({ hide_when_empty })}
              />
            </div>
          </div>
        )}
      </Card>

      {/* ---------------- Live preview ---------------- */}
      <Card className="space-y-3 self-start p-4">
        <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-faint)]">
          {t("builder.livePreview")}
        </h3>

        <div className="flex justify-center rounded-md border border-[var(--color-border)] bg-[var(--color-matrix-bg)] p-2">
          <AwtrixMatrixPreview
            text={preview?.text ?? ""}
            icon={icon}
            iconUrl={icon && /^\d+$/.test(icon) ? iconThumbnail(icon) : null}
            color={colour}
            background={display.background}
            font={display.font}
            noScroll={display.scroll_mode === "static"}
            scrollSpeed={display.scroll_speed}
            progress={
              display.show_progress && preview?.data.progress !== null
                ? (preview?.data.progress ?? null)
                : null
            }
            progressColor={barColour}
            progressBackground={display.progress_background}
            scale={7}
          />
        </div>

        <p className="text-center text-xs text-[var(--color-text-faint)]">
          {preview?.sample ? t("builder.sampleData") : t("builder.liveData")}
          <span className="ml-2 font-mono">
            {columnsUsed}/{columnsFree}
          </span>
        </p>

        {shownAsCode.length > 0 && (
          <p className="rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 px-2 py-1.5 text-xs text-[var(--color-warning)]">
            {t("builder.showsAnIdentifier", {
              code: shownAsCode.map((name) => `{{ ${name} }}`).join(", "),
              instead: shownAsCode.map((name) => `{{ ${name.slice(0, -5)} }}`).join(", "),
            })}
          </p>
        )}

        {willScroll && (
          <p className="rounded-lg border border-[var(--color-info)]/30 bg-[var(--color-info)]/10 px-2 py-1.5 text-xs text-[var(--color-info)]">
            {t("builder.willScroll")}
          </p>
        )}

        {preview?.warning_code && (
          <p className="rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 px-2 py-1.5 text-xs text-[var(--color-warning)]">
            {t("builder.previewFallback")}
          </p>
        )}
        {preview && preview.payload === null && (
          <p className="text-xs text-[var(--color-text-muted)]">{t("builder.hidden")}</p>
        )}

        {descriptor.variables.length > 0 && (
          <div>
            <p className="mb-1.5 text-[10px] uppercase tracking-wide text-[var(--color-text-faint)]">
              {t("builder.variables")}
            </p>
            <div className="flex flex-wrap gap-1">
              {descriptor.variables.map((variable) => (
                <button
                  key={variable.name}
                  type="button"
                  // Le libellé seul ne distingue pas la prose de l'identifiant ;
                  // l'exemple, lui, saute aux yeux : « Couvert » face à
                  // « overcast ».
                  title={`${tApi(
                    `variable.${descriptor.type}.${variable.name}`,
                    undefined,
                    variable.label,
                  )} — ex. : ${variable.example}`}
                  onClick={() => patch({ text: `${display.text}{{ ${variable.name} }}` })}
                  className="rounded border border-[var(--color-border)] px-1.5 py-0.5 font-mono text-[10px]
                    text-[var(--color-text-muted)] transition hover:border-[var(--color-accent)]/50
                    hover:text-[var(--color-text)]"
                >
                  {variable.name}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <Button
            type="submit"
            variant="primary"
            loading={busy}
            disabled={deviceIds.length === 0}
            className="flex-1"
          >
            {widget ? t("builder.update") : t("builder.save")}
          </Button>
          <Button type="button" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
        </div>
      </Card>
    </form>
  );
}

