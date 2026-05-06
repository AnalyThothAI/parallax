import type { TradingAttentionItem } from "../api/types";
import { compactNumber, formatRelativeTime } from "../lib/format";
import {
  DetailDrawerCard,
  DetailDrawerField,
  DetailDrawerFieldGrid,
  DetailDrawerHeader,
  DetailDrawerMetric,
  DetailDrawerMetricGrid,
  DetailDrawerSection,
  DetailDrawerShell,
  DetailDrawerTagStrip
} from "./DetailDrawer";

type SignalLabInspectorProps = {
  item: TradingAttentionItem;
};

export function SignalLabInspector({ item }: SignalLabInspectorProps) {
  return (
    <DetailDrawerShell className="signal-lab-inspector">
      <DetailDrawerHeader
        badge={item.priority.toUpperCase()}
        eyebrow="selected trading attention"
        metrics={
          <DetailDrawerMetricGrid>
            <DetailDrawerMetric label="heat" value={compactNumber(item.heat_score)} />
            <DetailDrawerMetric label="mentions" value={compactNumber(item.metrics.window_mentions)} />
            <DetailDrawerMetric label="accounts" value={compactNumber(item.metrics.watched_author_count)} />
            <DetailDrawerMetric label="confidence" value={compactNumber(item.metrics.confidence * 100)} />
          </DetailDrawerMetricGrid>
        }
        subtitle={
          <>
            @{item.source.handle ?? "unknown"} · {item.kind_label} · {formatRelativeTime(item.received_at_ms)} ago
          </>
        }
        title={item.title}
      />
      <DetailDrawerSection className="detail-drawer-card-stack">
        <DetailDrawerCard title="Why it matters" tone="accent">
          <p>{item.why_it_matters}</p>
          <p>{item.summary}</p>
        </DetailDrawerCard>
        <DetailDrawerCard title="Original post">
          <DetailDrawerFieldGrid>
            <DetailDrawerField label="event" value={item.event.event_id} />
            <DetailDrawerField label="source" value={`@${item.source.handle ?? "unknown"}`} />
            <DetailDrawerField label="event_type" value={item.event_type ?? "unclassified"} />
            <DetailDrawerField label="direction" value={item.direction_hint ?? "unknown"} />
          </DetailDrawerFieldGrid>
          <p>{item.event.text || "No text available."}</p>
        </DetailDrawerCard>
        <DetailDrawerCard title="Linked tokens">
          {item.linked_tokens.length ? (
            <DetailDrawerFieldGrid>
              {item.linked_tokens.map((token) => (
                <DetailDrawerField
                  key={token.identity_key ?? token.token_id ?? token.symbol}
                  label={token.symbol ?? token.identity_key ?? "token"}
                  value={[token.status, token.relation, token.chain, token.address].filter(Boolean).join(" · ")}
                />
              ))}
            </DetailDrawerFieldGrid>
          ) : (
            <p>No direct token link. This stays as topic attention until a token relationship is proven.</p>
          )}
        </DetailDrawerCard>
        <DetailDrawerCard title="Linked topics">
          {item.linked_topics.length ? (
            <DetailDrawerFieldGrid>
              {item.linked_topics.map((topic) => <DetailDrawerField key={topic.key} label={topic.label} value={topic.role} />)}
            </DetailDrawerFieldGrid>
          ) : (
            <p>No topic terms extracted.</p>
          )}
        </DetailDrawerCard>
        <DetailDrawerCard title="Risks">
          <DetailDrawerTagStrip emptyLabel="No explicit risk flags." items={item.risks} />
          <DetailDrawerField label="next_action" value={item.next_action} />
        </DetailDrawerCard>
      </DetailDrawerSection>
    </DetailDrawerShell>
  );
}
