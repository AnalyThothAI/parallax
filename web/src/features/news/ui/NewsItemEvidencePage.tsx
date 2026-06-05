import { formatRelativeTime } from "@lib/format";
import type {
  NewsAgentBrief,
  NewsAgentDataGap,
  NewsAgentEvidenceRef,
  NewsFactLane,
  NewsItemDetail,
  NewsResearchToolResult,
  NewsTokenLane,
} from "@shared/model/newsIntel";
import { newsLifecycleLabel } from "@shared/model/newsIntel";
import {
  Activity,
  Braces,
  Brain,
  Database,
  ExternalLink,
  FileText,
  ShieldCheck,
} from "lucide-react";
import type { ComponentType } from "react";

import {
  newsDisplayTokenLanes,
  newsSignalLabel,
  newsSignalScoreLabel,
  newsSignalTone,
  tokenImpactLabel,
  tokenMarketLabel,
} from "../model/newsSignalViewModel";
import "./NewsItemEvidencePage.css";

type NewsItemEvidencePageProps = {
  item: NewsItemDetail;
};

type IconComponent = ComponentType<{ "aria-hidden"?: boolean; size?: number }>;

export function NewsItemEvidencePage({ item }: NewsItemEvidencePageProps) {
  const tokenImpacts = newsDisplayTokenLanes(item);
  const tokenIdentities = item.token_lanes ?? [];
  const facts = item.fact_lanes ?? [];
  const displaySignal = item.signal.display_signal;
  const providerSignal = item.signal.provider_signal;
  const brief = item.agent_brief ?? null;
  const run = item.agent_run ?? null;
  const toolResults = run?.tool_results ?? [];
  const requirement = item.signal.agent_requirement ?? item.agent_requirement_json ?? null;
  const requirementStatus =
    item.agent_requirement_status ?? requirement?.status ?? brief?.requirement_status ?? null;
  const requirementReason =
    item.agent_requirement_reason ?? requirement?.reason ?? brief?.requirement_reason ?? brief?.eligibility_reason ?? null;
  const displayTitle = brief?.title_zh || displaySignal.title_zh || item.headline;
  const sourceDomains = sourceDomainList(item);

  return (
    <article className="news-evidence-page">
      <header className="news-evidence-hero">
        <div className="news-evidence-hero-copy">
          <div className="news-evidence-kicker">
            <span>Evidence page</span>
            <span className={newsSignalTone(displaySignal)}>{newsSignalLabel(displaySignal)}</span>
            <span>{brief?.decision_class || "decision pending"}</span>
            <span>{brief?.confirmation_state || "confirmation pending"}</span>
          </div>
          <h2>{displayTitle}</h2>
          <p>{brief?.summary_zh || displaySignal.summary_zh || item.summary || "No summary is present."}</p>
        </div>
        <SourcePacket item={item} displayTitle={displayTitle} sourceDomains={sourceDomains} />
      </header>

      <section className="news-evidence-metric-grid" aria-label="news item state">
        <EvidenceMetric
          label="Provider aiRating"
          value={providerSignal ? newsSignalScoreLabel(providerSignal) : "score --"}
          detail={providerSignal?.method || providerSignal?.provider || providerSignal?.source}
        />
        <EvidenceMetric
          label="Source set"
          value={`${sourceDomains.length || 1} domain${sourceDomains.length === 1 ? "" : "s"}`}
          detail={`duplicates ${displayScalar(item.duplicate_observation_count ?? providerObservationCount(item))}`}
        />
        <EvidenceMetric
          label="Agent run"
          value={run?.outcome || brief?.status || "pending"}
          detail={run?.latency_ms == null ? run?.model : `${formatDuration(run.latency_ms)} · ${run.model || ""}`}
        />
        <EvidenceMetric
          label="Agent gate"
          value={requirementStatus || item.agent_status || "unknown"}
          detail={requirementReason || "reason missing"}
        />
      </section>

      <div className="news-evidence-layout">
        <main className="news-evidence-main">
          <OriginalArticle item={item} />
          <AiInterpretation brief={brief} displayDirection={displaySignal.direction} />
          {hasLegacyAgentAudit(run, toolResults) ? (
            <LegacyAgentAudit run={run} toolResults={toolResults} />
          ) : null}
          <RawJson brief={brief} run={run} />
        </main>
        <aside className="news-evidence-side" aria-label="news evidence metadata">
          <ProviderSignalEvidence item={item} tokenImpacts={tokenImpacts} />
          <AgentBriefState item={item} brief={brief} run={run} />
          <TokenIdentityEvidence tokens={tokenIdentities} />
          <FactEvidence facts={facts} />
          <ObservationEvidence item={item} />
          <MetadataEvidence item={item} />
        </aside>
      </div>
    </article>
  );
}

function SourcePacket({
  item,
  displayTitle,
  sourceDomains,
}: {
  item: NewsItemDetail;
  displayTitle: string;
  sourceDomains: string[];
}) {
  return (
    <section className="news-evidence-source-packet" aria-label="source packet">
      <span>Source packet</span>
      <b>{item.source?.source_name || item.source_domain || "source unknown"}</b>
      <p>{displayTitle}</p>
      <small>
        {sourceDomains.join(", ") || item.source?.provider_type || item.provider_type || "provider unknown"}
        {item.latest_at_ms ? ` · ${formatRelativeTime(item.latest_at_ms)} ago` : ""}
      </small>
      {item.canonical_url ? (
        <a className="news-outline-link" href={item.canonical_url} rel="noreferrer" target="_blank">
          <ExternalLink aria-hidden size={13} />
          Original
        </a>
      ) : null}
    </section>
  );
}

function EvidenceMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string | null;
}) {
  return (
    <div className="news-evidence-metric">
      <span>{label}</span>
      <b>{value}</b>
      <small>{detail || "not present"}</small>
    </div>
  );
}

function OriginalArticle({ item }: { item: NewsItemDetail }) {
  const originalText = item.body_text || item.content || item.summary || "";
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={FileText} title="Original article" tag="原文" />
      <h3 className="news-evidence-source-title">{item.title || item.headline}</h3>
      <p className="news-evidence-original-text">
        {originalText || "No original body text is persisted for this item."}
      </p>
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Published" value={formatTimestamp(item.published_at_ms)} />
        <FieldRow label="Fetched" value={formatTimestamp(item.fetched_at_ms)} />
        <FieldRow label="Canonical URL" value={item.canonical_url} />
        <FieldRow label="Language" value={item.language} />
        <FieldRow label="Content class" value={item.content_class} />
        <FieldRow label="Analysis admission" value={item.analysis_admission_status} />
        <FieldRow label="Admission reason" value={item.analysis_admission_reason} />
        <FieldRow label="Lifecycle" value={newsLifecycleLabel(item.lifecycle_status)} />
        <FieldRow label="Processing error" value={item.processing_terminal_error} />
      </dl>
    </section>
  );
}

function AiInterpretation({
  brief,
  displayDirection,
}: {
  brief?: NewsAgentBrief | null;
  displayDirection?: string | null;
}) {
  return (
    <section className="news-evidence-section news-evidence-ai-section">
      <SectionHeading icon={Brain} title="AI interpretation" tag={brief?.status || "no brief"} />
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Direction" value={brief?.direction || displayDirection} />
        <FieldRow label="Decision" value={brief?.decision_class} />
        <FieldRow label="Novelty" value={brief?.novelty_status} />
        <FieldRow label="Confirmation" value={brief?.confirmation_state} />
        <FieldRow label="Confidence" value={brief?.confidence} />
        <FieldRow label="Used calls" value={(brief?.used_tool_call_ids ?? []).join(", ")} />
      </dl>
      <NarrativeBlock label="Market read" text={brief?.market_read_zh} />
      <NarrativeBlock label="Source consensus" text={brief?.source_consensus_zh} />
      <NarrativeBlock label="Retrieval notes" text={brief?.retrieval_notes_zh} />
      <div className="news-evidence-view-grid">
        <ViewCard title="Bull view" strength={brief?.bull_strength} text={brief?.bull_view?.thesis_zh} />
        <ViewCard title="Bear view" strength={brief?.bear_strength} text={brief?.bear_view?.thesis_zh} />
      </div>
      <ExecutionGapPanel brief={brief} />
      <ListBlock title="Watch triggers" items={brief?.watch_triggers ?? []} />
      <ListBlock title="Invalidation" items={brief?.invalidation_conditions ?? []} />
      <ListBlock title="Research todos" items={brief?.research_todos_zh ?? []} />
      <JsonDetails title="Affected assets JSON" value={brief?.affected_assets ?? []} />
    </section>
  );
}

function LegacyAgentAudit({
  run,
  toolResults,
}: {
  run?: NewsItemDetail["agent_run"] | null;
  toolResults: NewsResearchToolResult[];
}) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={Database} title="Legacy agent audit" tag={`${toolResults.length} calls`} />
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Run" value={run?.run_id} />
        <FieldRow label="Model" value={run?.model} />
        <FieldRow label="Provider" value={run?.provider} />
        <FieldRow label="Latency" value={run?.latency_ms == null ? null : formatDuration(run.latency_ms)} />
        <FieldRow label="Tokens" value={usageLabel(run?.usage_json)} />
        <FieldRow label="Input hash" value={run?.input_hash} />
      </dl>
      <JsonDetails title="Research plan JSON" value={run?.research_plan ?? {}} />
      {toolResults.length ? (
        <div className="news-evidence-tool-list">
          {toolResults.map((tool, index) => (
            <ToolResultCard key={`${tool.tool_call_id || tool.tool_name || "tool"}-${index}`} tool={tool} />
          ))}
        </div>
      ) : (
        <p className="news-evidence-muted">No legacy tool results are attached to this run.</p>
      )}
      <JsonDetails title="Research execution JSON" value={run?.research_execution ?? {}} />
      <JsonDetails title="Research hashes JSON" value={run?.research_hashes ?? {}} />
    </section>
  );
}

function ToolResultCard({ tool }: { tool: NewsResearchToolResult }) {
  const rows = tool.rows ?? [];
  return (
    <article className="news-evidence-tool-card">
      <div className="news-evidence-tool-card-head">
        <div>
          <span>{tool.tool_call_id || "call"}</span>
          <b>{tool.tool_name || "unknown tool"}</b>
        </div>
        <span className={`news-evidence-pill ${tool.truncated ? "is-short" : "is-context"}`}>
          {tool.truncated ? "truncated" : tool.skipped_reason || "ok"}
        </span>
      </div>
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Rows" value={tool.row_count ?? rows.length} />
        <FieldRow label="Latency" value={tool.latency_ms == null ? null : formatDuration(tool.latency_ms)} />
        <FieldRow label="Tables" value={(tool.source_tables ?? []).join(", ")} />
        <FieldRow label="Hash" value={tool.result_hash} />
        <FieldRow label="Schema" value={tool.schema_version} />
        <FieldRow label="Query" value={tool.query_version} />
      </dl>
      <EvidenceRefList refs={tool.evidence_refs ?? []} />
      <JsonDetails title="Tool input JSON" value={tool.input ?? {}} />
      <JsonDetails title="Tool rows JSON" value={rows} />
      <ListBlock title="Redaction notes" items={tool.redaction_notes ?? []} />
    </article>
  );
}

function hasLegacyAgentAudit(
  run: NewsItemDetail["agent_run"] | null | undefined,
  toolResults: NewsResearchToolResult[],
): boolean {
  if (toolResults.length > 0) return true;
  return Boolean(
    run &&
      (hasObjectKeys(run.research_plan) ||
        hasObjectKeys(run.research_execution) ||
        hasObjectKeys(run.research_hashes) ||
        hasObjectKeys(run.base_packet)),
  );
}

function RawJson({
  brief,
  run,
}: {
  brief?: NewsAgentBrief | null;
  run?: NewsItemDetail["agent_run"] | null;
}) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={Braces} title="Raw JSON" tag="audit" />
      <JsonDetails title="AI brief JSON" value={brief?.brief_json ?? {}} open />
      <JsonDetails title="AI response JSON" value={run?.response_json ?? {}} open />
      <JsonDetails title="Agent request JSON" value={run?.request_json ?? {}} />
      <JsonDetails title="Validation errors JSON" value={run?.validation_errors_json ?? []} />
    </section>
  );
}

function hasObjectKeys(value: Record<string, unknown> | null | undefined): boolean {
  return Boolean(value && Object.keys(value).length > 0);
}

function ProviderSignalEvidence({
  item,
  tokenImpacts,
}: {
  item: NewsItemDetail;
  tokenImpacts: NewsTokenLane[];
}) {
  const displaySignal = item.signal.display_signal;
  const providerSignal = item.signal.provider_signal;
  return (
    <section className="news-evidence-section news-evidence-provider-rating">
      <SectionHeading
        icon={ShieldCheck}
        title="Provider aiRating"
        tag={providerSignal?.status || "missing"}
        tone={newsSignalTone(displaySignal)}
      />
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Source" value={providerSignal?.provider || providerSignal?.source} />
        <FieldRow label="Method" value={providerSignal?.method} />
        <FieldRow label="Direction" value={providerSignal?.direction} />
        <FieldRow label="Signal" value={providerSignal?.signal} />
        <FieldRow label="Score" value={providerSignal?.score} />
        <FieldRow label="Grade" value={providerSignal?.grade} />
      </dl>
      <p>
        {providerSignal?.summary_zh ||
          providerSignal?.summary_en ||
          "No provider aiRating summary is present."}
      </p>
      <TokenImpactList tokens={tokenImpacts} />
    </section>
  );
}

function TokenImpactList({ tokens }: { tokens: NewsTokenLane[] }) {
  if (!tokens.length) {
    return <p className="news-evidence-muted">No provider token impact rows are attached.</p>;
  }
  return (
    <div className="news-evidence-card-list" aria-label="Token impacts">
      {tokens.map((token, index) => (
        <div className="news-evidence-card" key={`${token.symbol ?? token.target_id ?? "impact"}-${index}`}>
          <b>{token.symbol || token.target_id || "unknown token"}</b>
          <span>{token.provider_signal || "provider signal missing"}</span>
          <small>
            {tokenImpactLabel(token)} · {tokenMarketLabel(token)}
          </small>
        </div>
      ))}
    </div>
  );
}

function ExecutionGapPanel({ brief }: { brief?: NewsAgentBrief | null }) {
  return (
    <section className="news-evidence-inner-section">
      <div className="news-evidence-section-heading">
        <h3>Execution gaps</h3>
        <span className="news-evidence-pill is-context">{brief?.data_gap_count ?? 0} gaps</span>
      </div>
      <div className="news-evidence-gap-grid">
        <GapItem
          label="Price reaction"
          text={gapText(brief, "price_reaction", "No persisted price reaction field is attached.")}
        />
        <GapItem
          label="Liquidity / OI"
          text={gapText(brief, "liquidity", "No persisted liquidity or open-interest field is attached.")}
        />
        <GapItem label="Agent thesis" text={agentThesisText(brief)} />
      </div>
    </section>
  );
}

function GapItem({ label, text }: { label: string; text: string }) {
  return (
    <div className="news-evidence-gap-item">
      <b>{label}</b>
      <p>{text}</p>
    </div>
  );
}

function FactEvidence({ facts }: { facts: NewsFactLane[] }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={FileText} title="Facts" tag={`${facts.length} rows`} />
      {facts.length ? (
        <div className="news-evidence-card-list">
          {facts.map((fact, index) => (
            <div className="news-evidence-card" key={`${fact.event_type ?? "fact"}-${index}`}>
              <b>{fact.claim || fact.event_type || "fact candidate"}</b>
              <span>{fact.status || "status missing"}</span>
              <small>
                {fact.realis ? `${fact.realis} · ` : ""}
                {Array.isArray(fact.affected_targets)
                  ? `${fact.affected_targets.length} affected target candidates`
                  : "target extraction not present"}
              </small>
            </div>
          ))}
        </div>
      ) : (
        <p className="news-evidence-muted">No fact lane rows are attached.</p>
      )}
    </section>
  );
}

function AgentBriefState({
  item,
  brief,
  run,
}: {
  item: NewsItemDetail;
  brief?: NewsAgentBrief | null;
  run?: NewsItemDetail["agent_run"] | null;
}) {
  const requirement = item.signal.agent_requirement ?? item.agent_requirement_json ?? null;
  const requirementStatus =
    item.agent_requirement_status ?? requirement?.status ?? brief?.requirement_status ?? null;
  const requirementReason =
    item.agent_requirement_reason ?? requirement?.reason ?? brief?.requirement_reason ?? brief?.eligibility_reason ?? null;
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={Activity} title="Agent state" tag={brief?.status || "absent"} />
      <dl className="news-evidence-definition-list">
        <FieldRow label="Requirement" value={requirementStatus} />
        <FieldRow label="Requirement reason" value={requirementReason} />
        <FieldRow label="Requirement priority" value={item.agent_requirement_priority ?? requirement?.priority} />
        <FieldRow label="Status" value={brief?.status || run?.status || "absent"} />
        <FieldRow label="Eligibility reason" value={brief?.eligibility_reason} />
        <FieldRow label="Admission" value={item.analysis_admission_status} />
        <FieldRow label="Admission reason" value={item.analysis_admission_reason} />
        <FieldRow
          label="Push block"
          value={item.signal.alert_eligibility?.external_push_block_reason}
        />
        <FieldRow label="Outcome" value={run?.outcome} />
        <FieldRow label="Run" value={run?.run_id} />
        <FieldRow label="Lane" value={run?.lane} />
        <FieldRow label="Prompt" value={run?.prompt_version || brief?.prompt_version} />
        <FieldRow label="Schema" value={run?.schema_version || brief?.schema_version} />
        <FieldRow label="Computed" value={formatTimestamp(brief?.computed_at_ms)} />
      </dl>
    </section>
  );
}

function TokenIdentityEvidence({ tokens }: { tokens: NewsTokenLane[] }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={Database} title="Token impacts" tag={`${tokens.length} rows`} />
      {tokens.length ? (
        <div className="news-evidence-card-list">
          {tokens.map((token, index) => (
            <div className="news-evidence-card" key={`${token.symbol ?? token.target_id ?? "identity"}-${index}`}>
              <b>{token.symbol || token.target_id || "unknown token"}</b>
              <span>{token.resolution_status || token.lane}</span>
              <small>
                {[token.target_type, token.market_type, token.target_id].filter(Boolean).join(" · ") ||
                  "identity metadata missing"}
              </small>
            </div>
          ))}
        </div>
      ) : (
        <p className="news-evidence-muted">No token identity rows are attached.</p>
      )}
    </section>
  );
}

function ObservationEvidence({ item }: { item: NewsItemDetail }) {
  const edges = item.observation_edges ?? [];
  const observations = item.provider_observations ?? [];
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={Database} title="Observation set" tag={`${edges.length} edges`} />
      <dl className="news-evidence-definition-list">
        <FieldRow label="Source ids" value={uniqueStrings(edges.map((edge) => edge.source_id)).join(", ")} />
        <FieldRow label="Domains" value={uniqueStrings(edges.map((edge) => edge.source_domain)).join(", ")} />
        <FieldRow label="Provider rows" value={observations.length} />
        <FieldRow label="Duplicate" value={item.duplicate_observation_count} />
      </dl>
      <JsonDetails title="Observation edges JSON" value={edges} />
      <JsonDetails title="Provider observations JSON" value={observations} />
    </section>
  );
}

function MetadataEvidence({ item }: { item: NewsItemDetail }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={ShieldCheck} title="Source metadata" tag={item.source?.source_quality_status || "raw"} />
      <dl className="news-evidence-definition-list">
        <FieldRow label="Lifecycle" value={item.lifecycle_status} />
        <FieldRow label="Provider" value={item.source?.provider_type || item.provider_type} />
        <FieldRow label="Source" value={item.source?.source_name || item.source_domain} />
        <FieldRow label="Domain" value={item.source?.source_domain || item.source_domain} />
        <FieldRow label="Trust" value={item.source?.trust_tier} />
      </dl>
    </section>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  tag,
  tone = "is-context",
}: {
  icon: IconComponent;
  title: string;
  tag?: string | null;
  tone?: string;
}) {
  return (
    <div className="news-evidence-section-heading">
      <div className="news-evidence-section-title">
        <Icon aria-hidden size={15} />
        <h3>{title}</h3>
      </div>
      {tag ? <span className={`news-evidence-pill ${tone}`}>{tag}</span> : null}
    </div>
  );
}

function FieldRow({ label, value }: { label: string; value?: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{displayScalar(value)}</dd>
    </div>
  );
}

function NarrativeBlock({ label, text }: { label: string; text?: string | null }) {
  if (!text) return null;
  return (
    <div className="news-evidence-narrative">
      <b>{label}</b>
      <p>{text}</p>
    </div>
  );
}

function ViewCard({
  title,
  strength,
  text,
}: {
  title: string;
  strength?: string | null;
  text?: string | null;
}) {
  return (
    <div className="news-evidence-view-card">
      <span>{title}</span>
      <b>{strength || "not scored"}</b>
      <p>{text || "No thesis text is persisted."}</p>
    </div>
  );
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="news-evidence-list-block">
      <b>{title}</b>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceRefList({ refs }: { refs: NewsAgentEvidenceRef[] }) {
  if (!refs.length) return null;
  return <ListBlock title="Evidence refs" items={refs.map(evidenceRefLabel)} />;
}

function JsonDetails({
  title,
  value,
  open = false,
}: {
  title: string;
  value: unknown;
  open?: boolean;
}) {
  return (
    <details className="news-evidence-json-block" open={open}>
      <summary>{title}</summary>
      <pre>{formatJson(value)}</pre>
    </details>
  );
}

function sourceDomainList(item: NewsItemDetail): string[] {
  return uniqueStrings([
    item.source?.source_domain,
    item.source_domain,
    ...(item.observation_edges ?? []).map((edge) => edge.source_domain),
  ]);
}

function providerObservationCount(item: NewsItemDetail): number {
  return item.provider_observations?.length || item.observation_edges?.length || 0;
}

function usageLabel(value?: Record<string, unknown>): string | null {
  if (!value) return null;
  const input = value.input_tokens ?? value.prompt_tokens ?? value.input;
  const output = value.output_tokens ?? value.completion_tokens ?? value.output;
  const total = value.total_tokens ?? value.total;
  if (total != null) return `${displayScalar(total)} total`;
  if (input != null || output != null) return `${displayScalar(input)} in / ${displayScalar(output)} out`;
  return null;
}

function gapText(brief: NewsAgentBrief | null | undefined, kind: string, fallback: string): string {
  const matchingGap = (brief?.data_gaps ?? []).find((gap) => dataGapMatches(gap, kind));
  if (!matchingGap) return fallback;
  return dataGapDescription(matchingGap);
}

function dataGapMatches(gap: NewsAgentDataGap, kind: string): boolean {
  if (typeof gap === "string") return gap.toLowerCase().includes(kind);
  return [gap.kind, gap.reason, gap.description, gap.description_zh]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(kind));
}

function dataGapDescription(gap: NewsAgentDataGap): string {
  if (typeof gap === "string") return gap;
  return gap.description_zh || gap.description || gap.reason || gap.kind || "Persisted data gap.";
}

function agentThesisText(brief: NewsAgentBrief | null | undefined): string {
  const matchingGap = (brief?.data_gaps ?? []).find((gap) => dataGapMatches(gap, "agent_thesis"));
  if (matchingGap) return dataGapDescription(matchingGap);
  return "No persisted agent thesis field is attached to this news item.";
}

function evidenceRefLabel(ref: NewsAgentEvidenceRef): string {
  if (typeof ref === "string") return ref;
  return [ref.ref, ref.label, ref.source, ref.quote].filter(Boolean).join(" · ") || "evidence ref";
}

function formatTimestamp(value?: number | null): string | null {
  if (!value) return null;
  return `${formatRelativeTime(value)} ago · ${new Date(value).toLocaleString()}`;
}

function formatDuration(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${value}ms`;
}

function displayScalar(value: unknown): string {
  if (value === null || value === undefined || value === "") return "not present";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "not present";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.length ? value.map(displayScalar).join(", ") : "none";
  return formatJson(value);
}

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? null, null, 2);
}

function uniqueStrings(values: unknown[]): string[] {
  return [...new Set(values.map((value) => (typeof value === "string" ? value.trim() : "")).filter(Boolean))];
}
