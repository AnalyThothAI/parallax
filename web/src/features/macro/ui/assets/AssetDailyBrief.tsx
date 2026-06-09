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
