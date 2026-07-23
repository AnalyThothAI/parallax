import * as PageState from "@shared/ui/PageState";
import type { UseQueryResult } from "@tanstack/react-query";
import { Bot, CheckCircle2 } from "lucide-react";
import type { ReactNode } from "react";

import type { DailyMacroJudgmentReadData } from "../model/macroTypes";

import "./DailyMacroAnalysis.css";

type Publication = NonNullable<DailyMacroJudgmentReadData["publication"]>;
type Pressure = Publication["judgment"]["pressures"][number];
type Direction = Publication["judgment"]["spy_5d"]["direction"];

const DIRECTION_LABELS: Record<Direction, string> = {
  down: "偏下",
  no_call: "不判断",
  range: "区间",
  up: "偏上",
};

const PRESSURE_AXIS_LABELS: Record<Pressure["axis"], string> = {
  credit: "信用",
  growth: "增长",
  inflation: "通胀",
  liquidity_funding: "流动性与融资",
  policy_real_rates: "政策与实际利率",
  term_premium_supply: "期限溢价与供给",
};

const PRESSURE_STATE_LABELS: Record<Pressure["state"], string> = {
  easing: "缓和",
  elevated: "高位",
  neutral: "中性",
  rising: "上升",
  unclear: "不明确",
};

const EMPTY_STATE_LABELS: Record<DailyMacroJudgmentReadData["state"], string> = {
  blocked: "今日研判被证据门槛阻断",
  current: "今日研判尚未发布",
  failed: "今日研判生成失败",
  historical: "所选历史研判不存在",
  missing: "今日研判尚未生成",
  pending: "今日研判等待生成",
  retryable: "今日研判等待重试",
  running: "今日研判生成中",
  stale: "当前交易日研判尚未发布",
};

export function DailyMacroAnalysis({
  query,
}: {
  query: UseQueryResult<DailyMacroJudgmentReadData, Error>;
}) {
  if (query.isLoading) {
    return (
      <DailyMacroStateFrame>
        <PageState.Loading label="加载每日 AI 宏观研判" layout="panel" rows={2} />
      </DailyMacroStateFrame>
    );
  }
  if (query.isError) {
    return (
      <DailyMacroStateFrame>
        <PageState.Error error={query.error} onRetry={() => void query.refetch()} />
      </DailyMacroStateFrame>
    );
  }
  if (!query.data?.publication) {
    const state = query.data?.state ?? "missing";
    return (
      <DailyMacroStateFrame>
        <PageState.Empty
          hint={
            query.data
              ? `目标交易日 ${query.data.target_session_date}；页面不会临时调用模型。`
              : "页面不会临时调用模型。"
          }
          title={EMPTY_STATE_LABELS[state]}
        />
      </DailyMacroStateFrame>
    );
  }

  return <PublishedDailyMacroAnalysis data={query.data} publication={query.data.publication} />;
}

function DailyMacroStateFrame({ children }: { children: ReactNode }) {
  return (
    <section
      aria-labelledby="daily-macro-analysis-title"
      className="macro-daily-analysis macro-daily-analysis-state-only"
    >
      <header className="macro-daily-analysis-header">
        <DailyMacroTitle />
      </header>
      {children}
    </section>
  );
}

function DailyMacroTitle() {
  return (
    <div>
      <span className="macro-daily-analysis-kicker">
        <Bot aria-hidden />
        DEEPAGENT DAILY
      </span>
      <h2 id="daily-macro-analysis-title">每日 AI 宏观研判</h2>
    </div>
  );
}

function PublishedDailyMacroAnalysis({
  data,
  publication,
}: {
  data: DailyMacroJudgmentReadData;
  publication: Publication;
}) {
  const judgment = publication.judgment;
  return (
    <section
      aria-labelledby="daily-macro-analysis-title"
      className="macro-daily-analysis"
      data-health={judgment.data_health}
    >
      <header className="macro-daily-analysis-header">
        <DailyMacroTitle />
        <div className="macro-daily-analysis-meta">
          <span>{data.is_current ? "当前交易日" : "历史 / 滞后"}</span>
          <time dateTime={publication.session_date}>{publication.session_date}</time>
          <span data-health={judgment.data_health}>
            数据{judgment.data_health === "ready" ? "正常" : "降级"}
          </span>
          {publication.review.disposition === "pass" ? (
            <span>
              <CheckCircle2 aria-hidden />
              已复核
            </span>
          ) : null}
        </div>
      </header>

      <div className="macro-daily-analysis-grid">
        <div className="macro-daily-analysis-state">
          <span>宏观状态 / 压力</span>
          <p>{judgment.macro_state}</p>
          <div className="macro-daily-pressure-list">
            {judgment.pressures.map((pressure) => (
              <article key={pressure.axis}>
                <header>
                  <strong>{PRESSURE_AXIS_LABELS[pressure.axis]}</strong>
                  <span data-state={pressure.state}>{PRESSURE_STATE_LABELS[pressure.state]}</span>
                </header>
                <p>{pressure.mechanism}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="macro-daily-spy-calls">
          <span>SPY 未来方向</span>
          <SpyCall call={judgment.spy_5d} label="5D" />
          <SpyCall call={judgment.spy_20d} label="20D" />
        </div>
      </div>

      <div className="macro-daily-counterevidence">
        <strong>关键反证</strong>
        <ul>
          {judgment.counterevidence.map((item) => (
            <li key={`${item.statement}:${item.evidence_refs.join(",")}`}>{item.statement}</li>
          ))}
        </ul>
      </div>

      <footer>
        <span>实验性影子研究，不是交易指令</span>
        <span>分析模型 {publication.model_name}</span>
      </footer>
    </section>
  );
}

function SpyCall({
  call,
  label,
}: {
  call: Publication["judgment"]["spy_5d"];
  label: "5D" | "20D";
}) {
  return (
    <article className="macro-daily-spy-call" data-direction={call.direction}>
      <header>
        <strong>{label}</strong>
        <span>{DIRECTION_LABELS[call.direction]}</span>
      </header>
      <p>{call.thesis}</p>
    </article>
  );
}
