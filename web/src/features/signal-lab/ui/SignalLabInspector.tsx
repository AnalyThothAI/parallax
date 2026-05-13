import { compactNumber, formatRelativeTime, formatUsdCompact } from "@lib/format";
import { requireTokenFactorSnapshot } from "@lib/tokenFactorSnapshot";
import type { SignalPulseItem } from "@lib/types";
import { signalPulseVenueActions } from "@lib/venue";
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
} from "@shared/ui/DetailDrawer";

type SignalLabInspectorProps = {
  item: SignalPulseItem;
};

export function SignalLabInspector({ item }: SignalLabInspectorProps) {
  const factorSnapshot = requireTokenFactorSnapshot(item.factor_snapshot);
  const venueActions = signalPulseVenueActions(item);
  const sourceEventIds = stringList(item.source_event_ids);
  const evidenceEventIds = stringList(item.evidence_event_ids);
  const gateBlockedReasons = stringList(item.gate.blocked_reasons);
  const factorGateBlockedReasons = stringList(factorSnapshot.gates.blocked_reasons);
  const blockedReasons = [...new Set([...factorGateBlockedReasons, ...gateBlockedReasons])];
  const recommendation = item.agent_recommendation;
  const playbooks = Array.isArray(item.playbooks) ? item.playbooks : [];
  const alphaFamilies = alphaFamilyEntries(factorSnapshot.families);
  const normalization = factorSnapshot.normalization;
  const healthWarnings = dataHealthWarnings(factorSnapshot.data_health);
  return (
    <DetailDrawerShell className="signal-lab-inspector">
      <DetailDrawerHeader
        badge={stringValue(item.gate.score_band) ?? item.score_band ?? item.pulse_status}
        eyebrow="selected Signal Pulse"
        metrics={
          <DetailDrawerMetricGrid>
            <DetailDrawerMetric
              label="score"
              value={compactNumber(numberValue(item.gate.candidate_score) ?? item.candidate_score)}
            />
            <DetailDrawerMetric label="status" value={statusLabel(item.pulse_status)} />
            <DetailDrawerMetric label="gate" value={stringValue(item.gate.pulse_status) ?? "-"} />
            <DetailDrawerMetric
              label="updated"
              value={`${formatRelativeTime(item.updated_at_ms)} ago`}
            />
          </DetailDrawerMetricGrid>
        }
        subtitle={
          <>
            {recommendation.recommendation} · {factorSnapshot.composite.recommended_decision} ·{" "}
            {item.window}/{item.scope}
          </>
        }
        title={
          factorSnapshot.subject.symbol || item.symbol || item.subject_key || item.candidate_id
        }
      />
      <DetailDrawerSection className="detail-drawer-card-stack">
        <DetailDrawerCard title="Agent Recommendation" tone="accent">
          <p>{recommendation.summary_zh || "No recommendation summary available."}</p>
          <DetailDrawerFieldGrid>
            <DetailDrawerField label="recommendation" value={recommendation.recommendation} />
            <DetailDrawerField label="schema_version" value={recommendation.schema_version} />
            <DetailDrawerField
              label="primary_reasons"
              value={<ReasonList items={recommendation.primary_reasons} />}
            />
            <DetailDrawerField
              label="upgrade_conditions"
              value={<ConditionList items={recommendation.upgrade_conditions} />}
            />
            <DetailDrawerField
              label="invalidation_conditions"
              value={<ConditionList items={recommendation.invalidation_conditions} />}
            />
            <DetailDrawerField
              label="residual_risks"
              value={<RiskList items={recommendation.residual_risks} />}
            />
          </DetailDrawerFieldGrid>
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

        <DetailDrawerCard title="Fact Card">
          <DetailDrawerFieldGrid>
            <DetailDrawerField
              label="market_cap_usd"
              value={usdValue(item.fact_card.market_cap_usd)}
            />
            <DetailDrawerField
              label="liquidity_usd"
              value={usdValue(item.fact_card.liquidity_usd)}
            />
            <DetailDrawerField
              label="holders"
              value={compactNumber(numberValue(item.fact_card.holders))}
            />
            <DetailDrawerField
              label="volume_24h_usd"
              value={usdValue(item.fact_card.volume_24h_usd)}
            />
            <DetailDrawerField
              label="mentions_1h"
              value={compactNumber(numberValue(item.fact_card.mentions_1h))}
            />
            <DetailDrawerField
              label="unique_authors"
              value={compactNumber(numberValue(item.fact_card.unique_authors))}
            />
            <DetailDrawerField
              label="watched_mentions"
              value={compactNumber(numberValue(item.fact_card.watched_mentions))}
            />
            <DetailDrawerField
              label="market_status"
              value={stringValue(item.fact_card.market_status) ?? "-"}
            />
          </DetailDrawerFieldGrid>
        </DetailDrawerCard>

        <DetailDrawerCard title="Eligibility Gates">
          <DetailDrawerFieldGrid>
            <DetailDrawerField
              label="eligible_for_high_alert"
              value={String(Boolean(factorSnapshot.gates.eligible_for_high_alert))}
            />
            <DetailDrawerField
              label="max_decision"
              value={factorSnapshot.gates.max_decision ?? "-"}
            />
            <DetailDrawerField
              label="gate_status"
              value={stringValue(item.gate.pulse_status) ?? "-"}
            />
            <DetailDrawerField
              label="candidate_score"
              value={compactNumber(numberValue(item.gate.candidate_score) ?? item.candidate_score)}
            />
            <DetailDrawerField
              label="score_band"
              value={stringValue(item.gate.score_band) ?? item.score_band ?? "-"}
            />
          </DetailDrawerFieldGrid>
          <DetailDrawerTagStrip emptyLabel="No blocked reasons." items={blockedReasons} />
        </DetailDrawerCard>

        <DetailDrawerCard title="Data Health">
          <DetailDrawerFieldGrid>
            <DetailDrawerField label="identity" value={factorSnapshot.data_health.identity} />
            <DetailDrawerField label="market" value={factorSnapshot.data_health.market} />
            <DetailDrawerField label="social" value={factorSnapshot.data_health.social} />
            <DetailDrawerField label="alpha" value={factorSnapshot.data_health.alpha} />
            <DetailDrawerField
              label="alpha_rank"
              value={rankValue(normalization.alpha_rank, normalization.cohort_size)}
            />
            <DetailDrawerField label="normalization" value={normalization.status ?? "-"} />
          </DetailDrawerFieldGrid>
          <DetailDrawerTagStrip emptyLabel="No data-health warnings." items={healthWarnings} />
        </DetailDrawerCard>

        <DetailDrawerCard title="Alpha Families">
          {alphaFamilies.length ? (
            <div className="detail-drawer-card-stack">
              {alphaFamilies.map(([familyName, family]) => (
                <section className="detail-drawer-family" key={familyName}>
                  <h4>{familyName}</h4>
                  <DetailDrawerFieldGrid>
                    <DetailDrawerField label="score" value={compactNumber(family.score)} />
                    <DetailDrawerField label="data_health" value={family.data_health ?? "-"} />
                  </DetailDrawerFieldGrid>
                  <pre>
                    <code>
                      {JSON.stringify(
                        { facts: family.facts ?? {}, factors: family.factors ?? {} },
                        null,
                        2,
                      )}
                    </code>
                  </pre>
                </section>
              ))}
            </div>
          ) : (
            <p>No factor families available.</p>
          )}
        </DetailDrawerCard>

        <DetailDrawerCard title="Source Events">
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

        <JsonCard title="factor_snapshot" value={jsonValue(factorSnapshot)} />
        <JsonCard title="gate" value={jsonValue(item.gate)} />
        {playbooks.length ? <JsonCard title="playbooks" value={playbooks} /> : null}

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

const ALPHA_FAMILY_ORDER = [
  "social_heat",
  "social_propagation",
  "semantic_catalyst",
  "timing_risk",
] as const;

function alphaFamilyEntries(families: SignalPulseItem["factor_snapshot"]["families"]) {
  return ALPHA_FAMILY_ORDER.map((familyName) => [familyName, families[familyName]] as const).filter(
    ([, family]) => Boolean(family),
  );
}

function dataHealthWarnings(
  dataHealth: SignalPulseItem["factor_snapshot"]["data_health"],
): string[] {
  return Object.entries(dataHealth)
    .filter(([, status]) => typeof status === "string" && status !== "ready")
    .map(([key, status]) => `${key}:${status}`);
}

function rankValue(rank: unknown, cohortSize: unknown): string {
  const parsedRank = numberValue(rank);
  const parsedCohortSize = numberValue(cohortSize);
  if (parsedRank === null) {
    return "-";
  }
  return parsedCohortSize === null ? `#${parsedRank}` : `#${parsedRank} / ${parsedCohortSize}`;
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

function ReasonList({
  items,
}: {
  items: SignalPulseItem["agent_recommendation"]["primary_reasons"];
}) {
  return <ListValue items={items.map((item) => `${item.factor_key}: ${item.explanation_zh}`)} />;
}

function ConditionList({
  items,
}: {
  items:
    | SignalPulseItem["agent_recommendation"]["upgrade_conditions"]
    | SignalPulseItem["agent_recommendation"]["invalidation_conditions"];
}) {
  return (
    <ListValue
      items={items.map(
        (item) =>
          `${item.factor_key} ${item.operator} ${String(item.value)}: ${item.description_zh}`,
      )}
    />
  );
}

function RiskList({ items }: { items: SignalPulseItem["agent_recommendation"]["residual_risks"] }) {
  return <ListValue items={items.map((item) => `${item.factor_key}: ${item.description_zh}`)} />;
}

function usdValue(value: unknown): string {
  const number = numberValue(value);
  return number === null ? "-" : formatUsdCompact(number);
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
