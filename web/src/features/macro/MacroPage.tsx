import type {
  MacroChainNode,
  MacroData,
  MacroFeatureSnapshot,
  MacroIndicator,
  MacroPanel,
  MacroScenario,
  MacroScorecard,
  MacroSnapshotSummary,
  MacroTrigger,
} from "@lib/types";
import * as Tabs from "@radix-ui/react-tabs";
import { RemoteState } from "@shared/ui/RemoteState";
import clsx from "clsx";
import {
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type LineData,
} from "lightweight-charts";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Banknote,
  CalendarDays,
  ChevronRight,
  CircleDot,
  Database,
  Gauge,
  GitBranch,
  Landmark,
  LineChart,
  ListChecks,
  Map as MapIcon,
  ShieldCheck,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useMacroQuery } from "./api/useMacroQuery";
import "./macro.css";

type MacroModuleId =
  | "overview"
  | "assets"
  | "rates"
  | "fed"
  | "liquidity"
  | "economy"
  | "volatility"
  | "credit";

type ModuleTone = "stress" | "constructive" | "neutral" | "gap";

type MacroModule = {
  id: MacroModuleId;
  navLabel: string;
  title: string;
  subtitle: string;
  userQuestion: string;
  icon: LucideIcon;
  chainKeys: string[];
  panelKeys: string[];
  indicatorKeys: string[];
  featureKeys: string[];
  triggerKeywords: string[];
  secondaries: SecondaryPage[];
  missingTopics?: string[];
};

type SecondaryPage = {
  id: string;
  label: string;
  title: string;
  description: string;
  featureKeys: string[];
  indicatorKeys: string[];
};

type ScenarioSignal = NonNullable<MacroScenario["confirmations"]>[number];
type TradeMapEntry = NonNullable<MacroScenario["trade_map"]>[number];

const CHAIN_ORDER = [
  "rates",
  "fed_corridor",
  "liquidity",
  "credit",
  "volatility",
  "positioning",
  "cross_asset",
];

const MODULES: MacroModule[] = [
  {
    id: "overview",
    navLabel: "总览",
    title: "宏观状态机",
    subtitle: "把利率、流动性、信用、波动率和资产价格压缩成一张可验证的 regime map。",
    userQuestion: "现在的市场主线是什么，哪些证据确认，哪些证据反驳？",
    icon: Gauge,
    chainKeys: CHAIN_ORDER,
    panelKeys: ["rates", "liquidity", "credit", "volatility", "cross_asset"],
    indicatorKeys: [
      "ust_10y_yield_pct",
      "sofr_iorb_spread_bps",
      "net_liquidity_usd_millions",
      "hy_oas_pct",
      "ig_oas_pct",
      "vix",
      "sp500_index",
    ],
    featureKeys: [
      "fred:DGS10",
      "nyfed:SOFR",
      "fred:WALCL",
      "treasury_fiscal:operating_cash_balance",
      "fred:BAMLH0A0HYM2",
      "fred:VIXCLS",
      "fred:SP500",
    ],
    triggerKeywords: [],
    secondaries: [
      {
        id: "snapshot",
        label: "总览",
        title: "Regime Snapshot",
        description: "先看当前 regime、链路平均分和确认/反驳项。",
        featureKeys: ["fred:DGS10", "fred:WALCL", "fred:BAMLH0A0HYM2", "fred:VIXCLS"],
        indicatorKeys: ["ust_10y_yield_pct", "net_liquidity_usd_millions", "hy_oas_pct", "vix"],
      },
      {
        id: "chain",
        label: "传导链",
        title: "Liquidity Transmission Chain",
        description: "按因果顺序看：利率/Fed -> funding -> credit -> vol -> asset confirmation。",
        featureKeys: ["fred:DGS10", "nyfed:SOFR", "fred:WRBWFRBL", "fred:SP500"],
        indicatorKeys: ["sofr_iorb_spread_bps", "net_liquidity_usd_millions"],
      },
    ],
  },
  {
    id: "assets",
    navLabel: "大类资产",
    title: "大类资产确认",
    subtitle: "价格是结果，不是原因。用股、债、商品、美元和高 beta 资产确认宏观叙事。",
    userQuestion: "风险偏好是真扩张，还是只有少数资产在拉动？",
    icon: BarChart3,
    chainKeys: ["cross_asset", "credit", "volatility"],
    panelKeys: ["cross_asset", "credit", "volatility"],
    indicatorKeys: ["sp500_index", "vix", "hy_oas_pct", "ig_oas_pct"],
    featureKeys: [
      "fred:SP500",
      "stooq:spy.us",
      "stooq:qqq.us",
      "stooq:iwm.us",
      "stooq:tlt.us",
      "stooq:hyg.us",
      "stooq:lqd.us",
      "stooq:uso.us",
      "stooq:gld.us",
      "fred:DTWEXBGS",
      "fred:DCOILWTICO",
    ],
    triggerKeywords: ["term", "hy", "vix"],
    secondaries: [
      {
        id: "equity",
        label: "股票",
        title: "Equity Leadership",
        description: "看 SPX、QQQ、IWM 分化，判断是广谱 risk-on 还是 mega-cap 挤压。",
        featureKeys: ["fred:SP500", "stooq:spy.us", "stooq:qqq.us", "stooq:iwm.us"],
        indicatorKeys: ["sp500_index"],
      },
      {
        id: "quality",
        label: "债券/信用 ETF",
        title: "Bond And Credit Confirmation",
        description: "用 TLT、HYG、LQD 看利率压力和信用质量是否支持股票价格。",
        featureKeys: ["stooq:tlt.us", "stooq:hyg.us", "stooq:lqd.us"],
        indicatorKeys: ["hy_oas_pct", "ig_oas_pct"],
      },
      {
        id: "macro-beta",
        label: "商品/美元",
        title: "Inflation And Dollar Beta",
        description: "油、金、美元指数用于区分通胀冲击、避险美元和真实需求。",
        featureKeys: ["stooq:uso.us", "stooq:gld.us", "fred:DCOILWTICO", "fred:DTWEXBGS"],
        indicatorKeys: [],
      },
    ],
  },
  {
    id: "rates",
    navLabel: "利率",
    title: "利率与期限溢价",
    subtitle: "把名义利率拆成政策路径、实际利率、通胀预期和曲线形态。",
    userQuestion: "长端上行来自增长、通胀、实际利率，还是供给/期限溢价？",
    icon: LineChart,
    chainKeys: ["rates", "fed_corridor", "liquidity"],
    panelKeys: ["rates", "liquidity"],
    indicatorKeys: ["ust_10y_yield_pct", "ust_10y_2y_curve_pct"],
    featureKeys: [
      "fred:DGS2",
      "fred:DGS5",
      "fred:DGS10",
      "fred:DGS30",
      "fred:DFII10",
      "fred:T10Y2Y",
      "fred:T10Y3M",
      "fred:T10YIE",
      "fred:T5YIFR",
    ],
    triggerKeywords: ["term", "yield", "real"],
    secondaries: [
      {
        id: "curve",
        label: "曲线",
        title: "Nominal Yield Curve",
        description: "前端对应 Fed 路径，长端对应增长、通胀和期限溢价。",
        featureKeys: ["fred:DGS2", "fred:DGS5", "fred:DGS10", "fred:DGS30"],
        indicatorKeys: ["ust_10y_yield_pct", "ust_10y_2y_curve_pct"],
      },
      {
        id: "real-inflation",
        label: "实际/通胀",
        title: "Real Yield And Inflation Compensation",
        description: "实际利率压估值，breakeven 和 5Y5Y 决定通胀叙事是否被确认。",
        featureKeys: ["fred:DFII10", "fred:T10YIE", "fred:T5YIFR"],
        indicatorKeys: [],
      },
    ],
  },
  {
    id: "fed",
    navLabel: "美联储",
    title: "Fed Corridor",
    subtitle: "话术是预期管理，利率走廊是执行约束。核心看 EFFR/SOFR/IORB 是否稳定。",
    userQuestion: "政策执行是否稳定，repo 是否开始挑战准备金充裕状态？",
    icon: Landmark,
    chainKeys: ["fed_corridor", "liquidity", "rates"],
    panelKeys: ["rates", "liquidity"],
    indicatorKeys: ["sofr_iorb_spread_bps"],
    featureKeys: ["fred:DFEDTARL", "fred:DFEDTARU", "fred:EFFR", "fred:IORB", "nyfed:SOFR"],
    triggerKeywords: ["sofr", "repo", "iorb", "fed"],
    secondaries: [
      {
        id: "corridor",
        label: "走廊",
        title: "Policy Corridor",
        description: "目标区间、EFFR、IORB、SOFR 的相对位置决定政策传导是否顺畅。",
        featureKeys: ["fred:DFEDTARL", "fred:DFEDTARU", "fred:EFFR", "fred:IORB", "nyfed:SOFR"],
        indicatorKeys: ["sofr_iorb_spread_bps"],
      },
      {
        id: "implementation",
        label: "执行",
        title: "Implementation Stress",
        description: "SOFR-IORB 是边际 funding 压力；正利差持续扩大才需要升级风险。",
        featureKeys: ["nyfed:SOFR", "fred:IORB", "fred:EFFR"],
        indicatorKeys: ["sofr_iorb_spread_bps"],
      },
    ],
  },
  {
    id: "liquidity",
    navLabel: "流动性",
    title: "美元流动性",
    subtitle: "净流动性不是单一水位，而是 Fed balance sheet、RRP、TGA、准备金和 SOFR 的组合。",
    userQuestion: "系统是在释放现金，还是财政/融资压力正在抽水？",
    icon: Waves,
    chainKeys: ["liquidity", "fed_corridor", "credit", "cross_asset"],
    panelKeys: ["liquidity", "credit", "cross_asset"],
    indicatorKeys: ["net_liquidity_usd_millions", "sofr_iorb_spread_bps"],
    featureKeys: [
      "fred:WALCL",
      "fred:WRBWFRBL",
      "fred:RRPONTSYD",
      "treasury_fiscal:operating_cash_balance",
      "nyfed:SOFR",
      "fred:IORB",
    ],
    triggerKeywords: ["rrp", "tga", "liquidity", "sofr", "repo"],
    secondaries: [
      {
        id: "net-liquidity",
        label: "净流动性",
        title: "WALCL - RRP - TGA",
        description: "Fed 资产负债表、RRP 缓冲和 TGA 抽水共同决定系统现金水位。",
        featureKeys: ["fred:WALCL", "fred:RRPONTSYD", "treasury_fiscal:operating_cash_balance"],
        indicatorKeys: ["net_liquidity_usd_millions"],
      },
      {
        id: "funding",
        label: "资金价格",
        title: "SOFR / IORB Funding Price",
        description: "总量没恶化不代表没压力；repo 的边际价格会先动。",
        featureKeys: ["nyfed:SOFR", "fred:IORB", "fred:WRBWFRBL"],
        indicatorKeys: ["sofr_iorb_spread_bps"],
      },
    ],
  },
  {
    id: "economy",
    navLabel: "经济数据",
    title: "增长与通胀数据",
    subtitle: "第一版先展示已接入的增长/通胀代理，明确标出 CPI、就业、ISM 等待接入。",
    userQuestion: "价格信号是否有宏观数据确认，还是只有市场预期在抢跑？",
    icon: CalendarDays,
    chainKeys: ["rates", "cross_asset"],
    panelKeys: ["rates", "cross_asset"],
    indicatorKeys: ["ust_10y_yield_pct"],
    featureKeys: ["fred:T10YIE", "fred:T5YIFR", "fred:DCOILWTICO", "fred:DTWEXBGS"],
    triggerKeywords: ["inflation", "yield", "oil"],
    missingTopics: ["CPI / PCE", "NFP / Unemployment", "ISM / PMI", "Retail sales"],
    secondaries: [
      {
        id: "inflation",
        label: "通胀",
        title: "Inflation Proxy",
        description: "Breakeven、5Y5Y 和油价先作为通胀数据接入前的可交易代理。",
        featureKeys: ["fred:T10YIE", "fred:T5YIFR", "fred:DCOILWTICO"],
        indicatorKeys: [],
      },
      {
        id: "growth",
        label: "增长",
        title: "Growth Proxy",
        description: "当前只用 SPX、美元、曲线代理增长预期；正式宏观 release 需要后续补齐。",
        featureKeys: ["fred:SP500", "fred:DTWEXBGS", "fred:T10Y3M"],
        indicatorKeys: ["sp500_index"],
      },
    ],
  },
  {
    id: "volatility",
    navLabel: "波动率",
    title: "波动率结构",
    subtitle: "VIX 点位只是入口，真正要看曲线、期限结构，以及信用/利率是否共振。",
    userQuestion: "市场是在卖波动的平静期，还是压力还没传到股票？",
    icon: Activity,
    chainKeys: ["volatility", "credit", "rates"],
    panelKeys: ["volatility", "credit", "rates"],
    indicatorKeys: ["vix", "hy_oas_pct"],
    featureKeys: ["fred:VIXCLS", "fred:BAMLH0A0HYM2", "fred:DGS10"],
    triggerKeywords: ["vix", "volatility"],
    missingTopics: ["VIX9D / VIX3M / VIX1Y", "MOVE proxy", "IV vs RV", "GEX proxy"],
    secondaries: [
      {
        id: "equity-vol",
        label: "股票波动",
        title: "Equity Vol",
        description: "VIX 作为第一层，后续补 VIX term structure 判断 contango/backwardation。",
        featureKeys: ["fred:VIXCLS"],
        indicatorKeys: ["vix"],
      },
      {
        id: "cross-vol",
        label: "共振",
        title: "Vol / Credit / Rates",
        description: "VIX 若与 HY OAS 和长端利率共振，风险级别高于单独 VIX 上行。",
        featureKeys: ["fred:VIXCLS", "fred:BAMLH0A0HYM2", "fred:DGS10"],
        indicatorKeys: ["hy_oas_pct", "ust_10y_yield_pct"],
      },
    ],
  },
  {
    id: "credit",
    navLabel: "信用市场",
    title: "信用确认器",
    subtitle: "股票会被权重和期权推动，信用利差更接近融资条件，是风险资产质量检查。",
    userQuestion: "风险资产上涨有没有被 HY/IG 信用确认？",
    icon: Banknote,
    chainKeys: ["credit", "liquidity", "volatility", "cross_asset"],
    panelKeys: ["credit", "liquidity", "volatility"],
    indicatorKeys: ["hy_oas_pct", "ig_oas_pct", "vix"],
    featureKeys: [
      "fred:BAMLH0A0HYM2",
      "fred:BAMLC0A0CM",
      "stooq:hyg.us",
      "stooq:lqd.us",
      "fred:VIXCLS",
    ],
    triggerKeywords: ["hy", "ig", "credit", "oas"],
    missingTopics: ["CDX IG/HY", "single-name CDS", "bank CDS", "private credit proxy"],
    secondaries: [
      {
        id: "oas",
        label: "OAS",
        title: "HY / IG OAS",
        description: "HY 扩大说明低质量资产压力，IG 稳定但 HY 扩大通常是早期分化。",
        featureKeys: ["fred:BAMLH0A0HYM2", "fred:BAMLC0A0CM"],
        indicatorKeys: ["hy_oas_pct", "ig_oas_pct"],
      },
      {
        id: "etf-confirmation",
        label: "ETF 确认",
        title: "HYG / LQD Confirmation",
        description: "用 HYG/LQD 观察信用 ETF 是否确认股票风险偏好。",
        featureKeys: ["stooq:hyg.us", "stooq:lqd.us"],
        indicatorKeys: [],
      },
    ],
  },
];

const MODULE_BY_ID = Object.fromEntries(MODULES.map((module) => [module.id, module])) as Record<
  MacroModuleId,
  MacroModule
>;

const FEATURE_TITLES: Record<string, string> = {
  "cftc:financial_futures:sp500_net_noncommercial": "CFTC SPX net noncommercial",
  "fred:BAMLC0A0CM": "IG OAS",
  "fred:BAMLH0A0HYM2": "HY OAS",
  "fred:DCOILWTICO": "WTI oil",
  "fred:DFEDTARL": "Fed lower bound",
  "fred:DFEDTARU": "Fed upper bound",
  "fred:DFII10": "10Y real yield",
  "fred:DGS10": "10Y Treasury",
  "fred:DGS2": "2Y Treasury",
  "fred:DGS30": "30Y Treasury",
  "fred:DGS5": "5Y Treasury",
  "fred:DTWEXBGS": "Broad dollar",
  "fred:EFFR": "EFFR",
  "fred:IORB": "IORB",
  "fred:RRPONTSYD": "ON RRP",
  "fred:SP500": "S&P 500",
  "fred:T10Y2Y": "10Y-2Y curve",
  "fred:T10Y3M": "10Y-3M curve",
  "fred:T10YIE": "10Y breakeven",
  "fred:T5YIFR": "5Y5Y inflation",
  "fred:VIXCLS": "VIX",
  "fred:WALCL": "Fed assets",
  "fred:WRBWFRBL": "Reserve balances",
  "nyfed:SOFR": "SOFR",
  "stooq:gld.us": "GLD",
  "stooq:hyg.us": "HYG",
  "stooq:iwm.us": "IWM",
  "stooq:lqd.us": "LQD",
  "stooq:qqq.us": "QQQ",
  "stooq:spy.us": "SPY",
  "stooq:tlt.us": "TLT",
  "stooq:uso.us": "USO",
  "treasury_fiscal:operating_cash_balance": "TGA",
};

const CHART_COLORS = ["#8fd6ff", "#f5be62", "#86dfa7", "#ee899a", "#d5c2ff", "#f2a56f"];

export function MacroPage({ token }: { token: string }) {
  const query = useMacroQuery({ token });
  const data = query.data ?? null;
  const snapshot = data?.snapshot ?? null;
  const [activeModule, setActiveModule] = useState<MacroModuleId>("overview");
  const moduleCards = useMemo(() => MODULES.map((module) => moduleSummary(module, data)), [data]);
  const activeRegime = data?.scenario.current_regime ?? snapshot?.regime ?? "pending";

  return (
    <section className="macro-workbench" aria-label="Macro">
      <MacroHero
        activeRegime={activeRegime}
        data={data}
        isFetching={query.isFetching}
        snapshot={snapshot}
      />

      {query.isLoading ? <RemoteState.Loading layout="route" label="loading macro" /> : null}
      {query.isError ? <RemoteState.Error error={query.error} /> : null}
      {!query.isLoading && !query.isError && !snapshot ? (
        <div className="macro-empty-state">
          <AlertTriangle aria-hidden />
          <b>Macro pending</b>
          <span>{data?.data_gaps?.[0] ?? "macro_view_snapshot_missing"}</span>
        </div>
      ) : null}

      {snapshot && data ? (
        <Tabs.Root
          activationMode="manual"
          className="macro-shell"
          value={activeModule}
          onValueChange={(next) => setActiveModule(next as MacroModuleId)}
        >
          <aside className="macro-module-rail" aria-label="Macro modules">
            <Tabs.List className="macro-module-list">
              {moduleCards.map(({ module, score, regime, tone }) => (
                <Tabs.Trigger
                  className={clsx("macro-module-tab", tone)}
                  key={module.id}
                  value={module.id}
                >
                  <module.icon aria-hidden />
                  <span>
                    <b>{module.navLabel}</b>
                    <small>{regime}</small>
                  </span>
                  <em>{scoreLabel(score)}</em>
                </Tabs.Trigger>
              ))}
            </Tabs.List>
          </aside>

          <div className="macro-module-stage">
            {MODULES.map((module) => (
              <Tabs.Content className="macro-module-content" key={module.id} value={module.id}>
                <ModulePage data={data} module={MODULE_BY_ID[module.id]} />
              </Tabs.Content>
            ))}
          </div>
        </Tabs.Root>
      ) : null}
    </section>
  );
}

function MacroHero({
  activeRegime,
  data,
  isFetching,
  snapshot,
}: {
  activeRegime: string;
  data: MacroData | null;
  isFetching: boolean;
  snapshot: MacroSnapshotSummary | null;
}) {
  const scorecard = data?.scorecard ?? {};
  const scenario = data?.scenario ?? {};
  return (
    <header className="macro-hero">
      <div className="macro-hero-copy">
        <span className="macro-eyebrow">US Macro Regime Console</span>
        <h2>Macro</h2>
        <p>
          从用户视角重排宏观链路：先看市场主线，再进入大类资产、利率、美联储、
          流动性、经济数据、波动率与信用市场。
        </p>
      </div>
      <div className="macro-hero-state">
        <div className={clsx("macro-regime-badge", regimeTone(activeRegime))}>
          <small>current regime</small>
          <strong>{activeRegime}</strong>
        </div>
        <div className="macro-hero-kpis">
          <MetricTile label="status" value={snapshot?.status ?? "missing"} />
          <MetricTile
            label="score"
            value={scoreLabel(scorecard.overall_score ?? snapshot?.overall_score)}
          />
          <MetricTile label="confidence" value={percentLabel(scenario.confidence)} />
          <MetricTile label="coverage" value={coverageLabel(scorecard)} />
          <MetricTile label="asof" value={snapshot?.asof_date ?? "-"} />
          <MetricTile label="refresh" value={isFetching ? "updating" : "live"} />
        </div>
      </div>
    </header>
  );
}

function ModulePage({ data, module }: { data: MacroData; module: MacroModule }) {
  const summary = moduleSummary(module, data);
  const triggers = matchingTriggers(data.triggers, module);
  const chainEntries = orderedSubset(data.chain, module.chainKeys, CHAIN_ORDER);
  const panelEntries = orderedSubset(data.panels, module.panelKeys, module.panelKeys);
  const indicators = pickRecord(data.indicators, module.indicatorKeys);
  const features = pickRecord(data.features, module.featureKeys);

  return (
    <article className="macro-module-page">
      <ModuleHeader
        module={module}
        score={summary.score}
        coverage={summary.coverage}
        regime={summary.regime}
        tone={summary.tone}
      />

      <section className="macro-module-read">
        <ReaderCard icon={GitBranch} label="这页回答" value={module.userQuestion} />
        <ReaderCard
          icon={ShieldCheck}
          label="当前判断"
          value={`${summary.regime} · score ${scoreLabel(summary.score)} · coverage ${summary.coverage}`}
        />
        <ReaderCard
          icon={ListChecks}
          label="阅读顺序"
          value="先看图表方向，再看验证/反驳，最后看触发条件和数据缺口。"
        />
      </section>

      {module.id === "overview" ? (
        <OverviewGrid data={data} />
      ) : (
        <Tabs.Root
          activationMode="manual"
          className="macro-secondary-tabs"
          defaultValue={module.secondaries[0]?.id ?? "snapshot"}
        >
          <Tabs.List className="macro-secondary-list" aria-label={`${module.navLabel} sub pages`}>
            {module.secondaries.map((secondary) => (
              <Tabs.Trigger key={secondary.id} value={secondary.id}>
                {secondary.label}
              </Tabs.Trigger>
            ))}
            <Tabs.Trigger value="signals">验证</Tabs.Trigger>
            <Tabs.Trigger value="sources">数据</Tabs.Trigger>
          </Tabs.List>

          {module.secondaries.map((secondary) => (
            <Tabs.Content
              className="macro-secondary-content"
              key={secondary.id}
              value={secondary.id}
            >
              <SecondaryPageView data={data} module={module} secondary={secondary} />
            </Tabs.Content>
          ))}

          <Tabs.Content className="macro-secondary-content" value="signals">
            <SignalsWorkbench
              chainEntries={chainEntries}
              indicators={indicators}
              panels={panelEntries}
              scenario={data.scenario}
              triggers={triggers}
            />
          </Tabs.Content>

          <Tabs.Content className="macro-secondary-content" value="sources">
            <SourceWorkbench
              dataGaps={data.data_gaps}
              features={features}
              indicators={indicators}
              missingTopics={module.missingTopics ?? []}
              scorecard={data.scorecard}
              sourceCoverage={data.source_coverage}
            />
          </Tabs.Content>
        </Tabs.Root>
      )}
    </article>
  );
}

function ModuleHeader({
  coverage,
  module,
  regime,
  score,
  tone,
}: {
  coverage: string;
  module: MacroModule;
  regime: string;
  score: number | null;
  tone: ModuleTone;
}) {
  return (
    <header className="macro-module-head">
      <div>
        <span className="macro-module-icon">
          <module.icon aria-hidden />
        </span>
        <div>
          <span className="macro-eyebrow">{module.navLabel}</span>
          <h3>{module.title}</h3>
          <p>{module.subtitle}</p>
        </div>
      </div>
      <div className={clsx("macro-module-status", tone)}>
        <MetricTile label="regime" value={regime} />
        <MetricTile label="score" value={scoreLabel(score)} />
        <MetricTile label="coverage" value={coverage} />
      </div>
    </header>
  );
}

function OverviewGrid({ data }: { data: MacroData }) {
  const chainEntries = orderedSubset(data.chain, CHAIN_ORDER, CHAIN_ORDER);
  const indicators = pickRecord(data.indicators, MODULE_BY_ID.overview.indicatorKeys);
  const features = pickRecord(data.features, MODULE_BY_ID.overview.featureKeys);
  return (
    <div className="macro-overview-grid">
      <section className="macro-map-panel">
        <SectionTitle icon={GitBranch} title="宏观传导链" />
        <div className="macro-chain-map">
          {chainEntries.map(([key, node], index) => (
            <ChainStep index={index + 1} key={key} node={node} nodeKey={key} />
          ))}
        </div>
      </section>

      <section className="macro-map-panel">
        <SectionTitle icon={MapIcon} title="情景与交易地图" />
        <ScenarioDesk
          scenario={data.scenario}
          scorecard={data.scorecard}
          triggers={data.triggers}
        />
      </section>

      <section className="macro-map-panel wide">
        <SectionTitle icon={LineChart} title="核心指标趋势" />
        <MacroChartGrid features={features} />
      </section>

      <section className="macro-map-panel">
        <SectionTitle icon={ShieldCheck} title="验证矩阵" />
        <DecisionBoard
          indicators={data.indicators}
          scenario={data.scenario}
          triggers={data.triggers}
        />
      </section>

      <section className="macro-map-panel">
        <SectionTitle icon={Database} title="数据覆盖" />
        <SourceWorkbench
          dataGaps={data.data_gaps}
          features={features}
          indicators={indicators}
          missingTopics={[]}
          scorecard={data.scorecard}
          sourceCoverage={data.source_coverage}
        />
      </section>
    </div>
  );
}

function SecondaryPageView({
  data,
  module,
  secondary,
}: {
  data: MacroData;
  module: MacroModule;
  secondary: SecondaryPage;
}) {
  const features = pickRecord(data.features, secondary.featureKeys);
  const indicators = pickRecord(data.indicators, secondary.indicatorKeys);
  const chainEntries = orderedSubset(data.chain, module.chainKeys, CHAIN_ORDER);
  const panels = orderedSubset(data.panels, module.panelKeys, module.panelKeys);
  return (
    <div className="macro-secondary-grid">
      <section className="macro-map-panel wide">
        <SectionTitle icon={LineChart} title={secondary.title} />
        <p className="macro-section-copy">{secondary.description}</p>
        <MacroChartGrid features={features} />
      </section>
      <section className="macro-map-panel">
        <SectionTitle icon={Gauge} title="关键指标" />
        <IndicatorTable indicators={indicators} />
        <FeatureTable features={features} />
      </section>
      <section className="macro-map-panel">
        <SectionTitle icon={GitBranch} title="链路定位" />
        <ChainAndPanelList chainEntries={chainEntries} panels={panels} />
      </section>
    </div>
  );
}

function SignalsWorkbench({
  chainEntries,
  indicators,
  panels,
  scenario,
  triggers,
}: {
  chainEntries: Array<[string, MacroChainNode]>;
  indicators: Record<string, MacroIndicator>;
  panels: Array<[string, MacroPanel]>;
  scenario: MacroScenario;
  triggers: MacroTrigger[];
}) {
  return (
    <div className="macro-secondary-grid">
      <section className="macro-map-panel wide">
        <SectionTitle icon={ShieldCheck} title="验证 / 反驳 / 等待" />
        <DecisionBoard indicators={indicators} scenario={scenario} triggers={triggers} />
      </section>
      <section className="macro-map-panel">
        <SectionTitle icon={CircleDot} title="模块状态" />
        <ChainAndPanelList chainEntries={chainEntries} panels={panels} />
      </section>
      <section className="macro-map-panel">
        <SectionTitle icon={MapIcon} title="交易地图" />
        <TradeMapList entries={scenario.trade_map ?? []} scenario={scenario} triggers={triggers} />
      </section>
    </div>
  );
}

function SourceWorkbench({
  dataGaps,
  features,
  indicators,
  missingTopics,
  scorecard,
  sourceCoverage,
}: {
  dataGaps: string[];
  features: Record<string, MacroFeatureSnapshot>;
  indicators: Record<string, MacroIndicator>;
  missingTopics: string[];
  scorecard: MacroScorecard;
  sourceCoverage: Record<string, number | string | null | undefined>;
}) {
  const gaps = [...dataGaps, ...missingTopics.map((topic) => `not_connected_yet:${topic}`)];
  return (
    <div className="macro-source-layout">
      <div className="macro-source-kpis">
        <MetricTile label="coverage" value={coverageLabel(scorecard)} />
        <MetricTile label="ratio" value={percentLabel(numericOrNull(scorecard.coverage_ratio))} />
        <MetricTile label="latest" value={String(sourceCoverage.latest_observed_at ?? "-")} />
        <MetricTile label="gaps" value={String(scorecard.data_gap_count ?? dataGaps.length)} />
      </div>
      <IndicatorTable indicators={indicators} />
      <FeatureTable features={features} />
      <GapList gaps={gaps} />
    </div>
  );
}

function ReaderCard({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <article className="macro-reader-card">
      <Icon aria-hidden />
      <span>{label}</span>
      <b>{value}</b>
    </article>
  );
}

function SectionTitle({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <div className="macro-section-head">
      <Icon aria-hidden />
      <h4>{title}</h4>
    </div>
  );
}

function MacroChartGrid({ features }: { features: Record<string, MacroFeatureSnapshot> }) {
  const entries = Object.entries(features).slice(0, 6);
  if (entries.length === 0) {
    return <span className="macro-muted">no chartable features</span>;
  }
  return (
    <div className="macro-chart-grid">
      {entries.map(([key, feature], index) => (
        <FeatureChartCard
          color={CHART_COLORS[index % CHART_COLORS.length]}
          feature={feature}
          featureKey={key}
          key={key}
        />
      ))}
    </div>
  );
}

function FeatureChartCard({
  color,
  feature,
  featureKey,
}: {
  color: string;
  feature: MacroFeatureSnapshot;
  featureKey: string;
}) {
  return (
    <article className="macro-chart-card">
      <div className="macro-chart-head">
        <span>
          <b>{featureTitle(featureKey)}</b>
          <small>{feature.latest?.observed_at ?? "pending"}</small>
        </span>
        <strong>
          {valueLabel(feature.latest?.value)}
          {feature.latest?.unit ? <em>{unitShort(feature.latest.unit)}</em> : null}
        </strong>
      </div>
      <FeatureTrendChart color={color} feature={feature} featureKey={featureKey} />
      <div className="macro-chart-meta">
        <MetricTile label="5d" value={deltaLabel(feature.delta?.["5d"])} />
        <MetricTile label="20d" value={deltaLabel(feature.delta?.["20d"])} />
        <MetricTile label="z" value={scoreLabel(feature.zscore?.value)} />
      </div>
    </article>
  );
}

function FeatureTrendChart({
  color,
  feature,
  featureKey,
}: {
  color: string;
  feature: MacroFeatureSnapshot;
  featureKey: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const data = useMemo(() => trendData(feature), [feature]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || data.length < 2) {
      return undefined;
    }
    const chart: IChartApi = createChart(container, {
      autoSize: true,
      height: 140,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8f978a",
      },
      grid: {
        horzLines: { color: "rgba(255,255,255,0.05)" },
        vertLines: { color: "rgba(255,255,255,0.03)" },
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { bottom: 0.18, top: 0.16 },
      },
      timeScale: {
        borderVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        timeVisible: false,
      },
      crosshair: {
        horzLine: { visible: false },
        vertLine: { color: "rgba(255,255,255,0.16)" },
      },
    });
    const series = chart.addSeries(LineSeries, {
      color,
      lineWidth: 2,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    series.setData(data);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [color, data]);

  if (data.length < 2) {
    return (
      <div className="macro-chart-empty">
        <LineChart aria-hidden />
        <span>{featureTitle(featureKey)} latest only</span>
      </div>
    );
  }
  return <div className="macro-chart-canvas" ref={containerRef} />;
}

function ChainStep({
  index,
  node,
  nodeKey,
}: {
  index: number;
  node: MacroChainNode;
  nodeKey: string;
}) {
  const regime = node.regime ?? "data_gap";
  const evidence = node.evidence ?? [];
  const gaps = node.data_gaps ?? [];
  return (
    <article className={clsx("macro-chain-step", regimeTone(regime))}>
      <div className="macro-chain-index">{String(index).padStart(2, "0")}</div>
      <div>
        <span>{nodeTitle(nodeKey)}</span>
        <b>{regime}</b>
        <small>{evidence[0] ?? gaps[0] ?? "awaiting chain evidence"}</small>
      </div>
      <strong>{scoreLabel(node.score)}</strong>
      <ChevronRight aria-hidden />
    </article>
  );
}

function ScenarioDesk({
  scenario,
  scorecard,
  triggers,
}: {
  scenario: MacroScenario;
  scorecard: MacroScorecard;
  triggers: MacroTrigger[];
}) {
  return (
    <div className="macro-scenario-desk">
      <div className="macro-scenario-kpis">
        <MetricTile label="regime" value={scenario.current_regime ?? "scenario pending"} />
        <MetricTile label="confidence" value={percentLabel(scenario.confidence)} />
        <MetricTile label="window" value={scenario.time_window ?? "-"} />
        <MetricTile label="chain avg" value={scoreLabel(scorecard.chain_average)} />
      </div>
      <TriggerList triggers={triggers} />
      <TradeMapList entries={scenario.trade_map ?? []} scenario={scenario} triggers={triggers} />
    </div>
  );
}

function DecisionBoard({
  indicators,
  scenario,
  triggers,
}: {
  indicators: Record<string, MacroIndicator>;
  scenario: MacroScenario;
  triggers: MacroTrigger[];
}) {
  return (
    <div className="macro-decision-grid">
      <SignalColumn
        emptyLabel="no confirmations"
        indicators={indicators}
        items={scenario.confirmations ?? []}
        label="confirms"
        tone="confirm"
      />
      <SignalColumn
        emptyLabel="no contradictions"
        indicators={indicators}
        items={scenario.contradictions ?? []}
        label="contradicts"
        tone="contradict"
      />
      <SignalColumn
        emptyLabel="no watch triggers"
        indicators={indicators}
        items={scenario.watch_triggers ?? []}
        label="watch next"
        tone="watch"
      />
      <SignalColumn
        emptyLabel="no invalidations"
        indicators={indicators}
        items={scenario.invalidations ?? []}
        label="invalidates"
        tone="contradict"
      />
      <div className="macro-signal-column active-trigger-column">
        <span className="macro-column-label">active triggers</span>
        <TriggerList triggers={triggers} />
      </div>
    </div>
  );
}

function SignalColumn({
  emptyLabel,
  indicators,
  items,
  label,
  tone,
}: {
  emptyLabel: string;
  indicators?: Record<string, MacroIndicator>;
  items: ScenarioSignal[];
  label: string;
  tone: "confirm" | "contradict" | "watch";
}) {
  return (
    <div className="macro-signal-column">
      <span className="macro-column-label">{label}</span>
      <SignalList emptyLabel={emptyLabel} indicators={indicators} items={items} tone={tone} />
    </div>
  );
}

function SignalList({
  emptyLabel,
  indicators,
  items,
  tone,
}: {
  emptyLabel: string;
  indicators?: Record<string, MacroIndicator>;
  items: ScenarioSignal[];
  tone: "confirm" | "contradict" | "watch";
}) {
  if (items.length === 0) {
    return <span className="macro-muted">{emptyLabel}</span>;
  }
  return (
    <div className="macro-signal-list">
      {items.map((item, index) => {
        const code = item.code || `signal_${index + 1}`;
        return (
          <article className={clsx("macro-signal-item", tone)} key={`${code}-${index}`}>
            <b>{code}</b>
            <small>{signalDetail(item)}</small>
            <IndicatorTokenLine indicators={indicators} keys={item.indicator_keys ?? []} />
          </article>
        );
      })}
    </div>
  );
}

function TradeMapList({
  entries,
  scenario,
  triggers,
}: {
  entries: TradeMapEntry[];
  scenario: MacroScenario;
  triggers: MacroTrigger[];
}) {
  if (entries.length === 0) {
    return <span className="macro-muted">no trade map</span>;
  }
  const tokenStatus = tradeTokenStatuses(scenario, triggers);
  return (
    <div className="macro-trade-map-list">
      {entries.map((entry, index) => {
        const expression = entry.expression || `trade_map_${index + 1}`;
        return (
          <article className="macro-trade-map-item" key={`${expression}-${index}`}>
            <div>
              <b>{expression}</b>
              <span>{entry.time_window ?? "-"}</span>
            </div>
            <TokenLine
              label="confirms"
              statusByToken={tokenStatus}
              tokens={entry.confirms_on ?? []}
            />
            <TokenLine
              label="invalidates"
              statusByToken={tokenStatus}
              tokens={entry.invalidates_on ?? []}
            />
          </article>
        );
      })}
    </div>
  );
}

function ChainAndPanelList({
  chainEntries,
  panels,
}: {
  chainEntries: Array<[string, MacroChainNode]>;
  panels: Array<[string, MacroPanel]>;
}) {
  return (
    <div className="macro-status-list">
      {chainEntries.map(([key, node]) => (
        <StatusRow
          detail={(node.evidence ?? node.data_gaps ?? [])[0] ?? "awaiting evidence"}
          key={`chain:${key}`}
          label={nodeTitle(key)}
          score={node.score}
          status={node.regime ?? "pending"}
        />
      ))}
      {panels.map(([key, panel]) => (
        <StatusRow
          detail={
            (panel.evidence.length ? panel.evidence : panel.data_gaps)[0] ?? "awaiting evidence"
          }
          key={`panel:${key}`}
          label={panelTitle(key)}
          score={panel.score}
          status={panel.regime}
        />
      ))}
      {chainEntries.length === 0 && panels.length === 0 ? (
        <span className="macro-muted">no module state</span>
      ) : null}
    </div>
  );
}

function StatusRow({
  detail,
  label,
  score,
  status,
}: {
  detail: string;
  label: string;
  score?: number | null;
  status: string;
}) {
  return (
    <article className={clsx("macro-status-row", regimeTone(status))}>
      <span>
        <b>{label}</b>
        <small>{detail}</small>
      </span>
      <em>{status}</em>
      <strong>{scoreLabel(score)}</strong>
    </article>
  );
}

function IndicatorTable({ indicators }: { indicators: Record<string, MacroIndicator> }) {
  const entries = Object.entries(indicators);
  if (entries.length === 0) {
    return <span className="macro-muted">no indicators for this page</span>;
  }
  return (
    <div className="macro-indicator-table">
      {entries.map(([key, indicator]) => (
        <article className="macro-indicator-row" key={key}>
          <span>
            <b>{indicator.label || key}</b>
            <small>{indicator.series_keys?.join(" / ") || key}</small>
          </span>
          <strong>
            {valueLabel(indicator.value)}
            {indicator.unit ? <em>{unitShort(indicator.unit)}</em> : null}
          </strong>
          <small>{indicator.observed_at ?? "-"}</small>
        </article>
      ))}
    </div>
  );
}

function FeatureTable({ features }: { features: Record<string, MacroFeatureSnapshot> }) {
  const entries = Object.entries(features);
  if (entries.length === 0) {
    return <span className="macro-muted">no feature snapshots for this page</span>;
  }
  return (
    <div className="macro-feature-table">
      {entries.map(([key, feature]) => (
        <article className="macro-feature-row" key={key}>
          <span>
            <b>{featureTitle(key)}</b>
            <small>{key}</small>
          </span>
          <strong>
            {valueLabel(feature.latest?.value)}
            {feature.latest?.unit ? <em>{unitShort(feature.latest.unit)}</em> : null}
          </strong>
          <span className="macro-feature-deltas">
            <small>5d {deltaLabel(feature.delta?.["5d"])}</small>
            <small>20d {deltaLabel(feature.delta?.["20d"])}</small>
            <small>z {scoreLabel(feature.zscore?.value)}</small>
          </span>
        </article>
      ))}
    </div>
  );
}

function TriggerList({ triggers }: { triggers: MacroTrigger[] }) {
  if (triggers.length === 0) {
    return <span className="macro-muted">no active triggers</span>;
  }
  return (
    <div className="macro-chip-list">
      {triggers.map((trigger) => (
        <span key={trigger.code} className="macro-chip hot">
          <b>{trigger.code}</b>
          {trigger.description ? <small>{trigger.description}</small> : null}
        </span>
      ))}
    </div>
  );
}

function GapList({ gaps }: { gaps: string[] }) {
  if (gaps.length === 0) {
    return <span className="macro-muted">coverage complete</span>;
  }
  return (
    <div className="macro-chip-list">
      {gaps.slice(0, 24).map((gap) => (
        <span key={gap} className="macro-chip gap">
          {gap}
        </span>
      ))}
      {gaps.length > 24 ? <span className="macro-muted">+{gaps.length - 24} more gaps</span> : null}
    </div>
  );
}

function TokenLine({
  label,
  statusByToken,
  tokens,
}: {
  label: string;
  statusByToken: Record<string, string>;
  tokens: string[];
}) {
  if (tokens.length === 0) {
    return null;
  }
  return (
    <div className="macro-token-line">
      <span>{label}</span>
      <div>
        {tokens.map((token) => (
          <small className={statusByToken[token] ?? "unresolved"} key={token}>
            {token}
          </small>
        ))}
      </div>
    </div>
  );
}

function IndicatorTokenLine({
  indicators,
  keys,
}: {
  indicators?: Record<string, MacroIndicator>;
  keys: string[];
}) {
  if (!indicators || keys.length === 0) {
    return null;
  }
  return (
    <div className="macro-indicator-token-line">
      {keys.map((key) => {
        const indicator = indicators[key];
        return (
          <small key={key}>
            {key}: {indicator ? valueLabel(indicator.value) : "pending"}
            {indicator?.unit ? ` ${unitShort(indicator.unit)}` : ""}
          </small>
        );
      })}
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <span className="macro-metric-tile">
      <small>{label}</small>
      <b>{value}</b>
    </span>
  );
}

function moduleSummary(module: MacroModule, data: MacroData | null) {
  if (!data) {
    return {
      coverage: "-",
      module,
      regime: "pending",
      score: null,
      tone: "gap" as ModuleTone,
    };
  }
  const chain = module.chainKeys.map((key) => data.chain[key]).filter(Boolean);
  const panels = module.panelKeys.map((key) => data.panels[key]).filter(Boolean);
  const scoreValues = [...chain, ...panels]
    .map((entry) => entry.score)
    .filter((value): value is number => typeof value === "number");
  const score = scoreValues.length
    ? scoreValues.reduce((total, value) => total + value, 0) / scoreValues.length
    : null;
  const primaryRegime =
    chain.find((entry) => entry.regime)?.regime ??
    panels.find((entry) => entry.regime)?.regime ??
    data.scorecard.chain_regimes?.[module.chainKeys[0] ?? ""] ??
    data.scenario.current_regime ??
    "pending";
  const featureCount = module.featureKeys.length + module.indicatorKeys.length;
  const presentCount =
    module.featureKeys.filter((key) => data.features[key]).length +
    module.indicatorKeys.filter((key) => data.indicators[key]).length;
  return {
    coverage: featureCount ? `${presentCount}/${featureCount}` : coverageLabel(data.scorecard),
    module,
    regime: String(primaryRegime),
    score,
    tone: regimeTone(String(primaryRegime)),
  };
}

function matchingTriggers(triggers: MacroTrigger[], module: MacroModule): MacroTrigger[] {
  if (module.triggerKeywords.length === 0) {
    return triggers;
  }
  return triggers.filter((trigger) => {
    const haystack = `${trigger.code} ${trigger.description ?? ""}`.toLowerCase();
    return module.triggerKeywords.some((keyword) => haystack.includes(keyword));
  });
}

function orderedSubset<T>(
  record: Record<string, T>,
  keys: string[],
  fallbackOrder: string[],
): Array<[string, T]> {
  const seen = new Set<string>();
  const ordered: Array<[string, T]> = [];
  for (const key of keys) {
    if (record[key]) {
      seen.add(key);
      ordered.push([key, record[key]]);
    }
  }
  for (const key of fallbackOrder) {
    if (!seen.has(key) && record[key]) {
      seen.add(key);
      ordered.push([key, record[key]]);
    }
  }
  return ordered;
}

function pickRecord<T>(record: Record<string, T>, keys: string[]): Record<string, T> {
  const picked: Record<string, T> = {};
  for (const key of keys) {
    if (record[key]) {
      picked[key] = record[key];
    }
  }
  return picked;
}

function trendData(feature: MacroFeatureSnapshot): LineData[] {
  const latestValue = numericOrNull(feature.latest?.value);
  const observedAt = feature.latest?.observed_at;
  if (latestValue === null || !observedAt) {
    return [];
  }
  const points: LineData[] = [];
  const windows = [
    { key: "60d", days: 60 },
    { key: "20d", days: 20 },
    { key: "5d", days: 5 },
  ];
  for (const window of windows) {
    const delta = numericOrNull(feature.delta?.[window.key]);
    if (delta !== null) {
      points.push({
        time: shiftDate(observedAt, -window.days),
        value: latestValue - delta,
      });
    }
  }
  points.push({ time: observedAt, value: latestValue });
  const deduped = new globalThis.Map<string, LineData>();
  for (const point of points) {
    deduped.set(String(point.time), point);
  }
  return Array.from(deduped.values()).sort((a, b) => String(a.time).localeCompare(String(b.time)));
}

function shiftDate(dateText: string, days: number): string {
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function featureTitle(key: string): string {
  return FEATURE_TITLES[key] ?? key;
}

function nodeTitle(key: string): string {
  const titles: Record<string, string> = {
    credit: "Credit",
    cross_asset: "Asset Confirmation",
    fed_corridor: "Fed Corridor",
    liquidity: "Onshore Funding",
    positioning: "Positioning",
    rates: "Rates / Inflation",
    volatility: "Vol Structure",
  };
  return titles[key] ?? key;
}

function panelTitle(key: string): string {
  const titles: Record<string, string> = {
    credit: "Credit",
    cross_asset: "Cross-Asset",
    liquidity: "Liquidity",
    rates: "Rates",
    volatility: "Volatility",
  };
  return titles[key] ?? key;
}

function signalDetail(item: ScenarioSignal): string {
  if (item.description) {
    return item.description;
  }
  if (item.node || item.regime) {
    return [item.node, item.regime].filter(Boolean).join(" / ");
  }
  return item.evidence?.[0] ?? "";
}

function tradeTokenStatuses(
  scenario: MacroScenario,
  triggers: MacroTrigger[],
): Record<string, string> {
  const statusByToken: Record<string, string> = {};
  for (const trigger of triggers) {
    statusByToken[trigger.code] = "active";
  }
  for (const signal of scenario.confirmations ?? []) {
    if (signal.code) {
      statusByToken[signal.code] = "active";
    }
  }
  for (const signal of scenario.watch_triggers ?? []) {
    if (signal.code) {
      statusByToken[signal.code] = "watch";
    }
  }
  for (const signal of scenario.invalidations ?? []) {
    if (signal.code) {
      statusByToken[signal.code] = "invalidate";
    }
  }
  return statusByToken;
}

function regimeTone(regime: string): ModuleTone {
  if (regime.includes("stress") || regime.includes("pressure") || regime.includes("tightening")) {
    return "stress";
  }
  if (regime.includes("risk_on") || regime.includes("carry") || regime.includes("orderly")) {
    return "constructive";
  }
  if (regime.includes("gap") || regime.includes("pending") || regime.includes("missing")) {
    return "gap";
  }
  return "neutral";
}

function coverageLabel(scorecard: MacroScorecard): string {
  if (scorecard.observed_series_count !== null && scorecard.observed_series_count !== undefined) {
    if (scorecard.required_series_count !== null && scorecard.required_series_count !== undefined) {
      return `${scorecard.observed_series_count}/${scorecard.required_series_count}`;
    }
    return String(scorecard.observed_series_count);
  }
  return percentLabel(scorecard.coverage_ratio);
}

function percentLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

function scoreLabel(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return value.toFixed(2).replace(/\.?0+$/, "");
  }
  return String(value);
}

function valueLabel(value: number | string | null | undefined): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function deltaLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2).replace(/\.?0+$/, "")}`;
}

function numericOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function unitShort(unit: string): string {
  const units: Record<string, string> = {
    billions_usd: "$B",
    bps: "bp",
    index: "idx",
    millions_usd: "$M",
    percent: "%",
    percentage_points: "ppt",
    price: "$",
    usd_per_barrel: "$/bbl",
  };
  return units[unit] ?? unit;
}
