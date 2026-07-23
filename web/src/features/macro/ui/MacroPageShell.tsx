import { NavLink } from "react-router-dom";

import {
  formatMacroTimestamp,
  macroCodeLabel,
  macroEvidenceRefsLabel,
  macroGapLabel,
  macroLabel,
} from "../model/macroDisplay";
import { MACRO_NAVIGATION_ITEMS, type MacroPageId } from "../model/macroNavigation";
import type { MacroPageCommonData } from "../model/macroTypes";

import {
  MacroDecisionList,
  MacroEvidenceList,
  MacroSection,
  MacroUnavailableList,
} from "./MacroEvidenceBlocks";

import "./MacroPageShell.css";

export function MacroPageShell({
  children,
  data,
  pageId,
  question,
  title,
}: {
  children: React.ReactNode;
  data: MacroPageCommonData;
  pageId: MacroPageId;
  question: string;
  title: string;
}) {
  return (
    <section aria-label={`${title}页面`} className="macro-evidence-page" data-macro-page={pageId}>
      <nav aria-label="宏观页面" className="macro-evidence-nav">
        {MACRO_NAVIGATION_ITEMS.map((item) => (
          <NavLink end={item.href === "/macro"} key={item.id} to={item.href}>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <header className="macro-evidence-header">
        <div className="macro-evidence-heading">
          <span>完成快照 · 未来 1–4 周</span>
          <h1>{title}</h1>
          <p>{question}</p>
        </div>
        <div className="macro-evidence-conclusion" data-status={data.conclusion.status}>
          <span>{macroLabel(data.conclusion.status)}</span>
          <strong>{macroLabel(data.conclusion.judgment)}</strong>
          <code>{data.conclusion.judgment}</code>
        </div>
      </header>

      <dl className="macro-snapshot-meta" aria-label="快照元数据">
        <Meta label="投影版本" value={data.snapshot.projection_version} />
        <Meta label="事实水位" value={data.snapshot.fact_watermark ?? "未提供"} />
        <Meta label="市场截止" value={data.snapshot.market_cutoff ?? "未提供"} />
        <Meta label="计算时间" value={formatMacroTimestamp(data.snapshot.computed_at_ms)} />
        <Meta label="判断期限" value="1–4 周" />
        <Meta label="页面新鲜度" value={macroLabel(data.freshness.status)} />
        <Meta label="规则版本" value={data.conclusion.rule_version} />
      </dl>

      <div className="macro-decision-grid">
        <MacroSection eyebrow={`${data.drivers.length} 项`} title="驱动">
          <MacroDecisionList emptyLabel="本快照未命中主要驱动。" items={data.drivers} />
        </MacroSection>
        <MacroSection eyebrow={`${data.confirmations.length} 项`} title="确认">
          <MacroDecisionList emptyLabel="本快照暂无确认项。" items={data.confirmations} />
        </MacroSection>
        <MacroSection eyebrow={`${data.contradictions.length} 项`} title="反证">
          <MacroDecisionList emptyLabel="本快照暂无反证项。" items={data.contradictions} />
        </MacroSection>
        <MacroSection
          eyebrow={`${data.upgrade_invalidation.upgrade.length} / ${data.upgrade_invalidation.invalidation.length}`}
          title="升级 / 失效"
        >
          <div className="macro-upgrade-grid">
            <div>
              <h3>升级条件</h3>
              <MacroDecisionList
                emptyLabel="证据不足时不设置升级条件。"
                items={data.upgrade_invalidation.upgrade}
              />
            </div>
            <div>
              <h3>失效条件</h3>
              <MacroDecisionList
                emptyLabel="本快照未提供失效条件。"
                items={data.upgrade_invalidation.invalidation}
              />
            </div>
          </div>
        </MacroSection>
      </div>

      <MacroSection eyebrow={`${data.conclusion.rule_hits.length} 项`} title="实际规则命中">
        {data.conclusion.rule_hits.length ? (
          <ul className="macro-rule-hit-list">
            {data.conclusion.rule_hits.map((hit) => (
              <li key={`${hit.rule_id}:${hit.outcome}`}>
                <span>{macroCodeLabel(hit.rule_id)}</span>
                <code>{hit.rule_id}</code>
                <b>{macroLabel(hit.outcome)}</b>
                <small>{macroEvidenceRefsLabel(hit.evidence_refs)}</small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="macro-evidence-empty">本快照没有规则命中。</p>
        )}
      </MacroSection>

      <MacroSection eyebrow={macroLabel(data.freshness.status)} title="新鲜度与证据引用">
        <div className="macro-freshness-grid">
          <GapList label="关键缺失" values={data.freshness.critical_missing} />
          <GapList label="关键过期" values={data.freshness.critical_stale} />
          <GapList label="可选不可用" values={data.freshness.optional_unavailable} />
          <GapList label="页面证据引用" values={data.evidence_refs} />
        </div>
      </MacroSection>

      {children}

      <MacroEvidenceList items={data.evidence} title="完整证据与溯源" />
      <MacroUnavailableList items={data.unavailable_evidence} />
    </section>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function GapList({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <h3>{label}</h3>
      {values.length ? (
        <ul>
          {values.map((value) => (
            <li key={value}>
              <span>{macroGapLabel(value)}</span>
              <code>{value}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p>无</p>
      )}
    </div>
  );
}
