import { ArrowRight } from "lucide-react";
import type { AttentionFrontierItem, NarrativeFlowItem, TokenFlowItem } from "../api/types";
import { compactNumber, formatPercentShare, formatRelativeTime, tokenLabel } from "../lib/format";
import { DecisionTag } from "./DecisionTag";

type NarrativePanelProps = {
  token?: TokenFlowItem | null;
  narratives: NarrativeFlowItem[];
  frontierItems: AttentionFrontierItem[];
  llmConfigured: boolean;
  isLoading?: boolean;
};

export function NarrativePanel({
  token,
  narratives,
  frontierItems,
  llmConfigured,
  isLoading
}: NarrativePanelProps) {
  const tokenFrontier = token ? frontierItems.filter((item) => frontierMatchesToken(item, token)) : frontierItems;
  if (isLoading) {
    return <div className="empty-state">加载中文叙事中</div>;
  }
  if (!llmConfigured && narratives.length === 0 && frontierItems.length === 0) {
    return <div className="empty-state">LLM 叙事未启用</div>;
  }
  if (token && tokenFrontier.length === 0) {
    return <div className="empty-state">当前 token 暂无 watched seed link</div>;
  }
  return (
    <div className="narrative-panel">
      {token ? null : (
        <section className="narrative-flow-list">
          {narratives.slice(0, 6).map((item) => (
            <NarrativeFlowRow item={item} key={`${item.narrative_label}:${item.window}`} />
          ))}
          {narratives.length === 0 ? <div className="empty-state">当前窗口暂无中文叙事流</div> : null}
        </section>
      )}

      <section className="narrative-link-list">
        {tokenFrontier.slice(0, token ? 12 : 6).map((item) => (
          <FrontierRow item={item} key={`${item.seed.seed_id}:${item.link.identity.identity_key}`} token={token} />
        ))}
      </section>
    </div>
  );
}

function NarrativeFlowRow({ item }: { item: NarrativeFlowItem }) {
  const display = item.display;
  if (!display || display.readability_status !== "ready" || !display.headline_zh) {
    return <article className="narrative-row error-state">narrative_display_missing</article>;
  }
  return (
    <article className="narrative-row">
      <div>
        <strong>{display.headline_zh}</strong>
        <span>{display.summary_zh}</span>
      </div>
      <b>{compactNumber(item.watched_mention_count)} / {compactNumber(item.mention_count)}</b>
    </article>
  );
}

function FrontierRow({ item, token }: { item: AttentionFrontierItem; token?: TokenFlowItem | null }) {
  const display = item.seed.display;
  const linkSignal = item.link.signal;
  if (!display || display.readability_status !== "ready" || !display.headline_zh) {
    return <article className="narrative-row error-state">narrative_display_missing</article>;
  }
  return (
    <article className="narrative-row frontier-row">
      <div>
        <strong>
          @{item.seed.author_handle ?? "watched"} <ArrowRight aria-hidden />{" "}
          {token ? tokenLabel(token) : `$${item.link.identity.symbol ?? "TOKEN"}`}
        </strong>
        <span>{display.headline_zh}</span>
        <em>{display.market_interpretation_zh}</em>
      </div>
      <aside>
        <DecisionTag decision={linkSignal.decision} />
        <span>{formatRelativeTime(item.seed.received_at_ms)} ago</span>
        <span>lag {formatRelativeTime(Date.now() - Number(item.link.flow.lag_ms ?? 0))}</span>
        <span>conf {formatPercentShare(item.link.evidence.link_confidence)}</span>
      </aside>
    </article>
  );
}

function frontierMatchesToken(item: AttentionFrontierItem, token: TokenFlowItem): boolean {
  const keys = new Set(frontierTokenKeys(token.identity));
  return frontierTokenKeys(item.link.identity).some((key) => keys.has(key));
}

function frontierTokenKeys(identity: TokenFlowItem["identity"]): string[] {
  return [
    `identity:${identity.identity_key}`,
    identity.token_id ? `token:${identity.token_id}` : "",
    identity.address ? `address:${identity.address.toLowerCase()}` : "",
    identity.symbol ? `symbol:${identity.symbol.toUpperCase()}` : ""
  ].filter(Boolean);
}
