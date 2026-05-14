import { formatRelativeTime } from "@lib/format";
import { watchlistPath } from "@shared/routing/paths";
import { RemoteState } from "@shared/ui/RemoteState";
import {
  ObsidianActionBar,
  ObsidianEvidenceList,
  ObsidianField,
  ObsidianFieldGrid,
  ObsidianMiniPage,
  ObsidianPill,
  ObsidianRecord,
  ObsidianSection,
} from "@shared/ui/case-file";
import clsx from "clsx";
import { Link, useSearchParams } from "react-router-dom";

import type { WatchlistAccountCase } from "../model/watchlistCase";
import { normalizeWatchlistHandle } from "../model/watchlistCase";

type WatchlistPageProps = {
  accountCases: WatchlistAccountCase[];
};

export function WatchlistPage({ accountCases }: WatchlistPageProps) {
  const [searchParams] = useSearchParams();
  const selectedHandle =
    normalizeWatchlistHandle(searchParams.get("handle")) ?? accountCases[0]?.handle ?? null;
  const selectedCase =
    accountCases.find((item) => item.handle === selectedHandle) ?? accountCases[0] ?? null;

  if (!selectedCase) {
    return (
      <section className="watchlist-page" aria-label="Watchlist">
        <RemoteState.Empty title="No watchlist handles configured." />
      </section>
    );
  }

  return (
    <section className="watchlist-page" aria-label="Watchlist">
      <ObsidianMiniPage
        aside={
          <WatchlistAccountList accountCases={accountCases} selectedHandle={selectedCase.handle} />
        }
        eyebrow="watchlist account file"
        meta={
          <ObsidianPill tone={selectedCase.unreadCount ? "opportunity" : "neutral"}>
            unread {selectedCase.unreadCount}
          </ObsidianPill>
        }
        subtitle={
          selectedCase.lastSeenAtMs
            ? `Last seen ${formatRelativeTime(selectedCase.lastSeenAtMs)} ago`
            : "No recent event in the active window"
        }
        title={`@${selectedCase.handle}`}
      >
        <ObsidianSection
          actions={
            <ObsidianActionBar>
              {selectedCase.searchLinks.map((link) => (
                <Link key={link.href} to={link.href}>
                  {link.label}
                </Link>
              ))}
            </ObsidianActionBar>
          }
          title="Account proof"
        >
          <ObsidianFieldGrid>
            <ObsidianField
              label="Unread"
              source="social"
              tone={selectedCase.unreadCount ? "opportunity" : "neutral"}
              value={selectedCase.unreadCount}
            />
            <ObsidianField
              detail={selectedCase.emptyState ?? "Recent source events are available."}
              label="Recent evidence"
              source="social"
              tone={selectedCase.recentEvents.length ? "health" : "neutral"}
              value={selectedCase.recentEvents.length}
            />
            <ObsidianField
              label="Token mentions"
              source="deterministic"
              tone={selectedCase.tokenMentions.length ? "info" : "neutral"}
              value={selectedCase.tokenMentions.length}
            />
            <ObsidianField
              label="Narrative clusters"
              source="deterministic"
              tone={selectedCase.narrativeClusters.length ? "agent" : "neutral"}
              value={selectedCase.narrativeClusters.length}
            />
          </ObsidianFieldGrid>
        </ObsidianSection>

        <ObsidianSection title="Token mentions">
          <ClusterGrid
            emptyLabel="No token mentions in this window."
            items={selectedCase.tokenMentions}
          />
        </ObsidianSection>

        <ObsidianSection title="Narrative clusters">
          <ClusterGrid
            emptyLabel="No narrative clusters in this window."
            items={selectedCase.narrativeClusters}
          />
        </ObsidianSection>

        <ObsidianSection title="Recent evidence">
          <ObsidianEvidenceList
            emptyLabel={selectedCase.emptyState ?? "No recent evidence."}
            items={selectedCase.recentEvents.map((item) => ({
              body: item.body,
              href: item.href,
              id: item.id,
              meta: item.meta,
              title: item.title,
              tone: "health",
            }))}
          />
        </ObsidianSection>

        <ObsidianSection title="Risk notes">
          <ObsidianEvidenceList
            emptyLabel="No account-level risk notes in this window."
            items={selectedCase.riskNotes.map((note, index) => ({
              body: note,
              id: `risk-${index}`,
              title: "Risk note",
              tone: "risk",
            }))}
          />
        </ObsidianSection>
      </ObsidianMiniPage>
    </section>
  );
}

function WatchlistAccountList({
  accountCases,
  selectedHandle,
}: {
  accountCases: WatchlistAccountCase[];
  selectedHandle: string;
}) {
  return (
    <aside className="watchlist-case-list" aria-label="Watchlist accounts">
      <span className="ods-kicker">accounts</span>
      {accountCases.map((item) => (
        <Link
          className={clsx("ods-record-link", item.handle === selectedHandle && "active")}
          key={item.handle}
          to={watchlistPath({ handle: item.handle })}
        >
          <ObsidianRecord
            action={
              item.unreadCount ? (
                <ObsidianPill tone="opportunity">{item.unreadCount}</ObsidianPill>
              ) : null
            }
            avatar={item.handle}
            meta={item.lastSeenAtMs ? `${formatRelativeTime(item.lastSeenAtMs)} ago` : "no recent"}
            title={`@${item.handle}`}
          />
        </Link>
      ))}
    </aside>
  );
}

function ClusterGrid({
  emptyLabel,
  items,
}: {
  emptyLabel: string;
  items: WatchlistAccountCase["tokenMentions"];
}) {
  if (!items.length) {
    return <RemoteState.Empty title={emptyLabel} />;
  }

  return (
    <ObsidianFieldGrid>
      {items.map((item) => (
        <ObsidianField
          detail={`${item.count} event${item.count === 1 ? "" : "s"} in window`}
          key={item.label}
          label={item.label}
          source="deterministic"
          tone="info"
          value={item.query}
        />
      ))}
    </ObsidianFieldGrid>
  );
}
