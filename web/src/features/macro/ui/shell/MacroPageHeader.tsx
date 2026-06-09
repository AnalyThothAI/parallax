import { MacroBreadcrumb } from "./MacroBreadcrumb";
import type { MacroShellHeaderModel } from "./MacroShell";

export function MacroPageHeader({ header }: { header: MacroShellHeaderModel }) {
  return (
    <header className="macro-shell-header">
      <div className="macro-shell-header-topline">
        <MacroBreadcrumb breadcrumbs={header.breadcrumbs} />
        {header.statusItems.length ? (
          <dl className="macro-shell-state" aria-label="页面状态">
            {header.statusItems.map((item) => (
              <div className="macro-shell-state-item" key={item.label}>
                <dt>{item.label}</dt>
                <dd>{compactStatusValue(item.label, item.value)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
      <div className="macro-shell-heading-row">
        <div className="macro-shell-heading-copy">
          <span className="macro-shell-kicker">{header.eyebrow}</span>
          <h1>{header.title}</h1>
        </div>
        {header.actions ? (
          <div className="macro-shell-actions" aria-label="页面操作">
            {header.actions}
          </div>
        ) : null}
      </div>
    </header>
  );
}

function compactStatusValue(
  label: string,
  value: MacroShellHeaderModel["statusItems"][number]["value"],
) {
  if (typeof value !== "string") {
    return value;
  }
  const trimmed = value.trim();
  if (label === "截至") {
    return trimmed.replace(/^截至\s*/, "");
  }
  return trimmed;
}
