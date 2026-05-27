import { formatRelativeTime } from "@lib/format";
import type {
  NewsAgentBrief,
  NewsAgentDataGap,
  NewsFactLane,
  NewsItemDetail,
  NewsTokenLane,
} from "@shared/model/newsIntel";
import { newsLifecycleLabel } from "@shared/model/newsIntel";
import { ExternalLink } from "lucide-react";

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

export function NewsItemEvidencePage({ item }: NewsItemEvidencePageProps) {
  const tokenImpacts = newsDisplayTokenLanes(item);
  const tokenIdentities = item.token_lanes ?? [];
  const facts = item.fact_lanes ?? [];

  return (
    <article className="news-evidence-page">
      <header className="news-evidence-hero">
        <div className="news-evidence-hero-copy">
          <div className="news-evidence-kicker">
            <span>Evidence page</span>
            <span className={newsSignalTone(item.signal)}>{newsSignalLabel(item.signal)}</span>
            <span>{newsSignalScoreLabel(item.signal)}</span>
          </div>
          <h2>{item.headline}</h2>
          <p>{item.summary || item.signal.summary_en || "No persisted source summary is present."}</p>
        </div>
        <SourcePacket item={item} />
      </header>

      <section className="news-evidence-metric-grid" aria-label="provider signal context">
        <EvidenceMetric
          label="Provider aiRating"
          value={newsSignalScoreLabel(item.signal)}
          detail={item.signal.method || item.signal.provider || item.signal.source}
        />
        <EvidenceMetric
          label="Direction"
          value={newsSignalLabel(item.signal)}
          detail={item.signal.direction}
        />
        <EvidenceMetric
          label="Token impacts"
          value={String(tokenImpacts.length)}
          detail={newsLifecycleLabel(item.lifecycle_status)}
        />
      </section>

      <div className="news-evidence-layout">
        <div className="news-evidence-main">
          <ProviderSignalEvidence item={item} tokenImpacts={tokenImpacts} />
          <ExecutionGapPanel brief={item.agent_brief} />
          <FactEvidence facts={facts} />
        </div>
        <aside className="news-evidence-side" aria-label="news evidence metadata">
          <AgentBriefState brief={item.agent_brief} run={item.agent_run} />
          <TokenIdentityEvidence tokens={tokenIdentities} />
          <MetadataEvidence item={item} />
        </aside>
      </div>
    </article>
  );
}

function SourcePacket({ item }: { item: NewsItemDetail }) {
  return (
    <section className="news-evidence-source-packet" aria-label="source packet">
      <span>Source packet</span>
      <b>{item.source?.source_name || item.source_domain || item.signal.provider || "source unknown"}</b>
      <p>{item.headline}</p>
      <small>
        {item.source?.provider_type || item.provider_type || item.signal.source}
        {item.latest_at_ms ? ` · ${formatRelativeTime(item.latest_at_ms)} ago` : ""}
      </small>
      {item.canonical_url ? (
        <a
          className="news-outline-link"
          href={item.canonical_url}
          rel="noreferrer"
          target="_blank"
        >
          <ExternalLink aria-hidden />
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

function ProviderSignalEvidence({
  item,
  tokenImpacts,
}: {
  item: NewsItemDetail;
  tokenImpacts: NewsTokenLane[];
}) {
  return (
    <section className="news-evidence-section news-evidence-provider-rating">
      <div className="news-evidence-section-heading">
        <h3>Provider rating details</h3>
        <span className={`news-evidence-pill ${newsSignalTone(item.signal)}`}>
          {item.signal.status}
        </span>
      </div>
      <dl className="news-evidence-definition-grid">
        <FieldRow label="Source" value={item.signal.provider || item.signal.source} />
        <FieldRow label="Method" value={item.signal.method} />
        <FieldRow label="Direction" value={item.signal.direction} />
        <FieldRow label="Signal" value={item.signal.signal} />
        <FieldRow label="Score" value={item.signal.score == null ? null : String(item.signal.score)} />
        <FieldRow label="Grade" value={item.signal.grade} />
      </dl>
      <p>
        {item.signal.summary_zh ||
          item.signal.summary_en ||
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
        <div
          className="news-evidence-card"
          key={`${token.symbol ?? token.target_id ?? "impact"}-${index}`}
        >
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
    <section className="news-evidence-section news-evidence-gap-panel">
      <div className="news-evidence-section-heading">
        <h3>Execution gaps</h3>
        <span className="news-evidence-pill is-context">{brief?.status || "no brief"}</span>
      </div>
      <div className="news-evidence-gap-grid">
        <GapItem
          label="Price reaction"
          text={gapText(
            brief,
            "price_reaction",
            "No persisted price reaction field is attached to this news item.",
          )}
        />
        <GapItem
          label="Liquidity / OI"
          text={gapText(
            brief,
            "liquidity",
            "No persisted liquidity or open-interest field is attached to this news item.",
          )}
        />
        <GapItem
          label="Agent thesis"
          text={agentThesisText(brief)}
        />
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
      <div className="news-evidence-section-heading">
        <h3>Facts</h3>
        <span className="news-evidence-pill is-context">{facts.length} rows</span>
      </div>
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
  brief,
  run,
}: {
  brief?: NewsAgentBrief | null;
  run?: NewsItemDetail["agent_run"];
}) {
  return (
    <section className="news-evidence-section">
      <div className="news-evidence-section-heading">
        <h3>Agent brief state</h3>
        <span className="news-evidence-pill is-context">{brief?.status || "absent"}</span>
      </div>
      <dl className="news-evidence-definition-list">
        <FieldRow label="Status" value={brief?.status || "absent"} />
        <FieldRow label="Run" value={brief?.agent_run_id || run?.run_id} />
        <FieldRow label="Model" value={brief?.model || run?.model} />
        <FieldRow label="Prompt" value={brief?.prompt_version || run?.prompt_version} />
        <FieldRow label="Schema" value={brief?.schema_version || run?.schema_version} />
        <FieldRow label="Computed" value={formatTimestamp(brief?.computed_at_ms)} />
      </dl>
    </section>
  );
}

function TokenIdentityEvidence({ tokens }: { tokens: NewsTokenLane[] }) {
  return (
    <section className="news-evidence-section">
      <div className="news-evidence-section-heading">
        <h3>Token identity</h3>
        <span className="news-evidence-pill is-context">{tokens.length} rows</span>
      </div>
      {tokens.length ? (
        <div className="news-evidence-card-list">
          {tokens.map((token, index) => (
            <div
              className="news-evidence-card"
              key={`${token.symbol ?? token.target_id ?? "identity"}-${index}`}
            >
              <b>{token.symbol || token.target_id || "unknown token"}</b>
              <span>{token.resolution_status || token.lane}</span>
              <small>{[token.target_type, token.market_type, token.target_id].filter(Boolean).join(" · ") || "identity metadata missing"}</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="news-evidence-muted">No token identity rows are attached.</p>
      )}
    </section>
  );
}

function MetadataEvidence({ item }: { item: NewsItemDetail }) {
  return (
    <section className="news-evidence-section">
      <div className="news-evidence-section-heading">
        <h3>Source metadata</h3>
        <span className="news-evidence-pill is-context">{item.source?.source_quality_status || "raw"}</span>
      </div>
      <dl className="news-evidence-definition-list">
        <FieldRow label="Lifecycle" value={item.lifecycle_status} />
        <FieldRow label="Provider" value={item.source?.provider_type || item.provider_type} />
        <FieldRow label="Source" value={item.source?.source_name || item.source_domain} />
        <FieldRow label="Domain" value={item.source?.source_domain || item.source_domain} />
        <FieldRow label="Trust" value={item.source?.trust_tier} />
        <FieldRow label="Story id" value={item.story_id} />
      </dl>
    </section>
  );
}

function FieldRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value || "not present"}</dd>
    </div>
  );
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

function formatTimestamp(value?: number | null): string | null {
  return value ? `${formatRelativeTime(value)} ago` : null;
}
