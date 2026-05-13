import { eventHandle, eventText, formatRelativeTime, shortAddress } from "@lib/format";
import type {
  AlertRecord,
  EntityRecord,
  EventRecord,
  TokenIntentRecord,
  TokenResolutionRecord,
} from "@lib/types";
import { DetailDrawerHeader, DetailDrawerSection, DetailDrawerShell } from "@shared/ui/DetailDrawer";
import { ExternalLink } from "lucide-react";



export type EvidenceDetailDrawerProps = {
  mode: "event";
  event: EventRecord;
  entities: EntityRecord[];
  alerts: AlertRecord[];
  tokenIntents: TokenIntentRecord[];
  tokenResolutions: TokenResolutionRecord[];
  matchType?: string | null;
  score?: number | null;
  sourceLabel: string;
};

export function EvidenceDetailDrawer(props: EvidenceDetailDrawerProps) {
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
