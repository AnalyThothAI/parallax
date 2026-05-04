import type { AccountQualityData, TokenSocialTimelineData } from "../api/types";
import { compactNumber, formatRelativeTime, formatScore } from "../lib/format";

type AccountLaneProps = {
  timeline?: TokenSocialTimelineData | null;
  accountQuality?: AccountQualityData | null;
  isLoading?: boolean;
};

export function AccountLane({ timeline, accountQuality, isLoading }: AccountLaneProps) {
  if (isLoading) {
    return <div className="empty-state">加载账号质量中</div>;
  }
  const qualityByHandle = new Map(
    (accountQuality?.accounts ?? [])
      .filter((item) => item.profile?.handle)
      .map((item) => [String(item.profile?.handle), item])
  );
  const authors = timeline?.authors ?? [];
  if (!authors.length) {
    return <div className="empty-state">暂无作者质量线索</div>;
  }
  return (
    <div className="account-lane-list">
      {authors.map((author) => {
        const quality = qualityByHandle.get(author.handle);
        const summary = quality?.summary;
        return (
          <article className="account-lane-card" key={author.handle}>
            <header>
              <strong>@{author.handle}</strong>
              <span>{author.role ?? "author"}</span>
            </header>
            <div className="account-kv">
              <span>first</span>
              <b>{formatRelativeTime(author.first_seen_ms)}</b>
              <span>posts</span>
              <b>{compactNumber(author.posts)}</b>
              <span>followers</span>
              <b>{compactNumber(author.followers)}</b>
              <span>quality</span>
              <b>{summary?.status === "ready" ? formatScore(summary.precision_score) : "样本不足"}</b>
              <span>early</span>
              <b>{summary?.early_call_score !== null && summary?.early_call_score !== undefined ? formatScore(summary.early_call_score) : "-"}</b>
              <span>spam risk</span>
              <b>{summary?.spam_risk_score !== null && summary?.spam_risk_score !== undefined ? formatScore(summary.spam_risk_score) : "-"}</b>
            </div>
          </article>
        );
      })}
    </div>
  );
}
