export type EquityEventBrief = {
  status: string;
  direction: string | null;
  decision_class: string | null;
  summary_zh: string | null;
  event_read_zh: string | null;
  bull_view: EquityEventSideView | null;
  bear_view: EquityEventSideView | null;
  company_impacts: EquityEventCompanyImpact[];
  watch_triggers: string[];
  invalidation_conditions: string[];
  data_gaps: EquityEventDataGap[];
  evidence_refs: string[];
};

export type EquityEventSideView = {
  strength: string | null;
  thesis_zh: string | null;
  evidence_refs: string[];
};

export type EquityEventCompanyImpact = {
  ticker: string;
  company_name: string | null;
  impact_direction: string | null;
  reason_zh: string | null;
  evidence_refs: string[];
};

export type EquityEventDataGap = {
  description_zh: string;
  severity: string | null;
};

export type EquityEventDocument = {
  event_document_id: string | null;
  document_type: string | null;
  form_type: string | null;
  accession_number: string | null;
  fiscal_period: string | null;
  document_url: string | null;
  event_time_ms: number | null;
  source_role: string | null;
};

export type EquityEventFact = {
  fact_candidate_id: string | null;
  fact_type: string | null;
  metric_name: string | null;
  value_numeric: number | null;
  value_unit: string | null;
  period: string | null;
  direction: string | null;
  claim: string | null;
  evidence_quote: string | null;
  source_role: string | null;
  validation_status: string | null;
  rejection_reasons: string[];
};

export type EquityEventSpan = {
  span_id: string | null;
  event_document_id: string | null;
  source_id: string | null;
  span_type: string | null;
  section_key: string | null;
  evidence_quote: string | null;
  confidence: number | null;
};

export type EquityEventStory = {
  story_id: string | null;
  representative_headline: string | null;
  event_count: number | null;
};

export type EquityEventRow = {
  row_id: string | null;
  company_event_id: string;
  story_id: string | null;
  company_id: string | null;
  ticker: string;
  company_name: string | null;
  event_type: string;
  priority: string;
  source_role: string;
  latest_event_at_ms: number | null;
  lifecycle_status: string | null;
  headline: string;
  summary: string | null;
  facts: EquityEventFact[];
  documents: EquityEventDocument[];
  spans: EquityEventSpan[];
  brief: EquityEventBrief;
  computed_at_ms: number | null;
};

export type EquityEventDetail = EquityEventRow & {
  event: Record<string, unknown> | null;
  story: EquityEventStory | null;
};

export type EquityEventsPage = {
  items: EquityEventRow[];
  next_cursor: string | null;
};

export type EquityEventCalendarRow = {
  row_id: string | null;
  expected_event_id: string;
  company_id: string | null;
  ticker: string;
  company_name: string | null;
  event_type: string;
  priority: string;
  source_role: string;
  fiscal_period: string | null;
  expected_at_ms: number | null;
  status: string;
  headline: string;
  calendar: Record<string, unknown>;
  observed_company_event_id: string | null;
  computed_at_ms: number | null;
};

export type EquityEventCalendarData = {
  items: EquityEventCalendarRow[];
};

export type EquityEventSummary = {
  p0_open_count: number;
  today_count: number;
  brief_pending_count: number;
  latest_event_at_ms: number | null;
};

export const normalizeEquityEventRow = (raw: unknown): EquityEventRow => {
  const payload = objectOrNull(raw) ?? {};
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
    facts: normalizeEquityEventFacts(payload.facts ?? payload.facts_json),
    documents: normalizeEquityEventDocuments(payload.documents ?? payload.documents_json),
    spans: normalizeEquityEventSpans(payload.spans ?? payload.spans_json ?? payload.source_spans),
    brief: normalizeEquityEventBrief(payload.brief ?? payload.brief_json),
    computed_at_ms: numberOrNull(payload.computed_at_ms),
  };
};

export const normalizeEquityEventDetail = (raw: unknown): EquityEventDetail => {
  const payload = objectOrNull(raw) ?? {};
  return {
    ...normalizeEquityEventRow(payload),
    event: objectOrNull(payload.event),
    story: normalizeEquityEventStory(payload.story ?? payload.story_json),
  };
};

export const normalizeEquityCalendarRow = (raw: unknown): EquityEventCalendarRow => {
  const payload = objectOrNull(raw) ?? {};
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
};

export const normalizeEquityEventSummary = (raw: unknown): EquityEventSummary => {
  const payload = objectOrNull(raw) ?? {};
  return {
    p0_open_count: numberOrNull(payload.p0_open_count) ?? 0,
    today_count: numberOrNull(payload.today_count) ?? 0,
    brief_pending_count: numberOrNull(payload.brief_pending_count) ?? 0,
    latest_event_at_ms: numberOrNull(payload.latest_event_at_ms),
  };
};

export const normalizeEquityEventBrief = (raw: unknown): EquityEventBrief => {
  const payload = objectOrNull(raw) ?? {};
  return {
    status: stringOrNull(payload.status) ?? "pending",
    direction: stringOrNull(payload.direction),
    decision_class: stringOrNull(payload.decision_class),
    summary_zh: stringOrNull(payload.summary_zh),
    event_read_zh: stringOrNull(payload.event_read_zh),
    bull_view: normalizeSideView(payload.bull_view),
    bear_view: normalizeSideView(payload.bear_view),
    company_impacts: arrayOrEmpty(payload.company_impacts).map(normalizeCompanyImpact),
    watch_triggers: stringArray(payload.watch_triggers),
    invalidation_conditions: stringArray(payload.invalidation_conditions),
    data_gaps: normalizeDataGaps(payload.data_gaps),
    evidence_refs: stringArray(payload.evidence_refs),
  };
};

const normalizeEquityEventDocuments = (raw: unknown): EquityEventDocument[] =>
  arrayOrEmpty(raw).map((item) => {
    const payload = objectOrNull(item) ?? {};
    return {
      event_document_id: stringOrNull(payload.event_document_id),
      document_type: stringOrNull(payload.document_type),
      form_type: stringOrNull(payload.form_type),
      accession_number: stringOrNull(payload.accession_number),
      fiscal_period: stringOrNull(payload.fiscal_period),
      document_url: stringOrNull(payload.document_url),
      event_time_ms: numberOrNull(payload.event_time_ms),
      source_role: stringOrNull(payload.source_role),
    };
  });

const normalizeEquityEventFacts = (raw: unknown): EquityEventFact[] =>
  arrayOrEmpty(raw).map((item) => {
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

const normalizeEquityEventSpans = (raw: unknown): EquityEventSpan[] =>
  arrayOrEmpty(raw).map((item) => {
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

const normalizeEquityEventStory = (raw: unknown): EquityEventStory | null => {
  const payload = objectOrNull(raw);
  if (!payload) return null;
  return {
    story_id: stringOrNull(payload.story_id),
    representative_headline: stringOrNull(payload.representative_headline),
    event_count: numberOrNull(payload.event_count),
  };
};

const normalizeSideView = (raw: unknown): EquityEventSideView | null => {
  const payload = objectOrNull(raw);
  if (!payload) return null;
  return {
    strength: stringOrNull(payload.strength),
    thesis_zh: stringOrNull(payload.thesis_zh),
    evidence_refs: stringArray(payload.evidence_refs),
  };
};

const normalizeCompanyImpact = (raw: unknown): EquityEventCompanyImpact => {
  const payload = objectOrNull(raw) ?? {};
  return {
    ticker: (stringOrNull(payload.ticker) ?? "").toUpperCase(),
    company_name: stringOrNull(payload.company_name),
    impact_direction: stringOrNull(payload.impact_direction),
    reason_zh: stringOrNull(payload.reason_zh),
    evidence_refs: stringArray(payload.evidence_refs),
  };
};

const normalizeDataGaps = (raw: unknown): EquityEventDataGap[] =>
  arrayOrEmpty(raw).flatMap((item) => {
    const payload = objectOrNull(item);
    if (!payload) {
      const description = stringOrNull(item);
      return description ? [{ description_zh: description, severity: null }] : [];
    }
    const description = stringOrNull(
      payload.description_zh ?? payload.description ?? payload.reason ?? payload.kind,
    );
    return description ? [{ description_zh: description, severity: stringOrNull(payload.severity) }] : [];
  });

const objectOrNull = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const arrayOrEmpty = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

const numberOrNull = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const stringOrNull = (value: unknown): string | null =>
  typeof value === "string" && value.trim() ? value : null;

const stringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.flatMap((item) => (stringOrNull(item) ? [String(item)] : [])) : [];
