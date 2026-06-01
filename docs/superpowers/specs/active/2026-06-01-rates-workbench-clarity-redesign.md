# Spec — Rates Workbench Clarity Redesign

**Status**: Approved
**Date**: 2026-06-01
**Owner**: Codex
**Related**:
- Current benchmark comparison: `https://timsun.net/rates/fed-funds`, `https://timsun.net/rates/yield-curve`, `https://timsun.net/rates/auctions`, `https://timsun.net/rates/real-rates`, `https://timsun.net/rates/expectations`
- Local product routes: `/macro/rates/fed-funds`, `/macro/rates/yield-curve`, `/macro/rates/auctions`, `/macro/rates/real-rates`, `/macro/rates/expectations`
- Existing macro redesign spec: `docs/superpowers/specs/active/2026-05-22-macro-workbench-benchmark-redesign-cn.md`
- Frontend architecture guardrails: `docs/FRONTEND.md`
- Macro Intel architecture: `src/parallax/domains/macro_intel/ARCHITECTURE.md`

## Background

The Parallax Macro route now has a real module contract, but the rates pages still read like an internal projection audit instead of a rates workbench.

Grounding in current code and docs:

- Macro facts and read models are owned by Macro Intel. `macro_observations`, `macro_observation_series_rows`, and `macro_view_snapshots` are documented as the durable fact and rebuildable projection path in `src/parallax/domains/macro_intel/ARCHITECTURE.md:11`.
- API handlers and frontend pages must not call FRED, NY Fed, Treasury, Cboe, CFTC, crypto providers, or `macrodata` directly. The same boundary is documented in `src/parallax/domains/macro_intel/ARCHITECTURE.md:3`.
- `/api/macro/modules/{module_id}` builds a display-ready `macro_module_view_v3` response from the latest macro snapshot plus module observations in `src/parallax/app/surfaces/api/routes_macro.py:109`.
- `build_macro_module_view` assembles `snapshot`, `tiles`, `primary_chart`, `tables`, `module_read`, `module_evidence`, `transmission`, `data_health`, `provenance`, and `related_routes` in `src/parallax/domains/macro_intel/services/macro_module_views.py:22`.
- Rates module configuration already knows the five target pages and their required or optional concepts in `src/parallax/domains/macro_intel/services/macro_module_catalog.py:179`.
- Fed funds requires target bounds, EFFR, and IORB, with SOFR and SOFR 30D as optional supporting concepts in `src/parallax/domains/macro_intel/services/macro_module_catalog.py:179`.
- Yield curve expects 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, and 30Y for the curve, plus 10Y-2Y and 10Y-3M spreads in `src/parallax/domains/macro_intel/services/macro_module_catalog.py:210`.
- Treasury auctions are currently represented by yield-curve proxy concepts and explicit gaps for auction calendar and results in `src/parallax/domains/macro_intel/services/macro_module_catalog.py:253`.
- Real rates already have a focused TIPS and breakeven concept set in `src/parallax/domains/macro_intel/services/macro_module_catalog.py:271`.
- Policy expectations currently use short-end Treasury yields and target bounds as proxies, with explicit gaps for Fed funds futures and FOMC probability feed in `src/parallax/domains/macro_intel/services/macro_module_catalog.py:285`.
- Gap remediation already names the correct upstream expansions for Fed funds futures, Treasury auctions, and related missing sources in `src/parallax/domains/macro_intel/services/macro_gap_payloads.py:142`.
- The frontend renders all leaf module routes through one generic `MacroLeafModulePage` in `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx:27`.
- That generic page renders metric strip, market board, extra tables, read panel, transmission panel, evidence panel, data source table, and data health panel in a fixed order in `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx:35`.
- The current "module judgment" panel is generic and lists `regime_label`, `confidence_label`, `crypto_read`, `token_impact`, `data_note`, and `methodology_note` as audit-like rows in `web/src/features/macro/ui/primitives/MacroReadPanel.tsx:7`.
- The market board chooses `MacroYieldCurveChart` whenever the chart id includes `curve` or the module is `rates/yield-curve` in `web/src/features/macro/ui/pages/MacroMarketBoard.tsx:75`.
- `useMacroPrimarySeries` deliberately skips `/api/macro/series` for charts whose id contains `curve`, so yield-curve rendering depends entirely on inline chart values in `web/src/features/macro/ui/pages/MacroPrimarySeries.ts:13`.
- `buildMacroYieldCurveModel` currently derives curve points from `series.latest`, not from the final point in `series.points`, in `web/src/features/macro/model/macroChartModel.ts:138`.
- `MacroDataTable` already uses TanStack table sorting, but the same generic table surface is used for product data and availability diagnostics in `web/src/features/macro/ui/tables/MacroDataTable.tsx:22`.
- `docs/FRONTEND.md` requires macro pages to render deterministic state from `/api/macro`, `/api/macro/modules/{module_id}`, and module-adjacent endpoints, and forbids frontend recomputation of macro scoring or module reads.

Runtime observation on 2026-06-01 against `http://localhost:8765`:

- `uv run parallax config` reported operator-owned paths under `/Users/qinghuan/.parallax/`, so the local comparison used real runtime config rather than repo fixtures.
- Macrodata is enabled, but `FINANCE_FRED_API_KEY` is not configured. This should surface as source coverage and data quality state, not be hidden.
- `uv run parallax macro status` reported `status=partial`, `concept_count=36`, `history_ready=false`, and many required history concepts below threshold.
- Fed funds has target upper/lower, EFFR, IORB, and SOFR available.
- Yield curve has 2Y, 5Y, 10Y, 30Y, 10Y-2Y, and 10Y-3M available, but is missing several tenors. The current local page still renders the primary curve as empty, which is a frontend rendering defect rather than a full data-source outage.
- Auctions and policy expectations are intentionally proxy-only today because Treasury auction facts and Fed funds futures/FOMC probabilities are not yet imported.
- Real rates has enough current concepts to support a focused page, but the generic layout hides the simple nominal-real-breakeven story.

Benchmark observation on 2026-06-01:

- The benchmark rates pages answer a specific trader question first, then show charts and source details.
- The benchmark yield curve page explains curve shape, key spreads, current versus prior curves, global long-rate context, and nominal versus real versus breakeven decomposition.
- The benchmark auction page shows future auction calendar, recent results, bid-to-cover, indirect bidder share, and tail.
- The benchmark expectations page shows target range, next FOMC date, implied probabilities, ZQ inputs, and data explanation.

The benchmark is useful as a product-quality reference. It is not a dependency and must not be copied mechanically.

## Problem

The current local rates pages are technically honest but cognitively upside down: the first user impression is status, version, partial coverage, generic metric cards, generic tables, evidence buckets, and global gap counts. A trader or operator looking at rates wants to know what the curve, corridor, auctions, real rates, and policy path are saying now. They can tolerate partial data if the page clearly separates "market read", "available facts", "proxy caveat", and "data gaps". Today those layers are mixed together, so the page feels like an audit report rather than a workbench.

## First Principles

1. **A rates workbench answers the decision question first.** Each page must lead with a concise market read, the handful of facts behind it, and the most relevant visualization. Audit details are still available, but they are not the primary experience.
2. **PostgreSQL projections remain the business truth.** Rates pages consume `macro_module_view_v3`, `/api/macro/series`, and future module-adjacent read models. They do not call providers from React or request handlers, and they do not infer macro scores locally.
3. **Partial data is a product state, not an excuse for unreadable UI.** A page may be `partial`, `proxy`, or `missing`, but the UI must say which conclusion is supported, which widgets are proxy-only, and which missing sources prevent stronger conclusions.
4. **Diagnostics are secondary but still inspectable.** Provenance, source coverage, missing concept lists, gap codes, and projection health must remain accessible for operators, but the default hierarchy should favor market comprehension.
5. **Rates pages need domain-specific components.** Generic module pages are acceptable for low-traffic or early macro modules, but rates pages are first-class product surfaces and need chart, table, and copy patterns designed for rates.

## Goals

- G1. Replace the generic rates leaf-page experience with a domain-specific rates workbench grammar that makes the top of each page understandable within one viewport at desktop width.
- G2. Ensure every rates subpage starts with a plain-language answer to its page question, supported by values, dates, and source status from backend projections.
- G3. Move availability tables, module evidence buckets, global gaps, and raw provenance out of the primary scan path while keeping them visible in a diagnostics section.
- G4. Fix the yield-curve rendering contract so available tenors draw a curve whenever at least two valid tenor points exist.
- G5. Clearly distinguish real facts, proxy facts, and missing upstream data for auctions and policy expectations.
- G6. Preserve Macro Intel boundaries: no provider calls in frontend or API handlers, no frontend scoring, no hidden stale data.
- G7. Preserve responsive, accessible, harness-compliant frontend behavior across desktop, tablet, and mobile.
- G8. Keep the spec focused on rates pages only. This work may reuse existing macro primitives, but it does not redesign all Macro modules.

## Non-Goals

- N1. Do not scrape, embed, or depend on `timsun.net`.
- N2. Do not add direct FRED, Treasury, CME, Yahoo, NY Fed, or macrodata calls inside React components or FastAPI request handlers.
- N3. Do not claim auctions or policy expectations are "ready" until their required upstream facts exist.
- N4. Do not make frontend code compute rate-regime scores, Fed probabilities, confidence values, or trade recommendations from raw series.
- N5. Do not redesign Token Radar, Stocks, News, Watchlist, Ops, or the global cockpit shell.
- N6. Do not turn the rates pages into a marketing page. The target is a dense, operational workbench.
- N7. Do not remove provenance, data health, or source gaps. Reposition and summarize them.

## Target Architecture

Rates should become a first-class workbench inside the existing Macro route family. It still receives deterministic module data from Macro Intel, but the frontend renders rates pages with rates-specific layout and language.

### Page Family

The target page family is:

| Route | Target role | Primary user question |
|-------|-------------|-----------------------|
| `/macro/rates` | Rates overview or rates section hub | What is the rates complex saying across policy, curve, real rates, auctions, and expectations? |
| `/macro/rates/fed-funds` | Policy corridor | Is the Fed corridor stable, and is overnight funding pressuring the target range? |
| `/macro/rates/yield-curve` | Curve shape | Is the curve pricing recession pressure, policy easing, or term-premium supply pressure? |
| `/macro/rates/auctions` | Treasury supply and demand | Is auction supply or weak demand pressuring duration? |
| `/macro/rates/real-rates` | Real-rate pressure | Are real yields tightening financial conditions or are breakevens driving nominal rates? |
| `/macro/rates/expectations` | Policy path | Is the market repricing cuts, unchanged policy, or hikes? |

If `/macro/rates` remains a redirect in the first implementation slice, the child pages still need a rates-local navigation bar and summary strip so the user understands the five-page workbench. The evolution path should eventually make `/macro/rates` a real overview page.

### Workbench Grammar

Every rates page should use the same product hierarchy:

1. **Decision header**
   - Breadcrumb and compact rates subnav.
   - Page title and one-sentence question.
   - Status shown as small data-quality metadata, not as the visual headline.
   - As-of date and source state.

2. **Market read**
   - One concise headline sentence.
   - A short "why it matters" sentence.
   - Three to five supporting facts with values, dates, and sources.
   - Clear labels for `ready`, `partial`, `proxy`, `stale`, or `missing`.

3. **Primary visual**
   - One domain-specific chart, immediately visible.
   - A readable legend and latest values.
   - Missing series summary in prose, not raw concept codes.
   - Empty state that says what is missing and what still can be read.

4. **Decision support**
   - Confirming signals, contradicting signals, watch triggers, invalidation triggers.
   - These are backed by `module_read` and `module_evidence`, but rendered as product copy rather than evidence buckets.

5. **Detail table**
   - The most useful domain table for the page.
   - Sortable where useful.
   - Availability/proxy notes separated from primary data tables.

6. **Diagnostics**
   - Data availability table.
   - Provenance.
   - Module data health.
   - Global gaps as collapsed or visually subordinate reference state.

The first viewport should never be dominated by "macro_module_view_v3", global gap counts, missing concept lists, or generic evidence buckets.

### Page-Specific Requirements

#### Fed Funds And Corridor

Primary read:

- Corridor range: target lower and target upper.
- EFFR relative to corridor.
- IORB and SOFR relative to target upper.
- Whether funding is normal, tight but contained, or outside the corridor.
- FOMC calendar caveat if next-meeting data is absent.

Primary visual:

- Corridor band chart with target lower/upper as band boundaries.
- Lines for EFFR, IORB, SOFR, and SOFR 30D when available.
- Latest-value chips attached to the right side or in a compact legend.

Detail table:

- Latest value, 20-day change, distance to upper/lower bound when applicable, observed date, source.

Diagnostics:

- Missing SOFR 30D should be a chart caveat, not the headline.
- Missing FOMC calendar should appear as a future integration gap and, if shown in the read, as "meeting-calendar unavailable".

#### Yield Curve

Primary read:

- Current curve shape using available tenors.
- 2s10s and 3m10s interpretation when those spreads exist.
- Short-end, belly, and long-end movement over a selected window when enough series exist.
- Plain caveat when a full 1M to 30Y curve is unavailable.

Primary visual:

- Current yield curve across available tenors.
- It must draw when at least two tenor points exist.
- Missing tenors should be shown as unavailable markers or a compact "missing: 1M, 3M, 6M..." note.
- Later expansion may add 1w/1m/3m comparison curves, but the current curve must work first.

Detail table:

- Tenor, latest yield, window change, observed date, source, status.
- Spread table for 10Y-2Y, 10Y-3M, and other available spreads.

Diagnostics:

- Missing optional tenors should not hide available 2Y/5Y/10Y/30Y.

#### Treasury Auctions

Primary read:

- If official auction results are absent, the page must explicitly say it is a Treasury supply proxy page.
- If official auction results exist, the read should summarize recent demand through bid-to-cover, indirect bidder share, and tail.
- Future supply calendar should be the main object once calendar facts exist.

Primary visual:

- Current phase: duration pressure proxy using 2Y/7Y/10Y/30Y or whatever available tenors support.
- Future phase: auction calendar timeline and recent tail/bid-to-cover chart.

Detail table:

- Current phase: available yield proxy table with clear proxy labeling.
- Future phase: upcoming auctions and recent auction results.

Diagnostics:

- Missing auction calendar and auction results are source gaps, not UI bugs.

#### Real Rates

Primary read:

- Whether real yields are tightening financial conditions.
- Whether nominal rate moves are driven more by real yield or breakeven inflation.
- Crypto/long-duration relevance should be stated only if backend read data supports it.

Primary visual:

- Nominal 10Y, real 10Y, and 10Y breakeven relationship when all are available.
- If nominal 10Y is not part of the module payload, the page should still show real 10Y versus breakeven and explain the missing nominal leg.

Detail table:

- Real yield, breakeven, 5y5y forward, latest, change, source, observed date.

Diagnostics:

- Missing 5Y or 30Y TIPS should not block the 10Y real-rate read.

#### Policy Expectations

Primary read:

- If Fed funds futures/FOMC probabilities are absent, the page must say it is using short-end rate proxies.
- When futures/probability facts exist, the page should summarize next meeting, implied path, cut/hold/hike distribution, and market expectation label.

Primary visual:

- Current phase: proxy path from 3M/1Y/2Y and target range.
- Future phase: FOMC meeting probability matrix and implied policy path chart.

Detail table:

- Current phase: short-end proxy table with target range.
- Future phase: meeting-date probability table plus underlying futures input table.

Diagnostics:

- Missing `fed_funds_futures_missing` and `fomc_probability_feed_missing` should be visible but not confused with a frontend failure.

### Product Copy Rules

Rates pages should use product language, not implementation language:

- Use "数据不足以生成正式降息概率" instead of raw "fomc_probability_feed_missing" in primary UI.
- Use "当前为代理页面" instead of "部分可用" as the only explanatory text when an entire page lacks its official feed.
- Use "可读结论" and "阻碍更强结论的数据缺口" as separate concepts.
- Never show raw concept keys such as `rates:dgs1mo` in primary UI.
- Never show projection version, source snapshot id, or global gap count above the diagnostic section.

### Visual Design Direction

The target aesthetic is a quiet trading desk, not a generic analytics dashboard:

- Compact but legible.
- Chart-first where the chart carries the decision.
- Small status badges, not big status panels.
- Cards only for repeated metrics or bounded panels.
- No nested cards.
- No marketing hero, decorative backgrounds, or explanatory onboarding text.
- Strong table density with stable column widths.
- Clear color semantics for policy band, risk-on/risk-off, real yield, breakeven, missing/proxy status.

### Detailed Page Design

The rates workbench should feel like an operator screen that can be scanned in under thirty seconds. The page must not explain how to use itself. It should simply put the most important rates read in the strongest visual position and let diagnostics fall behind it.

#### Shared Layout Anatomy

Desktop layout uses a single page surface inside the existing Macro shell:

```text
+-----------------------------------------------------------------------+
| Breadcrumb / Rates subnav / as-of / compact data state                |
| H1 + page question                                                     |
+-------------------------------+---------------------------------------+
| Market read                   | Primary facts strip                   |
| headline, 1-2 lines why       | 3-5 dense fact tiles                  |
| support / caveat chips        | value, change, date, source           |
+-------------------------------+---------------------------------------+
| Primary visual                                                        |
| chart, legend, latest labels, partial/proxy note                      |
+--------------------------------------+--------------------------------+
| Decision support                     | Detail table                   |
| confirmations / contradictions       | domain-specific table          |
| watch / invalidation triggers        |                                |
+--------------------------------------+--------------------------------+
| Diagnostics                                                           |
| source availability, provenance, module health, global gap reference  |
+-----------------------------------------------------------------------+
```

The top row should answer four questions without scrolling:

- What is this page answering?
- What is the current read?
- Which facts support that read?
- Is this a full, partial, proxy, stale, or missing read?

The diagnostics section should be visually present but subordinate. It may use collapsible disclosure or a low-emphasis panel, but it must remain reachable without hidden keyboard traps or route changes.

#### Shared Components

The design assumes these semantic components. They may reuse existing primitives, but their user-facing behavior should match the definitions below.

| Component | Purpose | Content | Interaction |
|-----------|---------|---------|-------------|
| Rates Subnav | Keep the five rates pages visible as one workbench. | Fed funds, curve, auctions, real rates, expectations. | Segmented route links, active state, no horizontal body overflow. |
| Market Read | Primary product answer. | Headline, short explanation, support chips, caveat chip. | No sorting or expansion in the first viewport. |
| Fact Tile | Dense supporting fact. | Short label, value, unit, change, observed date, source. | Optional hover/focus tooltip for longer source note. |
| Primary Visual | The page's main mental model. | Domain chart plus latest labels and missing/proxy note. | Range selector only where real history exists. |
| Signal Rail | Decision support. | Confirmations, contradictions, watch triggers, invalidators. | Compact groups with counts; details can expand inline. |
| Detail Table | Product data table. | Domain fields, not availability rows. | Sort where meaningful, sticky header where dense. |
| Diagnostics Panel | Operator inspectability. | Availability, provenance, module health, global gap count. | Collapsible or secondary tab; default state does not dominate page. |

#### Shared Status Language

Use the same status vocabulary across all rates pages:

| Status | User-facing meaning | Visual treatment |
|--------|---------------------|------------------|
| Ready | Required facts exist and the page can make its intended read. | Small positive badge, not celebratory. |
| Partial | Core read exists but some supporting series are missing. | Amber or neutral badge plus "what is missing". |
| Proxy | Official feed is missing and the page is using market proxies. | Distinct proxy badge near the read and chart title. |
| Stale | Facts exist but are outside freshness threshold. | Stale badge plus observed date emphasis. |
| Missing | Required facts are absent. | Empty state with next data requirement and diagnostics link. |

The UI should never show `partial` alone as an explanation. It must state what is still readable, for example: "曲线可用：2Y/5Y/10Y/30Y；短端 1M/3M/6M 缺失。"

#### Shared Chart Behavior

Charts must be operational, not decorative:

- The chart title names the market object, not the implementation object.
- Latest values appear in a legend or right-edge labels.
- Units are visible on values and axes where the library supports them.
- Missing series are summarized in a compact note below the title or legend.
- A chart with enough facts draws even when optional series are absent.
- Empty states describe the absent market object, not generic "暂无数据".
- Range controls appear only for time-series history; current curve and probability matrix views do not need a fake time range selector.

#### Shared Table Behavior

Primary product tables should not be mixed with availability/proxy tables:

- Product tables answer market questions: latest yield, change, distance to corridor, tail, bid-to-cover, probability, source.
- Availability tables answer operator questions: imported/missing, history coverage, source notes.
- Primary tables appear near the relevant chart.
- Availability tables appear in diagnostics.
- Tables use concise headers and stable widths. Long notes wrap in diagnostics only, not primary data rows.

#### Desktop Composition

At desktop width, each child page should use a two-column composition above the fold:

- Left column: market read.
- Right column: primary fact strip or compact fact grid.
- Full-width chart underneath.
- Decision support and table split into two columns below the chart.
- Diagnostics full-width at the bottom.

The page should not stack five independent cards before the chart. The chart is the working surface, so it must arrive early.

#### Tablet And Mobile Composition

Tablet:

- Rates subnav becomes horizontally scrollable inside its own container or wraps into two rows.
- Market read appears above fact tiles.
- Primary visual remains above detail table.
- Diagnostics are reachable after decision support.

Mobile:

- H1 and market read appear first.
- Fact tiles become a two-column compact grid when width permits, otherwise a single-column list.
- The primary chart keeps a stable minimum height and never overlaps labels.
- Dense tables use bounded horizontal scrolling inside their frames.
- Diagnostics are collapsed by default only if the collapse control is keyboard and screen-reader reachable.

#### Rates Overview Page

`/macro/rates` should eventually become a real overview rather than only a redirect. Its job is not to duplicate all five child pages; it should answer whether the rates complex is broadly easing, tightening, steepening, supply-stressed, or policy-path repricing.

First viewport:

```text
Rates Workbench
Question: Are rates helping or tightening risk appetite?

[Market read]
Policy corridor contained; curve partial but long-end pressure visible; auctions and policy probabilities are proxy-only.

[Five-lane summary strip]
Fed corridor | Curve | Auctions | Real rates | Expectations
ready/partial/proxy badges, one value, one interpretation each

[Cross-rates visual]
2Y, 10Y, real 10Y, breakeven, target upper, SOFR latest context
```

The overview page should link into child pages through the five-lane summary strip. If it is not implemented in the first slice, child pages still need the subnav and the spec should not be considered fully realized.

#### Fed Funds Page Design

Purpose: show whether the policy corridor is functioning and whether overnight funding is pressuring the Fed's target range.

First viewport:

```text
联邦基金与走廊                         [as of] [partial/ready]
政策走廊是否稳定，隔夜融资是否溢出目标区间？

+ Market read ----------------------------------------------------------+
| 走廊稳定，EFFR/SOFR 仍在目标区间内。                                  |
| EFFR 3.62% 位于 3.50-3.75% 目标区间内，SOFR 距上限约 13bp。            |
| Caveat: SOFR 30D unavailable; FOMC calendar unavailable.              |
+----------------------------------------------------------------------+

[FF upper 3.75] [FF lower 3.50] [EFFR 3.62] [IORB 3.65] [SOFR 3.62]

+ Corridor chart -------------------------------------------------------+
| shaded target band, EFFR, IORB, SOFR, SOFR 30D if available           |
+----------------------------------------------------------------------+
```

Primary visual:

- Use a band chart where target lower and upper create a shaded corridor.
- Use visually distinct lines for EFFR, IORB, SOFR, and SOFR 30D.
- Latest labels should sit near the latest point or in a tight legend, not only in tiles above.
- If SOFR 30D is missing, render the rest of the chart and show "SOFR 30D 未入库" as a small chart note.

Decision support:

- "Contained": EFFR inside target range.
- "Funding pressure watch": SOFR distance to upper bound.
- "Calendar caveat": FOMC meeting date unavailable if gap exists.
- "Invalidation": EFFR or SOFR exits target corridor, or SOFR persistently trades at/above upper bound.

Detail table:

| Column | Meaning |
|--------|---------|
| Rate | Target upper/lower, EFFR, IORB, SOFR, SOFR 30D when available. |
| Latest | Percent value. |
| Change | 20-day change where meaningful. |
| Distance | Distance to target upper/lower when meaningful. |
| Observed | Latest observation date. |
| Source | FRED or NY Fed. |

Empty/partial rules:

- With target range and EFFR only, the page still renders as a policy-rate page.
- With no target range, the page becomes `missing`.
- With target range but no SOFR, the page is `partial`, not `missing`.

#### Yield Curve Page Design

Purpose: show curve shape, curve slope, and whether rates are pricing recession pressure, policy easing, or term-premium pressure.

First viewport:

```text
收益率曲线                               [as of] [partial]
曲线是在交易衰退压力，还是期限溢价？

+ Market read ----------------------------------------------------------+
| 当前只具备 2Y/5Y/10Y/30Y 曲线骨架；10Y-2Y 为 +47bp。                 |
| 可读结论：中长端曲线向上倾斜，但短端缺失限制完整曲线判断。             |
| Missing: 1M, 3M, 6M, 1Y, 3Y, 7Y, 20Y.                                |
+----------------------------------------------------------------------+

[2Y 3.99] [5Y 4.15] [10Y 4.45] [30Y 4.98] [10Y-2Y +47bp] [10Y-3M +76bp]

+ Current curve --------------------------------------------------------+
| x-axis tenor, y-axis yield, draw available tenors only                |
+----------------------------------------------------------------------+
```

Primary visual:

- X-axis is tenor order, not synthetic dates.
- Available tenors draw as points connected by a line.
- Missing tenors appear as subtle gaps or as a compact missing-tenors note; they must not collapse the chart to empty.
- The chart should include latest observed date context because FRED tenor dates may differ by one day from spread dates.

Secondary visual, future expansion:

- Current versus 1w/1m/3m curves when enough historical tenor snapshots exist.
- Spread time-series for 2s10s and 3m10s.

Decision support:

- "Slope": 10Y-2Y and 10Y-3M values.
- "Long-end pressure": 10Y and 30Y changes.
- "Short-end confidence": lower when 1M/3M/6M/1Y are missing.
- "Invalidation": curve draw should not claim full shape when more than half tenors are missing.

Detail tables:

| Table | Columns |
|-------|---------|
| Tenor table | Tenor, latest yield, 20-day change, observed, source, status. |
| Spread table | Spread, latest bp, 20-day change, interpretation, observed, source. |

Empty/partial rules:

- At least two tenor points: render current curve.
- One tenor point: show fact tile and an empty chart state explaining at least two tenors are needed.
- Zero tenors: `missing`.
- Missing optional tenors never hide available tenors.

#### Treasury Auctions Page Design

Purpose: show whether Treasury supply and auction demand are adding pressure to duration. Current Parallax data cannot fully answer this yet, so the page must be honest and useful in proxy mode.

First viewport in current proxy mode:

```text
国债拍卖                                 [as of] [proxy]
拍卖供给压力是否体现在曲线和长端收益率上？

+ Market read ----------------------------------------------------------+
| 当前为拍卖代理页面：官方拍卖日历和结果尚未入库。                     |
| 可读结论：用 2Y/10Y/30Y 收益率观察供给压力是否已反映到曲线。           |
| Missing official feed: calendar, results, tail, bid-to-cover, indirect.|
+----------------------------------------------------------------------+

[2Y] [10Y] [30Y] [10Y-2Y] [Proxy status]

+ Auction pressure proxy ----------------------------------------------+
| duration/yield proxy chart or curve slice                             |
+----------------------------------------------------------------------+
```

First viewport after official auction data exists:

```text
国债拍卖                                 [as of] [ready]
拍卖需求是否足以消化未来供给？

+ Market read ----------------------------------------------------------+
| 未来三周供给集中；最近付息券需求偏正常/偏弱。                        |
| Bid-to-cover, indirect share, and tail determine demand quality.       |
+----------------------------------------------------------------------+

[Upcoming auctions] [Avg bid-to-cover] [Avg tail] [Indirect share] [Next long-end auction]

+ Calendar and demand visual ------------------------------------------+
| upcoming auction timeline + recent tail/bid-to-cover panel            |
+----------------------------------------------------------------------+
```

Primary visual in proxy mode:

- Show available yield proxy series or curve slice.
- Title must include "代理" so users do not confuse it with auction results.
- Missing official fields appear as a concise caveat near the chart title.

Primary visual in official mode:

- Future auction calendar timeline by date, tenor, size, and reopening.
- Recent results chart with tail and bid-to-cover.
- Optional split between bills and coupons, because bills and coupon auctions answer different risk questions.

Detail tables:

| Mode | Table | Columns |
|------|-------|---------|
| Proxy | Yield proxy table | Tenor, latest yield, change, observed, source, proxy note. |
| Official | Upcoming auctions | Auction date, security type, tenor, amount, settlement date, reopening. |
| Official | Recent results | Date, type, tenor, amount, high yield, bid-to-cover, indirect share, tail. |

Decision support:

- "Supply pressure": upcoming long-end supply if available.
- "Demand quality": bid-to-cover and indirect share if available.
- "Weak auction warning": positive tail above configured threshold if backend provides it.
- "Proxy caveat": no formal demand conclusion without official results.

Empty/partial rules:

- With no official auctions but available yield proxies, page is `proxy`.
- With official calendar but no results, page reads supply calendar only and demand section is partial.
- With official results but no future calendar, page reads recent demand only and supply section is partial.

#### Real Rates Page Design

Purpose: show whether real yields are tightening financial conditions and whether nominal moves are coming from real rates or inflation compensation.

First viewport:

```text
实际利率                                 [as of] [ready/partial]
实际利率是在压制估值，还是通胀补偿主导？

+ Market read ----------------------------------------------------------+
| 10Y real yield remains elevated; breakeven is stable/moderate.         |
| 可读结论：real-rate pressure matters for long-duration risk.           |
+----------------------------------------------------------------------+

[10Y real] [10Y breakeven] [5y5y forward] [Nominal 10Y if available]

+ Real-rate decomposition ---------------------------------------------+
| nominal 10Y = real 10Y + breakeven, or real vs breakeven if nominal missing |
+----------------------------------------------------------------------+
```

Primary visual:

- Best state: stacked or paired decomposition of nominal 10Y, real 10Y, and breakeven.
- Current available state: line chart of real 10Y and 10Y breakeven, plus a note if nominal 10Y is not in the module payload.
- 5y5y forward appears as a supporting fact or secondary line only if it does not crowd the primary read.

Decision support:

- "Tightening pressure": real 10Y level and change.
- "Inflation compensation": breakeven level and change.
- "Forward inflation watch": 5y5y forward.
- "Invalidation": real yield falls materially while nominal yields remain stable, implying less valuation pressure.

Detail table:

| Column | Meaning |
|--------|---------|
| Indicator | Real 10Y, 10Y breakeven, 5y5y forward, nominal 10Y if included. |
| Latest | Percent value. |
| Change | 20-day change. |
| Interpretation | Real tightening, inflation compensation, or context. |
| Observed | Date. |
| Source | FRED. |

Empty/partial rules:

- Real 10Y alone supports a minimal real-rate page.
- Real 10Y plus breakeven supports the main current design.
- Missing nominal 10Y should not block the page, but the decomposition wording must be adjusted.

#### Policy Expectations Page Design

Purpose: show whether the market is repricing cuts, unchanged policy, or hikes. Current Parallax data is proxy-only until Fed funds futures or an FOMC probability source is imported.

First viewport in current proxy mode:

```text
政策预期                                 [as of] [proxy]
市场是否在重新定价降息/维持/加息路径？

+ Market read ----------------------------------------------------------+
| 当前为政策路径代理页面：正式 FedWatch/Fed funds futures 概率未入库。 |
| 可读结论：用 3M/1Y/2Y 与目标区间观察短端再定价。                      |
+----------------------------------------------------------------------+

[Target range] [2Y] [1Y if available] [3M if available] [5y5y context]

+ Policy path proxy ----------------------------------------------------+
| short-end yields vs target range                                      |
+----------------------------------------------------------------------+
```

First viewport after futures/probabilities exist:

```text
政策预期                                 [as of] [ready]
市场是否在重新定价下一次 FOMC？

+ Market read ----------------------------------------------------------+
| 下一次会议维持/降息/加息概率；年内隐含路径。                         |
+----------------------------------------------------------------------+

[Next FOMC] [Hold probability] [Cut probability] [Hike probability] [Implied rate]

+ FOMC probability matrix ---------------------------------------------+
| meeting rows x target range columns + implied path                    |
+----------------------------------------------------------------------+
```

Primary visual in proxy mode:

- A policy path proxy chart using target upper/lower and available short rates.
- Missing 3M or 1Y should appear as "short-end proxy incomplete", not as an empty chart.

Primary visual in official mode:

- Meeting probability matrix with columns ordered by target range.
- Implied rate path chart below or beside the matrix.
- Underlying futures input table stays below the main probability surface.

Decision support:

- "Policy path proxy": relationship between 2Y/1Y/3M and target range.
- "Probability unavailable": official caveat while futures feed is missing.
- "Invalidation": proxy cannot be converted into probability without official source.

Detail tables:

| Mode | Table | Columns |
|------|-------|---------|
| Proxy | Short-end proxy table | Indicator, latest, change, relation to target, observed, source. |
| Official | Meeting probabilities | Meeting date, target ranges, implied rate, dominant market expectation. |
| Official | Futures inputs | Contract, settlement, implied rate, last updated, source. |

Empty/partial rules:

- Target range plus 2Y supports proxy mode.
- Without target range, expectations page is `missing` even if 2Y exists.
- Official probabilities take precedence over proxy reads once available.

#### Diagnostics Section Design

Diagnostics should use a consistent section on all rates pages:

```text
Diagnostics
[Data coverage] [Sources] [Projection health] [Global gaps reference]

Data coverage table:
Item | Status | Latest observation | History coverage | User-facing note

Sources table:
Source | Latest observation | Status | Indicator count | Notes

Health summary:
Module gaps | Chart gaps | Future integration gaps | Global reference count
```

Primary diagnostics rules:

- Data coverage rows may contain missing concepts, but labels must be human-readable.
- Raw gap codes may appear only if an explicit developer/operator mode is introduced; they should not appear in default product UI.
- Global gap count is a reference, not a page verdict.
- The diagnostics heading should be lower-emphasis than the market read and chart.

#### Interaction Model

The rates workbench should keep interactions few and predictable:

- Route subnav changes pages.
- Chart range selector appears only for time-series charts with enough history.
- Table sorting is allowed for detail tables.
- Diagnostics can expand/collapse but must not require modal interaction.
- Hover/focus tooltips may explain source notes, proxy labels, and abbreviations such as EFFR, IORB, SOFR, 2s10s, and 5y5y.
- No route should require a user to open diagnostics to understand whether the page is proxy or partial.

#### Copy Examples

Acceptable primary copy:

- "走廊稳定：EFFR 与 SOFR 均位于目标区间内。"
- "曲线骨架可读，但短端缺失限制完整曲线判断。"
- "当前为拍卖代理页面：官方日历和结果尚未入库。"
- "实际利率仍是估值压力来源，breakeven 暂未显示失控通胀定价。"
- "当前为政策路径代理页面，不能生成正式降息概率。"

Unacceptable primary copy:

- "macro_module_view_v3 partial"
- "chart_missing:rates:dgs3mo"
- "模块覆盖 6/13"
- "总览级缺口 86"
- "未在最新宏观投影中出现；检查 macrodata bundle 和 importer 映射。"

### Data Ownership

The fastest useful implementation can remain additive on top of `macro_module_view_v3`, but the target semantic ownership should be:

- Backend owns market read fields, source states, confidence language, proxy status, and gap summaries.
- Frontend owns layout, formatting, responsive behavior, chart rendering, and local reveal/hide state for diagnostics.
- Frontend may derive presentational labels from existing fields, but it must not invent rate-regime conclusions, Fed probabilities, auction demand labels, or crypto impact.

## Conceptual Data Flow

```text
macrodata-cli bundle and future provider bundles
  -> macro sync/import
  -> macro_observations
  -> macro observation series rows
  -> macro_regime_v4 snapshot
  -> macro_module_view_v3 and future rates-specific additive fields
  -> /api/macro/modules/{rates module}
  -> web rates workbench components
  -> market read, visual, detail table, diagnostics
```

Changed arrows:

- `macro_module_view_v3 -> web rates workbench components` changes from generic leaf rendering to rates-specific rendering.
- Future `macrodata-cli bundle -> macro_observations` should expand to include Treasury auction calendar/results and Fed funds futures/FOMC probabilities. This is source expansion, not frontend repair.
- The yield-curve visual must consume available module chart series and/or module series data in a way that does not require a separate provider call.

## Core Models

### Rates Workbench Page

Semantic page model consumed by rates UI, whether represented as existing module fields or additive backend fields:

- `module_id`: one of the rates module ids.
- `page_question`: the decision question.
- `asof_label`: date the read represents.
- `readiness`: `ready | partial | proxy | stale | missing`.
- `market_read`: concise headline and supporting explanation.
- `primary_facts`: ordered values that justify the read.
- `primary_visual`: one rates-specific chart payload.
- `decision_support`: confirmations, contradictions, watch triggers, invalidations.
- `detail_tables`: product tables.
- `diagnostics`: source state, data gaps, provenance, global gap reference.

Invariant: `readiness=ready` is not allowed when required official data for that page is missing.

### Rates Fact Card

Ordered supporting fact:

- `label`
- `value`
- `unit`
- `observed_at_label`
- `source_label`
- `window_change_label`
- `status`
- `interpretation`

Invariant: a card must not display a value without either an observation date or an explicit reason why the date is absent.

### Rates Visual

Rates-specific visual payload:

- `visual_type`: `corridor_band | yield_curve | auction_proxy | auction_results | real_rate_decomposition | policy_path_proxy | fomc_probabilities`.
- `title`
- `subtitle`
- `series`
- `annotations`
- `missing_items`
- `proxy_note`
- `empty_state`

Invariant: the chart can be partial without being empty. If at least the minimum meaningful facts exist, it should draw and label what is missing.

### Rates Diagnostics

Operator-facing diagnostics:

- `module_gaps`
- `chart_gaps`
- `future_integration_gaps`
- `global_gap_reference_count`
- `provenance_rows`
- `publication_state`

Invariant: diagnostics are not the default user read. They must remain inspectable and testable.

## Interface Contracts

### HTTP

The existing public surface remains:

- `/api/macro/modules/rates/fed-funds`
- `/api/macro/modules/rates/yield-curve`
- `/api/macro/modules/rates/auctions`
- `/api/macro/modules/rates/real-rates`
- `/api/macro/modules/rates/expectations`
- `/api/macro/series`

Required semantic contract:

- Module responses continue to return deterministic module state only.
- Additive rates-specific fields may be added to `macro_module_view_v3` if they do not break existing consumers.
- If rates-specific fields become structurally different from generic module fields, the plan must propose a versioned contract rather than overloading ambiguous fields.
- `/api/macro/series` may provide chart history, but the rates UI must not require frontend provider IO.
- Error states remain data-state errors, not provider retries from the request path.

### Frontend

The rates workbench frontend contract:

- The page renders from feature API hooks only.
- It uses the existing macro shell and navigation architecture.
- It keeps feature CSS under the macro feature namespace and within the CSS architecture harness.
- It does not display raw concept keys, raw gap codes, JSON provenance, source snapshot ids, or projection version in primary UI.
- It provides explicit loading, empty, partial, stale, and proxy states.

### CLI And Operations

Operational diagnosis remains:

- `uv run parallax config`
- `uv run parallax macro status`
- `uv run parallax db health`

These commands are verification and support surfaces, not product UI. The product page should summarize their implications, not mirror their raw structure.

## Acceptance Criteria

- AC1. WHEN a user opens any rates page on desktop, THEN the first viewport SHALL show the page question, a concise market read, primary facts, and the primary visual before detailed diagnostics.
- AC2. WHEN a rates page is `partial`, THEN the page SHALL say what can still be read and what missing source prevents a stronger conclusion.
- AC3. WHEN a user opens `/macro/rates/fed-funds` with current target range, EFFR, IORB, and SOFR available, THEN the page SHALL render a corridor read and chart without making missing SOFR 30D the central experience.
- AC4. WHEN a user opens `/macro/rates/yield-curve` with at least two available tenor points, THEN the page SHALL render a yield curve using available tenors and label missing tenors as partial data.
- AC5. WHEN official Treasury auction calendar/results are unavailable, THEN `/macro/rates/auctions` SHALL clearly present itself as a proxy page and keep auction calendar/results gaps in diagnostics.
- AC6. WHEN Treasury auction calendar/results become available, THEN `/macro/rates/auctions` SHALL prefer future supply and recent demand tables over yield proxy tables.
- AC7. WHEN a user opens `/macro/rates/real-rates` with real 10Y and breakeven data available, THEN the page SHALL present the real-rate versus inflation-compensation interpretation before diagnostics.
- AC8. WHEN Fed funds futures or FOMC probability feeds are unavailable, THEN `/macro/rates/expectations` SHALL show a policy-path proxy read rather than an empty probability workbench.
- AC9. WHEN Fed funds futures or FOMC probability feeds become available, THEN `/macro/rates/expectations` SHALL show meeting probability and implied path surfaces as the primary experience.
- AC10. WHEN data health, provenance, availability tables, module evidence, and global gap counts are present, THEN they SHALL appear in a diagnostics section below or beside the main workbench hierarchy, not as the primary headline.
- AC11. WHEN a page renders missing data labels, THEN it SHALL use human-readable labels and SHALL NOT expose raw concept keys, raw gap codes, projection ids, or JSON blobs in primary UI.
- AC12. WHEN the viewport is tablet or mobile, THEN rates pages SHALL remain readable with no horizontal body overflow, no overlapping text, and reachable diagnostics.
- AC13. WHEN the frontend architecture harness runs, THEN rates CSS SHALL remain macro-owned and SHALL NOT recreate retired CSS buckets or restyle shared internals.
- AC14. WHEN the implementation is verified, THEN manual macro smoke SHALL cover all five rates child routes and record which pages are fact-backed versus proxy-backed.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Rates pages become prettier but still generic | High | Require page-specific acceptance criteria for each rates child route. |
| UI hides real data gaps | High | Keep a diagnostics section and explicit proxy/partial labels. |
| Frontend starts inventing market reads | High | Backend owns read semantics; frontend only formats and lays out. |
| Yield curve remains empty despite available data | High | Acceptance requires drawing from available tenor points when at least two exist. |
| Auctions and expectations look broken until new sources exist | Medium | Treat current state as proxy mode with clear copy and diagnostics. |
| Scope expands into all Macro pages | Medium | Scope is limited to rates pages and shared primitives needed by rates. |
| Dense UI becomes unreadable on mobile | Medium | Responsive acceptance criteria require no overflow, no overlap, and reachable diagnostics. |
| Data-source expansion is conflated with UI redesign | Medium | Spec separates immediate UI clarity from future Treasury/CME source ingestion. |

## Evolution Path

The first implementation should make current facts readable and fix the yield-curve rendering defect. The next expansion should add official upstream data for Treasury auctions and Fed funds futures/FOMC probabilities through the existing macro sync/import path. After those facts exist, `/macro/rates` can become a true rates overview page that summarizes the five child pages into a single policy/curve/supply/real-rate/expectations board.

This design should not foreclose a future `rates_workbench_view_v1` contract if additive `macro_module_view_v3` fields become too overloaded. It should also leave room for side-by-side current/1w/1m/3m curve comparison, auction tail history, and FOMC meeting probability ladders once the backend owns those facts.

## Alternatives Considered

- **Polish the generic MacroLeafModulePage only.** Rejected because the core problem is hierarchy and domain meaning, not merely spacing or color. The same generic order cannot make Fed funds, yield curve, auctions, real rates, and policy expectations all feel like purposeful workbenches.
- **Clone the benchmark pages.** Rejected because Parallax has different truth boundaries, different data readiness, and a crypto/operator-console context. The benchmark informs information architecture, not implementation dependency or visual copying.
- **Wait for all missing data sources before redesigning.** Rejected because Fed funds, real rates, and partial yield-curve data are already useful, and current UI makes available facts harder to read than necessary.
- **Hide all diagnostics from the product pages.** Rejected because Macro is operator-facing and partial data quality matters. The right fix is hierarchy, not deletion.
- **Create new persisted rates read models immediately.** Deferred because the fastest improvement can likely be additive on the existing module contract. A new versioned rates contract should be proposed in the plan only if the additive path creates ambiguity or frontend inference pressure.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Rates pages lead with market read, primary facts, primary visual, and clear partial/proxy state. |
| Always | Missing source data remains visible in diagnostics and relevant page caveats. |
| Always | Frontend consumes Macro API contracts and does not call providers or compute rates scores. |
| Ask first | Introduce a new versioned rates-specific API contract instead of additive module fields. |
| Ask first | Add new macrodata provider bundles, migrations, or worker ownership changes. |
| Never | Show raw concept keys, raw gap codes, projection ids, or JSON provenance as primary product UI. |
| Never | Claim auctions or policy expectations are fully ready while official feeds are absent. |
| Never | Redesign unrelated Macro domains as part of this rates-only spec. |
