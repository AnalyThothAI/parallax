import { Separator } from "@shared/ui/separator";

import { MacroBreadcrumb } from "./MacroBreadcrumb";
import type { MacroShellHeaderModel } from "./MacroShell";

export function MacroPageHeader({ header }: { header: MacroShellHeaderModel }) {
  return (
    <header className="macro-shell-header">
      <MacroBreadcrumb breadcrumbs={header.breadcrumbs} />
      <div className="macro-shell-heading-row">
        <div className="macro-shell-heading-copy">
          <span className="macro-shell-kicker">{header.eyebrow}</span>
          <h1>{header.title}</h1>
          {header.question ? <p>{header.question}</p> : null}
        </div>
        <div className="macro-shell-status-actions">
          <dl className="macro-shell-state" aria-label="页面状态">
            {header.statusItems.map((item) => (
              <div className="macro-shell-state-item" key={item.label}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
          {header.actions ? (
            <div className="macro-shell-actions" aria-label="页面操作">
              {header.actions}
            </div>
          ) : null}
        </div>
      </div>
      <Separator className="macro-shell-separator" />
    </header>
  );
}
