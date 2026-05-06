import type { TradingAttentionItem } from "../api/types";
import { compactNumber, formatRelativeTime } from "../lib/format";

type SignalLabInspectorProps = {
  item: TradingAttentionItem;
};

export function SignalLabInspector({ item }: SignalLabInspectorProps) {
  return (
    <aside className="detail-drawer drawer signal-lab-inspector">
      <header className="drawer-head">
        <div className="drawer-title">
          <div>
            <div className="eyebrow">selected trading attention</div>
            <h2>{item.title}</h2>
            <p>
              @{item.source.handle ?? "unknown"} · {item.kind_label} · {formatRelativeTime(item.received_at_ms)} ago
            </p>
          </div>
          <div className="opportunity-score">{item.priority.toUpperCase()}</div>
        </div>
        <div className="drawer-kv">
          <div>
            <span>heat</span>
            <b>{compactNumber(item.heat_score)}</b>
          </div>
          <div>
            <span>mentions</span>
            <b>{compactNumber(item.metrics.window_mentions)}</b>
          </div>
          <div>
            <span>accounts</span>
            <b>{compactNumber(item.metrics.watched_author_count)}</b>
          </div>
          <div>
            <span>confidence</span>
            <b>{compactNumber(item.metrics.confidence * 100)}</b>
          </div>
        </div>
      </header>
      <section className="drawer-section signal-inspector-body">
        <article className="signal-inspector-card signal-inspector-primary">
          <h3>Why it matters</h3>
          <p>{item.why_it_matters}</p>
          <p>{item.summary}</p>
        </article>
        <article className="signal-inspector-card">
          <h3>Original post</h3>
          <div className="signal-inspector-fields">
            <Field label="event" value={item.event.event_id} />
            <Field label="source" value={`@${item.source.handle ?? "unknown"}`} />
            <Field label="event_type" value={item.event_type ?? "unclassified"} />
            <Field label="direction" value={item.direction_hint ?? "unknown"} />
          </div>
          <p>{item.event.text || "No text available."}</p>
        </article>
        <article className="signal-inspector-card">
          <h3>Linked tokens</h3>
          {item.linked_tokens.length ? (
            <div className="signal-inspector-fields">
              {item.linked_tokens.map((token) => (
                <Field
                  key={token.identity_key ?? token.token_id ?? token.symbol}
                  label={token.symbol ?? token.identity_key ?? "token"}
                  value={[token.status, token.relation, token.chain, token.address].filter(Boolean).join(" · ")}
                />
              ))}
            </div>
          ) : (
            <p>No direct token link. This stays as topic attention until a token relationship is proven.</p>
          )}
        </article>
        <article className="signal-inspector-card">
          <h3>Linked topics</h3>
          {item.linked_topics.length ? (
            <div className="signal-inspector-fields">
              {item.linked_topics.map((topic) => <Field key={topic.key} label={topic.label} value={topic.role} />)}
            </div>
          ) : (
            <p>No topic terms extracted.</p>
          )}
        </article>
        <article className="signal-inspector-card">
          <h3>Risks</h3>
          <div className="risk-strip signal-inspector-risk-strip">
            {item.risks.length ? item.risks.map((risk) => <span key={risk}>{risk}</span>) : <span>No explicit risk flags.</span>}
          </div>
          <Field label="next_action" value={item.next_action} />
        </article>
      </section>
    </aside>
  );
}

function Field({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="signal-inspector-field">
      <span>{label}</span>
      <b>{value || "-"}</b>
    </div>
  );
}
