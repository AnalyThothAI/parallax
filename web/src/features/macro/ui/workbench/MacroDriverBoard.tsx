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
  return (
    <MacroPanel
      ariaLabel={ariaLabel}
      className="macro-workbench-driver-panel"
      meta={meta ?? `${drivers.evidenceCount} 条证据`}
      span="full"
      title={title}
    >
      <div className="macro-workbench-driver-layout">
        <section aria-label="传导路径" className="macro-workbench-flow" role="group">
          <div className="macro-workbench-section-head">
            <h4>传导路径</h4>
            <span>{drivers.transmissionCount}</span>
          </div>
          <ol className="macro-workbench-flow-list">
            {transmission.length > 0 ? (
              transmission.map((node, index) => (
                <li className="macro-workbench-flow-node" key={`${node.label ?? "node"}:${index}`}>
                  <span>{formatMacroScalar(node.label ?? node.kind ?? "传导节点")}</span>
                  <b>{formatMacroScalar(node.value ?? node.status_label ?? node.status)}</b>
                </li>
              ))
            ) : (
              <li className="macro-workbench-flow-node">
                <span>传导路径</span>
                <b>暂无</b>
              </li>
            )}
          </ol>
        </section>
        <section aria-label="证据与反证" className="macro-workbench-evidence" role="group">
          <div className="macro-workbench-section-head">
            <h4>证据与反证</h4>
            <span>{drivers.evidenceCount}</span>
          </div>
          <div className="macro-workbench-evidence-grid">
            {drivers.evidenceGroups.map((group) => (
              <article className="macro-workbench-evidence-group" key={group.key}>
                <div className="macro-workbench-evidence-group-head">
                  <h5>{group.label}</h5>
                  <span>{group.items.length}</span>
                </div>
                {group.items.length > 0 ? (
                  <ul className="macro-workbench-evidence-list">
                    {group.items.map((item, index) => (
                      <li key={`${group.key}:${item.label}:${index}`}>
                        <b>{item.label}</b>
                        <span>{item.detail}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="macro-workbench-empty">暂无</p>
                )}
              </article>
            ))}
          </div>
        </section>
      </div>
    </MacroPanel>
  );
}
