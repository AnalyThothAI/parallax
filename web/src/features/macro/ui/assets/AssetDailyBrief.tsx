import type { MacroDailyBrief } from "../../model/macroAssetOverviewModel";

import "./macroAssetOverview.css";

export function AssetDailyBrief({
  brief,
  fallback,
}: {
  brief: MacroDailyBrief | null;
  fallback: string;
}) {
  return (
    <div className="macro-daily-brief">
      <strong>{brief?.headline ?? fallback}</strong>
      {brief?.dataQuality ? <DailyBriefQuality quality={brief.dataQuality} /> : null}
      {brief?.blocks.length ? (
        <div className="macro-daily-brief-grid">
          {brief.blocks.map((block) => (
            <article className="macro-daily-brief-block" key={block.id}>
              <span>{block.stance}</span>
              <b>{block.title}</b>
              <p>{block.body}</p>
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function DailyBriefQuality({ quality }: { quality: NonNullable<MacroDailyBrief["dataQuality"]> }) {
  return (
    <dl className="macro-daily-brief-quality" aria-label="今日判断数据质量">
      <div>
        <dt>最新覆盖</dt>
        <dd>{formatRatio(quality.latestCoverageRatio)}</dd>
      </div>
      <div>
        <dt>历史覆盖</dt>
        <dd>{formatRatio(quality.historyCoverageRatio)}</dd>
      </div>
      <div>
        <dt>缺口</dt>
        <dd>{quality.gapCount ?? 0}</dd>
      </div>
    </dl>
  );
}

function formatRatio(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "待确认";
  return `${Math.round(value * 100)}%`;
}
