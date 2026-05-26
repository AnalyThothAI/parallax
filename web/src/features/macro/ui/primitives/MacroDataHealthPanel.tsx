import type { MacroDataHealthBucket } from "../../model/macroModulePresentation";

import { MacroPanel } from "./MacroPanel";

export function MacroDataHealthPanel({
  ariaLabel = "模块数据健康",
  buckets,
  meta,
  title = "模块数据健康",
}: {
  ariaLabel?: string;
  buckets: MacroDataHealthBucket[];
  meta?: string | null;
  title?: string;
}) {
  const hasItems = buckets.some(
    (bucket) => bucket.items.length > 0 || (bucket.referenceCount ?? 0) > 0,
  );

  return (
    <MacroPanel ariaLabel={ariaLabel} meta={meta} title={title}>
      {hasItems ? (
        <div className="macro-health-buckets">
          {buckets.map((bucket) => (
            <section className="macro-health-bucket" key={bucket.key}>
              <div className="macro-health-bucket-head">
                <h4>{bucket.label}</h4>
                <span>{bucket.referenceCount ?? bucket.items.length}</span>
              </div>
              {bucket.referenceCount ? (
                <p className="macro-health-reference">总览级缺口，仅供参考</p>
              ) : bucket.items.length > 0 ? (
                <div className="macro-health-chip-list">
                  {bucket.items.map((item, index) => (
                    <span className="macro-health-chip" key={`${bucket.key}:${index}:${item}`}>
                      {item}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="macro-health-empty">暂无</div>
              )}
            </section>
          ))}
        </div>
      ) : (
        <div className="macro-health-empty" role="status">
          暂无数据缺口
        </div>
      )}
    </MacroPanel>
  );
}
