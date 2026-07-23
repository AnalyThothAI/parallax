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

import { MacroDecisionList, MacroEvidenceList, MacroUnavailableList } from "./MacroEvidenceBlocks";

import "./MacroPageFrame.css";

export function MacroPageFrame({
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
    <section
      aria-label={`${title}页面`}
      className="macro-workbench"
      data-macro-page={pageId}
      data-page-archetype="decision"
    >
      <MacroPageHeader
        conclusion={data.conclusion.judgment}
        question={question}
        status={data.conclusion.status}
        title={title}
      />

      <MacroDomainNavigation />

      <section aria-label="当前判断" className="macro-judgment-band">
        <DecisionColumn emptyLabel="本快照未命中主要驱动。" items={data.drivers} title="主要驱动" />
        <DecisionColumn emptyLabel="暂无跨领域确认。" items={data.confirmations} title="确认" />
        <DecisionColumn emptyLabel="暂无关键反证。" items={data.contradictions} title="反证" />
        <DecisionColumn
          emptyLabel="本快照未提供失效条件。"
          items={data.upgrade_invalidation.invalidation}
          title="失效条件"
        />
      </section>

      {children}

      <MacroAuditDrawer data={data} />
    </section>
  );
}

export function MacroPageHeader({
  conclusion,
  question,
  status,
  title,
}: {
  conclusion: string;
  question: string;
  status: string;
  title: string;
}) {
  return (
    <header className="macro-workbench-header">
      <div>
        <span>PARALLAX · 1–4 周风险窗口</span>
        <h1>{title}</h1>
        <p>{question}</p>
      </div>
      <div className="macro-workbench-verdict" data-status={status}>
        <span>{macroLabel(status)}</span>
        <strong>{macroLabel(conclusion)}</strong>
      </div>
    </header>
  );
}

export function MacroDomainNavigation() {
  return (
    <nav aria-label="宏观分析维度" className="macro-domain-navigation">
      {MACRO_NAVIGATION_ITEMS.map((item) => (
        <NavLink end={item.href === "/macro"} key={item.id} to={item.href}>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function MacroAuditDrawer({ data }: { data: MacroPageCommonData }) {
  return (
    <details className="macro-audit-drawer">
      <summary>
        <span>审计与证据</span>
        <small>
          {data.evidence.length} 条证据 · {macroLabel(data.freshness.status)}
        </small>
      </summary>
      <div className="macro-audit-body">
        <dl className="macro-audit-meta" aria-label="快照元数据">
          <Meta label="投影版本" value={data.snapshot.projection_version} />
          <Meta label="事实水位" value={data.snapshot.fact_watermark ?? "未提供"} />
          <Meta label="市场截止" value={data.snapshot.market_cutoff ?? "未提供"} />
          <Meta label="计算时间" value={formatMacroTimestamp(data.snapshot.computed_at_ms)} />
          <Meta label="规则版本" value={data.conclusion.rule_version} />
        </dl>

        <div className="macro-audit-grid">
          <AuditList label="关键缺失" values={data.freshness.critical_missing} />
          <AuditList label="关键过期" values={data.freshness.critical_stale} />
          <AuditList label="可选不可用" values={data.freshness.optional_unavailable} />
          <AuditList label="页面证据引用" values={data.evidence_refs} />
        </div>

        <section className="macro-audit-rules">
          <h2>实际规则命中</h2>
          {data.conclusion.rule_hits.length ? (
            <ul>
              {data.conclusion.rule_hits.map((hit) => (
                <li key={`${hit.rule_id}:${hit.outcome}`}>
                  <b>{macroCodeLabel(hit.rule_id)}</b>
                  <span>{macroLabel(hit.outcome)}</span>
                  <code>{hit.rule_id}</code>
                  <small>{macroEvidenceRefsLabel(hit.evidence_refs)}</small>
                </li>
              ))}
            </ul>
          ) : (
            <p>本快照没有规则命中。</p>
          )}
        </section>

        <MacroEvidenceList items={data.evidence} title="完整证据与溯源" />
        <MacroUnavailableList items={data.unavailable_evidence} />
      </div>
    </details>
  );
}

function DecisionColumn({
  emptyLabel,
  items,
  title,
}: {
  emptyLabel: string;
  items: MacroPageCommonData["drivers"];
  title: string;
}) {
  return (
    <div>
      <h2>{title}</h2>
      <MacroDecisionList emptyLabel={emptyLabel} items={items} />
    </div>
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

function AuditList({ label, values }: { label: string; values: string[] }) {
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
