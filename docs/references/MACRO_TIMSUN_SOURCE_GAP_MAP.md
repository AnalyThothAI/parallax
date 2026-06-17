# Macro TimSun Source Gap Map

Fetch date: 2026-06-17.

## Purpose

This reference turns the TimSun parity backlog into source-gated work. It is not
a runtime backlog, product placeholder, route compatibility list, or permission
to restore deleted macro pages. A surface may return only when it has source
coverage, deterministic read-model ownership, user-facing data health, and
tests that prove the old placeholder path is gone.

## Benchmark Shape

Source URL: https://timsun.net/

Summary: The benchmark homepage is a macro decision console, not a directory of
terminal pages. Its first screen combines a macro state, Trade Map, judgement
review, top changes, confirmation/divergence, liquidity pressure, 24h/72h
catalysts, a data credibility layer, a structured cross-domain analysis chain,
market event flow, research/news context, and watchlist triggers. Its navigation
also exposes deeper domains: assets, rates, Fed, liquidity, economy, volatility,
and credit.

Rule supported: Parallax should keep the retained decision console and fold weak
signals into retained source-backed pages until a distinct source-backed page has
earned its own route. Page count is not the target; evidence-backed decision
flow is the target.

## Current Implemented Baseline

Source URL: `/Users/qinghuan/Documents/code/macrodata-cli/docs/reference/catalog.md`

Summary: The local macrodata-cli checkout exposes public bundles for rates,
rates-market, liquidity, economy, volatility, credit, assets, crypto
derivatives, macro calendar, Fed text, Treasury auctions, and macro-core.
Parallax already pins macrodata-cli `0.1.22` and defaults macro sync to numeric
macro-core plus event and crypto-derivatives bundles. The remaining gap is mostly
product/read-model depth, operational verification, and licensed-source access,
not a total absence of raw sources.

Rule supported: Do not create "future source" rows for concepts already present
in macrodata-cli. If a bundle exists but a retained page lacks evidence, surface
that as `data_health` repair work on the retained page and fix the sync/projection
path.

## Source Classes

| Class            | Meaning                                                                                                         | Product rule                                                                      |
| ---------------- | --------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Implemented      | Source exists in macrodata-cli and Parallax has a retained route that can render it.                            | Fix sync, history, freshness, and diagnostics before adding new surfaces.         |
| Public candidate | Official/public source can be integrated without user approval for paid data, subject to terms and rate limits. | Add a provider/bundle and fold into retained pages first.                         |
| License gate     | Source exists but requires explicit market-data, redistribution, or vendor approval.                            | No route, fixture, static row, or hidden page until licensing is approved.        |
| Model gap        | Raw source exists, but the product value requires deterministic scoring or backtest design.                     | Build scoring/read-model spec first; raw text or raw prices alone are not enough. |
| No source        | No reliable legal source identified.                                                                            | Keep deleted.                                                                     |

## Gap Matrix

| TimSun-aligned domain                | Current Parallax state                                                                                                                                                    | Missing source or model                                                                                | Candidate source                                                                                                                                    | Gate before product restoration                                                                                                                                  |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Trade Map reliability / backtest     | Overview has Trade Map, 1D/5D/20D holding-period judgement review, and historical-trust summaries.                                                                        | Longer historical decision snapshots, richer asset-history joins, and win/loss attribution.            | Internal Parallax snapshots and macro observations; no external feed required.                                                                      | Add a read-model spec for historical judgement history and attribution; prove no LLM or frontend recomputation.                                                  |
| Fed communication                    | `fed-text-core` imports official FOMC statements, minutes, press releases, and speeches into overview event/structured rows.                                              | Delta scoring, hawk/dove stance, speaker narrative, and before/after comparison.                       | Federal Reserve official feeds and pages already provide raw documents.                                                                             | Add deterministic text-diff/scoring spec and backtest; do not restore Fed statement/speech pages as raw-document shells.                                         |
| Rate probabilities / FedWatch        | `rates/fed-funds` has target/EFFR/IORB/SOFR corridor evidence; `rates/expectations` is deleted.                                                                           | Meeting probability tree by target range, meeting date, and as-of.                                     | CME FedWatch Tool / FedWatch API, or licensed CME 30-Day Fed Funds futures data.                                                                    | Operator approves CME/API/data terms; provider stores probability rows with provenance; route test proves no fake FedWatch fixture or compatibility path.        |
| VIX futures curve                    | `volatility/vix` has VIX/VIX3M and public Cboe/CME/Yahoo volatility proxies.                                                                                              | VX term structure, CFE volume/OI, options surface, realized-vol comparison.                            | Cboe CFE historical data for volume/OI and select futures price/volume; Cboe DataShop/LiveVol for richer history/options.                           | Public CFE provider may fold into `volatility/vix`; any options-surface/dashboard route needs approved Cboe/OPRA/LiveVol source and surface tests.               |
| Options OI / GEX                     | Standalone options/GEX pages are deleted.                                                                                                                                 | Option-chain OI by strike/expiry plus a defensible dealer-gamma model.                                 | OPRA consolidated options feeds and approved OPRA vendors; Cboe options analytics or DataShop where licensed.                                       | Licensing and model spec approved; GEX is modeled output, not a raw OPRA field, so tests must pin formula and provenance.                                        |
| Crypto derivatives                   | `crypto-derivatives-core` has OKX/Deribit BTC/ETH OI, funding, basis, and DVOL; folded into `assets/crypto`.                                                              | Live operational verification, stale-source checks, normalized history, richer tenor/expiry structure. | OKX and Deribit public APIs already implemented in macrodata-cli.                                                                                   | Verify unrestricted sync to Postgres and provider freshness; keep standalone `assets/crypto-derivatives` deleted unless a broader term-structure product exists. |
| Global dollar / cross-currency basis | FX and dollar proxy evidence exists; global-dollar route is deleted.                                                                                                      | Cross-currency basis, offshore dollar funding pressure, and region-level transmission.                 | CME EUR/USD Cross Currency Basis Index API for one licensed index; broader coverage likely needs Bloomberg/Refinitiv/BIS or other licensed sources. | Source license and series universe approved; fold first into retained liquidity/FX diagnostics before considering a distinct global-dollar route.                |
| Subsurface funding / STFM            | `liquidity/rrp-tga` has RRP/TGA and NY Fed repo-rate/volume depth.                                                                                                        | OFR STFM repo/MMF/primary-dealer distributions, percentiles, and collateral/tenor/rate/volume slices.  | OFR Short-term Funding Monitor public API.                                                                                                          | Add `ofr_stfm` provider and retained liquidity data-health; no `liquidity/subsurface` route until the page has unique diagnostics beyond RRP/TGA.                |
| Treasury auctions                    | Official auction calendar/results enter overview event flow with no runtime `tail missing` placeholder; `rates/auctions` is deleted.                                      | Auction tail versus when-issued yield and richer demand diagnostics.                                   | Treasury FiscalData covers calendar/results; when-issued yield requires an approved market source.                                                  | Keep folded into overview/rates until a legal WI source exists and tail formula is tested; do not expose auction-tail future-source copy in product rows.        |
| Economy actual / revisions           | Economy pages have FRED/BEA/FRED-mirrored macro series and official event catalysts; official BLS/BEA calendar rows are labelled as release/revision watch, not surprise. | Release actual-vs-prior, revisions, and consensus surprise history.                                    | BLS Public Data API and BEA API/schedule for actuals/revisions; consensus requires licensed vendor.                                                 | Implement actual/revision lanes first; do not label "surprise" without consensus source and timestamped expectations.                                            |
| Credit microstructure                | `credit/stress` has OAS ladder, SLOOS, loan quality, financial conditions, and ETF price proxies.                                                                         | TRACE trade activity, ETF premium/discount, CDS/CDX, and issuer-level credit deterioration.            | FINRA Fixed Income Data/TRACE for public or licensed use; issuer ETF data subject to issuer terms; CDS/CDX usually Markit/Bloomberg/ICE licensed.   | Add public FINRA aggregates only if user agreement permits; restore `credit/cds` only with approved CDS/CDX source.                                              |

## First-Principles Source Priority

The next source work should optimize for decision-console usefulness per unit of
source risk, not for route count. A candidate is priority-ready only if it meets
all four tests:

1. It is an official or public source with clear access mechanics.
2. It can strengthen a retained page without restoring a deleted shell.
3. It can be imported through macrodata-cli or `macro_sync`, not React or request
   handlers.
4. Its output is a fact or deterministic derived metric, not an untested model
   claim.

### Implement Next Without A License Decision

| Order | Source lane                          | Why it comes next                                                                                                                                                                                                   | Target retained surface                                                           | Acceptance signal                                                                                                                  |
| ----- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 1     | OFR STFM public API                  | It is public, tokenless, JSON-based, and directly fills the weakest liquidity/subsurface gap: repo, MMF, reference-rate, primary-dealer, collateral, tenor, volume, and rate slices.                                | Fold into `liquidity/rrp-tga` as a funding-depth diagnostic and data-health lane. | `ofr_stfm` bundle imports bounded history; `liquidity/rrp-tga` renders source/as-of rows; no `liquidity/subsurface` route returns. |
| 2     | BLS/BEA actual and revision lanes    | Current economy pages have broad FRED level data and official calendars, but not a clean actual/prior/revision path. BLS and BEA are official sources for published values and metadata.                            | Fold into `economy/gdp`, `economy/employment`, and `economy/inflation`.           | Pages distinguish actual/prior/revision from consensus surprise; no `surprise` label appears without a consensus source.           |
| 3     | Cboe CFE futures history             | Current volatility page has VIX spot, short-horizon indexes, VVIX, SKEW, and ETF proxies, but TimSun-style vol depth needs VX futures curve/OI/volume. Cboe exposes historical futures/statistics/archive surfaces. | Fold into `volatility/vix` as VIX futures curve/depth evidence.                   | `volatility/vix` renders VX tenor rows and curve diagnostics; deleted volatility dashboard remains absent.                         |
| 4     | Internal Trade Map judgement history | The source already exists inside Parallax: daily snapshots and macro observations. This improves usability more than adding another weak external page.                                                             | Fold into overview Trade Map and judgement review.                                | Historical judgement read model has stable keys, hit attribution, and no frontend recomputation.                                   |
| 5     | Fed communication delta model        | Raw official Fed text is already imported; the gap is deterministic scoring/diff, not source acquisition.                                                                                                           | Fold into overview structured analysis and retained rates/Fed context.            | Text-diff/scoring tests pin hawk/dove deltas, speaker/event provenance, and before/after comparison.                               |

### Keep License-Gated

| Source lane                                    | Why it stays gated                                                                                 | Product rule                                                                                               |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| CME FedWatch / Fed Funds futures probabilities | Meeting probabilities require CME/Fed Funds futures terms or an approved licensed feed.            | Do not restore `rates/expectations` until probability rows have approved provenance and formula tests.     |
| OPRA options chain / GEX                       | OPRA is a consolidated options data plan and GEX is a model output, not a raw field.               | Do not restore options/GEX routes until license and dealer-gamma formula are both approved.                |
| TRACE/CDS/CDX microstructure                   | FINRA fixed-income data has agreement constraints, while CDS/CDX are usually licensed.             | Keep `credit/cds` deleted until source terms and redistribution are explicit.                              |
| Cross-currency basis / global dollar funding   | One CME basis index exists, but broad offshore-dollar coverage usually needs licensed market data. | Fold approved series into retained liquidity/FX diagnostics first; keep `liquidity/global-dollar` deleted. |
| Consensus surprise                             | Official BLS/BEA provide actuals and revisions, not a timestamped consensus expectation.           | Calendar rows may be official; surprise labels require approved expectations data.                         |

## External Source References

| Source URL                                                                                        | Fetch date | Summary                                                                                                                                             | Rule or formula supported                                                                                 |
| ------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| https://timsun.net/                                                                               | 2026-06-17 | Benchmark homepage and navigation show the desired decision-console shape and deep domains.                                                         | Align to decision flow, not one-for-one weak route count.                                                 |
| https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html                            | 2026-06-17 | CME FedWatch presents FOMC rate-move probabilities implied by 30-Day Fed Funds futures.                                                             | `rates/expectations` needs approved FedWatch/probability source.                                          |
| https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html | 2026-06-17 | CME documents the probability-tree assumptions and use of Fed Funds futures and EFFR.                                                               | Probability calculations must be formula-backed and source-provenanced.                                   |
| https://www.cmegroup.com/market-data/market-data-api.html                                         | 2026-06-17 | CME lists market-data APIs including FedWatch, real-time futures/options, Term SOFR, cross-currency basis, Greeks/IV, CVOL, and DataMine.           | CME-derived surfaces are license-gated unless explicitly approved.                                        |
| https://www.cboe.com/us/futures/market_statistics/historical_data/                                | 2026-06-17 | Cboe exposes CFE historical futures data, daily volume/open-interest, settlement-window volume, archives, and select VX/VXT price-volume detail.    | Public VIX curve depth can start with CFE historical data; richer options analytics remain separate.      |
| https://www.financialresearch.gov/short-term-funding-monitor/                                     | 2026-06-17 | OFR STFM explains short-term funding monitor categories and downloadable datasets.                                                                  | Liquidity subsurface work should use OFR categories rather than static placeholders.                      |
| https://www.financialresearch.gov/short-term-funding-monitor/api/                                 | 2026-06-17 | OFR STFM API is public, tokenless, JSON-based, and exposes metadata and time-series endpoints.                                                      | `ofr_stfm` is a public candidate provider for liquidity depth.                                            |
| https://www.finra.org/finra-data/fixed-income                                                     | 2026-06-17 | FINRA Fixed Income Data includes TRACE/security/trade activity and market statistics with a user agreement and a current history availability note. | Credit microstructure needs FINRA terms review and cannot be treated as free unrestricted redistribution. |
| https://www.opraplan.com/                                                                         | 2026-06-17 | OPRA disseminates consolidated last-sale and quotation information from SEC-approved options exchanges and lists approved vendors/participants.     | Options/GEX needs OPRA/vendor licensing and a separate dealer-gamma model.                                |
| https://www.bls.gov/developers/                                                                   | 2026-06-17 | BLS Public Data API exposes published historical timeseries through JSON/XLSX; v2 requires registration and v1 is more limited.                     | Economy actual/revision data can be public; consensus surprise cannot be inferred.                        |
| https://apps.bea.gov/api/signup/                                                                  | 2026-06-17 | BEA API provides programmatic access to published BEA statistics and metadata.                                                                      | GDP/PCE actual/revision lanes can use BEA data.                                                           |
| https://www.bea.gov/news/schedule                                                                 | 2026-06-17 | BEA release schedule includes 2026 release dates/times and machine-readable formats.                                                                | Calendar events can be official; surprise requires separate expectations.                                 |
| https://www.federalreserve.gov/feeds/                                                             | 2026-06-17 | Federal Reserve data and feed surfaces include official policy, data, and speech/document references.                                               | Fed text raw-source coverage is not enough for hawk/dove pages without scoring design.                    |

## Task Breakdown

1. Lock the current source inventory: assert Parallax runtime has the pinned
   macrodata-cli version, configured bundle names, and required bundle series.
2. Implement OFR STFM as the next public-source provider and fold it into
   `liquidity/rrp-tga` diagnostics.
3. Implement Cboe CFE VX/VXT futures depth as a public-source extension to
   `volatility/vix`, then decide whether Cboe DataShop/LiveVol is worth a
   license gate for options depth.
4. Add BLS/BEA actual and revision lanes to retained economy pages. Keep
   surprise labels out until consensus data is approved.
5. Run an operator licensing decision for CME FedWatch/Fed Funds futures. Only
   after approval, build `rates/expectations` from real probability rows.
6. Run an operator licensing decision for OPRA/options vendors and CDS/CDX
   sources. Do not restore options/GEX/CDS pages from proxies.
7. Build a deterministic Fed communication delta model from official documents
   before restoring any Fed communication terminal.
8. Add architecture guards for every restored source-backed page: no deleted
   route alias, no hidden compatibility shell, no static future-source row, and
   no frontend/provider call.

## Non-Negotiable Product Rules

- Deleted macro pages stay deleted until their source gate passes.
- New sources land in macrodata-cli or the macro sync lane first, never in React
  or request-time API provider calls.
- Retained pages may show actionable `data_health` repair rows for implemented
  but missing data; they must not show future-source marketing copy.
- Paid or restricted feeds require explicit operator approval before code,
  fixtures, route labels, or docs describe them as product capability.
