import { ExternalLink } from "lucide-react";
import type { AlertRecord, AssetAttributionRecord, EntityRecord, EventRecord, SearchData } from "../api/types";
import { eventHandle, eventText, formatRelativeTime, shortAddress } from "../lib/format";
import {
  DetailDrawerHeader,
  DetailDrawerMetric,
  DetailDrawerMetricGrid,
  DetailDrawerSection,
  DetailDrawerShell
} from "./DetailDrawer";

export type EvidenceDetailDrawerProps =
  | {
      mode: "event";
      event: EventRecord;
      entities: EntityRecord[];
      alerts: AlertRecord[];
      assetAttributions: AssetAttributionRecord[];
      matchType?: string | null;
      score?: number | null;
      sourceLabel: string;
    }
  | {
      mode: "query";
      query: string;
      data: SearchData | null;
      isFetching: boolean;
      error?: Error | null;
    };

export function EvidenceDetailDrawer(props: EvidenceDetailDrawerProps) {
  if (props.mode === "query") {
    return <SearchQueryDrawer {...props} />;
  }
  const chips = evidenceChips(props.event, props.entities);
  return (
    <DetailDrawerShell className="evidence-drawer">
      <DetailDrawerHeader
        badge={props.score === null || props.score === undefined ? "-" : Math.round(props.score)}
        eyebrow="selected evidence"
        subtitle={
          <>
            {props.sourceLabel} · {props.matchType ?? "stream"} · {formatRelativeTime(props.event.received_at_ms)}
          </>
        }
        title={`@${eventHandle(props.event)}`}
      />

      <DetailDrawerSection className="evidence-body" title="post">
        <p className="evidence-text">{eventText(props.event) || "no text"}</p>
        {props.event.canonical_url ? (
          <a className="external-row" href={props.event.canonical_url} rel="noreferrer" target="_blank">
            <ExternalLink aria-hidden />
            Open source post
          </a>
        ) : null}
      </DetailDrawerSection>

      <DetailDrawerSection title="entities">
        {chips.length ? (
          <div className="entity-tags evidence-tags">
            {chips.map((chip) => (
              <span key={`${chip.type}:${chip.value}`}>
                {chip.type}:{chip.value}
              </span>
            ))}
          </div>
        ) : (
          <div className="empty-state compact">no extracted entities</div>
        )}
      </DetailDrawerSection>

      <DetailDrawerSection title="asset attribution">
        {props.assetAttributions.length ? (
          <div className="evidence-list">
            {props.assetAttributions.map((item) => (
              <div className="evidence-kv-row" key={item.attribution_id ?? `${item.asset_id}:${item.venue_id}`}>
                <strong>{item.canonical_symbol ? `$${item.canonical_symbol}` : shortAddress(item.address ?? item.asset_id)}</strong>
                <span>
                  {item.venue_type ?? item.chain ?? item.exchange ?? "-"} · {item.attribution_status ?? item.identity_status ?? "-"} · conf {formatConfidence(item.confidence)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state compact">no asset attribution</div>
        )}
      </DetailDrawerSection>

      <DetailDrawerSection title="alerts">
        {props.alerts.length ? (
          <div className="evidence-list">
            {props.alerts.map((item) => (
              <div className="evidence-kv-row" key={`${item.alert_type}:${item.event_id}:${item.entity_key}`}>
                <strong>{item.alert_type}</strong>
                <span>{item.summary ?? item.entity_key ?? item.normalized_value ?? "-"}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state compact">no watched-account alert</div>
        )}
      </DetailDrawerSection>
    </DetailDrawerShell>
  );
}

function SearchQueryDrawer({ query, data, isFetching, error }: Extract<EvidenceDetailDrawerProps, { mode: "query" }>) {
  const total = data?.total_count ?? 0;
  const returned = data?.returned_count ?? 0;
  const items = data?.items ?? [];
  return (
    <DetailDrawerShell className="evidence-drawer">
      <DetailDrawerHeader
        badge={isFetching ? "..." : total}
        eyebrow="selected evidence"
        metrics={
          <DetailDrawerMetricGrid className="evidence-query-kv">
            <DetailDrawerMetric label="returned" value={returned} />
            <DetailDrawerMetric label="total" value={total} />
            <DetailDrawerMetric label="more" value={data?.has_more ? "yes" : "no"} />
            <DetailDrawerMetric label="state" value={error ? "error" : isFetching ? "loading" : "ready"} />
          </DetailDrawerMetricGrid>
        }
        subtitle={query || "empty query"}
        title="Search"
      />
      <DetailDrawerSection title="search context">
        <p className="ledger-note">
          {error ? error.message : total ? "命中项已收进当前 Evidence，上下文不再散落到底部面板。" : "没有命中时，尝试 CA、$SYMBOL、@handle 或更具体的文本。"}
        </p>
      </DetailDrawerSection>

      <DetailDrawerSection title="matches">
        {isFetching ? <div className="empty-state compact">检索中</div> : null}
        {!isFetching && items.length === 0 ? <div className="empty-state compact">no matches</div> : null}
        {!isFetching && items.length ? (
          <div className="evidence-list">
            {items.slice(0, 8).map((item) => (
              <article className="evidence-match-row" key={`${item.match_type}:${item.event.event_id}`}>
                <header>
                  <strong>@{eventHandle(item.event)}</strong>
                  <span>
                    {item.match_type} · {formatRelativeTime(item.event.received_at_ms)}
                  </span>
                </header>
                <p>{eventText(item.event) || "no text"}</p>
                {item.event.canonical_url ? (
                  <a className="external-row" href={item.event.canonical_url} rel="noreferrer" target="_blank">
                    <ExternalLink aria-hidden />
                    Open source post
                  </a>
                ) : null}
              </article>
            ))}
          </div>
        ) : null}
      </DetailDrawerSection>
    </DetailDrawerShell>
  );
}

function evidenceChips(event: EventRecord, entities: EntityRecord[]): Array<{ type: string; value: string }> {
  const rows = entities.map((item) => ({
    type: item.entity_type,
    value: item.entity_type === "ca" ? shortAddress(item.normalized_value) : item.normalized_value
  }));
  rows.push(...(event.cashtags ?? []).map((value) => ({ type: "$", value })));
  rows.push(...(event.hashtags ?? []).map((value) => ({ type: "#", value })));
  rows.push(...(event.mentions ?? []).map((value) => ({ type: "@", value })));
  rows.push(...(event.urls ?? []).map((value) => ({ type: "url", value })));
  const seen = new Set<string>();
  return rows.filter((item) => {
    const key = `${item.type}:${item.value}`;
    if (!item.value || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}
