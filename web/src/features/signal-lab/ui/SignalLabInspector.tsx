import type { SignalPulseItem } from "@lib/types";
import {
  ObsidianActionBar,
  ObsidianCase,
  ObsidianCaseHeader,
  ObsidianEvidenceList,
  ObsidianFieldGrid,
  ObsidianPill,
  ObsidianSection,
} from "@shared/ui/case-file";
import { Link } from "react-router-dom";

import { buildPulseCaseView } from "../model/pulseCase";

type SignalLabInspectorProps = {
  item: SignalPulseItem;
};

export function SignalLabInspector({ item }: SignalLabInspectorProps) {
  const view = buildPulseCaseView(item);
  const searchAction = view.actions.find((action) => action.kind === "search");
  const venueActions = view.actions.filter((action) => action.kind === "venue");
  return (
    <ObsidianCase
      aria-label={`Signal Pulse case ${view.subject.title}`}
      className="signal-lab-inspector signal-pulse-case"
    >
      <ObsidianCaseHeader
        actions={
          <ObsidianActionBar>
            {searchAction ? <Link to={searchAction.href}>{searchAction.label}</Link> : null}
            {venueActions.map((action) => (
              <a
                aria-label={`Open pulse case on ${action.label}`}
                href={action.href}
                key={`${action.label}:${action.href}`}
                rel="noreferrer"
                target="_blank"
              >
                {action.label}
              </a>
            ))}
          </ObsidianActionBar>
        }
        badge={<ObsidianPill tone={view.stage.tone}>{view.stage.value}</ObsidianPill>}
        eyebrow="selected pulse case"
        subtitle={view.subject.subtitle}
        title={view.subject.title}
      >
        <ObsidianFieldGrid fields={[view.stage, view.gate, view.agentMemo.recommendation]} />
      </ObsidianCaseHeader>

      <ObsidianSection
        title="Agent memo"
        subtitle="Agent-derived recommendation is labelled separately from deterministic facts."
      >
        <p className="signal-pulse-memo">{view.agentMemo.summary}</p>
        <ObsidianFieldGrid
          fields={[
            view.agentMemo.recommendation,
            {
              detail: "agent recommendation confidence",
              label: "Confidence",
              source: "agent",
              tone: "agent",
              value: view.agentMemo.confidence,
            },
            view.stage,
            view.gate,
          ]}
        />
        <div className="signal-pulse-memo-grid">
          <MemoList title="Primary reasons" items={view.agentMemo.reasons} />
          <MemoList title="Upgrade conditions" items={view.agentMemo.upgrades} />
          <MemoList title="Invalidations" items={view.agentMemo.invalidations} />
          <MemoList title="Residual risks" items={view.agentMemo.risks} />
        </div>
      </ObsidianSection>

      <ObsidianSection title="Fact ledger" subtitle="Market, social, and deterministic case facts.">
        <ObsidianFieldGrid fields={view.factLedger} />
      </ObsidianSection>

      <ObsidianSection
        title="Source events"
        subtitle="Candidate source IDs and agent evidence IDs."
      >
        <ObsidianEvidenceList
          emptyLabel="No source events recorded for this pulse."
          items={view.sourceEvents}
        />
      </ObsidianSection>

      <details className="pulse-debug-disclosure">
        <summary>Debug facts</summary>
        <ObsidianFieldGrid fields={view.debugFacts} />
        <DebugJson title="factor_snapshot" value={item.factor_snapshot} />
        <DebugJson title="gate" value={item.gate} />
        {item.playbooks.length ? <DebugJson title="playbooks" value={item.playbooks} /> : null}
        <ObsidianFieldGrid
          fields={[
            {
              detail: item.pulse_version ?? "-",
              label: "pulse_version",
              source: "deterministic",
              tone: "neutral",
              value: item.pulse_version ?? "-",
            },
            {
              detail: item.gate_version ?? "-",
              label: "gate_version",
              source: "deterministic",
              tone: "neutral",
              value: item.gate_version ?? "-",
            },
            {
              detail: item.prompt_version ?? "-",
              label: "prompt_version",
              source: "agent",
              tone: "agent",
              value: item.prompt_version ?? "-",
            },
            {
              detail: item.schema_version ?? "-",
              label: "schema_version",
              source: "deterministic",
              tone: "neutral",
              value: item.schema_version ?? "-",
            },
          ]}
        />
      </details>
    </ObsidianCase>
  );
}

function MemoList({
  emptyLabel = "No entries.",
  items,
  title,
}: {
  emptyLabel?: string;
  items: string[];
  title: string;
}) {
  return (
    <section className="signal-pulse-memo-list">
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>{emptyLabel}</p>
      )}
    </section>
  );
}

function DebugJson({ title, value }: { title: string; value: unknown }) {
  return (
    <section className="pulse-debug-json">
      <h4>{title}</h4>
      <pre>
        <code>{JSON.stringify(value, null, 2)}</code>
      </pre>
    </section>
  );
}
