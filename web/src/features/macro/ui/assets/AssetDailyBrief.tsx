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
              {displayStance(block.stance) ? <b>{displayStance(block.stance)}</b> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function DailyBriefQuality({ quality }: { quality: NonNullable<MacroDailyBrief["dataQuality"]> }) {
  const items = [
    { label: "最新覆盖", value: formatRatio(quality.latestCoverageRatio) },
    { label: "历史覆盖", value: formatRatio(quality.historyCoverageRatio) },
    { label: "缺口", value: formatCount(quality.gapCount) },
  ].filter((item): item is { label: string; value: string } => item.value !== null);

  if (items.length === 0) {
    return null;
  }

  return (
    <dl className="macro-daily-brief-quality" aria-label="今日判断数据质量">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function formatRatio(value: number | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return `${Math.round(value * 100)}%`;
}

function formatCount(value: number | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return String(value);
}

function cleanHeadline(value: string): string {
  return value.replace(/^今日判断[：:]\s*/, "");
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function displayStance(value: string): string | null {
  const text = value.trim();
  return looksInternalCode(text) ? null : text;
}

function looksInternalCode(value: string): boolean {
  return /^[a-z][a-z0-9_:.-]*$/i.test(value);
}
