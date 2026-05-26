import type { MacroEvidenceGroup } from "../../model/macroModulePresentation";
import { MacroPanel } from "./MacroPanel";

export function MacroEvidencePanel({
  ariaLabel = "模块证据",
  groups,
  meta,
  title = "模块证据",
}: {
  ariaLabel?: string;
  groups: MacroEvidenceGroup[];
  meta?: string | null;
  title?: string;
}) {
  const evidenceCount = groups.reduce((count, group) => count + group.items.length, 0);

  return (
    <MacroPanel
      ariaLabel={ariaLabel}
      meta={meta ?? `${String(evidenceCount)} 条`}
      span="full"
      title={title}
    >
      {evidenceCount > 0 ? (
        <div className="macro-evidence-grid">
          {groups.map((group) => (
            <section
              aria-label={group.label}
              className="macro-evidence-group"
              key={group.key}
              role="group"
            >
              <div className="macro-evidence-group-head">
                <h4>{group.label}</h4>
                <span>{group.items.length}</span>
              </div>
              {group.items.length > 0 ? (
                <div className="macro-evidence-list">
                  {group.items.map((item, index) => (
                    <article className="macro-evidence-item" key={`${item.label}:${index}`}>
                      <b>{item.label}</b>
                      <span>{item.detail}</span>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="macro-evidence-empty">暂无</div>
              )}
            </section>
          ))}
        </div>
      ) : (
        <div className="macro-evidence-empty" role="status">
          暂无模块证据
        </div>
      )}
    </MacroPanel>
  );
}
