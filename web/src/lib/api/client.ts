import { env } from "@lib/env/env";
import type { ApiResponse, BootstrapData } from "@lib/types";
import type {
  NewsAgentBrief,
  NewsAgentDataGap,
  NewsAgentEvidenceRef,
  NewsAgentRunSummary,
  NewsFactLane,
  NewsItemDetail,
  NewsRowsData,
  NewsRow,
  NewsSignalSummary,
  NewsSourceSummary,
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

export async function fetchNewsRows(
  params: {
    limit?: number;
    cursor?: string | null;
    min_score?: number | null;
    q?: string | null;
    signal?: "bullish" | "bearish" | "neutral" | string | null;
    status?: string | null;
    token?: string | null;
  } = {},
): Promise<NewsRowsData> {
  const response = await getApi<NewsRowsData>("/api/news", {
    params: {
      cursor: params.cursor,
      limit: params.limit ?? 100,
      min_score: params.min_score,
      q: params.q,
      signal: params.signal,
      status: params.status,
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
  const source = normalizeNewsSource(payload.source, payload);
  const contentTags = stringArray(payload.content_tags);
  const contentClassification = objectOrNull(payload.content_classification);
  return {
    ...row,
    canonical_url: stringOrNull(payload.canonical_url),
    content_class: stringOrNull(payload.content_class),
    content_tags: contentTags,
    content_classification: contentClassification ?? {},
    headline: stringOrNull(payload.headline) ?? "Untitled news item",
    latest_at_ms: numberOrNull(payload.latest_at_ms),
    provider_type: source?.provider_type ?? null,
    source,
    source_domain: stringOrNull(payload.source_domain) ?? source?.source_domain ?? null,
    source_quality_status: source?.source_quality_status ?? null,
    source_role: source?.source_role ?? null,
    summary: stringOrNull(payload.summary),
    trust_tier: source?.trust_tier ?? null,
    coverage_tags: source?.coverage_tags ?? [],
    signal: normalizeNewsSignal(payload.signal),
    token_impacts: normalizeTokenLanes(payload.token_impacts),
    token_lanes: normalizeTokenLanes(payload.token_lanes),
    fact_lanes: normalizeFactLanes(payload.fact_lanes),
    agent_brief: payload.agent_brief
      ? normalizeAgentBrief(payload.agent_brief, undefined, payload.agent_brief_computed_at_ms)
      : undefined,
    agent_brief_computed_at_ms: numberOrNull(payload.agent_brief_computed_at_ms),
  };
}

function normalizeNewsSource(raw: unknown, row: Record<string, unknown>): NewsSourceSummary | null {
  const payload = objectOrNull(raw);
  const sourceDomain = stringOrNull(payload?.source_domain ?? row.source_domain);
  const sourceName = stringOrNull(payload?.source_name ?? row.source_name);
  const providerType = stringOrNull(payload?.provider_type ?? row.provider_type);
  const sourceRole = stringOrNull(payload?.source_role ?? row.source_role);
  const trustTier = stringOrNull(payload?.trust_tier ?? row.trust_tier);
  const coverageTags = stringArray(payload?.coverage_tags ?? row.coverage_tags);
  const sourceQualityStatus = stringOrNull(
    payload?.source_quality_status ?? row.source_quality_status,
  );
  const sourceId = stringOrNull(payload?.source_id ?? row.source_id);
  if (
    !sourceDomain &&
    !sourceName &&
    !providerType &&
    !sourceRole &&
    !trustTier &&
    !coverageTags.length &&
    !sourceQualityStatus &&
    !sourceId
  ) {
    return null;
  }
  return {
    source_id: sourceId,
    source_name: sourceName,
    source_domain: sourceDomain,
    provider_type: providerType,
    source_role: sourceRole,
    trust_tier: trustTier,
    coverage_tags: coverageTags,
    source_quality_status: sourceQualityStatus,
  };
}

function normalizeNewsDetail(row: NewsItemDetail): NewsItemDetail {
  const payload = row as NewsItemDetail & Record<string, unknown>;
  return normalizeNewsRow({
    ...row,
    content: stringOrNull(payload.content ?? payload.body_text),
    source_domain: row.source_domain ?? row.source?.source_domain ?? null,
    token_lanes: row.token_lanes,
    fact_lanes: row.fact_lanes,
    agent_brief: payload.agent_brief
      ? normalizeAgentBrief(payload.agent_brief, undefined, payload.agent_brief_computed_at_ms)
      : undefined,
    agent_run: normalizeAgentRun(payload.agent_run),
  });
}

function normalizeNewsSignal(raw: unknown): NewsSignalSummary {
  const payload = objectOrNull(raw) ?? {};
  const direction = stringOrNull(payload.direction) ?? "neutral";
  const status = stringOrNull(payload.status) ?? "partial";
  return {
    ...(payload as Partial<NewsSignalSummary>),
    source: stringOrNull(payload.source) ?? "partial",
    provider: stringOrNull(payload.provider),
    status,
    direction,
    label_zh: stringOrNull(payload.label_zh),
    signal: stringOrNull(payload.signal),
    score: numberOrNull(payload.score),
    grade: stringOrNull(payload.grade),
    title_zh: stringOrNull(payload.title_zh),
    summary_zh: stringOrNull(payload.summary_zh),
    summary_en: stringOrNull(payload.summary_en),
    method: stringOrNull(payload.method),
  };
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
      reason_codes: stringArray(payload.reason_codes),
      resolution_status: resolution,
      symbol: stringOrNull(payload.symbol),
      target_id: targetId,
      target_type: stringOrNull(payload.target_type),
      provider_signal: stringOrNull(payload.provider_signal),
      provider_score: numberOrNull(payload.provider_score),
      provider_grade: stringOrNull(payload.provider_grade),
      market_type: stringOrNull(payload.market_type),
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
      affected_targets: arrayOrEmpty(payload.affected_targets),
      claim: stringOrNull(payload.claim),
      event_type: stringOrNull(payload.event_type),
      realis: stringOrNull(payload.realis),
      rejection_reasons: stringArray(payload.rejection_reasons),
      status: stringOrNull(payload.status) ?? "attention",
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
    stringOrNull(payload.status ?? statusAlias) ?? stringOrNull(briefJson?.status) ?? "pending";
  const bullView = normalizeAgentBriefView(payload.bull_view ?? briefJson?.bull_view);
  const bearView = normalizeAgentBriefView(payload.bear_view ?? briefJson?.bear_view);
  const dataGaps = normalizeAgentDataGaps(payload.data_gaps ?? briefJson?.data_gaps);
  return {
    ...(payload as Partial<NewsAgentBrief>),
    status,
    direction: stringOrNull(payload.direction ?? briefJson?.direction),
    decision_class: stringOrNull(payload.decision_class ?? briefJson?.decision_class),
    title_zh: stringOrNull(payload.title_zh ?? briefJson?.title_zh),
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
