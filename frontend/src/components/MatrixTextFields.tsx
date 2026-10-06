/**
 * The presentation controls a widget and a reminder both offer.
 *
 * **One component, deliberately.** The two forms grew their own copies and
 * drifted: a widget could choose its font, its letter case and what its icon
 * does beside scrolling text; a reminder could choose none of them. Nobody
 * could say why, because nobody had decided it — the reminder form had simply
 * been written first and never caught up.
 *
 * The fields are the ones `app/schemas/matrix_text.py` declares, and
 * `tests/test_frontend_contract.py` checks the two lists against each other:
 * an option added on the backend with no control here fails the suite.
 *
 * The widget form adds what only a widget can mean — the progress bar, the
 * weekday segments, hide-when-empty — after this block, not inside it.
 */

import {
  EFFECTS,
  FONTS,
  ICON_MODES,
  OVERLAYS,
  SCROLL_MODES,
  SCROLL_WHEN_FITS,
  TEXT_CASES,
} from "../api/client";
import type {
  Font,
  IconMode,
  ScrollMode,
  ScrollWhenFits,
  TextCase,
} from "../api/client";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/messages.en";
import { Field, Input, NativeSelect } from "./ui";

/** Exactly the fields of `MatrixText`, in the order it declares them. */
export interface MatrixTextValue {
  background: string | null;
  effect: string | null;
  overlay: string | null;
  icon_mode: IconMode;
  text_case: TextCase;
  font: Font;
  scroll_mode: ScrollMode;
  scroll_speed: number;
  scroll_when_fits: ScrollWhenFits;
}

export interface MatrixTextFieldsProps {
  value: MatrixTextValue;
  onChange: (patch: Partial<MatrixTextValue>) => void;
  /** Whether an empty overlay means "let the service choose".
   *
   *  It does for a widget — the weather one proposes one from the WMO code.
   *  A reminder has nothing upstream, so for it empty means none, and saying
   *  "au choix du service" there would name a service that does not exist. */
  overlayFromService?: boolean;
}

export function MatrixTextFields({
  value,
  onChange,
  overlayFromService = false,
}: MatrixTextFieldsProps) {
  const { t } = useI18n();
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label={t("builder.scrollMode")} hint={t("builder.scrollModeHelp")}>
        <NativeSelect
          value={value.scroll_mode}
          onChange={(mode) => onChange({ scroll_mode: mode as ScrollMode })}
          options={SCROLL_MODES.map((mode) => ({
            value: mode,
            label: t(`builder.scrollMode.${mode}`),
          }))}
        />
      </Field>
      <Field
        label={t("builder.scrollWhenFits")}
        hint={t("builder.scrollWhenFitsHelp")}
      >
        <NativeSelect
          value={value.scroll_when_fits}
          onChange={(mode) =>
            onChange({ scroll_when_fits: mode as ScrollWhenFits })
          }
          options={SCROLL_WHEN_FITS.map((mode) => ({
            value: mode,
            label: t(`builder.scrollWhenFits.${mode}`),
          }))}
        />
      </Field>
      <Field label={t("builder.scrollSpeed")} hint="%">
        <Input
          type="number"
          min={0}
          max={500}
          value={value.scroll_speed}
          onChange={(event) =>
            onChange({ scroll_speed: Number(event.target.value) || 100 })
          }
        />
      </Field>
      <Field label={t("builder.iconMode")} hint={t("builder.iconModeHelp")}>
        <NativeSelect
          value={value.icon_mode}
          onChange={(mode) => onChange({ icon_mode: mode as IconMode })}
          options={ICON_MODES.map((mode) => ({
            value: mode,
            label: t(`builder.iconMode.${mode}`),
          }))}
        />
      </Field>
      <Field label={t("builder.font")} hint={t("builder.fontHelp")}>
        <NativeSelect
          value={value.font}
          onChange={(name) => onChange({ font: name as Font })}
          options={FONTS.map((name) => ({
            value: name,
            label: t(`builder.font.${name}`),
          }))}
        />
      </Field>
      <Field label={t("builder.textCase")}>
        <NativeSelect
          value={value.text_case}
          onChange={(mode) => onChange({ text_case: mode as TextCase })}
          options={TEXT_CASES.map((mode) => ({
            value: mode,
            label: t(`builder.textCase.${mode}`),
          }))}
        />
      </Field>
      <Field label={t("builder.overlay")} hint={t("builder.overlayHelp")}>
        <NativeSelect
          value={value.overlay ?? ""}
          onChange={(name) => onChange({ overlay: name || null })}
          options={[
            {
              value: "",
              label: overlayFromService
                ? t("builder.overlayAuto")
                : t("builder.overlayNone"),
            },
            ...OVERLAYS.map((name) => ({
              value: name,
              label: t(`builder.overlay.${name}` as MessageKey),
            })),
          ]}
        />
      </Field>
      <Field label={t("builder.effect")} hint={t("builder.effectHelp")}>
        <NativeSelect
          value={value.effect ?? ""}
          onChange={(name) => onChange({ effect: name || null })}
          options={[
            { value: "", label: t("builder.effectNone") },
            // Not translated: these are the firmware's own names, the ones it
            // answers with when it refuses an unknown one.
            ...EFFECTS.map((name) => ({ value: name, label: name })),
          ]}
        />
      </Field>
      <Field label={t("builder.background")}>
        <Input
          value={value.background ?? ""}
          placeholder="#000000"
          onChange={(event) => onChange({ background: event.target.value || null })}
        />
      </Field>
    </div>
  );
}
