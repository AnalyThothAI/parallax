import { ExternalLink } from "lucide-react";

import type {
  AlertRecord,
  EntityRecord,
  EventRecord,
  SearchData,
  TokenIntentRecord,
  TokenResolutionRecord,
} from "../api/types";
import { eventHandle, eventText, formatRelativeTime, shortAddress } from "../lib/format";

import {
  DetailDrawerHeader,
  DetailDrawerMetric,
  DetailDrawerMetricGrid,
  DetailDrawerSection,
  DetailDrawerShell,
} from "./DetailDrawer";

export type EvidenceDetailDrawerProps =
  | {
      mode: "event";
      event: EventRecord;
      entities: EntityRecord[];
      alerts: AlertRecord[];
      tokenIntents: TokenIntentRecord[];
      tokenResolutions: TokenResolutionRecord[];
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
      hasMore: boolean;
      isFetchingNextPage: boolean;
      onLoadMore: () => void;
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
            {props.sourceLabel} · {props.matchType ?? "stream"} ·{" "}
            {formatRelativeTime(props.event.received_at_ms)}
          </>
        }
        title={`@${eventHandle(props.event)}`}
      />

      <DetailDrawerSection className="evidence-body" title="post">
        <p className="evidence-text">{eventText(props.event) || "no text"}</p>
        {props.event.canonical_url ? (
          <a
            className="external-row"
            href={props.event.canonical_url}
            rel="noreferrer"
            target="_blank"
          >
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

      <DetailDrawerSection title="token intent">
        {props.tokenIntents.length || props.tokenResolutions.length ? (
          <div className="evidence-list">
            {props.tokenIntents.map((item) => {
              const resolution = props.tokenResolutions.find(
                (row) => row.intent_id === item.intent_id,
              );
              return (
                <div
                  className="evidence-kv-row"
                  key={item.intent_id ?? `${item.display_symbol}:${item.address_hint}`}
                >
                  <strong>
                    {item.display_symbol
                      ? `$${item.display_symbol}`
                      : shortAddress(item.address_hint ?? item.intent_id)}
                  </strong>
                  <span>
                    {item.chain_hint ?? "intent"} ·{" "}
                    {resolution?.resolution_status ?? item.intent_status ?? "-"} · conf{" "}
                    {formatConfidence(item.intent_confidence)}
                  </span>
                </div>
              );
            })}
            {props.tokenIntents.length
              ? null
              : props.tokenResolutions.map((item) => (
                  <div
                    className="evidence-kv-row"
                    key={item.resolution_id ?? `${item.intent_id}:${item.target_id}`}
                  >
                    <strong>{shortAddress(item.target_id ?? item.intent_id)}</strong>
                    <span>
                      {item.pricefeed_id ?? item.target_type ?? "resolution"} ·{" "}
                      {item.resolution_status ?? "-"}
                    </span>
                  </div>
                ))}
          </div>
        ) : (
          <div className="empty-state compact">no token intent</div>
        )}
      </DetailDrawerSection>

      <DetailDrawerSection title="alerts">
        {props.alerts.length ? (
          <div className="evidence-list">
            {props.alerts.map((item) => (
              <div
                className="evidence-kv-row"
                key={`${item.alert_type}:${item.event_id}:${item.entity_key}`}
              >
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

function SearchQueryDrawer({
  query,
  data,
  isFetching,
  error,
  hasMore,
  isFetchingNextPage,
  onLoadMore,
}: Extract<EvidenceDetailDrawerProps, { mode: "query" }>) {
  const returned = data?.items.length ?? 0;
  const items = data?.items ?? [];
  const pageState = data?.page.has_more ? "more" : "end";
  return (
    <DetailDrawerShell className="evidence-drawer">
      <DetailDrawerHeader
        badge={isFetching ? "..." : returned}
        eyebrow="selected evidence"
        metrics={
          <DetailDrawerMetricGrid className="evidence-query-kv">
            <DetailDrawerMetric label="returned" value={returned} />
            <DetailDrawerMetric label="page" value={pageState} />
            <DetailDrawerMetric
              label="state"
              value={error ? "error" : isFetching ? "loading" : "ready"}
            />
          </DetailDrawerMetricGrid>
        }
        subtitle={query || "empty query"}
        title="Search"
      />
      <DetailDrawerSection title="search context">
        <p className="ledger-note">
          {error
            ? error.message
            : returned
              ? "命中项已收进当前 Evidence，上下文不再散落到底部面板。"
              : "没有命中时，尝试 CA、$SYMBOL、@handle 或更具体的文本。"}
        </p>
      </DetailDrawerSection>

      <DetailDrawerSection title="matches">
        {isFetching ? <div className="empty-state compact">检索中</div> : null}
        {!isFetching && items.length === 0 ? (
          <div className="empty-state compact">no matches</div>
        ) : null}
        {!isFetching && items.length ? (
          <div className="evidence-list">
            {items.map((item) => (
              <article
                className="evidence-match-row"
                key={`${item.match_type}:${item.event.event_id}`}
              >
                <header>
                  <strong>@{eventHandle(item.event)}</strong>
                  <span>
                    {item.match_type} · {formatRelativeTime(item.event.received_at_ms)}
                  </span>
                </header>
                <p>{eventText(item.event) || "no text"}</p>
                {item.event.canonical_url ? (
                  <a
                    className="external-row"
                    href={item.event.canonical_url}
                    rel="noreferrer"
                    target="_blank"
                  >
                    <ExternalLink aria-hidden />
                    Open source post
                  </a>
                ) : null}
              </article>
            ))}
          </div>
        ) : null}
        {hasMore ? (
          <button
            className="secondary-action"
            disabled={isFetchingNextPage}
            onClick={onLoadMore}
            type="button"
          >
            {isFetchingNextPage ? "Loading" : "Load more"}
          </button>
        ) : null}
      </DetailDrawerSection>
    </DetailDrawerShell>
  );
}

function evidenceChips(
  event: EventRecord,
  entities: EntityRecord[],
): Array<{ type: string; value: string }> {
  const rows = entities.map((item) => ({
    type: item.entity_type,
    value: item.entity_type === "ca" ? shortAddress(item.normalized_value) : item.normalized_value,
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
