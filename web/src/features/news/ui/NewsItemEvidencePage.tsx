import { formatRelativeTime } from "@lib/format";
import type {
  NewsAgentBrief,
  NewsAgentDataGap,
  NewsAgentEvidenceRef,
  NewsFactLane,
  NewsItemDetail,
  NewsMarketScope,
  NewsTokenLane,
} from "@shared/model/newsIntel";
import { newsLifecycleLabel } from "@shared/model/newsIntel";
import { Activity, Brain, Database, ExternalLink, FileText, ShieldCheck } from "lucide-react";
import type { ComponentType } from "react";

import {
  newsSignalLabel,
  newsSignalScoreLabel,
  newsSignalTone,
} from "../model/newsSignalViewModel";
import "./NewsItemEvidencePage.css";

type NewsItemEvidencePageProps = {
  item: NewsItemDetail;
};

type IconComponent = ComponentType<{ "aria-hidden"?: boolean; size?: number }>;

export function NewsItemEvidencePage({ item }: NewsItemEvidencePageProps) {
  const tokenIdentities = item.token_lanes ?? [];
  const facts = item.fact_lanes ?? [];
  const displaySignal = item.signal.display_signal;
  const brief = item.agent_brief ?? null;
  const run = item.agent_run ?? null;
  const displayTitle = brief?.title_zh || displaySignal.title_zh || item.headline;
  const sourceDomains = sourceDomainList(item);
  const marketScope = marketScopeForItem(item);
  const eligibility = item.signal.alert_eligibility;

  return (
    <article className="news-evidence-page">
      <header className="news-evidence-hero">
        <div className="news-evidence-hero-copy">
          <div className="news-evidence-kicker">
            <span>Evidence page</span>
            <span className={newsSignalTone(displaySignal)}>{newsSignalLabel(displaySignal)}</span>
            <span>{brief?.decision_class || "decision pending"}</span>
            <span>
              {eligibility.external_push_ready
                ? "push ready"
                : eligibility.external_push_block_reason || "push pending"}
            </span>
          </div>
          <h2>{displayTitle}</h2>
          <p>
            {brief?.summary_zh ||
              displaySignal.summary_zh ||
              item.summary ||
              "No summary is present."}
          </p>
        </div>
        <SourcePacket item={item} displayTitle={displayTitle} sourceDomains={sourceDomains} />
      </header>

      <section className="news-evidence-metric-grid" aria-label="news item state">
        <EvidenceMetric
          label="Signal"
          value={newsSignalScoreLabel(displaySignal)}
          detail={displaySignal.method || displaySignal.provider || displaySignal.source}
        />
        <EvidenceMetric
          label="Market scope"
          value={marketScopeLabel(marketScope)}
          detail={marketScope?.reason || eligibility.agent_admission_status}
        />
        <EvidenceMetric
          label="Source set"
          value={`${sourceDomains.length || 1} domain${sourceDomains.length === 1 ? "" : "s"}`}
          detail={`duplicates ${displayScalar(item.duplicate_observation_count ?? providerObservationCount(item))}`}
        />
        <EvidenceMetric
          label="Notification"
          value={notificationStateLabel(eligibility.external_push_ready)}
          detail={eligibility.external_push_block_reason || eligibility.external_push_basis}
        />
        <EvidenceMetric
          label="Agent run"
          value={run?.outcome || brief?.status || "pending"}
          detail={
            run?.latency_ms == null
              ? run?.model
              : `${formatDuration(run.latency_ms)} · ${run.model || ""}`
          }
        />
      </section>

      <div className="news-evidence-layout">
        <main className="news-evidence-main">
          <OriginalArticle item={item} />
          <AiInterpretation brief={brief} displayDirection={displaySignal.direction} />
        </main>
        <aside className="news-evidence-side" aria-label="news evidence metadata">
          <MarketScopeEvidence item={item} />
          <SignalEvidence item={item} />
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

function MarketScopeEvidence({ item }: { item: NewsItemDetail }) {
  const scope = marketScopeForItem(item);
  const eligibility = item.signal.alert_eligibility;
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={Activity} title="Market & notification" tag={marketScopeLabel(scope)} />
      <dl className="news-evidence-definition-list">
        <FieldRow label="Primary scope" value={scope?.primary} />
        <FieldRow label="Scope set" value={scope?.scope ?? []} />
        <FieldRow label="Scope reason" value={scope?.reason} />
        <FieldRow
          label="Agent admission"
          value={item.agent_admission_status || eligibility.agent_admission_status}
        />
        <FieldRow
          label="Admission reason"
          value={item.agent_admission_reason || eligibility.agent_admission_reason}
        />
        <FieldRow
          label="Representative"
          value={
            item.agent_representative_news_item_id ||
            item.agent_admission?.representative_news_item_id
          }
        />
        <FieldRow label="In-app eligible" value={eligibility.in_app_eligible} />
        <FieldRow
          label="External push"
          value={notificationStateLabel(eligibility.external_push_ready)}
        />
        <FieldRow label="Push block" value={eligibility.external_push_block_reason} />
      </dl>
      <JsonDetails title="Market scope JSON" value={scope ?? {}} />
      <JsonDetails title="Agent admission JSON" value={item.agent_admission ?? {}} />
    </section>
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
        {sourceDomains.join(", ") ||
          item.source?.provider_type ||
          item.provider_type ||
          "provider unknown"}
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
        <FieldRow
          label="Evidence refs"
          value={(brief?.evidence_refs ?? []).map(evidenceRefLabel).join(", ")}
        />
      </dl>
      <NarrativeBlock label="Market read" text={brief?.market_read_zh} />
      <div className="news-evidence-view-grid">
        <ViewCard
          title="Bull view"
          strength={brief?.bull_strength}
          text={brief?.bull_view?.thesis_zh}
        />
        <ViewCard
          title="Bear view"
          strength={brief?.bear_strength}
          text={brief?.bear_view?.thesis_zh}
        />
      </div>
      <ExecutionGapPanel brief={brief} />
      <ListBlock title="Watch triggers" items={brief?.watch_triggers ?? []} />
      <ListBlock title="Invalidation" items={brief?.invalidation_conditions ?? []} />
      <JsonDetails title="Affected entities JSON" value={brief?.affected_entities ?? []} />
    </section>
  );
}

function SignalEvidence({ item }: { item: NewsItemDetail }) {
  const displaySignal = item.signal.display_signal;
  return (
    <section className="news-evidence-section">
      <SectionHeading
        icon={ShieldCheck}
        title="Signal"
        tag={displaySignal.status || "missing"}
        tone={newsSignalTone(displaySignal)}
      />
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Source" value={displaySignal.provider || displaySignal.source} />
        <FieldRow label="Method" value={displaySignal.method} />
        <FieldRow label="Direction" value={displaySignal.direction} />
        <FieldRow label="Signal" value={displaySignal.signal} />
        <FieldRow label="Score" value={displaySignal.score} />
        <FieldRow label="Grade" value={displaySignal.grade} />
      </dl>
      <p>
        {displaySignal.summary_zh || displaySignal.summary_en || "No signal summary is present."}
      </p>
    </section>
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
          text={gapText(
            brief,
            "liquidity",
            "No persisted liquidity or open-interest field is attached.",
          )}
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
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={Activity} title="Agent state" tag={brief?.status || "absent"} />
      <dl className="news-evidence-definition-list">
        <FieldRow label="Admission" value={item.agent_admission_status} />
        <FieldRow label="Admission reason" value={item.agent_admission_reason} />
        <FieldRow label="Representative" value={item.agent_representative_news_item_id} />
        <FieldRow label="Status" value={brief?.status || run?.status || "absent"} />
        <FieldRow
          label="Push block"
          value={item.signal.alert_eligibility?.external_push_block_reason}
        />
        <FieldRow label="Outcome" value={run?.outcome} />
        <FieldRow label="Lane" value={run?.lane} />
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
            <div
              className="news-evidence-card"
              key={`${token.symbol ?? token.target_id ?? "identity"}-${index}`}
            >
              <b>{token.symbol || token.target_id || "unknown token"}</b>
              <span>{token.resolution_status || token.lane}</span>
              <small>
                {[token.target_type, token.market_type, token.target_id]
                  .filter(Boolean)
                  .join(" · ") || "identity metadata missing"}
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
        <FieldRow
          label="Source ids"
          value={uniqueStrings(edges.map((edge) => edge.source_id)).join(", ")}
        />
        <FieldRow
          label="Domains"
          value={uniqueStrings(edges.map((edge) => edge.source_domain)).join(", ")}
        />
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
      <SectionHeading
        icon={ShieldCheck}
        title="Source metadata"
        tag={item.source?.source_quality_status || "raw"}
      />
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

function marketScopeForItem(item: NewsItemDetail): NewsMarketScope | null {
  return item.market_scope ?? item.signal.alert_eligibility.market_scope ?? null;
}

function marketScopeLabel(scope?: NewsMarketScope | null): string {
  if (!scope?.primary) return "scope pending";
  return scope.primary.replace(/_/g, " ");
}

function notificationStateLabel(value?: boolean | null): string {
  if (value === true) return "push ready";
  if (value === false) return "push blocked";
  return "push pending";
}

function providerObservationCount(item: NewsItemDetail): number {
  return item.provider_observations?.length || item.observation_edges?.length || 0;
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
  return [
    ...new Set(
      values.map((value) => (typeof value === "string" ? value.trim() : "")).filter(Boolean),
    ),
  ];
}
