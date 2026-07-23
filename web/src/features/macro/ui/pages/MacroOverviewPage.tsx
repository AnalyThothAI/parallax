import type { components } from "@lib/types/openapi";
import * as PageState from "@shared/ui/PageState";
import { ArrowDownRight, ArrowRight, ArrowUpRight, CalendarClock, ShieldX } from "lucide-react";

import { useMacroOverviewQuery } from "../../api/useMacroPageQueries";
import {
  macroCodeLabel,
  macroConceptLabel,
  macroDecisionGapLabel,
  macroLabel,
} from "../../model/macroDisplay";
import type { MacroOverviewData } from "../../model/macroTypes";
import { MacroAuditDrawer, MacroDomainNavigation, MacroPageHeader } from "../MacroPageFrame";

import "./MacroOverviewPage.css";

type RiskLane = MacroOverviewData["risk_lanes"][number];
type Catalyst = components["schemas"]["MacroOfficialCatalystData"];

const LANE_LABELS: Record<RiskLane["lane_id"], string> = {
  credit: "信用",
  crypto: "加密资产",
  gold: "黄金",
  long_duration_treasuries: "长期美债",
  market_volatility: "市场波动率",
  oil: "原油",
  usd: "美元",
  us_equities: "美国股票",
};

const DIRECTION_LABELS: Record<RiskLane["direction"], string> = {
  headwind: "逆风",
  insufficient_evidence: "证据不足",
  neutral: "中性",
  tailwind: "顺风",
};

const TREND_LABELS: Record<RiskLane["trend"], string> = {
  insufficient_evidence: "缺少可比历史",
  stable: "基本不变",
  strengthening: "增强",
  weakening: "减弱",
};

const CONFIDENCE_LABELS: Record<RiskLane["confidence"], string> = {
  high: "高确信",
  insufficient_evidence: "证据不足",
  low: "低确信",
  medium: "中确信",
};

const SHOCK_STATE_LABELS: Record<MacroOverviewData["shock_summary"]["state"], string> = {
  dominant: "主导冲击",
  insufficient_evidence: "证据不足",
  no_dominant_shock: "无单一主导冲击",
};

export function MacroOverviewPage({ token }: { token: string }) {
  const query = useMacroOverviewQuery({ token });

  if (query.isError) {
    return <PageState.Error error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (query.isLoading || !query.data) {
    return <PageState.Loading label="加载跨资产风险地图" layout="route" />;
  }

  const data = query.data;

  return (
    <PageState.Stale updating={query.isFetching && !query.isLoading}>
      <section
        aria-label="跨资产风险地图"
        className="macro-workbench macro-overview"
        data-page-archetype="decision"
      >
        <div className="macro-overview-topline">
          <MacroPageHeader
            conclusion={data.conclusion.judgment}
            question="当前完成交易日的固定跨资产风险地图；只描述跨资产环境。"
            status={data.conclusion.status}
            title="跨资产风险地图"
          />
          <section
            aria-label="当前冲击状态"
            className="macro-shock-summary"
            data-state={data.shock_summary.state}
          >
            <div>
              <span>{SHOCK_STATE_LABELS[data.shock_summary.state]}</span>
              <strong>
                {data.shock_summary.candidate
                  ? macroLabel(data.shock_summary.candidate)
                  : SHOCK_STATE_LABELS[data.shock_summary.state]}
              </strong>
            </div>
            <p>{data.shock_summary.summary}</p>
            <dl>
              <div>
                <dt>五日变化</dt>
                <dd>{TREND_LABELS[data.shock_summary.trend]}</dd>
              </div>
              <div>
                <dt>确信度</dt>
                <dd>{CONFIDENCE_LABELS[data.shock_summary.confidence]}</dd>
              </div>
            </dl>
          </section>
        </div>

        <MacroDomainNavigation />

        <section aria-labelledby="risk-map-title" className="macro-risk-map">
          <header>
            <div>
              <span>当前完成交易日 vs 五个已完成交易日前</span>
              <h2 id="risk-map-title">八类风险暴露</h2>
            </div>
            <small>顺风 / 中性 / 逆风 / 证据不足</small>
          </header>
          <div className="macro-risk-lanes">
            {data.risk_lanes.map((lane) => (
              <MacroRiskLaneCard key={lane.lane_id} lane={lane} />
            ))}
          </div>
        </section>

        <section aria-label="关键变化、催化与失效" className="macro-overview-action-band">
          <div className="macro-key-changes">
            <header>
              <span>WHAT CHANGED</span>
              <h2>五个交易日内的关键变化</h2>
            </header>
            {data.key_changes.length ? (
              <ol>
                {data.key_changes.map((item) => (
                  <li key={`${item.rank}:${item.lane_id}`}>
                    <span>{item.rank}</span>
                    <div>
                      <b>{LANE_LABELS[item.lane_id]}</b>
                      <p>{item.summary}</p>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p>没有达到报告门槛的方向变化。</p>
            )}
          </div>

          <OverviewCatalyst catalyst={data.nearest_catalyst} />

          <div className="macro-core-invalidation">
            <header>
              <ShieldX aria-hidden />
              <div>
                <span>CORE INVALIDATION</span>
                <h2>核心失效条件</h2>
              </div>
            </header>
            {data.core_invalidation ? (
              <>
                <strong>{macroCodeLabel(data.core_invalidation.code)}</strong>
                <p>{data.core_invalidation.evidence_refs.map(macroConceptLabel).join(" · ")}</p>
              </>
            ) : (
              <p>证据不足时不设置失效条件。</p>
            )}
          </div>
        </section>

        <MacroAuditDrawer data={data} />
      </section>
    </PageState.Stale>
  );
}

function MacroRiskLaneCard({ lane }: { lane: RiskLane }) {
  const TrendIcon =
    lane.trend === "strengthening"
      ? ArrowUpRight
      : lane.trend === "weakening"
        ? ArrowDownRight
        : ArrowRight;
  return (
    <article
      aria-label={`${LANE_LABELS[lane.lane_id]}风险暴露`}
      className="macro-risk-lane"
      data-confidence={lane.confidence}
      data-direction={lane.direction}
    >
      <header>
        <div>
          <span>{LANE_LABELS[lane.lane_id]}</span>
          <strong>{DIRECTION_LABELS[lane.direction]}</strong>
        </div>
        <span className="macro-risk-lane-trend">
          <TrendIcon aria-hidden />
          {TREND_LABELS[lane.trend]}
        </span>
      </header>
      <p>{lane.summary}</p>
      <footer>
        <span>{CONFIDENCE_LABELS[lane.confidence]}</span>
        <small>{lane.current_session}</small>
      </footer>
      {lane.degradation_reason ? (
        <div className="macro-risk-lane-gap" role="status">
          局部证据缺口：{macroDecisionGapLabel(lane.degradation_reason)}
        </div>
      ) : null}
      {lane.contradiction ? (
        <div className="macro-risk-lane-contradiction">
          反证：{macroCodeLabel(lane.contradiction.code)}
        </div>
      ) : null}
    </article>
  );
}

function OverviewCatalyst({ catalyst }: { catalyst: Catalyst | null }) {
  return (
    <div className="macro-nearest-catalyst">
      <header>
        <CalendarClock aria-hidden />
        <div>
          <span>NEAREST CATALYST</span>
          <h2>最近官方催化</h2>
        </div>
      </header>
      {catalyst ? (
        <>
          <strong>{macroConceptLabel(catalyst.concept_key)}</strong>
          <time
            dateTime={
              catalyst.event_at_ms ? new Date(catalyst.event_at_ms).toISOString() : undefined
            }
          >
            {catalyst.event_at_ms
              ? new Intl.DateTimeFormat("zh-CN", {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(catalyst.event_at_ms)
              : `${catalyst.event_date} ${catalyst.event_time}`}
          </time>
          <small>
            官方时间 {catalyst.event_date} {catalyst.event_time} · {catalyst.timezone}
          </small>
          <a href={catalyst.source_url} rel="noreferrer" target="_blank">
            {catalyst.source_name}
          </a>
        </>
      ) : (
        <p>未来七天没有符合合同的官方事件。</p>
      )}
    </div>
  );
}
