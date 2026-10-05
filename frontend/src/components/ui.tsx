/**
 * Base components. Deliberately few and dependency-free: §13 asks not to turn
 * the frontend into a machine, and §9 bis to avoid the look of a generic
 * dashboard.
 */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import type { HealthStatus } from "../api/client";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/messages.en";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] ${className}`}
    >
      {children}
    </div>
  );
}

type Variant = "primary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-[var(--color-accent)] text-[#05210f] hover:brightness-110 font-medium",
  ghost:
    "border border-[var(--color-border-strong)] text-[var(--color-text)] hover:bg-[var(--color-surface-2)]",
  danger:
    "border border-[var(--color-danger)]/40 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10",
};

export function Button({
  variant = "ghost",
  loading = false,
  children,
  className = "",
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  loading?: boolean;
}) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3 py-1.5 text-sm
        transition disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
    >
      {loading && (
        <span
          aria-hidden
          className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}

/** States always carry a label, never colour alone (§9 bis). */
const STATUS: Record<HealthStatus, { key: MessageKey; color: string }> = {
  healthy: { key: "status.healthy", color: "var(--color-success)" },
  degraded: { key: "status.degraded", color: "var(--color-warning)" },
  error: { key: "status.error", color: "var(--color-danger)" },
  disabled: { key: "status.disabled", color: "var(--color-neutral)" },
  unknown: { key: "status.unknown", color: "var(--color-neutral)" },
};

export function StatusBadge({ status }: { status: HealthStatus }) {
  const { t } = useI18n();
  const { key, color } = STATUS[status];
  const label = t(key);
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs"
      style={{ color, borderColor: `${color}40`, backgroundColor: `${color}14` }}
    >
      <span
        aria-hidden
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-[var(--color-text-muted)]">{label}</span>
      {children}
      {hint && <span className="block text-xs text-[var(--color-text-faint)]">{hint}</span>}
    </label>
  );
}

export function Input({ className = "", ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={`w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]
        px-3 py-1.5 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-faint)]
        focus:border-[var(--color-accent)] focus:outline-none ${className}`}
    />
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[var(--color-border)] px-6 py-14 text-center">
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="max-w-sm text-sm text-[var(--color-text-muted)]">{description}</p>
      {action}
    </div>
  );
}

/** A reading, with an optional second line under it.
 *
 *  The display's own interface puts the raw value beneath the interpreted one
 *  — 93 % over 4.14 V, -63 dBm over "good", 5 % over "184 raw". It is worth
 *  copying: the interpreted number is what you read at a glance, and the raw
 *  one is what you need the day it looks wrong. */
export function Stat({
  label,
  value,
  detail,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
}) {
  return (
    <div className="rounded-lg bg-[var(--color-surface-2)] px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-faint)]">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-sm">{value}</div>
      {detail && (
        <div className="font-mono text-[10px] text-[var(--color-text-faint)]">{detail}</div>
      )}
    </div>
  );
}

export function Toggle({
  label,
  checked,
  onChange,
  disabled = false,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  /** Offering a switch that cannot do anything is a promise the engine will
   *  not keep. Pair it with `hint`: greyed out without a reason is worse than
   *  not greyed out at all. */
  disabled?: boolean;
  hint?: string;
}) {
  return (
    <span className="flex flex-col gap-0.5">
      <label
        className={`flex items-center gap-2 ${
          disabled ? "cursor-not-allowed text-[var(--color-text-faint)]" : ""
        }`}
      >
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          className="accent-[var(--color-accent)] disabled:opacity-50"
        />
        {label}
      </label>
      {hint && (
        <span className="pl-6 text-[11px] text-[var(--color-text-faint)]">{hint}</span>
      )}
    </span>
  );
}


export function NativeSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]
        px-3 py-1.5 text-sm text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
