import { env } from "@lib/env/env";
import type { ApiResponse, BootstrapData } from "@lib/types";
import type {
  NewsAgentBrief,
  NewsAgentAdmission,
  NewsAgentDataGap,
  NewsAgentEvidenceRef,
  NewsMarketScope,
  NewsFactLane,
  NewsItemDetail,
  NewsRowsData,
  NewsRow,
  NewsSignalEnvelope,
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
  for (const fieldName of [
    "market_scope",
    "provider_type",
    "source_role",
    "trust_tier",
    "coverage_tags",
    "source_quality_status",
  ]) {
    if (fieldName in payload) {
      throw new Error(`news_current_contract:retired.${fieldName}`);
    }
  }
  const source = normalizeNewsSource(payload.source);
  const contentTags = requiredNewsStringList(payload.content_tags, "content_tags");
  const contentClassification = requiredNewsObject(
    payload.content_classification,
    "content_classification",
  );
  const agentAdmission = normalizeAgentAdmission(payload.agent_admission);
  const agentAdmissionStatus = stringOrNull(payload.agent_admission_status);
  const agentAdmissionReason = stringOrNull(payload.agent_admission_reason);
  const normalized = {
    ...row,
    canonical_url: stringOrNull(payload.canonical_url),
    content_class: stringOrNull(payload.content_class),
    content_tags: contentTags,
    content_classification: contentClassification,
    processing_terminal_error: stringOrNull(payload.processing_terminal_error),
    headline: requiredNewsString(payload.headline, "headline"),
    latest_at_ms: numberOrNull(payload.latest_at_ms),
    source,
    source_domain: requiredNewsString(payload.source_domain, "source_domain"),
    summary: stringOrNull(payload.summary),
    signal: normalizeNewsSignal(payload.signal),
    provider_rating: normalizeProviderRating(payload.provider_rating),
    token_impacts: normalizeTokenLanes(payload.token_impacts, "token_impacts"),
    token_lanes: normalizeTokenLanes(payload.token_lanes),
    fact_lanes: normalizeFactLanes(payload.fact_lanes),
    agent_brief: normalizeAgentBrief(payload.agent_brief),
    agent_brief_computed_at_ms: numberOrNull(payload.agent_brief_computed_at_ms),
    agent_admission_status: agentAdmissionStatus,
    agent_admission_reason: agentAdmissionReason,
    agent_admission: agentAdmission,
    agent_representative_news_item_id: stringOrNull(payload.agent_representative_news_item_id),
  } as T & Record<string, unknown>;
  return normalized;
}

function normalizeProviderRating(raw: unknown) {
  const payload = objectOrNull(raw);
  if (!payload) return null;
  const rating = {
    provider: stringOrNull(payload.provider),
    status: stringOrNull(payload.status),
    direction: stringOrNull(payload.direction),
    signal: stringOrNull(payload.signal),
    score: numberOrNull(payload.score),
    grade: stringOrNull(payload.grade),
    method: stringOrNull(payload.method),
  };
  if (
    !rating.provider &&
    !rating.status &&
    !rating.direction &&
    !rating.signal &&
    rating.score === null &&
    !rating.grade &&
    !rating.method
  ) {
    return null;
  }
  return rating;
}

function normalizeNewsSource(raw: unknown): NewsSourceSummary {
  const payload = requiredNewsObject(raw, "source");
  const sourceDomain = requiredNewsString(payload.source_domain, "source.source_domain");
  const sourceName = stringOrNull(payload.source_name);
  const providerType = requiredNewsString(payload.provider_type, "source.provider_type");
  const sourceRole = requiredNewsString(payload.source_role, "source.source_role");
  const trustTier = requiredNewsString(payload.trust_tier, "source.trust_tier");
  const coverageTags = requiredNewsStringList(payload.coverage_tags, "source.coverage_tags");
  const sourceQualityStatus = requiredNewsString(
    payload.source_quality_status,
    "source.source_quality_status",
  );
  const sourceId = stringOrNull(payload.source_id);
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
    content: stringOrNull(payload.content),
    token_lanes: row.token_lanes,
    fact_lanes: row.fact_lanes,
    provider_item: objectOrNull(payload.provider_item),
    fetch_run: objectOrNull(payload.fetch_run),
    observation_edges: recordArray(payload.observation_edges),
    provider_observations: recordArray(payload.provider_observations),
  });
}

function normalizeNewsSignal(raw: unknown): NewsSignalEnvelope {
  const payload = requiredNewsObject(raw, "signal");
  const displayPayload = requiredNewsObject(payload.display_signal, "signal.display_signal");
  const agentPayload = requiredNewsObject(payload.agent_signal, "signal.agent_signal");
  const alertPayload = requiredNewsObject(payload.alert_eligibility, "signal.alert_eligibility");
  for (const fieldName of ["agent_admission_status", "agent_admission_reason"]) {
    if (fieldName in alertPayload) {
      throw new Error(`news_current_contract:retired.signal.alert_eligibility.${fieldName}`);
    }
  }
  requiredNewsString(agentPayload.status, "signal.agent_signal.status");
  return {
    display_signal: normalizeNewsSignalSummary(displayPayload),
    agent_signal: agentPayload,
    alert_eligibility: {
      in_app_eligible: requiredNewsBoolean(
        alertPayload.in_app_eligible,
        "signal.alert_eligibility.in_app_eligible",
      ),
      external_push_ready: requiredNewsBoolean(
        alertPayload.external_push_ready,
        "signal.alert_eligibility.external_push_ready",
      ),
      external_push_block_reason: stringOrNull(alertPayload.external_push_block_reason),
      external_push_basis: stringOrNull(alertPayload.external_push_basis),
      agent_status: requiredNewsString(
        alertPayload.agent_status,
        "signal.alert_eligibility.agent_status",
      ),
      decision_class: stringOrNull(alertPayload.decision_class),
      market_scope: normalizeMarketScope(alertPayload.market_scope),
    },
  };
}

function normalizeMarketScope(raw: unknown): NewsMarketScope {
  const payload = requiredNewsObject(raw, "signal.alert_eligibility.market_scope");
  return {
    ...(payload as NewsMarketScope),
    scope: requiredNewsStringArray(payload.scope, "signal.alert_eligibility.market_scope.scope"),
    primary: requiredNewsString(payload.primary, "signal.alert_eligibility.market_scope.primary"),
    status: requiredNewsString(payload.status, "signal.alert_eligibility.market_scope.status"),
    reason: requiredNewsString(payload.reason, "signal.alert_eligibility.market_scope.reason"),
    basis: requiredNewsObject(payload.basis, "signal.alert_eligibility.market_scope.basis"),
    version: requiredNewsString(payload.version, "signal.alert_eligibility.market_scope.version"),
  };
}

function normalizeAgentAdmission(raw: unknown): NewsAgentAdmission | null {
  const payload = objectOrNull(raw);
  if (!payload) return null;
  return {
    ...(payload as NewsAgentAdmission),
    eligible: booleanOrNull(payload.eligible),
    status: stringOrNull(payload.status),
    reason: stringOrNull(payload.reason),
    representative_news_item_id: stringOrNull(payload.representative_news_item_id),
    basis: objectOrNull(payload.basis) ?? {},
    version: stringOrNull(payload.version),
  };
}

function normalizeNewsSignalSummary(raw: unknown): NewsSignalSummary {
  const payload = requiredNewsObject(raw, "signal.display_signal");
  const publicPayload = { ...payload };
  delete publicPayload.score;
  delete publicPayload.grade;
  return {
    ...(publicPayload as Partial<NewsSignalSummary>),
    source: requiredNewsString(payload.source, "signal.display_signal.source"),
    provider: stringOrNull(payload.provider),
    status: requiredNewsString(payload.status, "signal.display_signal.status"),
    direction: requiredNewsString(payload.direction, "signal.display_signal.direction"),
    label_zh: stringOrNull(payload.label_zh),
    signal: stringOrNull(payload.signal),
    title_zh: stringOrNull(payload.title_zh),
    summary_zh: stringOrNull(payload.summary_zh),
    summary_en: stringOrNull(payload.summary_en),
    method: stringOrNull(payload.method),
  };
}

function normalizeTokenLanes(raw: unknown, fieldName = "token_lanes"): NewsTokenLane[] {
  return requiredNewsArray(raw, fieldName).map((lane, index) => {
    const payload = requiredNewsObject(lane, `${fieldName}.${index}`);
    const targetId = stringOrNull(payload.target_id);
    const resolution = stringOrNull(payload.resolution_status);
    return {
      lane: requiredNewsString(payload.lane, `${fieldName}.${index}.lane`),
      reason_codes: stringArray(payload.reason_codes),
      resolution_status: resolution,
      symbol: stringOrNull(payload.symbol),
      target_id: targetId,
      target_type: stringOrNull(payload.target_type),
      market_type: stringOrNull(payload.market_type),
      score: numberOrNull(payload.score),
      signal: stringOrNull(payload.signal),
    };
  });
}

function normalizeFactLanes(raw: unknown): NewsFactLane[] {
  return requiredNewsArray(raw, "fact_lanes").map((fact, index) => {
    const payload = requiredNewsObject(fact, `fact_lanes.${index}`);
    return {
      ...(payload as NewsFactLane),
      affected_targets: arrayOrEmpty(payload.affected_targets),
      claim: stringOrNull(payload.claim),
      event_type: stringOrNull(payload.event_type),
      realis: stringOrNull(payload.realis),
      rejection_reasons: stringArray(payload.rejection_reasons),
      status: requiredNewsString(payload.status, `fact_lanes.${index}.status`),
    };
  });
}

function normalizeAgentBrief(raw: unknown): NewsAgentBrief {
  const payload = requiredNewsObject(raw, "agent_brief");
  const status = requiredNewsString(payload.status, "agent_brief.status");
  const direction = stringOrNull(payload.direction);
  const decisionClass = stringOrNull(payload.decision_class);
  if (status === "ready") {
    requiredNewsString(direction, "agent_brief.direction");
    requiredNewsString(decisionClass, "agent_brief.decision_class");
  }
  const bullView = normalizeAgentBriefView(payload.bull_view);
  const bearView = normalizeAgentBriefView(payload.bear_view);
  const dataGaps = normalizeAgentDataGaps(payload.data_gaps);
  const titleZh = stringOrNull(payload.title_zh);
  const summaryZh = stringOrNull(payload.summary_zh);
  const marketReadZh = stringOrNull(payload.market_read_zh);
  const marketImpacts = arrayOrEmpty(payload.market_impacts);
  const watchTriggers = stringArray(payload.watch_triggers);
  const invalidationConditions = stringArray(payload.invalidation_conditions);
  const evidenceRefs = normalizeEvidenceRefs(payload.evidence_refs);
  return {
    status,
    direction,
    decision_class: decisionClass,
    title_zh: titleZh,
    summary_zh: summaryZh,
    market_read_zh: marketReadZh,
    market_impacts: marketImpacts,
    bull_strength: stringOrNull(payload.bull_strength),
    bear_strength: stringOrNull(payload.bear_strength),
    data_gap_count: numberOrNull(payload.data_gap_count),
    computed_at_ms: numberOrNull(payload.computed_at_ms),
    bull_view: bullView,
    bear_view: bearView,
    affected_entities: arrayOrEmpty(payload.affected_entities),
    data_gaps: dataGaps,
    watch_triggers: watchTriggers,
    invalidation_conditions: invalidationConditions,
    evidence_refs: evidenceRefs,
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

function arrayOrEmpty(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function recordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((entry) => {
    const record = objectOrNull(entry);
    return record ? [record] : [];
  });
}

function objectOrNull(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function requiredNewsObject(value: unknown, fieldName: string): Record<string, unknown> {
  const payload = objectOrNull(value);
  if (!payload) {
    throw new Error(`news_current_contract:${fieldName}`);
  }
  return payload;
}

function requiredNewsArray(value: unknown, fieldName: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new Error(`news_current_contract:${fieldName}`);
  }
  return value;
}

function requiredNewsString(value: unknown, fieldName: string): string {
  const normalized = stringOrNull(value);
  if (!normalized) {
    throw new Error(`news_current_contract:${fieldName}`);
  }
  return normalized;
}

function requiredNewsStringArray(value: unknown, fieldName: string): string[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`news_current_contract:${fieldName}`);
  }
  return value.map((entry, index) => requiredNewsString(entry, `${fieldName}.${index}`));
}

function requiredNewsStringList(value: unknown, fieldName: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error(`news_current_contract:${fieldName}`);
  }
  return value.map((entry, index) => requiredNewsString(entry, `${fieldName}.${index}`));
}

function requiredNewsBoolean(value: unknown, fieldName: string): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`news_current_contract:${fieldName}`);
  }
  return value;
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

function booleanOrNull(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
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
