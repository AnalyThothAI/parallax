import * as PageState from "@shared/ui/PageState";
import { Button } from "@shared/ui/button";
import {
  Activity,
  ArrowRight,
  CalendarClock,
  Database,
  ExternalLink,
  RefreshCw,
  Search,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useMacroLiveEvidenceQuery } from "../api/useMacroLiveEvidenceQuery";
import type {
  MacroLiveMetricData,
  MacroLiveReadViewId,
  MacroLiveResearchLinkData,
  MacroLiveViewData,
  MacroLiveViewId,
  MacroLiveWindow,
} from "../model/macroTypes";

import "./MacroLiveEvidencePage.css";
import "./MacroLiveEvidenceResponsive.css";

const WINDOWS: readonly MacroLiveWindow[] = ["30d", "90d", "1y", "5y"];
const VIEW_ROUTES: ReadonlyArray<{ id: MacroLiveViewId; path: string; label: string }> = [
  { id: "overview", path: "/macro/overview", label: "总览与官方催化" },
  { id: "rates-inflation", path: "/macro/rates-inflation", label: "利率与通胀" },
  { id: "growth-labor", path: "/macro/growth-labor", label: "增长与就业" },
  { id: "liquidity-funding", path: "/macro/liquidity-funding", label: "流动性与资金" },
  { id: "credit", path: "/macro/credit", label: "信用" },
  { id: "cross-asset", path: "/macro/cross-asset", label: "跨资产" },
];

export function MacroLiveEvidencePage({
  token,
  viewId,
}: {
  token: string;
  viewId: MacroLiveReadViewId;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedWindow = searchParams.get("window");
  const window = isMacroWindow(requestedWindow) ? requestedWindow : "90d";
  const query = useMacroLiveEvidenceQuery({ token, viewId, window });
  const nowMs = useCurrentTime();

  if (query.isError && !query.data) {
    return <PageState.Error error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (query.isLoading || !query.data) {
    return <PageState.Loading label="加载宏观实时数据" layout="route" rows={8} />;
  }

  const data = query.data;
  const activeView = viewId === "dashboard" ? null : (data.views[0] ?? null);

  return (
    <PageState.Stale updating={query.isFetching && !query.isLoading}>
      <main
        aria-label={viewId === "dashboard" ? "宏观实时数据总览" : activeView?.title}
        className="macro-live-workbench"
        data-page-archetype="decision"
      >
        <LiveHeader
          activeView={viewId}
          isFetching={query.isFetching}
          readAtMs={data.read_at_ms}
          refreshFailed={query.isRefetchError}
          window={window}
          onRefresh={() => void query.refetch()}
          onWindowChange={(nextWindow) => {
            const next = new URLSearchParams(searchParams);
            next.set("window", nextWindow);
            setSearchParams(next, { replace: true });
          }}
        />
        <MacroNavigation activeView={viewId} window={window} />

        {viewId === "dashboard" ? (
          <MacroDashboard
            nowMs={nowMs}
            research={data.research}
            unclassified={data.unclassified}
            views={data.views}
            window={window}
          />
        ) : activeView ? (
          <MacroDetail nowMs={nowMs} research={data.research} view={activeView} window={window} />
        ) : (
          <PageState.Empty title="该分类没有可展示数据" hint="返回宏观总览后重试。" />
        )}
      </main>
    </PageState.Stale>
  );
}

function LiveHeader({
  activeView,
  isFetching,
  readAtMs,
  refreshFailed,
  window,
  onRefresh,
  onWindowChange,
}: {
  activeView: MacroLiveReadViewId;
  isFetching: boolean;
  readAtMs: number;
  refreshFailed: boolean;
  window: MacroLiveWindow;
  onRefresh: () => void;
  onWindowChange: (window: MacroLiveWindow) => void;
}) {
  const title =
    activeView === "dashboard"
      ? "宏观实时数据"
      : (VIEW_ROUTES.find((item) => item.id === activeView)?.label ?? "宏观实时数据");
  return (
    <header className="macro-live-header">
      <div className="macro-live-heading">
        <span>LIVE MATERIAL FACTS · SOURCE-NATIVE</span>
        <h1>{title}</h1>
        <p>实时事实与已完成交易日的 DeepAgents 研究分离；页面只展示来源事实与透明计算。</p>
      </div>
      <div className="macro-live-controls">
        <label>
          历史窗口
          <select
            aria-label="历史窗口"
            onChange={(event) => onWindowChange(event.target.value as MacroLiveWindow)}
            value={window}
          >
            {WINDOWS.map((item) => (
              <option key={item} value={item}>
                {windowLabel(item)}
              </option>
            ))}
          </select>
        </label>
        <Button
          aria-label="刷新宏观实时数据"
          disabled={isFetching}
          onClick={onRefresh}
          size="sm"
          type="button"
          variant="outline"
        >
          <RefreshCw aria-hidden="true" />
          {isFetching ? "刷新中" : "刷新"}
        </Button>
      </div>
      <div
        aria-live="polite"
        className="macro-live-read-health"
        data-state={refreshFailed ? "failed" : "ok"}
      >
        <Activity aria-hidden="true" />
        <span>{refreshFailed ? "刷新失败，保留上次成功数据" : "读取正常"}</span>
        <small>最近成功读取 {formatInstant(readAtMs)}</small>
      </div>
    </header>
  );
}

function MacroNavigation({
  activeView,
  window,
}: {
  activeView: MacroLiveReadViewId;
  window: MacroLiveWindow;
}) {
  return (
    <nav aria-label="宏观数据分类" className="macro-live-navigation">
      <Link
        aria-current={activeView === "dashboard" ? "page" : undefined}
        to={`/macro?window=${window}`}
      >
        总览
      </Link>
      {VIEW_ROUTES.map((item) => (
        <Link
          aria-current={activeView === item.id ? "page" : undefined}
          key={item.id}
          to={`${item.path}?window=${window}`}
        >
          {item.label}
        </Link>
      ))}
      <Link to="/macro/research">完整研究</Link>
    </nav>
  );
}

function MacroDashboard({
  nowMs,
  research,
  unclassified,
  views,
  window,
}: {
  nowMs: number;
  research: MacroLiveResearchLinkData | null;
  unclassified: MacroLiveMetricData[];
  views: MacroLiveViewData[];
  window: MacroLiveWindow;
}) {
  return (
    <>
      <ResearchCard research={research} />
      <section aria-label="六类宏观数据" className="macro-live-category-grid">
        {views.map((view) => (
          <CategoryCard key={view.view_id} nowMs={nowMs} view={view} window={window} />
        ))}
      </section>
      <UnclassifiedFacts metrics={unclassified} nowMs={nowMs} />
    </>
  );
}

function ResearchCard({ research }: { research: MacroLiveResearchLinkData | null }) {
  if (!research) return null;
  return (
    <section aria-label="最近 DeepAgents 研究" className="macro-live-research-card">
      <div>
        <span>COMPLETED-SESSION RESEARCH</span>
        <h2>{research.title ?? researchStateLabel(research.state)}</h2>
        <p>
          {research.executive_summary ?? "研究文档尚未发布；实时数据页不会临时启动或恢复 Agent。"}
        </p>
      </div>
      <dl>
        <div>
          <dt>研究交易日</dt>
          <dd>{research.session_date}</dd>
        </div>
        <div>
          <dt>市场截止</dt>
          <dd>
            {research.market_cutoff_ms ? formatInstant(research.market_cutoff_ms) : "尚未记录"}
          </dd>
        </div>
        <div>
          <dt>声明缺口</dt>
          <dd>{research.evidence_gap_summaries.length}</dd>
        </div>
      </dl>
      <Link className="macro-live-primary-link" to={research.href}>
        阅读完整研究
        <ArrowRight aria-hidden="true" />
      </Link>
    </section>
  );
}

function CategoryCard({
  nowMs,
  view,
  window,
}: {
  nowMs: number;
  view: MacroLiveViewData;
  window: MacroLiveWindow;
}) {
  const route = VIEW_ROUTES.find((item) => item.id === view.view_id);
  return (
    <article className="macro-live-category-card">
      <header>
        <div>
          <span>
            {view.available_count}/{view.total_metric_count} 已有观测
          </span>
          <h2>{view.title}</h2>
        </div>
        <small>
          {view.latest_observed_at ? `最新观察 ${view.latest_observed_at}` : "暂无观察"}
        </small>
      </header>
      <p>{view.description}</p>
      <div className="macro-live-card-metrics">
        {view.metrics.map((metric) => (
          <CompactMetric key={metric.concept_key} metric={metric} nowMs={nowMs} />
        ))}
      </div>
      <Link to={`${route?.path ?? "/macro"}?window=${window}`}>
        查看全部明细
        <ArrowRight aria-hidden="true" />
      </Link>
    </article>
  );
}

function CompactMetric({ metric, nowMs }: { metric: MacroLiveMetricData; nowMs: number }) {
  return (
    <div className="macro-live-compact-metric" data-availability={metric.availability}>
      <span>{metric.display_label}</span>
      <strong>{formatMetricValue(metric)}</strong>
      <small>{metricTimingLabel(metric, nowMs)}</small>
    </div>
  );
}

function MacroDetail({
  nowMs,
  research,
  view,
  window,
}: {
  nowMs: number;
  research: MacroLiveResearchLinkData | null;
  view: MacroLiveViewData;
  window: MacroLiveWindow;
}) {
  const [search, setSearch] = useState("");
  const chartable = useMemo(
    () => view.metrics.filter((metric) => metric.history.filter(hasNumericValue).length >= 2),
    [view.metrics],
  );
  const [selectedConcept, setSelectedConcept] = useState(chartable[0]?.concept_key ?? "");

  useEffect(() => {
    if (!chartable.some((metric) => metric.concept_key === selectedConcept)) {
      setSelectedConcept(chartable[0]?.concept_key ?? "");
    }
  }, [chartable, selectedConcept]);

  const selectedMetric =
    chartable.find((metric) => metric.concept_key === selectedConcept) ?? chartable[0] ?? null;
  const normalizedSearch = search.trim().toLocaleLowerCase("zh-CN");
  const filtered = view.metrics.filter((metric) =>
    [
      metric.display_label,
      metric.concept_key,
      metric.source_name,
      metric.series_key,
      metric.section_label,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase("zh-CN").includes(normalizedSearch)),
  );

  return (
    <>
      <ResearchLinkStrip research={research} />
      <section aria-label={`${view.title}精选摘要`} className="macro-live-summary-grid">
        {view.metrics
          .filter((metric) => metric.summary)
          .map((metric) => (
            <MetricCard key={metric.concept_key} metric={metric} nowMs={nowMs} />
          ))}
      </section>
      <section aria-label={`${view.title}历史图表`} className="macro-live-chart-panel">
        <header>
          <div>
            <span>HISTORY · {windowLabel(window)}</span>
            <h2>历史序列</h2>
          </div>
          <label>
            图表指标
            <select
              aria-label="图表指标"
              disabled={!chartable.length}
              onChange={(event) => setSelectedConcept(event.target.value)}
              value={selectedMetric?.concept_key ?? ""}
            >
              {chartable.map((metric) => (
                <option key={metric.concept_key} value={metric.concept_key}>
                  {metric.display_label}
                </option>
              ))}
            </select>
          </label>
        </header>
        {selectedMetric ? (
          <MetricChart metric={selectedMetric} />
        ) : (
          <p className="macro-live-muted">当前窗口没有至少两个可绘制数值点。</p>
        )}
      </section>
      <section aria-label={`${view.title}完整明细`} className="macro-live-table-panel">
        <header>
          <div>
            <span>COMPLETE FACT TABLE</span>
            <h2>完整明细</h2>
            <p>按中文名称、concept key、来源或序列搜索；缺失只影响对应行。</p>
          </div>
          <label className="macro-live-search">
            <Search aria-hidden="true" />
            <span className="sr-only">搜索宏观指标</span>
            <input
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索名称、concept、source、series"
              type="search"
              value={search}
            />
          </label>
        </header>
        <MetricTable metrics={filtered} nowMs={nowMs} />
      </section>
    </>
  );
}

function ResearchLinkStrip({ research }: { research: MacroLiveResearchLinkData | null }) {
  if (!research) return null;
  return (
    <aside className="macro-live-research-strip">
      <CalendarClock aria-hidden="true" />
      <span>
        最近研究交易日 <strong>{research.session_date}</strong>
        {research.market_cutoff_ms ? ` · 截止 ${formatInstant(research.market_cutoff_ms)}` : ""}
      </span>
      <Link to={research.href}>查看完整冻结研究</Link>
    </aside>
  );
}

function MetricCard({ metric, nowMs }: { metric: MacroLiveMetricData; nowMs: number }) {
  return (
    <article className="macro-live-metric-card" data-availability={metric.availability}>
      <header>
        <span>{metric.section_label}</span>
        <small>{metric.kind === "derived" ? "透明计算" : (metric.frequency ?? "频率未提供")}</small>
      </header>
      <h2>{metric.display_label}</h2>
      <strong>{formatMetricValue(metric)}</strong>
      <p>{metricTimingLabel(metric, nowMs)}</p>
      {metric.calculation ? (
        <small title={metric.calculation.formula}>
          {formatCalculation(metric.calculation.result, metric.calculation.unit)} · 样本{" "}
          {metric.calculation.sample_size}
        </small>
      ) : null}
    </article>
  );
}

function MetricChart({ metric }: { metric: MacroLiveMetricData }) {
  const points = metric.history.filter(hasNumericValue);
  const values = points.map((point) => point.value_numeric as number);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const coordinates = points
    .map((point, index) => {
      const x = points.length === 1 ? 0 : (index / (points.length - 1)) * 100;
      const y = 90 - (((point.value_numeric as number) - minimum) / range) * 80;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <div className="macro-live-chart">
      <div>
        <strong>{metric.display_label}</strong>
        <span>
          {formatNumber(minimum)}–{formatNumber(maximum)} {unitLabel(metric.unit)}
        </span>
      </div>
      <svg
        aria-label={`${metric.display_label}历史折线图，共 ${points.length} 个样本`}
        preserveAspectRatio="none"
        role="img"
        viewBox="0 0 100 100"
      >
        <line x1="0" x2="100" y1="90" y2="90" />
        <polyline fill="none" points={coordinates} vectorEffect="non-scaling-stroke" />
      </svg>
      <footer>
        <span>{points[0]?.observed_at}</span>
        <span>{points.at(-1)?.observed_at}</span>
      </footer>
    </div>
  );
}

function MetricTable({ metrics, nowMs }: { metrics: MacroLiveMetricData[]; nowMs: number }) {
  if (!metrics.length) {
    return <PageState.Empty title="没有匹配的指标" hint="调整搜索词后重试。" />;
  }
  return (
    <div className="macro-live-table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">指标</th>
            <th scope="col">最新值</th>
            <th scope="col">变动 / 公式</th>
            <th scope="col">观察或事件时间</th>
            <th scope="col">系统接收</th>
            <th scope="col">来源与序列</th>
            <th scope="col">质量</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => (
            <tr data-availability={metric.availability} key={metric.concept_key}>
              <th scope="row">
                <strong>{metric.display_label}</strong>
                <code>{metric.concept_key}</code>
                <small>{metric.section_label}</small>
              </th>
              <td>{formatMetricValue(metric)}</td>
              <td>
                {metric.calculation ? (
                  <>
                    <strong>
                      {formatCalculation(metric.calculation.result, metric.calculation.unit)}
                    </strong>
                    <small title={metric.calculation.formula}>
                      {metric.calculation.formula_id} · n={metric.calculation.sample_size}
                    </small>
                  </>
                ) : (
                  <span>—</span>
                )}
              </td>
              <td>
                <span>{metricTimingLabel(metric, nowMs)}</span>
                <small>{metric.source_timestamp ?? "源时间未提供"}</small>
              </td>
              <td>
                <span>
                  {metric.received_at_ms ? formatInstant(metric.received_at_ms) : "未接收"}
                </span>
              </td>
              <td>
                <span>{metric.source_name ?? "来源未提供"}</span>
                <code>{metric.series_key ?? "series 未提供"}</code>
                {metric.source_url ? (
                  <a href={metric.source_url} rel="noreferrer" target="_blank">
                    来源
                    <ExternalLink aria-hidden="true" />
                  </a>
                ) : null}
              </td>
              <td>
                {metric.data_quality ?? (metric.availability === "missing" ? "缺失" : "未提供")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UnclassifiedFacts({ metrics, nowMs }: { metrics: MacroLiveMetricData[]; nowMs: number }) {
  return (
    <details className="macro-live-unclassified">
      <summary>
        <Database aria-hidden="true" />
        未分类最新事实（{metrics.length}）
      </summary>
      <p>这些事实不在 108 项展示目录中，但不会被隐藏或阻止 Agent 访问。</p>
      {metrics.length ? (
        <MetricTable metrics={metrics} nowMs={nowMs} />
      ) : (
        <p className="macro-live-muted">当前没有目录外事实。</p>
      )}
    </details>
  );
}

function useCurrentTime(): number {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(Date.now()), 30_000);
    return () => window.clearInterval(interval);
  }, []);
  return nowMs;
}

function isMacroWindow(value: string | null): value is MacroLiveWindow {
  return value !== null && WINDOWS.includes(value as MacroLiveWindow);
}

function hasNumericValue(point: { value_numeric: number | null }): boolean {
  return point.value_numeric !== null && Number.isFinite(point.value_numeric);
}

function formatMetricValue(metric: MacroLiveMetricData): string {
  if (metric.availability === "missing" || metric.value_numeric === null) return "—";
  return `${formatNumber(metric.value_numeric)} ${unitLabel(metric.unit)}`.trim();
}

function formatCalculation(value: number | null, unit: string): string {
  return value === null ? "不可计算" : `${formatNumber(value)} ${unitLabel(unit)}`.trim();
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 }).format(value);
}

function unitLabel(unit: string | null): string {
  const labels: Record<string, string> = {
    basis_points: "bp",
    billions_chained_usd: "十亿美元（不变价）",
    billions_usd: "十亿美元",
    correlation: "",
    days_until: "天",
    dollars_per_hour: "美元/小时",
    index: "点",
    millions_usd: "百万美元",
    number: "人",
    percent: "%",
    percentage_points: "百分点",
    percent_saar: "% SAAR",
    price: "",
    thousands: "千",
    thousands_persons: "千人",
    thousands_units: "千套",
  };
  return unit ? (labels[unit] ?? unit) : "";
}

function metricTimingLabel(metric: MacroLiveMetricData, nowMs: number): string {
  if (metric.availability === "missing") return "该行尚无持久化观测";
  if (metric.observed_at && Date.parse(`${metric.observed_at}T00:00:00Z`) > nowMs) {
    const days = Math.ceil((Date.parse(`${metric.observed_at}T00:00:00Z`) - nowMs) / 86_400_000);
    return `距官方事件 ${Math.max(0, days)} 天 · ${metric.observed_at}`;
  }
  if (metric.source_timestamp?.includes("T")) {
    const sourceMs = Date.parse(metric.source_timestamp);
    if (Number.isFinite(sourceMs))
      return `数据年龄 ${formatDuration(Math.max(0, nowMs - sourceMs))}`;
  }
  return metric.observed_at ? `观察期 ${metric.observed_at}` : "观察时间未提供";
}

function formatDuration(durationMs: number): string {
  const minutes = Math.floor(durationMs / 60_000);
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} 小时`;
  return `${Math.floor(hours / 24)} 天`;
}

function formatInstant(value: number): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function windowLabel(window: MacroLiveWindow): string {
  return { "30d": "30 天", "90d": "90 天", "1y": "1 年", "5y": "5 年" }[window];
}

function researchStateLabel(state: MacroLiveResearchLinkData["state"]): string {
  return {
    current: "最近研究",
    failed: "最近研究生成失败",
    generating: "最近研究正在生成",
    missing: "尚无最近研究",
  }[state];
}
