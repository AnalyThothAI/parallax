import type { MacroModuleView } from "@lib/types";

import { tableCaption, tableIdentifier } from "../../model/macroModulePageModel";
import type {
  MacroDataHealthBucket,
  MacroDataHealthBucketItem,
} from "../../model/macroModulePresentation";
import type { RatesWorkbenchView } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroDataTable } from "../tables/MacroDataTable";
import { MacroSourceTable } from "../tables/MacroSourceTable";

import "./ratesDataHealthGaps.css";

export function RatesDiagnosticsPanel({
  module,
  view,
}: {
  module: MacroModuleView;
  view: RatesWorkbenchView;
}) {
  const buckets = buildRatesHealthBuckets(view);
  const visibleBuckets = buckets.filter(
    (bucket) => bucket.items.length > 0 || (bucket.referenceCount ?? 0) > 0,
  );
  const meta = [
    view.diagnostics.moduleHealthLabel,
    `全局缺口 ${view.diagnostics.globalGapReferenceCount}`,
  ]
    .filter(Boolean)
    .join(" / ");
  const diagnosticTables = view.detailTables.filter(
    (entry) => entry.role === "diagnostic" && renderableDiagnosticTable(entry.table),
  );
  const hasSourceRows = Boolean(view.diagnostics.sourceMeta);

  return (
    <MacroPanel
      ariaLabel="数据诊断"
      className="macro-rates-diagnostics-panel"
      meta={meta}
      span="full"
      title="数据诊断"
    >
      <div className="macro-rates-diagnostics-board">
        {visibleBuckets.length > 0 ? (
          <div className="macro-rates-health-buckets">
            {visibleBuckets.map((bucket) => (
              <section className="macro-rates-health-bucket" key={bucket.key}>
                <div className="macro-rates-health-head">
                  <h4>{bucket.label}</h4>
                  <span>{bucket.referenceCount ?? bucket.items.length}</span>
                </div>
                {bucket.referenceCount ? (
                  <p className="macro-rates-empty macro-rates-empty-compact">
                    总览级缺口，仅供参考
                  </p>
                ) : bucket.items.length > 0 ? (
                  <GapList bucket={bucket} />
                ) : null}
              </section>
            ))}
          </div>
        ) : null}
        {diagnosticTables.length > 0 ? (
          <div className="macro-rates-table-stack">
            {diagnosticTables.map(({ table }) => (
              <DiagnosticTableBlock key={String(table.id)} table={table} />
            ))}
          </div>
        ) : null}
        {hasSourceRows ? (
          <div className="macro-rates-source-diagnostics">
            <div className="macro-rates-health-head">
              <h4>来源状态</h4>
              {view.diagnostics.sourceMeta ? <span>{view.diagnostics.sourceMeta}</span> : null}
            </div>
            <MacroSourceTable caption="利率数据源" source={module.provenance} />
          </div>
        ) : null}
      </div>
    </MacroPanel>
  );
}

function DiagnosticTableBlock({
  table,
}: {
  table: RatesWorkbenchView["detailTables"][number]["table"];
}) {
  const caption = tableCaption(table);
  return caption ? <MacroDataTable caption={caption} table={table} /> : null;
}

function renderableDiagnosticTable(
  table: RatesWorkbenchView["detailTables"][number]["table"],
): boolean {
  return Boolean(tableIdentifier(table) && tableCaption(table) && (table.rows?.length ?? 0) > 0);
}

function buildRatesHealthBuckets(view: RatesWorkbenchView): MacroDataHealthBucket[] {
  return [
    {
      items: view.diagnostics.coverage.map((item) => ({
        detail: null,
        key: item.key,
        label: item.label,
        scope: null,
        severity: item.severity,
      })),
      key: "rates_coverage",
      label: "覆盖状态",
    },
    {
      items: [],
      key: "global_gap_references",
      label: "全局缺口参考",
      referenceCount: view.diagnostics.globalGapReferenceCount,
    },
  ];
}

function GapList({ bucket }: { bucket: MacroDataHealthBucket }) {
  return (
    <ul className="macro-rates-health-gap-list">
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
