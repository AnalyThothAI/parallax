import type { SignalPulseItem } from "../api/types";
import { compactNumber, formatRelativeTime } from "../lib/format";
import { signalPulseVenueActions } from "../lib/venue";

import {
  DetailDrawerCard,
  DetailDrawerField,
  DetailDrawerFieldGrid,
  DetailDrawerHeader,
  DetailDrawerMetric,
  DetailDrawerMetricGrid,
  DetailDrawerSection,
  DetailDrawerShell,
  DetailDrawerTagStrip,
} from "./DetailDrawer";

type SignalLabInspectorProps = {
  item: SignalPulseItem;
};

export function SignalLabInspector({ item }: SignalLabInspectorProps) {
  const outcomeData = extractOutcomeData(item);
  const venueActions = signalPulseVenueActions(item);
  const bullCase = stringList(item.bull_case_zh);
  const bearCase = stringList(item.bear_case_zh);
  const confirmationTriggers = stringList(item.confirmation_triggers_zh);
  const invalidationTriggers = stringList(item.invalidation_triggers_zh);
  const topRisks = stringList(item.top_risks);
  const sourceEventIds = stringList(item.source_event_ids);
  const evidenceEventIds = stringList(item.evidence_event_ids);
  const playbooks = Array.isArray(item.playbooks) ? item.playbooks : [];
  return (
    <DetailDrawerShell className="signal-lab-inspector">
      <DetailDrawerHeader
        badge={item.score_band ?? item.pulse_status}
        eyebrow="selected Signal Pulse"
        metrics={
          <DetailDrawerMetricGrid>
            <DetailDrawerMetric label="score" value={compactNumber(item.candidate_score)} />
            <DetailDrawerMetric label="status" value={statusLabel(item.pulse_status)} />
            <DetailDrawerMetric label="phase" value={item.social_phase ?? "-"} />
            <DetailDrawerMetric
              label="updated"
              value={`${formatRelativeTime(item.updated_at_ms)} ago`}
            />
          </DetailDrawerMetricGrid>
        }
        subtitle={
          <>
            {item.verdict ?? "no verdict"} · {item.narrative_type ?? "narrative unknown"} ·{" "}
            {item.window}/{item.scope}
          </>
        }
        title={item.symbol || item.subject_key || item.candidate_id}
      />
      <DetailDrawerSection className="detail-drawer-card-stack">
        <DetailDrawerCard title="Why now" tone="accent">
          <p>{item.why_now_zh || item.summary_zh || "No thesis text available."}</p>
          {item.summary_zh ? <p>{item.summary_zh}</p> : null}
        </DetailDrawerCard>

        <DetailDrawerCard title="Token venue">
          {venueActions.length ? (
            <div className="signal-pulse-detail-links">
              {venueActions.map((action) => (
                <a
                  aria-label={`Open selected Signal Pulse token on ${action.label}`}
                  className="venue-link drawer-venue-link"
                  href={action.url}
                  key={`${action.label}:${action.url}`}
                  rel="noreferrer"
                  target="_blank"
                >
                  {action.label}
                </a>
              ))}
            </div>
          ) : (
            <p>No venue link available for this candidate.</p>
          )}
        </DetailDrawerCard>

        <DetailDrawerCard title="Cases">
          <DetailDrawerFieldGrid>
            <DetailDrawerField label="bull_case_zh" value={<ListValue items={bullCase} />} />
            <DetailDrawerField label="bear_case_zh" value={<ListValue items={bearCase} />} />
          </DetailDrawerFieldGrid>
        </DetailDrawerCard>

        <DetailDrawerCard title="Triggers">
          <DetailDrawerFieldGrid>
            <DetailDrawerField
              label="confirmation_triggers_zh"
              value={<ListValue items={confirmationTriggers} />}
            />
            <DetailDrawerField
              label="invalidation_triggers_zh"
              value={<ListValue items={invalidationTriggers} />}
            />
          </DetailDrawerFieldGrid>
        </DetailDrawerCard>

        <DetailDrawerCard title="top risks">
          <DetailDrawerTagStrip emptyLabel="No top risks." items={topRisks} />
        </DetailDrawerCard>

        <DetailDrawerCard title="Ids">
          <DetailDrawerFieldGrid>
            <DetailDrawerField label="candidate_id" value={item.candidate_id} />
            <DetailDrawerField label="candidate_type" value={item.candidate_type} />
            <DetailDrawerField
              label="target"
              value={[item.target_type, item.target_id].filter(Boolean).join(" · ")}
            />
            <DetailDrawerField label="agent_run_id" value={item.agent_run_id} />
            <DetailDrawerField
              label="source_event_ids"
              value={<ListValue items={sourceEventIds} />}
            />
            <DetailDrawerField
              label="evidence_event_ids"
              value={<ListValue items={evidenceEventIds} />}
            />
          </DetailDrawerFieldGrid>
        </DetailDrawerCard>

        <JsonCard title="radar_score_json" value={jsonValue(item.radar_score_json)} />
        <JsonCard title="market_context_json" value={jsonValue(item.market_context_json)} />
        <JsonCard title="thesis_json" value={jsonValue(item.thesis_json)} />
        <JsonCard title="gate_reasons_json" value={jsonValue(item.gate_reasons)} />
        <JsonCard title="risk_reasons_json" value={jsonValue(item.risk_reasons)} />
        {playbooks.length ? <JsonCard title="playbooks" value={playbooks} /> : null}
        {outcomeData ? <JsonCard title="outcome_json" value={outcomeData} /> : null}

        <DetailDrawerCard title="Versions">
          <DetailDrawerFieldGrid>
            <DetailDrawerField label="pulse_version" value={item.pulse_version} />
            <DetailDrawerField label="gate_version" value={item.gate_version} />
            <DetailDrawerField label="prompt_version" value={item.prompt_version} />
            <DetailDrawerField label="schema_version" value={item.schema_version} />
          </DetailDrawerFieldGrid>
        </DetailDrawerCard>
      </DetailDrawerSection>
    </DetailDrawerShell>
  );
}

function ListValue({ items }: { items: string[] }) {
  if (!items.length) {
    return <>-</>;
  }
  return <>{items.join(" · ")}</>;
}

function JsonCard({ title, value }: { title: string; value: unknown }) {
  return (
    <DetailDrawerCard title={title}>
      <pre>
        <code>{JSON.stringify(value, null, 2)}</code>
      </pre>
    </DetailDrawerCard>
  );
}

function extractOutcomeData(item: SignalPulseItem): unknown | null {
  const thesis = jsonObject(item.thesis_json);
  const market = jsonObject(item.market_context_json);
  const thesisOutcome = thesis.outcome ?? thesis.outcomes;
  const marketOutcome = market.outcome ?? market.outcomes;
  return thesisOutcome ?? marketOutcome ?? null;
}

function statusLabel(status: SignalPulseItem["pulse_status"]): string {
  if (status === "trade_candidate") return "trade";
  if (status === "token_watch") return "token";
  if (status === "theme_watch") return "theme";
  return "rejected";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
}

function jsonValue(value: unknown): unknown {
  return value ?? {};
}

function jsonObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
