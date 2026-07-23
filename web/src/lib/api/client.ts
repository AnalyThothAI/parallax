import { env } from "@lib/env/env";
import type { ApiResponse, BootstrapData } from "@lib/types";

export type RequestOptions = {
  token?: string;
  params?: Record<string, string | number | boolean | null | undefined>;
};

let authToken: string | null = null;

export class ApiError extends Error {
  status: number;
  code?: string | null;

  constructor(message: string, status: number, code?: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function setAuthToken(token: string | null): void {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

export async function getApi<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResponse<T>> {
  return requestApi<T>(path, { ...options, method: "GET" });
}

export async function postApi<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResponse<T>> {
  return requestApi<T>(path, { ...options, method: "POST" });
}

async function requestApi<T>(
  path: string,
  options: RequestOptions & { method: "GET" | "POST" } = { method: "GET" },
): Promise<ApiResponse<T>> {
  const url = new URL(path, env.apiBaseUrl);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  const requestToken = options.token ?? authToken;
  if (requestToken) {
    headers.Authorization = `Bearer ${requestToken}`;
  }

  const response = await fetch(url, { headers, method: options.method });
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = (await response.text()).trim();
    throw new ApiError(text || response.statusText || "Request failed", response.status);
  }
  const body = (await response.json()) as ApiResponse<T>;
  if (!response.ok || body.ok === false) {
    throw new ApiError(body.error ?? response.statusText, response.status, body.error);
  }
  return body;
}

export function getBootstrap(): Promise<ApiResponse<BootstrapData>> {
  return getApi<BootstrapData>("/api/bootstrap");
}

export function websocketUrl(): string {
  return env.wsUrl;
}
