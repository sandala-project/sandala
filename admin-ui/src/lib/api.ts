import { appConfig } from "./config";
import { ApiError, normalizeApiError } from "./errors";
import { resolveConfiguredUrl } from "./url";

type RequestOptions = {
  body?: unknown;
  headers?: HeadersInit;
  method?: string;
  signal?: AbortSignal;
};

async function request<TResponse>(path: string, options: RequestOptions = {}): Promise<TResponse> {
  const url = resolveConfiguredUrl(path, appConfig.apiBaseUrl);

  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;

  const response = await fetch(url, {
    cache: "no-store",
    method: options.method ?? "GET",
    headers: isFormData
      ? options.headers
      : {
          "Content-Type": "application/json",
          ...options.headers,
        },
    credentials: "include",
    body: options.body === undefined
      ? undefined
      : isFormData
        ? (options.body as FormData)
        : JSON.stringify(options.body),
    signal: options.signal,
  });

  if (response.status === 204) {
    return undefined as TResponse;
  }

  const payload = (await response.json().catch(() => null)) as unknown;

  if (!response.ok) {
    throw normalizeApiError(payload, response.status);
  }

  return payload as TResponse;
}

export const apiClient = {
  get: request,
  post<TResponse>(path: string, body?: unknown, options?: Omit<RequestOptions, "body" | "method">) {
    return request<TResponse>(path, { ...options, method: "POST", body });
  },
  postForm<TResponse>(path: string, body: FormData, options?: Omit<RequestOptions, "body" | "method">) {
    return request<TResponse>(path, { ...options, method: "POST", body });
  },
  patch<TResponse>(path: string, body?: unknown, options?: Omit<RequestOptions, "body" | "method">) {
    return request<TResponse>(path, { ...options, method: "PATCH", body });
  },
  delete<TResponse>(path: string, options?: Omit<RequestOptions, "body" | "method">) {
    return request<TResponse>(path, { ...options, method: "DELETE" });
  },
  put<TResponse>(path: string, body?: unknown, options?: Omit<RequestOptions, "body" | "method">) {
    return request<TResponse>(path, { ...options, method: "PUT", body });
  },
};

export { ApiError };
