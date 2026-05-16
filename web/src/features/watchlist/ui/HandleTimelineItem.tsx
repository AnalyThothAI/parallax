import { formatRelativeTime, formatTokenPriceUsd } from "@lib/format";
import type { WatchlistTimelineItem } from "@lib/types";
import { ObsidianPill } from "@shared/ui/case-file";

export function HandleTimelineItem({ item }: { item: WatchlistTimelineItem }) {
  const social = item.social_event;
  const summary = social?.summary_zh;
  const anchorTerms = termsFromRecords(social?.anchor_terms, "term");
  const tokenSymbols = termsFromRecords(social?.token_candidates, "symbol");
  const pills = uniquePills([
    social?.event_type,
    social?.subject,
    ...tokenResolutionPills(item.token_resolutions),
    ...tokenSymbols.map((value) => `$${value.replace(/^\$+/, "")}`),
    ...(item.cashtags?.map((value) => `$${value.replace(/^\$+/, "")}`) ?? []),
    ...(item.hashtags?.map((value) => `#${value.replace(/^#+/, "")}`) ?? []),
  ]).slice(0, 8);

  return (
    <li>
      <div className="watchlist-evidence-time">
        <span>
          {item.received_at_ms ? `${formatRelativeTime(item.received_at_ms)} ago` : "no timestamp"}
        </span>
      </div>
      <article className={`watchlist-evidence-card ${summary ? "signal" : "source"}`}>
        <div>
          {item.canonical_url ? (
            <a href={item.canonical_url} rel="noreferrer" target="_blank">
              @{item.author_handle ?? "source"}
            </a>
          ) : (
            <b>@{item.author_handle ?? "source"}</b>
          )}
          <ObsidianPill tone={summary ? "opportunity" : "health"}>
            {summary ? "signal" : "source"}
          </ObsidianPill>
        </div>
        {summary ? <p className="watchlist-signal-summary">{summary}</p> : null}
        {pills.length ? (
          <div className="watchlist-evidence-pills">
            {pills.map((pill) => (
              <span key={pill}>{pill}</span>
            ))}
          </div>
        ) : null}
        {anchorTerms.length ? (
          <div className="watchlist-anchor-row">
            {anchorTerms.slice(0, 5).map((term) => (
              <span key={term}>{term}</span>
            ))}
          </div>
        ) : null}
        {item.text_clean ? (
          <details className="watchlist-original-text">
            <summary>Original</summary>
            <p>{item.text_clean}</p>
          </details>
        ) : null}
      </article>
    </li>
  );
}

function tokenResolutionPills(resolutions: WatchlistTimelineItem["token_resolutions"]): string[] {
  return (resolutions ?? [])
    .flatMap((resolution) => {
      const symbol = tokenSymbol(resolution.symbol) ?? cexSymbolFromTargetId(resolution);
      const priceUsd = resolution.price?.price_usd;
      return [
        symbol ? `$${symbol}` : null,
        typeof priceUsd === "number" ? formatTokenPriceUsd(priceUsd) : null,
      ];
    })
    .filter((value): value is string => Boolean(value));
}

function tokenSymbol(value: string | null | undefined): string | null {
  const text = value?.replace(/^\$+/, "").trim();
  return text ? text.toUpperCase() : null;
}

function cexSymbolFromTargetId(
  resolution: NonNullable<WatchlistTimelineItem["token_resolutions"]>[number],
): string | null {
  if (resolution.target_type !== "CexToken") {
    return null;
  }
  return tokenSymbol(resolution.target_id?.split(":").pop());
}

function uniquePills(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const pills: string[] = [];
  for (const value of values) {
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    pills.push(value);
  }
  return pills;
}

function termsFromRecords(
  records: Array<Record<string, unknown>> | undefined,
  key: string,
): string[] {
  return [
    ...new Set(
      (records ?? [])
        .map((item) => {
          const value = item[key];
          return typeof value === "string" ? value : "";
        })
        .filter(Boolean),
    ),
  ];
}
