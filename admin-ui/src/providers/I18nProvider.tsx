import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import { appConfig } from "../lib/config";
import { isLocale, localeLoaders, localeOptions, type Locale, type TranslationCatalog, type TranslationKey } from "../locales";

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey) => string;
};

const storageKey = "sandala-admin-ui.locale";

const I18nContext = createContext<I18nContextValue | null>(null);

function getInitialLocale(): Locale {
  const saved = window.localStorage.getItem(storageKey);
  if (isLocale(saved)) {
    return saved;
  }

  return isLocale(appConfig.defaultLocale) ? appConfig.defaultLocale : localeOptions[0].value;
}

export function I18nProvider({ children }: PropsWithChildren) {
  const [locale, setLocaleState] = useState<Locale>(() => getInitialLocale());
  const [catalog, setCatalog] = useState<TranslationCatalog | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const loadedCatalogs = useRef<Partial<Record<Locale, TranslationCatalog>>>({});
  const loadRequest = useRef(0);

  const activateLocale = useCallback((nextLocale: Locale, persist: boolean) => {
    const requestId = loadRequest.current + 1;
    loadRequest.current = requestId;
    const cachedCatalog = loadedCatalogs.current[nextLocale];

    if (cachedCatalog !== undefined) {
      setCatalog(cachedCatalog);
      setLocaleState(nextLocale);
      setLoadError(null);
      if (persist) {
        window.localStorage.setItem(storageKey, nextLocale);
      }
      return;
    }

    localeLoaders[nextLocale]().then(({ default: nextCatalog }) => {
      if (requestId !== loadRequest.current) {
        return;
      }

      loadedCatalogs.current[nextLocale] = nextCatalog;
      setCatalog(nextCatalog);
      setLocaleState(nextLocale);
      setLoadError(null);
      if (persist) {
        window.localStorage.setItem(storageKey, nextLocale);
      }
    }).catch((error: unknown) => {
      if (requestId === loadRequest.current) {
        setLoadError(error);
      }
    });
  }, []);

  useEffect(() => {
    activateLocale(locale, false);
  }, [activateLocale, locale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale: (nextLocale) => activateLocale(nextLocale, true),
      t: (key) => catalog?.[key] ?? key,
    }),
    [activateLocale, catalog, locale],
  );

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  if (catalog === null) {
    return (
      <div aria-busy="true" className="i18n-loading-shell">
        {loadError === null ? null : <span>Unable to load the interface language.</span>}
      </div>
    );
  }

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (context === null) {
    throw new Error("I18nProvider is missing");
  }
  return context;
}
