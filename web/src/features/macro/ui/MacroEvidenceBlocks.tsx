import {
  formatMacroNumber,
  formatMacroSample,
  macroCapabilityLabel,
  macroCodeLabel,
  macroConceptLabel,
  macroEvidenceRefsLabel,
  macroLabel,
  macroReasonLabel,
  macroUnitLabel,
  macroWindowLabel,
} from "../model/macroDisplay";
import type {
  MacroDecisionItemData,
  MacroEvidenceData,
  MacroMetricData,
  MacroUnavailableEvidenceData,
} from "../model/macroTypes";

import "./MacroEvidenceBlocks.css";

export function MacroSection({
  children,
  eyebrow,
  title,
}: {
  children: React.ReactNode;
  eyebrow?: string;
  title: string;
}) {
  return (
    <section className="macro-evidence-section">
      <header className="macro-evidence-section-head">
        {eyebrow ? <span>{eyebrow}</span> : null}
        <h2>{title}</h2>
      </header>
      {children}
    </section>
  );
}

export function MacroDecisionList({
  emptyLabel,
  items,
}: {
  emptyLabel: string;
  items: MacroDecisionItemData[];
}) {
  if (!items.length) {
    return <p className="macro-evidence-empty">{emptyLabel}</p>;
  }

  return (
    <ul className="macro-decision-list">
      {items.map((item) => (
        <li key={`${item.code}:${item.evidence_refs.join(",")}`}>
          <span>{macroCodeLabel(item.code)}</span>
          <code>{item.code}</code>
          <small>{macroEvidenceRefsLabel(item.evidence_refs)}</small>
        </li>
      ))}
    </ul>
  );
}

export function MacroEvidenceList({ items, title }: { items: MacroEvidenceData[]; title: string }) {
  return (
    <MacroSection eyebrow={`${items.length} 项`} title={title}>
      {items.length ? (
        <div className="macro-evidence-card-grid">
          {items.map((item) => (
            <MacroEvidenceCard item={item} key={item.concept_key} />
          ))}
        </div>
      ) : (
        <p className="macro-evidence-empty">本快照没有该层证据。</p>
      )}
    </MacroSection>
  );
}

export function MacroEvidenceCard({ item }: { item: MacroEvidenceData }) {
  return (
    <article className="macro-evidence-card" data-evidence-status={item.status}>
      <header>
        <div>
          <strong>{macroConceptLabel(item.concept_key)}</strong>
          <code>{item.concept_key}</code>
          <span>{macroLabel(item.status)}</span>
        </div>
        <p>
          {formatMacroNumber(item.value)} <span>{macroUnitLabel(item.unit)}</span>{" "}
          <code>{item.unit}</code>
        </p>
      </header>
      <dl className="macro-evidence-meta">
        <Meta label="变化" value={formatMacroNumber(item.change)} />
        <CodedMeta
          code={item.change_window}
          label="变化窗口"
          value={macroWindowLabel(item.change_window)}
        />
        <Meta label="观测日" value={item.observed_at ?? "未提供"} />
        <CodedMeta code={item.frequency} label="频率" value={macroLabel(item.frequency)} />
        <Meta label="来源" value={item.source_name ?? "未提供"} />
        <Meta label="序列" value={item.series_key ?? "未提供"} />
        <Meta
          label="新鲜度"
          value={`${macroLabel(item.freshness.status)} · 观测年龄 ${item.freshness.age_days ?? "未提供"} 天 · 过期阈值 ${item.freshness.stale_after_days ?? "未提供"} 天`}
        />
        <Meta label="样本" value={formatMacroSample(item.sample)} />
        <CodedMeta code={item.data_quality} label="质量" value={macroLabel(item.data_quality)} />
        <CodedMeta code={item.role} label="角色" value={macroLabel(item.role)} />
        <CodedMeta code={item.criticality} label="关键性" value={macroLabel(item.criticality)} />
        <CodedMeta
          code={item.claim_effect}
          label="主张作用"
          value={macroLabel(item.claim_effect)}
        />
      </dl>
      {item.derivation ? (
        <div className="macro-evidence-derivation">
          <b>推导</b>
          <code>{item.derivation.formula}</code>
          <ul>
            {item.derivation.inputs.map((input, index) => (
              <li key={`${item.concept_key}:input:${index}`}>
                <DerivationInput input={input} />
              </li>
            ))}
          </ul>
          <small>
            引用：
            {item.derivation.references.length ? item.derivation.references.join(" · ") : "无"}
          </small>
        </div>
      ) : null}
      {item.reason ? (
        <p className="macro-evidence-reason">
          原因：{macroReasonLabel(item.reason)} <code>{item.reason}</code>
        </p>
      ) : null}
    </article>
  );
}

export function MacroMetricList({ items, title }: { items: MacroMetricData[]; title: string }) {
  return (
    <MacroSection eyebrow={`${items.length} 项`} title={title}>
      {items.length ? (
        <div className="macro-metric-grid">
          {items.map((item, index) => (
            <article className="macro-metric-card" key={`${item.concept_key ?? title}:${index}`}>
              <header>
                <div>
                  <strong>
                    {item.concept_key ? macroConceptLabel(item.concept_key) : "派生指标"}
                  </strong>
                  {item.concept_key ? <code>{item.concept_key}</code> : null}
                </div>
                <span>{macroLabel(item.status)}</span>
              </header>
              <p>
                {formatMacroNumber(item.value)} <span>{macroUnitLabel(item.unit)}</span>{" "}
                <code>{item.unit ?? "unit_not_provided"}</code>
              </p>
              <dl>
                <CodedMeta code={item.window} label="窗口" value={macroWindowLabel(item.window)} />
                <Meta label="样本" value={formatMacroSample(item.sample)} />
              </dl>
              {item.derivation ? <code>{item.derivation.formula}</code> : null}
              {item.reason ? (
                <small>
                  原因：{macroReasonLabel(item.reason)} <code>{item.reason}</code>
                </small>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <p className="macro-evidence-empty">本快照没有该层指标。</p>
      )}
    </MacroSection>
  );
}

export function MacroUnavailableList({ items }: { items: MacroUnavailableEvidenceData[] }) {
  return (
    <MacroSection eyebrow={`${items.length} 项`} title="未评估能力">
      {items.length ? (
        <ul className="macro-unavailable-list">
          {items.map((item) => (
            <li key={item.capability}>
              <div>
                <div>
                  <strong>{macroCapabilityLabel(item.capability)}</strong>
                  <code>{item.capability}</code>
                </div>
                <span>未评估 · 不计分</span>
              </div>
              <p>
                {macroReasonLabel(item.reason)} <code>{item.reason}</code>
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="macro-evidence-empty">本页没有命名的未评估能力。</p>
      )}
    </MacroSection>
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

function CodedMeta({ code, label, value }: { code: string | null; label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        <span>{value}</span>
        {code ? <code>{code}</code> : null}
      </dd>
    </div>
  );
}

function DerivationInput({
  input,
}: {
  input: NonNullable<MacroEvidenceData["derivation"]>["inputs"][number];
}) {
  if ("concept_key" in input && "source_unit" in input) {
    return (
      <>
        {macroConceptLabel(input.concept_key)} <code>{input.concept_key}</code>：
        {formatMacroNumber(input.value_millions_usd)} 百万美元{" "}
        <code>source_unit={input.source_unit}</code>
      </>
    );
  }
  if ("concept_key" in input) {
    return (
      <>
        {macroConceptLabel(input.concept_key)} <code>{input.concept_key}</code>：
        {formatMacroNumber(input.value)}
      </>
    );
  }
  return (
    <>
      {input.observed_at}: {formatMacroNumber(input.value)}
    </>
  );
}
