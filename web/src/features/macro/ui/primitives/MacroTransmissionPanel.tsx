import type { MacroTransmissionNode } from "@lib/types";

import { formatMacroScalar } from "../../model/macroPageViewModel";

import { MacroPanel } from "./MacroPanel";

export function MacroTransmissionPanel({
  ariaLabel = "传导链",
  meta,
  nodes,
  title = "传导链",
}: {
  ariaLabel?: string;
  meta?: string | null;
  nodes: MacroTransmissionNode[];
  title?: string;
}) {
  return (
    <MacroPanel ariaLabel={ariaLabel} meta={meta} span="minor" title={title}>
      <ol className="macro-transmission-list">
        {nodes.length > 0 ? (
          nodes.map((node, index) => (
            <li className="macro-transmission-node" key={`${node.label ?? "node"}:${index}`}>
              <span>{formatMacroScalar(node.label ?? node.kind ?? "传导节点")}</span>
              <b>{formatMacroScalar(node.value ?? node.status_label ?? node.status)}</b>
            </li>
          ))
        ) : (
          <li className="macro-transmission-node">
            <span>传导链</span>
            <b>暂无</b>
          </li>
        )}
      </ol>
    </MacroPanel>
  );
}
