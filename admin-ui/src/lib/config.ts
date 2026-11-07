export type AppConfig = {
  apiBaseUrl: string;
  appName: string;
  basePath: string;
  defaultLocale: string;
  minimumSupportedWidth: number;
};

type RuntimeConfig = {
  apiBaseUrl?: string;
  basePath?: string;
};

const defaultAppConfig: AppConfig = {
  apiBaseUrl: "/api/v1",
  appName: "Sandala",
  basePath: "/",
  defaultLocale: "en-US",
  minimumSupportedWidth: 900,
};

export const appConfig: AppConfig = createAppConfig(window.__SANDALA_RUNTIME_CONFIG__);

function createAppConfig(runtimeConfig: RuntimeConfig | undefined): AppConfig {
  return {
    ...defaultAppConfig,
    apiBaseUrl: typeof runtimeConfig?.apiBaseUrl === "string" && runtimeConfig.apiBaseUrl.length > 0
      ? runtimeConfig.apiBaseUrl
      : defaultAppConfig.apiBaseUrl,
    basePath: normalizeBasePath(runtimeConfig?.basePath),
  };
}

function normalizeBasePath(value: unknown) {
  if (typeof value !== "string" || value.trim().length === 0) {
    return defaultAppConfig.basePath;
  }

  const normalized = `/${value.trim().replace(/^\/+|\/+$/g, "")}`;
  return normalized === "/" ? "/" : `${normalized}/`;
}
