import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type {
  ConnectorInstance,
  Device,
  WidgetDescriptor,
  WidgetInstance,
} from "../../api/client";
import { useToast } from "../../components/Toast";
import { CardIcon } from "../../components/CardIcon";
import { Button, Card, EmptyState, StatusBadge } from "../../components/ui";
import { useI18n } from "../../i18n";
import { WidgetBuilder } from "./WidgetBuilder";

export function WidgetsPage() {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [widgets, setWidgets] = useState<WidgetInstance[] | null>(null);
  const [connectors, setConnectors] = useState<ConnectorInstance[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [types, setTypes] = useState<WidgetDescriptor[]>([]);
  // `seed` copies a widget's settings into a new one. Apart from `widget`,
  // which is what the builder reads to decide between PATCH and POST.
  const [editor, setEditor] = useState<{
    widget?: WidgetInstance;
    seed?: WidgetInstance;
  } | null>(null);
  //: True once the order was changed but not yet pushed to the displays.
  const [orderPending, setOrderPending] = useState(false);
  const [applying, setApplying] = useState(false);
  const editorRef = useRef<HTMLDivElement>(null);

  // The builder opens above the list. Editing a widget near the bottom would
  // otherwise look like nothing happened at all.
  useEffect(() => {
    if (editor) editorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [editor]);

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
      const [list, configured, deviceList, descriptors] = await Promise.all([
        api.listWidgets(),
        api.listConnectors(),
        api.listDevices(),
        api.widgetTypes(),
      ]);
      setWidgets(list);
      setConnectors(configured);
      setDevices(deviceList);
      setTypes(descriptors);
    } catch (error) {
      fail(error);
      setWidgets([]);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ready = connectors.length > 0 && devices.length > 0;

  /** Cheap: writes positions only. The displays keep their order until
   *  applyOrder rebuilds them. */
  async function move(index: number, delta: number) {
    if (!widgets) return;
    const next = [...widgets];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setWidgets(next);
    setOrderPending(true);
    try {
      await api.setWidgetOrder(next.map((widget) => widget.id));
    } catch (error) {
      fail(error);
      void load();
    }
  }

  /** The expensive half: AWTRIX keeps an app where it first landed, so the
   *  rotation has to be torn down and rebuilt. */
  async function applyOrder() {
    setApplying(true);
    try {
      const targeted = new Set(
        (widgets ?? []).flatMap((widget) => widget.targets.map((t) => t.device_id)),
      );
      for (const deviceId of targeted) {
        await api.reorderDevice(deviceId);
      }
      toast("success", t("widgets.orderApplied", { count: targeted.size }));
      setOrderPending(false);
    } catch (error) {
      fail(error);
    } finally {
      setApplying(false);
      void load();
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-medium">{t("widgets.title")}</h2>
          <p className="text-sm text-[var(--color-text-muted)]">{t("widgets.subtitle")}</p>
        </div>
        {!editor && ready && (
          <div className="flex flex-wrap items-center gap-2">
            {orderPending && (
              <Button
                onClick={applyOrder}
                loading={applying}
                title={t("widgets.applyOrderHint")}
              >
                {t("widgets.applyOrder")}
              </Button>
            )}
            <Button variant="primary" onClick={() => setEditor({})}>
              + {t("widgets.add")}
            </Button>
          </div>
        )}
      </header>

      {editor && (
        <div ref={editorRef}>
          <WidgetBuilder
            // Remount when the edited widget changes. Without it, React keeps
            // the same instance and its state — the form would still hold the
            // previous widget's name, template and icon while saving to the
            // new one. That is how a widget ended up overwritten by another.
            // The copied id belongs in the key too: duplicating one widget and
            // then another both read "new", and the second form would open on
            // the first one's settings.
            key={editor.widget?.id ?? (editor.seed ? `copy-${editor.seed.id}` : "new")}
            connectors={connectors}
            devices={devices}
            widgetTypes={types}
            seed={editor.seed}
            widget={editor.widget}
            onSaved={() => {
              setEditor(null);
              void load();
            }}
            onCancel={() => setEditor(null)}
          />
        </div>
      )}

      {widgets === null && (
        <p className="text-sm text-[var(--color-text-faint)]">{t("common.loading")}</p>
      )}

      {widgets?.length === 0 && !editor && (
        <EmptyState
          title={t("widgets.emptyTitle")}
          description={ready ? t("widgets.emptyBody") : t("widgets.needsPrerequisites")}
          action={
            ready ? (
              <Button variant="primary" onClick={() => setEditor({})}>
                {t("widgets.add")}
              </Button>
            ) : undefined
          }
        />
      )}

      {orderPending && (
        <p className="rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 px-3 py-2 text-xs text-[var(--color-warning)]">
          {t("widgets.orderPending")}
        </p>
      )}

      <div className="space-y-3">
        {widgets?.map((widget, index) => (
          <WidgetCard
            key={widget.id}
            widget={widget}
            onMoveUp={index > 0 ? () => move(index, -1) : undefined}
            onMoveDown={index < widgets.length - 1 ? () => move(index, 1) : undefined}
            descriptor={types.find((type) => type.type === widget.widget_type)}
            devices={devices}
            onChanged={load}
            onEdit={() => setEditor({ widget })}
            onDuplicate={() => setEditor({ seed: widget })}
            onError={fail}
          />
        ))}
      </div>
    </div>
  );
}

function WidgetCard({
  widget,
  devices,
  descriptor,
  onChanged,
  onEdit,
  onDuplicate,
  onError,
  onMoveUp,
  onMoveDown,
}: {
  widget: WidgetInstance;
  devices: Device[];
  descriptor?: WidgetDescriptor;
  onChanged: () => void;
  onEdit: () => void;
  onDuplicate: () => void;
  onError: (error: unknown) => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
}) {
  const { t, tApi } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const updated = await api.refreshWidget(widget.id);
      toast(
        updated.status === "healthy" ? "success" : "error",
        updated.last_error_code
          ? tApi(updated.last_error_code, undefined, updated.last_error ?? "")
          : `${widget.name} — ${t("widgets.refreshed")}`,
      );
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  async function toggle() {
    setBusy(true);
    try {
      // Disabling removes the app from the matrix: the scheduler reconciles
      // straight away rather than leaving it there until the next pass.
      await api.updateWidget(widget.id, { enabled: !widget.enabled });
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  async function remove() {
    if (!confirm(t("widgets.confirmDelete", { name: widget.name }))) return;
    try {
      await api.deleteWidget(widget.id);
      toast("success", t("widgets.deleted", { name: widget.name }));
      onChanged();
    } catch (error) {
      onError(error);
    }
  }

  const error = widget.last_error_code
    ? tApi(widget.last_error_code, undefined, widget.last_error ?? "")
    : widget.last_error;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3 p-4">
        {/* Position in the rotation. Moving is cheap; applying is not. */}
        <div className="flex shrink-0 flex-col gap-0.5 pt-0.5">
          <button
            type="button"
            onClick={onMoveUp}
            disabled={!onMoveUp}
            aria-label={t("widgets.moveUp")}
            title={t("widgets.moveUp")}
            className="rounded px-1.5 text-xs text-[var(--color-text-muted)] transition
              hover:text-[var(--color-text)] disabled:opacity-25"
          >
            ▲
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            disabled={!onMoveDown}
            aria-label={t("widgets.moveDown")}
            title={t("widgets.moveDown")}
            className="rounded px-1.5 text-xs text-[var(--color-text-muted)] transition
              hover:text-[var(--color-text)] disabled:opacity-25"
          >
            ▼
          </button>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {/* Before the name, not after: the eye reaches the icon first and
                the title reads as its label, which is how the reminder list
                already did it. */}
            <CardIcon
              icon={widget.last_icon ?? (widget.display.icon as string | null)}
            />
            <h3 className="truncate font-medium">{widget.name}</h3>
            <StatusBadge status={widget.enabled ? widget.status : "disabled"} />
            {widget.targets.length > 0 && (
              <span className="text-xs text-[var(--color-text-faint)]">
                {t("widgets.onDisplays", {
                  online: widget.targets.filter((t) => t.status === "healthy").length,
                  total: widget.targets.length,
                })}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            {descriptor
              ? tApi(`widgetType.${descriptor.type}.name`, undefined, descriptor.name)
              : widget.widget_type}
            {` · ${t("widgets.every", { seconds: widget.refresh_seconds })}`}
            {` · ${widget.app_name}`}
          </p>
        </div>
      </div>

      {error && (
        <p className="mx-4 mb-3 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]">
          {error}
        </p>
      )}

      {/* A widget can end up targeting nothing — its last display was deleted,
          or none was picked. It then collects nothing and shows nowhere, which
          "0 / 0" states without explaining. */}
      {widget.targets.length === 0 && (
        <p className="mx-4 mb-3 rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10 px-3 py-2 text-xs text-[var(--color-warning)]">
          {t("widgets.noDisplay")}
        </p>
      )}

      {/* One line per display: the same widget can be fine on one clock and
          failing on another, and a single badge would hide that. */}
      <ul className="mx-4 mb-3 space-y-1">
        {widget.targets.map((target) => {
          const device = devices.find((d) => d.id === target.device_id);
          const targetError = target.last_error_code
            ? tApi(target.last_error_code, undefined, target.last_error ?? "")
            : target.last_error;
          return (
            <li
              key={target.device_id}
              className="flex flex-wrap items-center gap-2 rounded-lg bg-[var(--color-surface-2)] px-3 py-1.5 text-xs"
            >
              <StatusBadge status={widget.enabled ? target.status : "disabled"} />
              <span>{device?.name ?? `#${target.device_id}`}</span>
              <span className="ml-auto font-mono text-[10px] text-[var(--color-text-faint)]">
                {target.last_pushed_at
                  ? new Date(target.last_pushed_at).toLocaleTimeString()
                  : t("widgets.neverPushed")}
              </span>
              {targetError && (
                <span className="w-full text-[var(--color-danger)]">{targetError}</span>
              )}
            </li>
          );
        })}
      </ul>

      <div className="flex flex-wrap gap-2 border-t border-[var(--color-border)] px-4 py-3">
        <Button onClick={toggle} loading={busy}>
          {widget.enabled ? t("widgets.disable") : t("widgets.enable")}
        </Button>
        <Button onClick={refresh} loading={busy} disabled={!widget.enabled}>
          {t("widgets.refresh")}
        </Button>
        <Button onClick={onDuplicate}>{t("common.duplicate")}</Button>
        <Button onClick={onEdit}>{t("common.edit")}</Button>
        <Button variant="danger" onClick={remove} className="ml-auto">
          {t("common.delete")}
        </Button>
      </div>
    </Card>
  );
}
