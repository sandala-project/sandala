import type enUS from "./en-US.json";

export type TranslationCatalog = typeof enUS;
export type TranslationKey = keyof TranslationCatalog;

export const localeOptions = [
  { label: "locale.english", value: "en-US" },
  { label: "locale.russian", value: "ru-RU" },
] as const satisfies ReadonlyArray<{ label: TranslationKey; value: string }>;

export type Locale = typeof localeOptions[number]["value"];

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && localeOptions.some((option) => option.value === value);
}

type LocaleModule = { default: TranslationCatalog };

export const localeLoaders = {
  "en-US": () => import("./en-US.json"),
  "ru-RU": () => import("./ru-RU.json"),
} satisfies Record<Locale, () => Promise<LocaleModule>>;
