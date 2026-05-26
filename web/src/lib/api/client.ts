import type {
  EquityEventBrief,
  EquityEventCalendarData,
  EquityEventCalendarRow,
  EquityEventDetail,
  EquityEventDocument,
  EquityEventFact,
  EquityEventRow,
  EquityEventSpan,
  EquityEventStory,
  EquityEventSummary,
  EquityEventsPage,
} from "@features/equity-events";
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
  const body = (await response.json()) as ApiResponse<T>;
  if (!response.ok || body.ok === false) {
    throw new ApiError(body.error ?? response.statusText, response.status, body.error);
  }
  return body;
}

export function getBootstrap(): Promise<ApiResponse<BootstrapData>> {
  return getApi<BootstrapData>("/api/bootstrap");
}

export async function fetchEquityEvents(
  params: {
    limit?: number;
    cursor?: string | null;
    event_type?: string | null;
    priority?: string | null;
    q?: string | null;
    status?: string | null;
    ticker?: string | null;
    token?: string | null;
  } = {},
): Promise<EquityEventsPage> {
  const response = await getApi<{ items?: unknown[]; next_cursor?: string | null }>(
    "/api/equity-events",
    {
      params: {
        cursor: params.cursor,
        event_type: params.event_type,
        lifecycle_status: params.status,
        limit: params.limit ?? 100,
        priority: params.priority,
        q: params.q,
        ticker: params.ticker,
      },
      token: params.token ?? undefined,
    },
  );
  return {
    items: (response.data.items ?? []).map(normalizeEquityEventClientRow),
    next_cursor: stringOrNull(response.data.next_cursor),
  };
}

export async function fetchEquityEventDetail({
  eventId,
  token,
}: {
  eventId: string;
  token?: string | null;
}): Promise<EquityEventDetail> {
  const response = await getApi<Record<string, unknown>>(
    `/api/equity-events/${encodeURIComponent(eventId)}`,
    { token: token ?? undefined },
  );
  return normalizeEquityEventClientDetail(response.data);
}

export async function fetchEquityEventCalendar(
  params: {
    status?: string | null;
    ticker?: string | null;
    token?: string | null;
  } = {},
): Promise<EquityEventCalendarData> {
  const response = await getApi<Record<string, unknown>>("/api/equity-events/calendar", {
    params: {
      status: params.status,
      ticker: params.ticker,
    },
    token: params.token ?? undefined,
  });
  return {
    items: arrayOrEmpty(response.data.items).map(normalizeEquityCalendarClientRow),
    calendar_configured: Boolean(response.data.calendar_configured),
    empty_reason: stringOrNull(response.data.empty_reason) ?? "",
  };
}

export async function fetchEquityEventSummary(
  params: { token?: string | null } = {},
): Promise<EquityEventSummary> {
  const response = await getApi<Record<string, unknown>>("/api/equity-events/summary", {
    token: params.token ?? undefined,
  });
  return normalizeEquityEventClientSummary(response.data);
}

export async function fetchNewsRows(
  params: {
    content_class?: string | null;
    content_tag?: string | null;
    coverage_tag?: string | null;
    limit?: number;
    cursor?: string | null;
    decision_class?: string | null;
    direction?: string | null;
    lane?: string | null;
    provider_type?: string | null;
    q?: string | null;
    source?: string | null;
    source_role?: string | null;
    status?: string | null;
    target?: string | null;
    token?: string | null;
    trust_tier?: string | null;
  } = {},
): Promise<NewsRowsData> {
  const response = await getApi<NewsRowsData>("/api/news", {
    params: {
      content_class: params.content_class,
      content_tag: params.content_tag,
      coverage_tag: params.coverage_tag,
      cursor: params.cursor,
      decision_class: params.decision_class,
      direction: params.direction,
      lane: params.lane,
      limit: params.limit ?? 100,
      provider_type: params.provider_type,
      q: params.q,
      source: params.source,
      source_role: params.source_role,
      status: params.status,
      target: params.target,
      trust_tier: params.trust_tier,
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
  const source = normalizeNewsSource(payload.source ?? payload.source_json, payload);
  const contentTags = stringArray(payload.content_tags ?? payload.content_tags_json);
  const contentClassification = objectOrNull(
    payload.content_classification ?? payload.content_classification_json,
  );
  return {
    ...row,
    canonical_url: stringOrNull(payload.canonical_url ?? payload.url),
    content_class: stringOrNull(payload.content_class),
    content_tags: contentTags,
    content_tags_json: contentTags,
    content_classification: contentClassification ?? {},
    content_classification_json: contentClassification ?? {},
    headline: stringOrNull(payload.headline ?? payload.title) ?? "Untitled news item",
    latest_at_ms: numberOrNull(
      payload.latest_at_ms ??
        payload.published_at_ms ??
        payload.fetched_at_ms ??
        payload.updated_at_ms,
    ),
    provider_type: source?.provider_type ?? null,
    source,
    source_domain: stringOrNull(payload.source_domain) ?? source?.source_domain ?? null,
    source_json: source,
    source_quality_status: source?.source_quality_status ?? null,
    source_role: source?.source_role ?? null,
    summary: stringOrNull(payload.summary),
    trust_tier: source?.trust_tier ?? null,
    coverage_tags: source?.coverage_tags ?? [],
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

function normalizeNewsSource(raw: unknown, row: Record<string, unknown>): NewsSourceSummary | null {
  const payload = objectOrNull(raw);
  const sourceDomain = stringOrNull(payload?.source_domain ?? row.source_domain);
  const sourceName = stringOrNull(payload?.source_name ?? row.source_name);
  const providerType = stringOrNull(payload?.provider_type ?? row.provider_type);
  const sourceRole = stringOrNull(payload?.source_role ?? row.source_role);
  const trustTier = stringOrNull(payload?.trust_tier ?? row.trust_tier);
  const coverageTags = stringArray(
    payload?.coverage_tags ??
      payload?.coverage_tags_json ??
      row.coverage_tags ??
      row.coverage_tags_json,
  );
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
    stringOrNull(payload.status ?? statusAlias) ?? stringOrNull(briefJson?.status) ?? "pending";
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

function normalizeEquityEventClientRow(row: unknown): EquityEventRow {
  const payload = objectOrNull(row) ?? {};
  const eventId =
    stringOrNull(payload.company_event_id ?? payload.event_id) ?? "unknown-equity-event";
  return {
    row_id: stringOrNull(payload.row_id),
    company_event_id: eventId,
    story_id: stringOrNull(payload.story_id),
    company_id: stringOrNull(payload.company_id),
    ticker: (stringOrNull(payload.ticker) ?? "").toUpperCase(),
    company_name: stringOrNull(payload.company_name),
    event_type: stringOrNull(payload.event_type) ?? "event",
    priority: stringOrNull(payload.priority) ?? "P3",
    source_role: stringOrNull(payload.source_role) ?? "observed_source",
    latest_event_at_ms: numberOrNull(payload.latest_event_at_ms ?? payload.event_time_ms),
    lifecycle_status: stringOrNull(payload.lifecycle_status),
    headline: stringOrNull(payload.headline) ?? eventId,
    summary: stringOrNull(payload.summary),
    facts: normalizeEquityEventClientFacts(payload.facts ?? payload.facts_json),
    documents: normalizeEquityEventClientDocuments(payload.documents ?? payload.documents_json),
    spans: normalizeEquityEventClientSpans(
      payload.spans ?? payload.spans_json ?? payload.source_spans,
    ),
    brief: normalizeEquityEventClientBrief(payload.brief ?? payload.brief_json),
    computed_at_ms: numberOrNull(payload.computed_at_ms),
  };
}

function normalizeEquityEventClientDetail(row: unknown): EquityEventDetail {
  const payload = objectOrNull(row) ?? {};
  return {
    ...normalizeEquityEventClientRow(payload),
    event: objectOrNull(payload.event),
    story: normalizeEquityEventClientStory(payload.story ?? payload.story_json),
  };
}

function normalizeEquityCalendarClientRow(row: unknown): EquityEventCalendarRow {
  const payload = objectOrNull(row) ?? {};
  const calendar = objectOrNull(payload.calendar ?? payload.calendar_json) ?? {};
  const expectedId =
    stringOrNull(payload.expected_event_id ?? payload.row_id) ?? "unknown-expected-event";
  return {
    row_id: stringOrNull(payload.row_id),
    expected_event_id: expectedId,
    company_id: stringOrNull(payload.company_id),
    ticker: (stringOrNull(payload.ticker) ?? "").toUpperCase(),
    company_name: stringOrNull(payload.company_name),
    event_type: stringOrNull(payload.event_type) ?? "event",
    priority: stringOrNull(payload.priority) ?? "P3",
    source_role: stringOrNull(payload.source_role) ?? "calendar",
    fiscal_period: stringOrNull(payload.fiscal_period),
    expected_at_ms: numberOrNull(payload.expected_at_ms),
    status: stringOrNull(payload.status) ?? "expected",
    headline: stringOrNull(payload.headline) ?? expectedId,
    calendar,
    observed_company_event_id: stringOrNull(
      payload.observed_company_event_id ?? calendar.observed_company_event_id,
    ),
    computed_at_ms: numberOrNull(payload.computed_at_ms),
  };
}

function normalizeEquityEventClientSummary(row: unknown): EquityEventSummary {
  const payload = objectOrNull(row) ?? {};
  return {
    p0_open_count: numberOrNull(payload.p0_open_count) ?? 0,
    today_count: numberOrNull(payload.today_count) ?? 0,
    due_brief_queue_count: numberOrNull(payload.due_brief_queue_count) ?? 0,
    retryable_brief_failure_count: numberOrNull(payload.retryable_brief_failure_count) ?? 0,
    stale_brief_count: numberOrNull(payload.stale_brief_count) ?? 0,
    historical_backlog_count: numberOrNull(payload.historical_backlog_count) ?? 0,
    latest_material_event_at_ms: numberOrNull(payload.latest_material_event_at_ms),
    latest_source_success_at_ms: numberOrNull(payload.latest_source_success_at_ms),
    latest_evidence_ready_at_ms: numberOrNull(payload.latest_evidence_ready_at_ms),
    latest_projection_at_ms: numberOrNull(payload.latest_projection_at_ms),
    calendar_configured: Boolean(payload.calendar_configured),
  };
}

function normalizeEquityEventClientBrief(raw: unknown): EquityEventBrief {
  const payload = objectOrNull(raw) ?? {};
  return {
    status: stringOrNull(payload.status) ?? "pending",
    direction: stringOrNull(payload.direction),
    decision_class: stringOrNull(payload.decision_class),
    summary_zh: stringOrNull(payload.summary_zh),
    event_read_zh: stringOrNull(payload.event_read_zh),
    bull_view: normalizeEquityEventClientSideView(payload.bull_view),
    bear_view: normalizeEquityEventClientSideView(payload.bear_view),
    company_impacts: arrayOrEmpty(payload.company_impacts).map((impact) => {
      const item = objectOrNull(impact) ?? {};
      return {
        ticker: (stringOrNull(item.ticker) ?? "").toUpperCase(),
        company_name: stringOrNull(item.company_name),
        impact_direction: stringOrNull(item.impact_direction),
        reason_zh: stringOrNull(item.reason_zh),
        evidence_refs: stringArray(item.evidence_refs),
      };
    }),
    watch_triggers: stringArray(payload.watch_triggers),
    invalidation_conditions: stringArray(payload.invalidation_conditions),
    data_gaps: normalizeEquityEventClientDataGaps(payload.data_gaps),
    evidence_refs: stringArray(payload.evidence_refs),
  };
}

function normalizeEquityEventClientDocuments(raw: unknown): EquityEventDocument[] {
  return arrayOrEmpty(raw).map((item) => {
    const payload = objectOrNull(item) ?? {};
    return {
      event_document_id: stringOrNull(payload.event_document_id),
      source_id: stringOrNull(payload.source_id),
      document_type: stringOrNull(payload.document_type),
      form_type: stringOrNull(payload.form_type),
      accession_number: stringOrNull(payload.accession_number),
      fiscal_period: stringOrNull(payload.fiscal_period),
      document_url: stringOrNull(payload.document_url),
      event_time_ms: numberOrNull(payload.event_time_ms),
      source_role: stringOrNull(payload.source_role),
      evidence_status: stringOrNull(payload.evidence_status),
      evidence_reason: stringOrNull(payload.evidence_reason),
      fact_extraction_status: stringOrNull(payload.fact_extraction_status),
      fact_extraction_reason: stringOrNull(payload.fact_extraction_reason),
    };
  });
}

function normalizeEquityEventClientFacts(raw: unknown): EquityEventFact[] {
  return arrayOrEmpty(raw).map((item) => {
    const payload = objectOrNull(item) ?? {};
    return {
      fact_candidate_id: stringOrNull(payload.fact_candidate_id),
      fact_type: stringOrNull(payload.fact_type),
      metric_name: stringOrNull(payload.metric_name),
      value_numeric: numberOrNull(payload.value_numeric),
      value_unit: stringOrNull(payload.value_unit),
      period: stringOrNull(payload.period),
      direction: stringOrNull(payload.direction),
      claim: stringOrNull(payload.claim),
      evidence_quote: stringOrNull(payload.evidence_quote),
      source_role: stringOrNull(payload.source_role),
      validation_status: stringOrNull(payload.validation_status),
      rejection_reasons: stringArray(payload.rejection_reasons),
    };
  });
}

function normalizeEquityEventClientSpans(raw: unknown): EquityEventSpan[] {
  return arrayOrEmpty(raw).map((item) => {
    const payload = objectOrNull(item) ?? {};
    return {
      span_id: stringOrNull(payload.span_id),
      event_document_id: stringOrNull(payload.event_document_id),
      source_id: stringOrNull(payload.source_id),
      span_type: stringOrNull(payload.span_type),
      section_key: stringOrNull(payload.section_key),
      evidence_quote: stringOrNull(payload.evidence_quote),
      confidence: numberOrNull(payload.confidence),
    };
  });
}

function normalizeEquityEventClientStory(raw: unknown): EquityEventStory | null {
  const payload = objectOrNull(raw);
  if (!payload) return null;
  return {
    story_id: stringOrNull(payload.story_id),
    representative_headline: stringOrNull(payload.representative_headline),
    event_count: numberOrNull(payload.event_count),
  };
}

function normalizeEquityEventClientSideView(raw: unknown) {
  const payload = objectOrNull(raw);
  if (!payload) return null;
  return {
    strength: stringOrNull(payload.strength),
    thesis_zh: stringOrNull(payload.thesis_zh),
    evidence_refs: stringArray(payload.evidence_refs),
  };
}

function normalizeEquityEventClientDataGaps(raw: unknown) {
  return arrayOrEmpty(raw).flatMap((gap) => {
    const payload = objectOrNull(gap);
    if (!payload) {
      const description = stringOrNull(gap);
      return description ? [{ description_zh: description, severity: null }] : [];
    }
    const description = stringOrNull(
      payload.description_zh ?? payload.description ?? payload.reason ?? payload.kind,
    );
    return description
      ? [{ description_zh: description, severity: stringOrNull(payload.severity) }]
      : [];
  });
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
