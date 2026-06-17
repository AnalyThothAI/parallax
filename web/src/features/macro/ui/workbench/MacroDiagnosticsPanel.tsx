import type { MacroSemanticRecord } from "@lib/types";

import type {
  MacroDataHealthBucket,
  MacroDataHealthBucketItem,
} from "../../model/macroModulePresentation";
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
  const visibleBuckets = diagnostics.buckets.filter(
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
          {diagnostics.statusLabel ? (
            <div>
              <dt>状态</dt>
              <dd>{diagnostics.statusLabel}</dd>
            </div>
          ) : null}
          <div>
            <dt>来源</dt>
            <dd>{diagnostics.sourceMeta}</dd>
          </div>
          <div>
            <dt>缺口</dt>
            <dd>{gapCount}</dd>
          </div>
        </dl>
        {visibleBuckets.length > 0 ? (
          <details className="macro-workbench-diagnostics-details">
            <summary>缺口明细</summary>
            <div className="macro-workbench-health-grid">
              {visibleBuckets.map((bucket) => (
                <section className="macro-workbench-health-bucket" key={bucket.key}>
                  <div className="macro-workbench-section-head">
                    <h4>{bucket.label}</h4>
                    <span>{bucket.referenceCount ?? bucket.items.length}</span>
                  </div>
                  {bucket.referenceCount ? (
                    <p className="macro-workbench-muted">总览级缺口，仅供参考</p>
                  ) : bucket.items.length > 0 ? (
                    <GapList bucket={bucket} />
                  ) : null}
                </section>
              ))}
            </div>
          </details>
        ) : null}
        {diagnostics.sourceCount > 0 ? (
          <details className="macro-workbench-source-block">
            <summary>
              <span>来源状态</span>
              <b>{diagnostics.sourceMeta}</b>
            </summary>
            <MacroSourceTable caption="数据源" source={source} />
          </details>
        ) : null}
      </div>
    </MacroPanel>
  );
}

function GapList({ bucket }: { bucket: MacroDataHealthBucket }) {
  return (
    <ul className="macro-workbench-gap-list">
      {bucket.items.map((item) => (
        <li data-severity={item.severity ?? undefined} key={`${bucket.key}:${item.key}`}>
          <b>{item.label}</b>
          {gapMeta(item) ? <span>{gapMeta(item)}</span> : null}
          {item.detail ? <small>{item.detail}</small> : null}
        </li>
      ))}
    </ul>
  );
}

function gapMeta(item: MacroDataHealthBucketItem): string | null {
  return [severityLabel(item.severity), scopeLabel(item.scope)].filter(Boolean).join(" · ") || null;
}

function severityLabel(severity: string | null): string | null {
  return (
    {
      critical: "严重",
      error: "错误",
      info: "提示",
      warning: "警告",
    }[severity ?? ""] ?? null
  );
}

function scopeLabel(scope: string | null): string | null {
  return (
    {
      chart_blocker: "图表阻断",
      global_reference: "总览参考",
      module_blocker: "模块阻断",
      module_reference: "模块参考",
    }[scope ?? ""] ?? null
  );
}
