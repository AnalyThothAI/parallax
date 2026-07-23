import { formatRelativeTime } from "@lib/format";
import { Activity, Database, ExternalLink, FileText, Layers3, ShieldCheck } from "lucide-react";
import type { ComponentType } from "react";

import type {
  NewsFactItem,
  NewsFactLane,
  NewsMarketScope,
  NewsProviderRating,
  NewsTokenLane,
} from "../model/newsFactViewModel";
import "./NewsItemEvidencePage.css";

type NewsItemEvidencePageProps = {
  item: NewsFactItem;
};

type IconComponent = ComponentType<{ "aria-hidden"?: boolean; size?: number }>;

export function NewsItemEvidencePage({ item }: NewsItemEvidencePageProps) {
  const sourceDomains = sourceDomainList(item);
  const providerRating = item.provider_rating;

  return (
    <article className="news-evidence-page" data-page-archetype="case">
      <header className="news-evidence-hero">
        <div className="news-evidence-hero-copy">
          <div className="news-evidence-kicker">
            <span>Evidence page</span>
            <span>{item.lifecycle_status}</span>
            <span>{item.content_class}</span>
            <span>{item.market_scope.primary}</span>
          </div>
          <h2>{item.title}</h2>
          <p>{item.summary || "No source summary is present."}</p>
        </div>
        <SourcePacket item={item} sourceDomains={sourceDomains} />
      </header>

      <section className="news-evidence-metric-grid" aria-label="news item facts">
        <EvidenceMetric
          label="Lifecycle"
          value={item.lifecycle_status}
          detail={formatTimestamp(item.processed_at_ms)}
        />
        <EvidenceMetric
          label="Story members"
          value={String(item.story.member_count)}
          detail={item.story.story_key}
        />
        <EvidenceMetric
          label="Token lanes"
          value={String(item.token_lanes.length)}
          detail={`${item.token_mentions.length} raw mentions`}
        />
        <EvidenceMetric
          label="Fact candidates"
          value={String(item.fact_lanes.length)}
          detail={`${item.fact_candidates.length} persisted candidates`}
        />
        <EvidenceMetric
          label="Provider rating"
          value={providerRatingLabel(providerRating)}
          detail={providerRating.method || providerRating.provider}
        />
        <EvidenceMetric
          label="Observations"
          value={String(item.provider_observations.length)}
          detail={`${item.duplicate_observation_count} duplicates`}
        />
      </section>

      <div className="news-evidence-layout">
        <main className="news-evidence-main">
          <OriginalArticle item={item} />
          <StoryEvidence item={item} />
          <ContentClassificationEvidence item={item} />
        </main>
        <aside className="news-evidence-side" aria-label="news evidence metadata">
          <MarketScopeEvidence scope={item.market_scope} />
          <TokenIdentityEvidence tokens={item.token_lanes} />
          <FactEvidence facts={item.fact_lanes} />
          <ObservationEvidence item={item} />
          <MetadataEvidence item={item} />
        </aside>
      </div>
    </article>
  );
}

function SourcePacket({ item, sourceDomains }: { item: NewsFactItem; sourceDomains: string[] }) {
  return (
    <section className="news-evidence-source-packet" aria-label="source packet">
      <span>Source packet</span>
      <b>{item.source.source_name || item.source.source_domain}</b>
      <p>{item.title}</p>
      <small>
        {sourceDomains.join(", ") || item.source.provider_type}
        {item.published_at_ms ? ` · ${formatRelativeTime(item.published_at_ms)} ago` : ""}
      </small>
      <a className="news-outline-link" href={item.canonical_url} rel="noreferrer" target="_blank">
        <ExternalLink aria-hidden size={13} />
        Original
      </a>
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

function OriginalArticle({ item }: { item: NewsFactItem }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={FileText} title="Original article" tag="source text" />
      <h3 className="news-evidence-source-title">{item.title}</h3>
      <p className="news-evidence-original-text">
        {item.body_text || "No original body text is persisted for this item."}
      </p>
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Published" value={formatTimestamp(item.published_at_ms)} />
        <FieldRow label="Fetched" value={formatTimestamp(item.fetched_at_ms)} />
        <FieldRow label="Updated" value={formatTimestamp(item.updated_at_ms)} />
        <FieldRow label="Language" value={item.language} />
        <FieldRow label="Content class" value={item.content_class} />
        <FieldRow label="Processing error" value={item.processing_error} />
      </dl>
    </section>
  );
}

function StoryEvidence({ item }: { item: NewsFactItem }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading
        icon={Layers3}
        title="Story membership"
        tag={`${item.story.member_count} members`}
      />
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Story key" value={item.story.story_key} />
        <FieldRow label="Representative" value={item.story.representative_news_item_id} />
        <FieldRow label="This item" value={item.news_item_id} />
      </dl>
      <JsonDetails title="Member news item ids" value={item.story.member_news_item_ids} />
      <JsonDetails title="Provider article keys" value={item.story.provider_article_keys ?? []} />
    </section>
  );
}

function ContentClassificationEvidence({ item }: { item: NewsFactItem }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={ShieldCheck} title="Content classification" tag={item.content_class} />
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Tags" value={item.content_tags} />
        <FieldRow label="Entities" value={item.entities.length} />
        <FieldRow label="Token mentions" value={item.token_mentions.length} />
      </dl>
      <JsonDetails title="Classification facts" value={item.content_classification} open />
    </section>
  );
}

function MarketScopeEvidence({ scope }: { scope: NewsMarketScope }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={Activity} title="Market scope" tag={scope.status} />
      <dl className="news-evidence-definition-list">
        <FieldRow label="Primary" value={scope.primary} />
        <FieldRow label="Scope set" value={scope.scope} />
        <FieldRow label="Reason" value={scope.reason} />
        <FieldRow label="Version" value={scope.version} />
      </dl>
      <JsonDetails title="Scope basis" value={scope.basis} />
    </section>
  );
}

function TokenIdentityEvidence({ tokens }: { tokens: NewsTokenLane[] }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={Database} title="Token identity lanes" tag={`${tokens.length} rows`} />
      {tokens.length ? (
        <div className="news-evidence-card-list">
          {tokens.map((token, index) => (
            <div
              className="news-evidence-card"
              key={`${token.symbol ?? token.target_id ?? "identity"}-${index}`}
            >
              <b>{tokenIdentityLabel(token)}</b>
              <span>{token.resolution_status || token.lane}</span>
              <small>
                {[token.target_type, token.target_id].filter(Boolean).join(" · ") ||
                  "identity metadata missing"}
              </small>
              {token.reason_codes?.length ? <small>{token.reason_codes.join(" · ")}</small> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="news-evidence-muted">No token identity rows are attached.</p>
      )}
    </section>
  );
}

function FactEvidence({ facts }: { facts: NewsFactLane[] }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading icon={FileText} title="Fact lanes" tag={`${facts.length} rows`} />
      {facts.length ? (
        <div className="news-evidence-card-list">
          {facts.map((fact, index) => (
            <div
              className="news-evidence-card"
              key={`${fact.fact_candidate_id ?? fact.event_type ?? "fact"}-${index}`}
            >
              <b>{fact.claim || fact.event_type || "fact candidate"}</b>
              <span>{fact.status}</span>
              <small>
                {fact.realis ? `${fact.realis} · ` : ""}
                {(fact.affected_targets ?? []).length} affected target candidates
              </small>
              {fact.rejection_reasons?.length ? (
                <small>{fact.rejection_reasons.join(" · ")}</small>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="news-evidence-muted">No fact lane rows are attached.</p>
      )}
    </section>
  );
}

function tokenIdentityLabel(token: NewsTokenLane): string {
  if (token.symbol && token.display_name) {
    return `${token.symbol} · ${token.display_name}`;
  }
  return token.symbol || token.display_name || token.target_id || "unknown token";
}

function ObservationEvidence({ item }: { item: NewsFactItem }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading
        icon={Database}
        title="Observation set"
        tag={`${item.observation_edges.length} edges`}
      />
      <dl className="news-evidence-definition-list">
        <FieldRow label="Provider rows" value={item.provider_observations.length} />
        <FieldRow label="Duplicate" value={item.duplicate_observation_count} />
        <FieldRow label="Source id" value={item.source_id} />
      </dl>
      <JsonDetails title="Observation edges" value={item.observation_edges} />
      <JsonDetails title="Provider observations" value={item.provider_observations} />
    </section>
  );
}

function MetadataEvidence({ item }: { item: NewsFactItem }) {
  return (
    <section className="news-evidence-section">
      <SectionHeading
        icon={ShieldCheck}
        title="Source metadata"
        tag={item.source.source_quality_status}
      />
      <dl className="news-evidence-definition-list">
        <FieldRow label="Provider" value={item.source.provider_type} />
        <FieldRow label="Source" value={item.source.source_name || item.source.source_domain} />
        <FieldRow label="Role" value={item.source.source_role} />
        <FieldRow label="Trust" value={item.source.trust_tier} />
        <FieldRow label="Coverage" value={item.source.coverage_tags} />
        <FieldRow label="Managed" value={item.source.managed_by_config} />
        <FieldRow label="Enabled" value={item.source.enabled} />
      </dl>
    </section>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  tag,
}: {
  icon: IconComponent;
  title: string;
  tag?: string | null;
}) {
  return (
    <div className="news-evidence-section-heading">
      <div className="news-evidence-section-title">
        <Icon aria-hidden size={15} />
        <h3>{title}</h3>
      </div>
      {tag ? <span className="news-evidence-pill is-context">{tag}</span> : null}
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

function sourceDomainList(item: NewsFactItem): string[] {
  return uniqueStrings([
    item.source.source_domain,
    item.source_domain,
    ...item.story.source_domains,
  ]);
}

function providerRatingLabel(rating: NewsProviderRating): string {
  if (rating.score == null) {
    return rating.status || "not scored";
  }
  return `${rating.score}${rating.grade ? ` ${rating.grade}` : ""}`;
}

function formatTimestamp(value?: number | null): string | null {
  if (!value) return null;
  return `${formatRelativeTime(value)} ago · ${new Date(value).toLocaleString()}`;
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
