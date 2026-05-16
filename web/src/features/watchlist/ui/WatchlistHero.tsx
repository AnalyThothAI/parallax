import { formatRelativeTime } from "@lib/format";
import { searchPath } from "@shared/routing/paths";
import { RouteBackLink } from "@shared/ui/RouteBackLink";
import { AtSign, ExternalLink, Radio, Search } from "lucide-react";
import { Link } from "react-router-dom";

export function WatchlistHero({
  handle,
  lastSeenAtMs,
}: {
  handle: string;
  lastSeenAtMs: number | null;
}) {
  return (
    <header className="watchlist-monitor-hero">
      <div className="watchlist-source-mark" aria-hidden>
        <AtSign />
      </div>
      <div className="watchlist-monitor-title">
        <span className="watchlist-kicker">
          <Radio aria-hidden />
          source monitor
        </span>
        <h2>@{handle}</h2>
        <p>{lastSeenCopy(lastSeenAtMs)}</p>
      </div>
      <div className="watchlist-monitor-actions" aria-label="Account actions">
        <RouteBackLink to="/" label="返回" ariaLabel="返回 Token Radar" />
        <Link className="watchlist-action primary" to={searchPath({ q: `@${handle}` })}>
          <Search aria-hidden />
          Search account
        </Link>
        <a
          className="watchlist-action"
          href={`https://x.com/${handle}`}
          rel="noreferrer"
          target="_blank"
        >
          <ExternalLink aria-hidden />
          Open X
        </a>
      </div>
    </header>
  );
}

function lastSeenCopy(value: number | null): string {
  return value ? `Last source event ${formatRelativeTime(value)} ago` : "No recent source event";
}
