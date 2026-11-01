import { describe, expect, it } from "vitest";
import en from "../i18n/locales/providers/en.json";
import tr from "../i18n/locales/providers/tr.json";

function flatten(value: unknown, prefix = ""): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { [prefix]: value };
  }
  return Object.assign(
    {},
    ...Object.entries(value).map(([key, item]) =>
      flatten(item, prefix ? `${prefix}.${key}` : key),
    ),
  );
}

function placeholders(value: string): string[] {
  return (value.match(/\{[^{}]+\}|%(?:\d+\$)?[sd]|<\/?[A-Za-z][^>]*>/g) ?? []).sort();
}

describe("Turkish provider messages", () => {
  const source = flatten(en);
  const translated = flatten(tr);

  it("keeps every provider key and dynamic placeholder intact", () => {
    expect(Object.keys(translated).sort()).toEqual(Object.keys(source).sort());
    for (const [key, value] of Object.entries(source)) {
      const localized = translated[key];
      expect(typeof localized, key).toBe(typeof value);
      if (typeof value === "string" && typeof localized === "string") {
        expect(placeholders(localized), key).toEqual(placeholders(value));
      }
    }
  });

  it.each([
    "providers_page.subscription_desc",
    "providers_page.login_waiting_browser",
    "providers_page.key_desc",
    "mission_billing.title",
    "mission_billing.confirm_intro",
    "mission_billing.confirm_billing",
    "mission_billing.confirm_caps",
    "mission_billing.confirm_action",
  ])("provides a Turkish translation for %s", (key) => {
    expect(translated[key]).not.toBe(source[key]);
    expect(typeof translated[key]).toBe("string");
  });
});