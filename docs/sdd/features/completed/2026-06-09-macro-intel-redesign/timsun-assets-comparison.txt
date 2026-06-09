# Timsun Assets Comparison

**Reference URL**: `https://timsun.net/assets/`
**Checked**: 2026-06-09
**Access note**: plain text browser fetch initially returned an access error, but `curl` with a desktop browser user-agent returned HTTP 200 and HTML.

## Product Shape Observed

The reference page is a dense macro research dashboard, not a marketing page. The first screen uses a persistent left navigation, breadcrumb, page title, and then begins immediately with asset tables.

The page order is:

1. `大类资产` page header.
2. Market groups as separate dense tables: `美股`, `债券`, `商品`, `ETF`, `外汇`, `加密货币`.
3. `跨资产相关性` with a heatmap, explicit date, rolling-window selector, and color legend for negative/neutral/positive correlation.
4. Correlation alert copy, for example the page flags stock/bond positive correlation as a portfolio-warning condition.
5. `交叉分析` prose blocks that interpret cross-asset moves, rates pressure, dollar/commodities, risk appetite, and short-term triggers.

## Useful Patterns To Carry Forward

- **Dense grouped tables beat generic cards**: each asset class starts with a compact table and a detail link. This is more readable for traders than many equal-weight metric cards.
- **Correlation deserves visual prominence**: the reference uses a heatmap with a date, window options, color legend, and a short interpretation. Our first slice keeps a table matrix; future visual work should consider a heatmap view once backend data shape is stable.
- **Narrative analysis is a distinct layer**: the reference separates raw market rows from the analyst read. Our `今日判断` panel is the right place, but it should eventually grow into explicit cross-asset paragraphs and triggers rather than only four short blocks.
- **Navigation is domain-first**: asset child routes include equities, ETF, options/GEX, positioning, bonds, commodities, FX, crypto, and crypto derivatives. Our route tree is cleaner but currently thinner for ETF/options/positioning.
- **Alerts are specific, not generic**: the reference highlights a concrete stock/bond correlation warning. Our diagnostics currently focuses data health; future product work should add market-condition alerts sourced from backend facts.

## Current Parallax Alignment

- We now match the reference's market-dashboard-first structure for `/macro/assets`.
- We now keep each asset class in a dedicated dense table with a detail link.
- We now have a correlation section and detail route, and the detail route has a dedicated `相关性简报`, `相关性矩阵`, `相关性证据`, and `数据诊断` grammar.
- We preserve backend truth: no front-end recomputation of macro scoring or unsupported signal generation.

## Remaining Gap

- The reference page has ETF and options/positioning asset subroutes; Parallax currently exposes fewer asset detail pages.
- The reference correlation module is a heatmap with a visual legend; Parallax currently renders an accessible table matrix.
- The reference has long-form cross-asset analysis paragraphs. Parallax has `今日判断` blocks but not yet a full analyst narrative section.
- The reference page is visually simpler than our inherited dark panel stack: less competing hierarchy, clearer table-first scanning, and fewer standalone diagnostics panels.
- Full visual parity is not the goal, but Parallax still needs a tighter first-screen density and better analyst-read hierarchy after the remaining macro pages are migrated.
