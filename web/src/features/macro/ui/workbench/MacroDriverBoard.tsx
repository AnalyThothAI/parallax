import type { MacroTransmissionNode } from "@lib/types";

import { formatMacroScalar } from "../../model/macroPageViewModel";
import type { MacroWorkbenchDrivers } from "../../model/macroWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

import "./macroWorkbench.css";

export function MacroDriverBoard({
  ariaLabel,
  drivers,
  meta,
  title,
  transmission,
}: {
  ariaLabel: string;
  drivers: MacroWorkbenchDrivers;
  meta?: string;
  title: string;
  transmission: MacroTransmissionNode[];
}) {
  const evidenceGroups = drivers.evidenceGroups.filter((group) => group.items.length > 0);
  const transmissionRows = transmission.flatMap((node) => {
    const key = textValue(node.key);
    const label = formatMacroScalar(node.label);
    const value = formatMacroScalar(node.value);
    return key && label && value ? [{ key, label, value }] : [];
  });
  const hasTransmission = transmissionRows.length > 0;
  const hasEvidence = evidenceGroups.length > 0;

  if (!hasTransmission && !hasEvidence) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel={ariaLabel}
      className="macro-workbench-driver-panel"
      meta={meta}
      span="full"
      title={title}
    >
      <div className="macro-workbench-driver-layout">
        {hasTransmission ? (
          <section aria-label="传导路径" className="macro-workbench-flow" role="group">
            <div className="macro-workbench-section-head">
              <h4>传导路径</h4>
              <span>{transmissionRows.length}</span>
            </div>
            <ol className="macro-workbench-flow-list">
              {transmissionRows.map((node) => (
                <li className="macro-workbench-flow-node" key={node.key}>
                  <span>{node.label}</span>
                  <b>{node.value}</b>
                </li>
              ))}
            </ol>
          </section>
        ) : null}
        {hasEvidence ? (
          <section aria-label="证据与反证" className="macro-workbench-evidence" role="group">
            <div className="macro-workbench-section-head">
              <h4>证据与反证</h4>
              <span>{drivers.evidenceCount}</span>
            </div>
            <div className="macro-workbench-evidence-grid">
              {evidenceGroups.map((group) => (
                <article className="macro-workbench-evidence-group" key={group.key}>
                  <div className="macro-workbench-evidence-group-head">
                    <h5>{group.label}</h5>
                    <span>{group.items.length}</span>
                  </div>
                  <ul className="macro-workbench-evidence-list">
                    {group.items.map((item) => (
                      <li key={item.key}>
                        <b>{item.label}</b>
                        <span>{item.detail}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </MacroPanel>
  );
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
