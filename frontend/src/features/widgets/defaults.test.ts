import { describe, expect, it } from "vitest";
import type { FormField, WidgetDescriptor } from "../../api/client";
import { defaultsOf } from "./WidgetBuilder";

function field(name: string, value: unknown): FormField {
  return {
    name,
    label: name,
    type: "select",
    required: true,
    default: value,
  } as FormField;
}

function descriptor(fields: FormField[]): WidgetDescriptor {
  return { fields } as WidgetDescriptor;
}

describe("defaultsOf", () => {
  it("fills in what a field declares", () => {
    expect(defaultsOf(descriptor([field("metric", "temperature")]))).toEqual({
      metric: "temperature",
    });
  });

  it("skips fields with no default", () => {
    expect(defaultsOf(descriptor([field("a", null), field("b", undefined)]))).toEqual({});
  });

  it("keeps a false default, which is a real value", () => {
    expect(defaultsOf(descriptor([field("verify", false)]))).toEqual({ verify: false });
  });

  it("keeps a zero default", () => {
    expect(defaultsOf(descriptor([field("offset", 0)]))).toEqual({ offset: 0 });
  });

  it("handles a widget with no field at all", () => {
    expect(defaultsOf(descriptor([]))).toEqual({});
  });

  it("handles no descriptor", () => {
    expect(defaultsOf(undefined)).toEqual({});
  });
});
