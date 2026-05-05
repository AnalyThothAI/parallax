import { ExternalLink } from "lucide-react";
import type { SignalLabChain } from "../api/types";
import { chainDisplayTitle, chainRelativeTime, chainScore, chainSource, chainStatusText } from "../lib/signalLabChains";

type SignalChainListProps = {
  items: SignalLabChain[];
  selectedChainId?: string | null;
  isLoading?: boolean;
  compact?: boolean;
  onSelect: (chain: SignalLabChain) => void;
};

export function SignalChainList({ compact, isLoading, items, selectedChainId, onSelect }: SignalChainListProps) {
  if (isLoading) {
    return <div className="empty-state">loading signal chains</div>;
  }
  if (!items.length) {
    return <div className="empty-state">No Signal Chains in this window</div>;
  }
  return (
    <div className={`signal-chain-list ${compact ? "compact" : ""}`}>
      {items.map((chain) => {
        const title = chainListTitle(chain);
        const sourceUrl = chainSourceUrl(chain);
        return (
          <article
            className={`signal-chain-row ${selectedChainId === chain.chain_id ? "selected" : ""}`}
            key={chain.chain_id}
          >
            <button
              aria-label={`open signal chain ${chainDisplayTitle(chain)}`}
              className="signal-chain-select"
              type="button"
              onClick={() => onSelect(chain)}
            >
              <span className={`signal-stage-badge ${chain.stage}`}>{chain.stage}</span>
              <span className="signal-chain-main">
                <strong>{title}</strong>
                <em>
                  {compact ? `${chainDisplayTitle(chain)} · updated ${chainRelativeTime(chain)} ago` : `updated ${chainRelativeTime(chain)} ago`}
                </em>
                <p>{chain.summary || "No summary provided."}</p>
                <span className="signal-chain-chipline">
                  {(chain.evidence_chips ?? []).slice(0, 3).map((chip) => (
                    <span key={chip}>{chip}</span>
                  ))}
                </span>
              </span>
              <span className="signal-chain-score">
                <b>{chainScore(chain)}</b>
                <small>{chainStatusText(chain)}</small>
              </span>
              <span className="signal-chain-time">{chainRelativeTime(chain)}</span>
            </button>
            {sourceUrl ? (
              <a
                aria-label={`open source tweet for ${chainDisplayTitle(chain)}`}
                className="signal-chain-twitter-link"
                href={sourceUrl}
                rel="noreferrer"
                target="_blank"
              >
                <ExternalLink aria-hidden />
              </a>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}

function chainListTitle(chain: SignalLabChain): string {
  const sourceAndType = `${chainSource(chain)} · ${chain.event_type ?? "event"}`;
  return chain.asset || chain.horizon ? `${sourceAndType} -> ${chainDisplayTitle(chain)}` : sourceAndType;
}

function chainSourceUrl(chain: SignalLabChain): string | null {
  const event = chain.social_event?.event;
  if (event?.canonical_url) {
    return event.canonical_url;
  }
  const handle = event?.author?.handle ?? chain.social_event?.author_handle ?? chain.source;
  if (handle && event?.tweet_id) {
    return `https://x.com/${handle.replace(/^@/, "")}/status/${event.tweet_id}`;
  }
  return null;
}
