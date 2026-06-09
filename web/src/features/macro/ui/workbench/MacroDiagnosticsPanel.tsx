import type { MacroSemanticRecord } from "@lib/types";

import type { MacroWorkbenchDiagnostics } from "../../model/macroWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroSourceTable } from "../tables/MacroSourceTable";

import "./macroWorkbench.css";

export function MacroDiagnosticsPanel({
  ariaLabel = "数据诊断",
  diagnostics,
  source,
  title = "数据诊断",
}: {
  ariaLabel?: string;
  diagnostics: MacroWorkbenchDiagnostics;
  source: MacroSemanticRecord;
  title?: string;
}) {
  const hasBucketItems = diagnostics.buckets.some(
    (bucket) => bucket.items.length > 0 || (bucket.referenceCount ?? 0) > 0,
  );
  const gapCount = diagnostics.buckets.reduce(
    (count, bucket) => count + (bucket.referenceCount ?? bucket.items.length),
    0,
  );

  return (
    <MacroPanel
      ariaLabel={ariaLabel}
      className="macro-workbench-diagnostics-panel"
      meta={diagnostics.statusLabel ?? diagnostics.sourceMeta}
      span="full"
      title={title}
    >
      <div className="macro-workbench-diagnostics">
        <dl className="macro-workbench-diagnostics-summary" aria-label="诊断摘要">
          <div>
            <dt>状态</dt>
            <dd>{diagnostics.statusLabel ?? "正常"}</dd>
          </div>
          <div>
            <dt>来源</dt>
            <dd>{diagnostics.sourceMeta}</dd>
          </div>
          <div>
            <dt>缺口</dt>
            <dd>{gapCount}</dd>
          </div>
        </dl>
        <details className="macro-workbench-diagnostics-details">
          <summary>缺口明细</summary>
          <div className="macro-workbench-health-grid">
            {hasBucketItems ? (
              diagnostics.buckets.map((bucket) => (
                <section className="macro-workbench-health-bucket" key={bucket.key}>
                  <div className="macro-workbench-section-head">
                    <h4>{bucket.label}</h4>
                    <span>{bucket.referenceCount ?? bucket.items.length}</span>
                  </div>
                  {bucket.referenceCount ? (
                    <p className="macro-workbench-muted">总览级缺口，仅供参考</p>
                  ) : bucket.items.length > 0 ? (
                    <div className="macro-workbench-chip-list">
                      {bucket.items.map((item, index) => (
                        <span
                          className="macro-workbench-chip"
                          key={`${bucket.key}:${item}:${index}`}
                        >
                          {item}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="macro-workbench-empty">暂无</p>
                  )}
                </section>
              ))
            ) : (
              <div className="macro-workbench-empty" role="status">
                暂无数据缺口
              </div>
            )}
          </div>
        </details>
        <details className="macro-workbench-source-block">
          <summary>
            <span>来源状态</span>
            <b>{diagnostics.sourceMeta}</b>
          </summary>
          <MacroSourceTable caption="数据源" source={source} />
        </details>
      </div>
    </MacroPanel>
  );
}
