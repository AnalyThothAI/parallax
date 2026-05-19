import { env } from "@lib/env/env";
import type { ApiResponse, BootstrapData } from "@lib/types";
import type {
  NewsFactLane,
  NewsItemDetail,
  NewsRowsData,
  NewsRow,
  NewsTokenLane,
} from "@shared/model/newsIntel";

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
  const body = (await response.json()) as ApiResponse<T>;
  if (!response.ok || body.ok === false) {
    throw new ApiError(body.error ?? response.statusText, response.status, body.error);
  }
  return body;
}

export function getBootstrap(): Promise<ApiResponse<BootstrapData>> {
  return getApi<BootstrapData>("/api/bootstrap");
}

export async function fetchNewsRows(
  params: {
    limit?: number;
    cursor?: string | null;
    lane?: string | null;
    q?: string | null;
    source?: string | null;
    status?: string | null;
    target?: string | null;
    token?: string | null;
  } = {},
): Promise<NewsRowsData> {
  const response = await getApi<NewsRowsData>("/api/news", {
    params: {
      cursor: params.cursor,
      lane: params.lane,
      limit: params.limit ?? 100,
      q: params.q,
      source: params.source,
      status: params.status,
      target: params.target,
    },
    token: params.token ?? undefined,
  });
  return {
    ...response.data,
    items: response.data.items.map(normalizeNewsRow),
  };
}

export async function fetchNewsItem({
  newsItemId,
  token,
}: {
  newsItemId: string;
  token?: string | null;
}): Promise<NewsItemDetail> {
  const response = await getApi<NewsItemDetail>(
    `/api/news/items/${encodeURIComponent(newsItemId)}`,
    {
      token: token ?? undefined,
    },
  );
  return normalizeNewsDetail(response.data);
}

function normalizeNewsRow<T extends NewsRow>(row: T): T {
  const payload = row as T & Record<string, unknown>;
  return {
    ...row,
    canonical_url: stringOrNull(payload.canonical_url ?? payload.url),
    headline: stringOrNull(payload.headline ?? payload.title) ?? "Untitled news item",
    latest_at_ms: numberOrNull(
      payload.latest_at_ms ??
        payload.published_at_ms ??
        payload.fetched_at_ms ??
        payload.updated_at_ms,
    ),
    source_domain: stringOrNull(payload.source_domain),
    summary: stringOrNull(payload.summary),
    token_lanes: normalizeTokenLanes(row.token_lanes ?? row.token_lanes_json),
    fact_lanes: normalizeFactLanes(row.fact_lanes ?? row.fact_lanes_json),
  };
}

function normalizeNewsDetail(row: NewsItemDetail): NewsItemDetail {
  const payload = row as NewsItemDetail & Record<string, unknown>;
  const tokenMentions = Array.isArray(row.token_mentions) ? row.token_mentions : [];
  return normalizeNewsRow({
    ...row,
    content: stringOrNull(payload.content ?? payload.body_text),
    source_domain: row.source_domain ?? row.source?.source_domain ?? null,
    token_lanes:
      row.token_lanes ??
      row.token_lanes_json ??
      tokenMentions.map((mention) => mentionToTokenLane(mention)),
    fact_lanes: row.fact_lanes ?? row.fact_lanes_json ?? row.fact_candidates ?? [],
  });
}

function normalizeTokenLanes(raw: unknown): NewsTokenLane[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.map((lane) => {
    const payload = lane && typeof lane === "object" ? (lane as Record<string, unknown>) : {};
    const targetId = stringOrNull(payload.target_id);
    const resolution = stringOrNull(payload.resolution_status);
    return {
      ...(payload as NewsTokenLane),
      lane:
        targetId || resolution === "resolved"
          ? "resolved"
          : stringOrNull(payload.lane) || "attention",
      reason_codes: stringArray(payload.reason_codes ?? payload.reason_codes_json),
      resolution_status: resolution,
      symbol: stringOrNull(payload.symbol ?? payload.display_symbol ?? payload.observed_symbol),
      target_id: targetId,
      target_type: stringOrNull(payload.target_type),
    };
  });
}

function normalizeFactLanes(raw: unknown): NewsFactLane[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.map((fact) => {
    const payload = fact && typeof fact === "object" ? (fact as Record<string, unknown>) : {};
    return {
      ...(payload as NewsFactLane),
      affected_targets: arrayOrEmpty(payload.affected_targets ?? payload.affected_targets_json),
      claim: stringOrNull(payload.claim),
      event_type: stringOrNull(payload.event_type),
      realis: stringOrNull(payload.realis),
      rejection_reasons: stringArray(payload.rejection_reasons ?? payload.rejection_reasons_json),
      status: stringOrNull(payload.status ?? payload.validation_status) ?? "attention",
    };
  });
}

function mentionToTokenLane(mention: unknown): NewsTokenLane {
  const payload =
    mention && typeof mention === "object" ? (mention as Record<string, unknown>) : {};
  const targetId = stringOrNull(payload.target_id);
  const resolution = stringOrNull(payload.resolution_status);
  return {
    lane: targetId || resolution === "resolved" ? "resolved" : "attention",
    reason_codes: stringArray(payload.reason_codes ?? payload.reason_codes_json),
    resolution_status: resolution,
    symbol: stringOrNull(payload.observed_symbol ?? payload.display_symbol ?? payload.symbol),
    target_id: targetId,
    target_type: stringOrNull(payload.target_type),
  };
}

function arrayOrEmpty(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numberOrNull(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

export function websocketUrl(): string {
  return env.wsUrl;
}
