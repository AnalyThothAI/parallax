import type { components } from "@lib/types/openapi";

import {
  formatMacroNumber,
  formatMacroSample,
  macroCodeLabel,
  macroConceptLabel,
  macroLabel,
  macroReasonLabel,
  macroUnitLabel,
  macroWindowLabel,
} from "../model/macroDisplay";
import type { MacroDecisionItemData } from "../model/macroTypes";

import { MacroDecisionList, MacroEvidenceCard, MacroSection } from "./MacroEvidenceBlocks";

import "./MacroDomainBlocks.css";

type MacroAssetReturnData = components["schemas"]["MacroAssetReturnData"];
type MacroCorrelationData = components["schemas"]["MacroCorrelationData"];
type MacroOfficialCatalystData = components["schemas"]["MacroOfficialCatalystData"];
type MacroInflationReleaseData = components["schemas"]["MacroInflationReleaseData"];

export function MacroFactGrid({
  facts,
}: {
  facts: Array<{ code?: string; label: string; value: string }>;
}) {
  return (
    <dl className="macro-domain-fact-grid">
      {facts.map((fact) => (
        <div key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>{fact.value}</dd>
          {fact.code ? <code>{fact.code}</code> : null}
        </div>
      ))}
    </dl>
  );
}

export function MacroDivergenceList({ items }: { items: MacroDecisionItemData[] }) {
  return (
    <MacroSection eyebrow={`${items.length} 项`} title="跨资产分化">
      <MacroDecisionList emptyLabel="本快照未识别跨资产分化。" items={items} />
    </MacroSection>
  );
}

export function MacroAssetReturnList({ items }: { items: MacroAssetReturnData[] }) {
  return (
    <MacroSection eyebrow={`${items.length} 项`} title="截止日对齐收益">
      {items.length ? (
        <div className="macro-domain-card-grid">
          {items.map((item) => (
            <article className="macro-domain-card" key={item.concept_key}>
              <header>
                <div>
                  <strong>{macroConceptLabel(item.concept_key)}</strong>
                  <code>{item.concept_key}</code>
                </div>
                <span>{macroLabel(item.status)}</span>
              </header>
              <div className="macro-return-window-grid">
                <ReturnWindow label="20 个交易日" window={item.return_20} />
                <ReturnWindow label="60 个交易日" window={item.return_60} />
              </div>
              <MacroEvidenceCard item={item.evidence} />
              {item.reason ? (
                <small>
                  原因：{macroReasonLabel(item.reason)} <code>{item.reason}</code>
                </small>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <p className="macro-evidence-empty">本快照没有可用的跨资产收益。</p>
      )}
    </MacroSection>
  );
}

export function MacroCorrelationList({
  items,
  title,
}: {
  items: MacroCorrelationData[];
  title: string;
}) {
  return (
    <MacroSection eyebrow={`${items.length} 对`} title={title}>
      {items.length ? (
        <div className="macro-correlation-grid">
          {items.map((item) => (
            <article
              className="macro-correlation-card"
              key={`${item.left}:${item.right}:${item.window}`}
            >
              <header>
                <div>
                  <strong>
                    {macroConceptLabel(item.left)} × {macroConceptLabel(item.right)}
                  </strong>
                  <code>
                    {item.left} × {item.right}
                  </code>
                </div>
                <span>{macroLabel(item.status)}</span>
              </header>
              <p>{formatMacroNumber(item.correlation)}</p>
              <dl>
                <div>
                  <dt>窗口</dt>
                  <dd>
                    {macroWindowLabel(item.window)} <code>{item.window}</code>
                  </dd>
                </div>
                <div>
                  <dt>共同样本</dt>
                  <dd>{formatMacroSample(item.sample)}</dd>
                </div>
              </dl>
              {item.reason ? (
                <small>
                  原因：{macroReasonLabel(item.reason)} <code>{item.reason}</code>
                </small>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <p className="macro-evidence-empty">本快照没有可用的共同样本相关性。</p>
      )}
    </MacroSection>
  );
}

export function MacroCatalystList({ items }: { items: MacroOfficialCatalystData[] }) {
  return (
    <MacroSection eyebrow="未来 7 天" title="官方催化日历">
      {items.length ? (
        <ol className="macro-catalyst-list">
          {items.map((item) => (
            <li key={`${item.series_key}:${item.event_date}:${item.event_time}`}>
              <time dateTime={`${item.event_date}T${item.event_time}`}>
                {item.event_date} · {item.event_time} · {item.timezone}
              </time>
              <strong>{macroConceptLabel(item.concept_key)}</strong>
              <span>{macroLabel(item.release_status)}</span>
              <a href={item.source_url} rel="noreferrer" target="_blank">
                {item.source_name}
              </a>
              <small>
                {item.series_key} · evidence={item.evidence_ref}
              </small>
            </li>
          ))}
        </ol>
      ) : (
        <p className="macro-evidence-empty">未来七天没有符合合同的官方事件。</p>
      )}
    </MacroSection>
  );
}

export function MacroInflationReleaseList({ items }: { items: MacroInflationReleaseData[] }) {
  return (
    <MacroSection eyebrow={`${items.length} 项`} title="发布期通胀变化">
      {items.length ? (
        <div className="macro-domain-card-grid">
          {items.map((item) => (
            <article className="macro-domain-card" key={item.evidence.concept_key}>
              <header>
                <div>
                  <strong>{macroConceptLabel(item.evidence.concept_key)}</strong>
                  <code>{item.evidence.concept_key}</code>
                </div>
                <span>{macroLabel(item.evidence.status)}</span>
              </header>
              <MacroFactGrid
                facts={[
                  {
                    code: item.release_change.unit ?? undefined,
                    label: "相邻发布变化",
                    value: `${formatMacroNumber(item.release_change.value)} ${macroUnitLabel(item.release_change.unit)}`,
                  },
                  {
                    code: item.year_over_year.unit ?? undefined,
                    label: "同比",
                    value: `${formatMacroNumber(item.year_over_year.value)} ${macroUnitLabel(item.year_over_year.unit)}`,
                  },
                  {
                    label: "发布变化样本",
                    value: formatMacroSample(item.release_change.sample),
                  },
                  {
                    label: "同比样本",
                    value: formatMacroSample(item.year_over_year.sample),
                  },
                ]}
              />
              <MacroEvidenceCard item={item.evidence} />
            </article>
          ))}
        </div>
      ) : (
        <p className="macro-evidence-empty">本快照没有发布期通胀证据。</p>
      )}
    </MacroSection>
  );
}

export function MacroCodeSummary({
  code,
  label,
  status,
}: {
  code: string;
  label: string;
  status: string;
}) {
  return (
    <div className="macro-code-summary">
      <span>{label}</span>
      <strong>{macroCodeLabel(code)}</strong>
      <code>{code}</code>
      <small>{macroLabel(status)}</small>
    </div>
  );
}

function ReturnWindow({
  label,
  window,
}: {
  label: string;
  window: components["schemas"]["MacroReturnWindowData"];
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>
        {formatMacroNumber(window.value)} {macroUnitLabel(window.unit)} <code>{window.unit}</code>
      </strong>
      <small>
        {macroLabel(window.status)} · {formatMacroSample(window.sample)}
      </small>
      {window.reason ? (
        <small>
          原因：{macroReasonLabel(window.reason)} <code>{window.reason}</code>
        </small>
      ) : null}
      {window.derivation ? <code>{window.derivation.formula}</code> : null}
    </div>
  );
}
