import { env } from "@lib/env/env";
import type { ApiResponse, BootstrapData } from "@lib/types";
import type {
  NewsAgentBrief,
  NewsAgentBriefStatus,
  NewsAgentDataGap,
  NewsAgentEvidenceRef,
  NewsAgentRunSummary,
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
    direction?: string | null;
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
      direction: params.direction,
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
    agent_brief: normalizeAgentBrief(
      payload.agent_brief_json ?? payload.agent_brief,
      payload.agent_brief_status ?? payload.agent_status,
      payload.agent_brief_computed_at_ms,
    ),
    agent_brief_json: normalizeAgentBrief(
      payload.agent_brief_json ?? payload.agent_brief,
      payload.agent_brief_status ?? payload.agent_status,
      payload.agent_brief_computed_at_ms,
    ),
    agent_status: stringOrNull(payload.agent_status) as NewsAgentBriefStatus | null,
    agent_brief_status: stringOrNull(
      payload.agent_brief_status ?? payload.agent_status,
    ) as NewsAgentBriefStatus | null,
    agent_brief_computed_at_ms: numberOrNull(payload.agent_brief_computed_at_ms),
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
    agent_brief: normalizeAgentBrief(
      payload.agent_brief_json ?? payload.agent_brief,
      payload.agent_brief_status ?? payload.agent_status,
      payload.agent_brief_computed_at_ms,
    ),
    agent_run: normalizeAgentRun(payload.agent_run),
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

function normalizeAgentBrief(
  raw: unknown,
  statusAlias?: unknown,
  computedAtAlias?: unknown,
): NewsAgentBrief {
  const payload = objectOrNull(raw) ?? {};
  const briefJson = objectOrNull(payload.brief_json);
  const status =
    stringOrNull(payload.status ?? statusAlias) ??
    stringOrNull(briefJson?.status) ??
    "pending";
  const bullView = normalizeAgentBriefView(payload.bull_view ?? briefJson?.bull_view);
  const bearView = normalizeAgentBriefView(payload.bear_view ?? briefJson?.bear_view);
  const dataGaps = normalizeAgentDataGaps(payload.data_gaps ?? briefJson?.data_gaps);
  return {
    ...(payload as Partial<NewsAgentBrief>),
    status,
    direction: stringOrNull(payload.direction ?? briefJson?.direction),
    decision_class: stringOrNull(payload.decision_class ?? briefJson?.decision_class),
    summary_zh: stringOrNull(payload.summary_zh ?? briefJson?.summary_zh),
    market_read_zh: stringOrNull(payload.market_read_zh ?? briefJson?.market_read_zh),
    bull_strength: stringOrNull(payload.bull_strength ?? bullView?.strength),
    bear_strength: stringOrNull(payload.bear_strength ?? bearView?.strength),
    data_gap_count: numberOrNull(payload.data_gap_count) ?? dataGaps.length,
    computed_at_ms: numberOrNull(payload.computed_at_ms ?? computedAtAlias),
    agent_run_id: stringOrNull(payload.agent_run_id),
    schema_version: stringOrNull(payload.schema_version),
    prompt_version: stringOrNull(payload.prompt_version),
    artifact_version_hash: stringOrNull(payload.artifact_version_hash),
    input_hash: stringOrNull(payload.input_hash),
    output_hash: stringOrNull(payload.output_hash),
    model: stringOrNull(payload.model),
    brief_json: briefJson,
    bull_view: bullView,
    bear_view: bearView,
    data_gaps: dataGaps,
    watch_triggers: stringArray(payload.watch_triggers ?? briefJson?.watch_triggers),
    invalidation_conditions: stringArray(
      payload.invalidation_conditions ?? briefJson?.invalidation_conditions,
    ),
    evidence_refs: normalizeEvidenceRefs(payload.evidence_refs ?? briefJson?.evidence_refs),
  };
}

function normalizeAgentDataGaps(value: unknown): NewsAgentDataGap[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap<NewsAgentDataGap>((gap) => {
    const payload = objectOrNull(gap);
    if (!payload) {
      const label = stringOrNull(gap);
      return label ? [label] : [];
    }
    const description = stringOrNull(
      payload.description_zh ?? payload.description ?? payload.reason ?? payload.kind,
    );
    if (!description) {
      return [];
    }
    return [
      {
        description_zh: description,
        severity: stringOrNull(payload.severity),
      },
    ];
  });
}

function normalizeAgentBriefView(raw: unknown) {
  const payload = objectOrNull(raw);
  if (!payload) return null;
  return {
    strength: stringOrNull(payload.strength),
    thesis_zh: stringOrNull(payload.thesis_zh),
    evidence_refs: normalizeEvidenceRefs(payload.evidence_refs),
  };
}

function normalizeAgentRun(raw: unknown): NewsAgentRunSummary | null {
  const payload = objectOrNull(raw);
  if (!payload) return null;
  return {
    ...(payload as NewsAgentRunSummary),
    run_id: stringOrNull(payload.run_id),
    status: stringOrNull(payload.status),
    outcome: stringOrNull(payload.outcome),
    model: stringOrNull(payload.model),
    prompt_version: stringOrNull(payload.prompt_version),
    schema_version: stringOrNull(payload.schema_version),
    started_at_ms: numberOrNull(payload.started_at_ms),
    finished_at_ms: numberOrNull(payload.finished_at_ms),
    execution_started:
      typeof payload.execution_started === "boolean" ? payload.execution_started : null,
    error_class: stringOrNull(payload.error_class),
    error: stringOrNull(payload.error),
    error_message: stringOrNull(payload.error_message ?? payload.error),
  };
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

function objectOrNull(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function normalizeEvidenceRefs(value: unknown): NewsAgentEvidenceRef[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((ref): ref is NewsAgentEvidenceRef => {
    return typeof ref === "string" || Boolean(objectOrNull(ref));
  });
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
