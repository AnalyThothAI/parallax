import { getAuthToken } from "@lib/api/client";
import {
  shortAddress,
} from "@lib/format";
import { OBSERVATION_WINDOWS } from "@lib/observationWindows";
import { tokenRadarRowToTokenItem } from "@lib/tokenRadar";
import { useMarketSubscription } from "@shared/socket/useMarketSubscription";
import { RemoteState } from "@shared/ui/RemoteState";
import { ScoreLedger } from "@shared/ui/ScoreLedger";
import { TokenPostsPanel } from "@shared/ui/TokenPostsPanel";
import { TokenSocialMarketTimeline } from "@shared/ui/TokenSocialMarketTimeline";
import { ArrowLeft } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { type TargetRef, targetRefEquals } from "../../../domain/tokenTarget";
import {
  mergeTokenPostPages,
  useTokenTargetRadarQuery,
  useTokenTargetPosts,
  useTokenTargetTimeline,
} from "../api/useTokenTargetQueries";
import {
  parseTokenTargetRouteState,
  serializeTokenTargetRouteState,
  type TokenTargetRouteState,
} from "../state/tokenTargetRouteState";

import { TokenTargetCaseSummary } from "./TokenTargetCaseSummary";

const VALID_TARGET_TYPES = new Set<TargetRef["target_type"]>(["Asset", "CexToken"]);

export function TokenTargetPage() {
  const navigate = useNavigate();
  const params = useParams<{ targetType: string; targetId: string }>();
  const [searchParams, replaceUrlSearch] = useSearchParams();
  const token = getAuthToken() ?? "";
  const routeState = parseTokenTargetRouteState(searchParams);
  const scope = routeState.scope;
  const windowKey = routeState.window;
  const postRange = routeState.postRange;
  const postSortMode = routeState.postSort;
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [watchedPostsOnly, setWatchedPostsOnly] = useState(false);
  const [hideDuplicateClusters, setHideDuplicateClusters] = useState(false);

  const updateRouteState = (patch: Partial<TokenTargetRouteState>) => {
    replaceUrlSearch(serializeTokenTargetRouteState({ ...routeState, ...patch }));
  };

  const targetType = params.targetType as TargetRef["target_type"] | undefined;
  const isValidTargetType = Boolean(targetType && VALID_TARGET_TYPES.has(targetType));
  const isValidParams = isValidTargetType && Boolean(params.targetId);
  const target = useMemo<TargetRef | null>(
    () =>
      isValidParams && targetType && params.targetId
        ? { target_type: targetType, target_id: params.targetId }
        : null,
    [isValidParams, params.targetId, targetType],
  );
  const subscribedTargets = useMemo(() => (target ? [target] : []), [target]);
  useMarketSubscription(subscribedTargets);

  const tokenPostRequestSort = postSortMode === "catalyst" ? "catalyst" : "recent";

  const assetFlowQuery = useTokenTargetRadarQuery({
    token,
    window: windowKey,
    scope,
    limit: 48,
    enabled: Boolean(target),
  });

  const timelineQuery = useTokenTargetTimeline({ token, target, window: windowKey, scope });
  const postsQuery = useTokenTargetPosts({
    token,
    target,
    window: windowKey,
    scope,
    range: postRange,
    sort: tokenPostRequestSort,
  });

  const tokenItem = useMemo(() => {
    if (!target) return null;
    const data = assetFlowQuery.data?.data;
    if (!data) return null;
    const rows = [...data.targets, ...data.attention];
    const matchedRow = rows.find((row) => {
      const rowTarget: TargetRef | null =
        row.target?.target_type && row.target.target_id
          ? {
              target_type: row.target.target_type as TargetRef["target_type"],
              target_id: row.target.target_id,
            }
          : null;
      return rowTarget && targetRefEquals(rowTarget, target);
    });
    if (!matchedRow) return null;
    return tokenRadarRowToTokenItem(matchedRow, windowKey, scope);
  }, [assetFlowQuery.data?.data, scope, target, windowKey]);

  const timeline = timelineQuery.data?.data ?? null;
  const posts = mergeTokenPostPages(postsQuery.data?.pages);

  if (!isValidParams) {
    return (
      <section className="mobile-task-surface" data-mobile-task-panel="radar">
        <section className="token-target-page" aria-label="Token audit page (not found)">
          <header className="token-case-header">
            <button
              className="ghost-icon-button"
              type="button"
              onClick={() => navigate("/")}
              aria-label="Back to Live"
            >
              <ArrowLeft aria-hidden />
              <span>Live</span>
            </button>
          </header>
          <RemoteState.Empty title="Token 不存在或链接已失效" />
        </section>
      </section>
    );
  }

  if (!tokenItem) {
    if (!assetFlowQuery.isPending && target) {
      const stages = timeline?.stages ?? [];
      const selectedStageFilter =
        selectedStageId && stages.some((stage) => stage.stage_id === selectedStageId)
          ? selectedStageId
          : null;
      return (
        <section className="mobile-task-surface" data-mobile-task-panel="radar">
          <section className="token-target-page" aria-label="Token audit page">
            <header className="token-case-header">
              <button
                className="ghost-icon-button"
                type="button"
                onClick={() => navigate(-1)}
                aria-label="Back to Token Radar"
              >
                <ArrowLeft aria-hidden />
                <span>Radar</span>
              </button>
              <div className="token-case-title">
                <span>
                  {target.target_type} · {target.target_id}
                </span>
                <h2>{targetDisplayLabel(target)}</h2>
              </div>
              <div className="token-case-actions">
                <div className="segmented mini range" aria-label="audit page window">
                  {OBSERVATION_WINDOWS.map((item) => (
                    <button
                      key={item}
                      className={windowKey === item ? "active" : ""}
                      type="button"
                      onClick={() => updateRouteState({ window: item })}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            </header>

            <div className="route-state-panel">
              <b>Not in current radar window</b>
              <p>
                This route target has no Token Radar row for {windowKey}. Timeline and posts can
                still load, but no score audit is shown without a real radar row.
              </p>
            </div>

            {timeline ? (
              <TokenSocialMarketTimeline
                activeStageId={selectedStageFilter ?? "all"}
                marketOverlay={timeline.market_overlay}
                timeline={timeline}
                onStageSelect={(stageId) => setSelectedStageId(stageId === "all" ? null : stageId)}
              />
            ) : null}

            <section className="case-section">
              <header>
                <span>message evidence</span>
                <b>{selectedStageFilter ? "stage filtered" : "all loaded posts"}</b>
              </header>
              <TokenPostsPanel
                hideDuplicateClusters={hideDuplicateClusters}
                isFetchingNextPage={postsQuery.isFetchingNextPage}
                isLoading={postsQuery.isLoading}
                posts={posts}
                postRange={postRange}
                postSortMode={postSortMode}
                selectedStageId={selectedStageFilter}
                watchedPostsOnly={watchedPostsOnly}
                onHideDuplicateClustersChange={setHideDuplicateClusters}
                onLoadMorePosts={() => void postsQuery.fetchNextPage()}
                onPostRangeChange={(range) => updateRouteState({ postRange: range })}
                onPostSortModeChange={(postSort) => updateRouteState({ postSort })}
                onWatchedPostsOnlyChange={setWatchedPostsOnly}
              />
            </section>
          </section>
        </section>
      );
    }
    return (
      <section className="mobile-task-surface" data-mobile-task-panel="radar">
        <section className="token-target-page" aria-label="Token audit page">
          <header className="token-case-header">
            <button
              className="ghost-icon-button"
              type="button"
              onClick={() => navigate(-1)}
              aria-label="Back"
            >
              <ArrowLeft aria-hidden />
              <span>Back</span>
            </button>
          </header>
          {assetFlowQuery.isPending ? (
            <RemoteState.Loading layout="route" rows={4} label="loading token audit" />
          ) : (
            <RemoteState.Empty title="token audit target missing" />
          )}
        </section>
      </section>
    );
  }

  const stages = timeline?.stages ?? [];
  const selectedStageFilter =
    selectedStageId && stages.some((stage) => stage.stage_id === selectedStageId)
      ? selectedStageId
      : null;

  return (
    <section className="mobile-task-surface" data-mobile-task-panel="radar">
      <section className="token-target-page" aria-label="Token audit page">
        <TokenTargetCaseSummary
          token={tokenItem}
          timeline={timeline}
          windowKey={windowKey}
          onBack={() => navigate(-1)}
          onWindowChange={(window) => updateRouteState({ window })}
        />

        {timeline ? (
          <TokenSocialMarketTimeline
            activeStageId={selectedStageFilter ?? "all"}
            marketOverlay={timeline.market_overlay}
            timeline={timeline}
            onStageSelect={(stageId) => setSelectedStageId(stageId === "all" ? null : stageId)}
          />
        ) : null}

        <section className="case-section">
          <header>
            <span>message evidence</span>
            <b>{selectedStageFilter ? "stage filtered" : "all loaded posts"}</b>
          </header>
          <TokenPostsPanel
            hideDuplicateClusters={hideDuplicateClusters}
            isFetchingNextPage={postsQuery.isFetchingNextPage}
            isLoading={postsQuery.isLoading}
            posts={posts}
            postRange={postRange}
            postSortMode={postSortMode}
            selectedStageId={selectedStageFilter}
            watchedPostsOnly={watchedPostsOnly}
            onHideDuplicateClustersChange={setHideDuplicateClusters}
            onLoadMorePosts={() => void postsQuery.fetchNextPage()}
            onPostRangeChange={(range) => updateRouteState({ postRange: range })}
            onPostSortModeChange={(postSort) => updateRouteState({ postSort })}
            onWatchedPostsOnlyChange={setWatchedPostsOnly}
          />
        </section>

        <section className="case-section">
          <header>
            <span>score audit</span>
            <b>{tokenItem.opportunity.score_version}</b>
          </header>
          <ScoreLedger token={tokenItem} />
        </section>
      </section>
    </section>
  );
}

function symbolFromTarget(target: TargetRef): string | null {
  if (target.target_type !== "CexToken") {
    return null;
  }
  const raw = target.target_id.startsWith("cex_token:")
    ? target.target_id.slice("cex_token:".length)
    : target.target_id;
  const symbol = raw
    .split(":")
    .pop()
    ?.replace(/-USDT$/i, "")
    .trim()
    .toUpperCase();
  return symbol || null;
}

function targetDisplayLabel(target: TargetRef): string {
  if (target.target_type === "CexToken") {
    const symbol = symbolFromTarget(target);
    return symbol ? `$${symbol}` : target.target_id;
  }
  const address = target.target_id.split(":").at(-1);
  return address ? shortAddress(address) : target.target_id;
}
