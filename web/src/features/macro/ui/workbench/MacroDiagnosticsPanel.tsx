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

  return (
    <MacroPanel
      ariaLabel={ariaLabel}
      className="macro-workbench-diagnostics-panel"
      meta={diagnostics.statusLabel ?? diagnostics.sourceMeta}
      span="full"
      title={title}
    >
      <div className="macro-workbench-diagnostics">
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
                      <span className="macro-workbench-chip" key={`${bucket.key}:${item}:${index}`}>
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
        <div className="macro-workbench-source-block">
          <div className="macro-workbench-section-head">
            <h4>来源状态</h4>
            <span>{diagnostics.sourceMeta}</span>
          </div>
          <MacroSourceTable caption="数据源" source={source} />
        </div>
      </div>
    </MacroPanel>
  );
}
