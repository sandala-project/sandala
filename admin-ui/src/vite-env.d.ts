/// <reference types="vite/client" />

declare global {
  interface Window {
    __SANDALA_RUNTIME_CONFIG__?: {
      apiBaseUrl?: string;
      basePath?: string;
    };
  }
}

export {};
