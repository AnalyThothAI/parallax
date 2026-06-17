import type { MacroDailyBrief } from "../../model/macroAssetOverviewModel";

import "./macroAssetOverview.css";

export function AssetDailyBrief({ brief }: { brief: MacroDailyBrief }) {
  const blocks = brief.blocks.slice(0, 3);
  const headline = textValue(brief.headline);
  if (!headline) {
    return null;
  }
  return (
    <div className="macro-daily-brief">
      <div className="macro-daily-brief-head">
        <span>今日判断</span>
        <strong>{cleanHeadline(headline)}</strong>
      </div>
      {brief.dataQuality ? <DailyBriefQuality quality={brief.dataQuality} /> : null}
      {blocks.length ? (
        <ul className="macro-daily-brief-signals" aria-label="今日判断信号">
          {blocks.map((block) => (
            <li key={block.id} title={block.body}>
              <span>{block.title}</span>
              <b>{stanceLabel(block.stance)}</b>
            </li>
          ))}
        </ul>
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
        <dd>{formatCount(quality.gapCount)}</dd>
      </div>
    </dl>
  );
}

function formatRatio(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "样本不足";
  return `${Math.round(value * 100)}%`;
}

function formatCount(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "样本不足";
  return String(value);
}

function cleanHeadline(value: string): string {
  return value.replace(/^今日判断[：:]\s*/, "");
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stanceLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized.includes("risk") || normalized.includes("supported")) return "支持";
  if (normalized.includes("watch") || normalized.includes("mixed")) return "观察";
  if (normalized.includes("neutral")) return "中性";
  return value;
}
