/** awtrixng-mgr API client. Single origin, so no base URL. */

import type { Params } from "../i18n";

export type HealthStatus = "unknown" | "healthy" | "degraded" | "error" | "disabled";

export interface Device {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string | null;
  has_password: boolean;
  enabled: boolean;
  firmware: string | null;
  uid: string | null;
  status: HealthStatus;
  last_seen: string | null;
  last_error: string | null;
  last_error_code: string | null;
}

/** What `GET /api/v1/device` reports, as the backend passes it on.
 *
 *  These are AWTRIX NG's names, not AWTRIX 3's renamed, and the difference is
 *  not cosmetic: a card still reading `bat`, `temp` and `hum` compiled
 *  perfectly and showed a dash in every tile, because the fields it asked for
 *  no longer exist. TypeScript cannot catch that — the backend's shape is not
 *  its business — so the tiles are pinned by a test against a real device
 *  response instead.
 *
 *  The set mirrors what the display's own web interface shows, so the two can
 *  be compared side by side without translating anything. */
export interface DeviceState {
  version?: string;
  uid?: string;
  hostname?: string;
  ip_address?: string;
  board_type?: string;
  current_app?: string;
  uptime_seconds?: number;
  free_heap_bytes?: number;
  reset_reason?: string;
  wifi_rssi?: number;
  fps?: number;
  brightness?: number;
  matrix_power?: boolean;
  light_level?: number;
  ldr_raw?: number;
  battery_percent?: number;
  battery_voltage?: number;
  low_battery?: boolean;
  temperature?: number;
  humidity?: number;
}

export interface TestResult {
  ok: boolean;
  /** English, readable on its own. Use `code` to translate. */
  message: string;
  code: string;
  params?: Params;
  firmware?: string | null;
  uid?: string | null;
  stats?: DeviceState | null;
}

// -- Connectors and widgets --------------------------------------------------

export type FieldType =
  | "text"
  | "number"
  | "boolean"
  | "select"
  | "multiselect"
  | "remote_select"
  | "remote_multiselect"
  | "secret"
  | "url"
  | "duration"
  | "color"
  | "template"
  | "place"
  | "device";

export interface FieldOption {
  value: string;
  label: string;
  hint?: string | null;
}

export interface FormField {
  name: string;
  label: string;
  type: FieldType;
  required: boolean;
  default: unknown;
  help?: string | null;
  placeholder?: string | null;
  options?: FieldOption[] | null;
  source?: string | null;
  depends_on?: string[] | null;
  min?: number | null;
  max?: number | null;
  unit?: string | null;
}

export interface Variable {
  name: string;
  label: string;
  example?: string | null;
}

/** Named modes, measured on a TC001 running NG 1.1.2: the firmware lists its
 *  own vocabulary in the 422 it answers with. AWTRIX 3 used integers here. */
export type IconMode = "fixed" | "pushOnce" | "push";
export type TextCase = "inherit" | "upper" | "asTyped";
export type ScrollMode = "wrap" | "bounce" | "static" | "loop";
export type ScrollWhenFits = "static" | "scroll";

export const ICON_MODES: IconMode[] = ["fixed", "pushOnce", "push"];
export const TEXT_CASES: TextCase[] = ["inherit", "upper", "asTyped"];
export const SCROLL_MODES: ScrollMode[] = ["wrap", "bounce", "static", "loop"];
export const SCROLL_WHEN_FITS: ScrollWhenFits[] = ["static", "scroll"];

/** The user's presentation choices.
 *
 *  Three options the previous project offered are gone, each because the
 *  firmware was asked and does not have it: `center` (no centring key at all),
 *  `rainbow` (`palette` colours effects, not text — pushed and read back off
 *  the matrix), and `no_scroll` (now `scroll_mode: "static"`). A control the
 *  firmware ignores is worse than no control. */
export interface DisplayOptions {
  text: string;
  icon: string | null;
  show_icon: boolean;
  color: string | null;
  /** Seconds. Converted to the firmware's milliseconds on the way out. */
  duration: number;
  background: string | null;
  effect: string | null;
  /** Weather drawn by the firmware over the text. New in NG; the display
   *  lists the ones it supports in its capabilities. */
  overlay: string | null;
  repeat: number | null;
  icon_mode: IconMode;
  text_case: TextCase;
  scroll_mode: ScrollMode;
  scroll_speed: number;
  scroll_when_fits: ScrollWhenFits;
  show_progress: boolean;
  progress_color: string | null;
  progress_background: string;
  show_series: "none" | "bar" | "line";
  hide_when_empty: boolean;
}

export interface WidgetData {
  values: Record<string, unknown>;
  status: "ok" | "empty" | "degraded";
  hint_icon: string | null;
  hint_color: string | null;
  progress: number | null;
  series: number[] | null;
  fetched_at: string;
}

export interface WidgetDescriptor {
  type: string;
  name: string;
  description: string;
  fields: FormField[];
  variables: Variable[];
  default_display: DisplayOptions;
  sample_data: WidgetData;
  default_refresh: number;
}

export interface ConnectorDescriptor {
  id: string;
  name: string;
  description: string;
  icon: string;
  config_schema: FormField[];
  widgets: WidgetDescriptor[];
  requires_credentials: boolean;
}

export interface ConnectorInstance {
  id: number;
  type: string;
  name: string;
  config: Record<string, unknown>;
  secrets_set: string[];
  enabled: boolean;
  status: HealthStatus;
  last_success: string | null;
  last_error: string | null;
  last_error_code: string | null;
  consecutive_failures: number;
}

export interface ConnectorTestResult {
  ok: boolean;
  message: string;
  code: string;
  params?: Params;
  details?: Record<string, unknown>;
}

/** One display a widget appears on, with its own state. */
export interface WidgetTarget {
  device_id: number;
  status: HealthStatus;
  last_error: string | null;
  last_error_code: string | null;
  last_pushed_at: string | null;
}

export interface WidgetInstance {
  id: number;
  name: string;
  connector_id: number;
  targets: WidgetTarget[];
  widget_type: string;
  config: Record<string, unknown>;
  /** Always a complete DisplayOptions: the backend serialises the whole model. */
  display: DisplayOptions;
  refresh_seconds: number;
  enabled: boolean;
  status: HealthStatus;
  last_success: string | null;
  last_error: string | null;
  last_error_code: string | null;
  app_name: string;
  /** The icon last pushed — the connector's own when none was chosen. */
  last_icon: string | null;
}

export interface Place {
  label: string;
  name: string;
  region: string | null;
  country: string | null;
  country_code: string | null;
  latitude: number;
  longitude: number;
  timezone: string | null;
}

/** What a `place` field stores in a connector's configuration. */
export interface PlaceValue {
  name: string;
  latitude: number;
  longitude: number;
}

export interface BackupSummary {
  ok: boolean;
  message: string;
  code: string;
  exported_at: string | null;
  /** Version of awtrixng-mgr that wrote the file. */
  app_version: string | null;
  devices: number;
  connectors: number;
  widgets: number;
  /** How many credentials the file carries. */
  secrets: number;
}

export interface RestoreResult {
  ok: boolean;
  message: string;
  code: string;
  devices: number;
  connectors: number;
  widgets: number;
  secrets: number;
}

/** A window where a display is dimmed and its buzzer silenced.
 *
 *  Kept by awtrixng-mgr, not by the clock: the firmware has no schedule of any
 *  kind. Its only brightness controls are a manual level, one driven by the
 *  light sensor, and a deep sleep that turns the matrix off.
 */
export interface BedroomMode {
  enabled: boolean;
  /** "22:00:00". The window may cross midnight. */
  start: string;
  end: string;
  /** 0-255, like the firmware's own. */
  brightness: number;
  /** True while the window is applied. Read-only — the scheduler owns it. */
  active: boolean;
}

/** The firmware names them; awtrixng-mgr showed a number until it noticed. */
export const TRANSITION_EFFECTS = [
  "Random", "Slide", "Dim", "Zoom", "Rotate", "Pixelate",
  "Curtain", "Ripple", "Blink", "Reload", "Fade",
] as const;

/** What the display itself is set to, as opposed to what awtrixng-mgr puts on it.
 *
 *  Fourteen of the thirty-nine keys a v0.98 exposes. The rest are left alone —
 *  colour calibration with an undocumented range is how a matrix ends up
 *  unreadable with no way back from a web form.
 */
/** What the installation decides for itself, as opposed to each browser. */
export interface AppSettings {
  /** The language of the words pushed to the matrix. Not the interface
   *  language: that one lives in each browser, because two people may read
   *  the same installation in two languages. */
  language: "en" | "fr";
}

export interface DeviceSettings {
  /** On, the firmware recomputes the brightness from the light sensor and
   *  whatever `brightness` holds is overwritten within seconds. */
  auto_brightness: boolean;
  /** 0-255. */
  brightness: number;
  /** 0-30, not 0-100. Reads as a percentage and is not one. */
  volume: number;
  /** Seconds — but only for an app that asked for no duration of its own, and
   *  every widget awtrixng-mgr pushes asks. So: the built-in apps, not yours. */
  app_seconds: number;
  auto_transition: boolean;
  /** 0-10. The firmware names them nowhere, so neither does awtrixng-mgr. */
  transition_effect: number;
  transition_ms: number;
  /** Percentage of the firmware's own speed. */
  scroll_speed: number;
  uppercase: boolean;
  celsius: boolean;
  time_format: string;
  date_format: string;
  week_starts_monday: boolean;
  show_weekday: boolean;
}

export interface DeviceSettingsResult {
  ok: boolean;
  message: string;
  code: string;
  settings: DeviceSettings;
  /** Firmware keys actually written. Empty when nothing differed. */
  applied: string[];
}

/** Exactly what the firmware accepts; anything else it ignores in silence. */
export const TIME_FORMATS = [
  "%H:%M:%S", "%l:%M:%S", "%H:%M", "%H %M",
  "%l:%M", "%l %M", "%l:%M %p", "%l %M %p",
] as const;
export const DATE_FORMATS = [
  "%d.%m.%y", "%d.%m", "%y-%m-%d", "%m-%d",
  "%m/%d/%y", "%m/%d", "%d/%m/%y", "%d/%m", "%m-%d-%y",
] as const;

/** One app on the display. `origin` is NG's own word for where it came from:
 *  "builtin" is the firmware's, "pushed" is ours or another tool's. */
export interface DeviceApp {
  name: string;
  enabled: boolean | null;
  inLoop: boolean | null;
  slot: number | null;
  present: boolean | null;
  origin: string | null;
}

/** Panel state. `power` is the only honest answer to "is anything visible?" —
 *  a display whose panel is off still returns a full framebuffer. */
export interface DisplayState {
  power: boolean;
  brightness: number;
  overlay: string | null;
}

export interface Icon {
  id: number;
  title: string;
  animated: boolean;
  thumbnail: string;
  filename: string;
}

export interface InstallResult {
  ok: boolean;
  message: string;
  code: string;
  filename: string | null;
}

export interface PreviewResponse {
  payload: Record<string, unknown> | null;
  text: string;
  data: WidgetData;
  sample: boolean;
  warning: string | null;
  warning_code: string | null;
}

export interface DeviceInput {
  name: string;
  host: string;
  port?: number;
  username?: string | null;
  password?: string | null;
  enabled?: boolean;
}

/**
 * An API failure, carrying the translatable code alongside the English text.
 * Components render it with `tApi(error.code, error.params, error.message)`.
 */
export interface AuthStatus {
  /** False when no password is configured: the application stays open. */
  required: boolean;
  authenticated: boolean;
}

export interface AuthResult {
  ok: boolean;
  message: string;
  code: string;
}

export interface Reminder {
  id: number;
  name: string;
  message: string;
  icon: string | null;
  color: string | null;
  /** "07:30:00" */
  at: string;
  /** Monday is 0. */
  days: number[];
  /** 1 = every week, 2 = every other, and so on. */
  every_weeks: number;
  /** Any day of a week it fires on; only the week matters. "2026-10-11" */
  anchor: string | null;
  /** Set, it rings that day only and `days`/`every_weeks` are ignored. */
  on_date: string | null;
  /** Set, the message may use {{ countdown }}, {{ days }} and {{ date }}. */
  countdown_to: string | null;
  duration_seconds: number;
  /** The display options a widget also has. Those a reminder cannot use —
   *  progress bar, hide-when-empty — are deliberately absent: it carries no
   *  data to measure or to miss. */
  scroll_mode: ScrollMode;
  scroll_speed: number;
  background: string | null;
  repeat_count: number;
  repeat_every_minutes: number;
  melody: string | null;
  /** Keeps its melody while the display is in bedroom mode. */
  rings_at_night: boolean;
  enabled: boolean;
  device_ids: number[];
  last_fired_at: string | null;
  next_at: string | null;
}

export type ReminderInput = Omit<
  Reminder,
  "id" | "last_fired_at" | "next_at"
>;

export class ApiError extends Error {
  readonly code: string;
  readonly params?: Params;

  constructor(message: string, code: string, params?: Params) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.params = params;
  }
}

/**
 * Called whenever the API refuses for lack of a session. The gate registers
 * itself here, so a session that ends mid-visit sends the whole application
 * back to the login screen instead of leaving pages that silently fail.
 */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("awtrixng-mgr is unreachable.", "api.unreachable");
  }

  if (response.status === 204) return undefined as T;

  const body = await response.text();
  const parsed = body ? JSON.parse(body) : null;

  if (!response.ok) {
    if (response.status === 401) onUnauthorized?.();
    const detail = parsed?.detail;
    throw new ApiError(
      typeof detail === "string" ? detail : `Error ${response.status}.`,
      typeof parsed?.code === "string" ? parsed.code : "api.httpError",
      parsed?.params ?? { status: response.status },
    );
  }
  return parsed as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/health"),

  authStatus: () => request<AuthStatus>("/auth/status"),
  login: (password: string) =>
    request<AuthResult>("/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<AuthResult>("/auth/logout", { method: "POST" }),

  listReminders: () => request<Reminder[]>("/reminders"),
  createReminder: (input: ReminderInput) =>
    request<Reminder>("/reminders", { method: "POST", body: JSON.stringify(input) }),
  updateReminder: (id: number, input: Partial<ReminderInput>) =>
    request<Reminder>(`/reminders/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  deleteReminder: (id: number) => request<void>(`/reminders/${id}`, { method: "DELETE" }),
  fireReminder: (id: number) =>
    request<TestResult>(`/reminders/${id}/fire`, { method: "POST" }),

  listDevices: () => request<Device[]>("/devices"),
  createDevice: (input: DeviceInput) =>
    request<Device>("/devices", { method: "POST", body: JSON.stringify(input) }),
  updateDevice: (id: number, input: Partial<DeviceInput>) =>
    request<Device>(`/devices/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  deleteDevice: (id: number) => request<void>(`/devices/${id}`, { method: "DELETE" }),
  testDevice: (id: number) => request<TestResult>(`/devices/${id}/test`, { method: "POST" }),
  notifyDevice: (id: number, payload: Record<string, unknown>) =>
    request<TestResult>(`/devices/${id}/notify`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  exportBackup: () => request<Record<string, unknown>>("/backup"),
  inspectBackup: (file: unknown) =>
    request<BackupSummary>("/backup/inspect", {
      method: "POST",
      body: JSON.stringify(file),
    }),
  restoreBackup: (file: unknown) =>
    request<RestoreResult>("/backup/restore", {
      method: "POST",
      body: JSON.stringify(file),
    }),

  bedroom: (id: number) => request<BedroomMode>(`/devices/${id}/bedroom`),
  setBedroom: (id: number, mode: BedroomMode) =>
    request<BedroomMode>(`/devices/${id}/bedroom`, {
      method: "PUT",
      body: JSON.stringify(mode),
    }),
  settings: () => request<AppSettings>("/settings"),
  setSettings: (settings: AppSettings) =>
    request<AppSettings>("/settings", { method: "PUT", body: JSON.stringify(settings) }),
  deviceSettings: (id: number) => request<DeviceSettings>(`/devices/${id}/settings`),
  setDeviceSettings: (id: number, settings: DeviceSettings) =>
    request<DeviceSettingsResult>(`/devices/${id}/settings`, {
      method: "POST",
      body: JSON.stringify(settings),
    }),
  deviceApps: (id: number) => request<DeviceApp[]>(`/devices/${id}/apps`),
  deviceDisplay: (id: number) => request<DisplayState>(`/devices/${id}/display`),
  setDevicePower: (id: number, on: boolean) =>
    request<{ ok: boolean; power: boolean }>(`/devices/${id}/power?on=${on}`, {
      method: "POST",
    }),

  connectorTypes: () => request<ConnectorDescriptor[]>("/connector-types"),
  listConnectors: () => request<ConnectorInstance[]>("/connectors"),
  createConnector: (input: {
    type: string;
    name: string;
    config: Record<string, unknown>;
    secrets: Record<string, string>;
  }) => request<ConnectorInstance>("/connectors", { method: "POST", body: JSON.stringify(input) }),
  updateConnector: (id: number, input: Record<string, unknown>) =>
    request<ConnectorInstance>(`/connectors/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  deleteConnector: (id: number) => request<void>(`/connectors/${id}`, { method: "DELETE" }),
  testConnector: (id: number) =>
    request<ConnectorTestResult>(`/connectors/${id}/test`, { method: "POST" }),
  discover: (id: number, source: string, query?: string) =>
    request<FieldOption[]>(
      `/connectors/${id}/discover?source=${encodeURIComponent(source)}` +
        (query ? `&query=${encodeURIComponent(query)}` : ""),
    ),

  widgetTypes: () => request<WidgetDescriptor[]>("/widget-types"),
  listWidgets: () => request<WidgetInstance[]>("/widgets"),
  createWidget: (input: Record<string, unknown>) =>
    request<WidgetInstance>("/widgets", { method: "POST", body: JSON.stringify(input) }),
  updateWidget: (id: number, input: Record<string, unknown>) =>
    request<WidgetInstance>(`/widgets/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  deleteWidget: (id: number) => request<void>(`/widgets/${id}`, { method: "DELETE" }),
  previewWidget: (input: {
    widget_type: string;
    display: DisplayOptions;
    config?: Record<string, unknown>;
    connector_id?: number | null;
  }) => request<PreviewResponse>("/widgets/preview", { method: "POST", body: JSON.stringify(input) }),
  refreshWidget: (id: number) =>
    request<WidgetInstance>(`/widgets/${id}/refresh`, { method: "POST" }),

  setWidgetOrder: (widgetIds: number[]) =>
    request<WidgetInstance[]>("/widgets/order", {
      method: "POST",
      body: JSON.stringify({ widget_ids: widgetIds }),
    }),
  reorderDevice: (deviceId: number) =>
    request<{ ok: boolean; pushed: number }>(`/devices/${deviceId}/reorder`, {
      method: "POST",
    }),

  searchIcons: (query: string, limit = 48) =>
    request<Icon[]>(
      `/icons?q=${encodeURIComponent(query)}&animated=true&limit=${limit}`,
    ),
  searchPlaces: (query: string, language: string) =>
    request<Place[]>(
      `/places?q=${encodeURIComponent(query)}&language=${encodeURIComponent(language)}`,
    ),
  deviceIcons: (deviceId: number) => request<string[]>(`/devices/${deviceId}/icons`),
  installIcon: (deviceId: number, iconId: number) =>
    request<InstallResult>(`/devices/${deviceId}/icons/${iconId}`, { method: "POST" }),
};

/** LaMetric serves the previews; awtrixng-mgr never redistributes an icon. */
export const iconThumbnail = (iconId: string | number) =>
  `https://developer.lametric.com/content/apps/icon_thumbs/${iconId}`;
