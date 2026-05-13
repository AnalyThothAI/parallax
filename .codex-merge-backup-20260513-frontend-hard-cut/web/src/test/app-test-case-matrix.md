# App Test Case Matrix

Source: `web/src/App.test.tsx` in the Task 0 baseline.

Purpose: preserve assertion intent while deleting or shrinking `App.test.tsx` during Task 8. Each row maps the current integration-style assertion to the target layer in the new test pyramid.

| Current line | Current test | Target | Destination |
|---:|---|---|---|
| 194 | renders radar rows with mock-aligned semantic fields and selected state | L1 | `features/live/ui/TokenRadarRow.test.tsx` |
| 225 | patches visible token-radar rows with websocket market updates | L2 | `features/live/__tests__/marketUpdatePatch.integration.test.tsx` |
| 265 | routes text search into the Search Intel page instead of the old evidence drawer | L2 | `features/search/__tests__/searchNavigation.integration.test.tsx` |
| 297 | routes cashtag input to Search Intel instead of selecting the current radar token | L2 | `features/search/__tests__/searchNavigation.integration.test.tsx` |
| 319 | routes bare uppercase input through Search Intel without local token matching | L2 | `features/search/__tests__/searchNavigation.integration.test.tsx` |
| 340 | selects Token Radar rows into the drawer and drills into Search Intel from the drawer action | L2 | `features/live/__tests__/liveSelection.integration.test.tsx` |
| 373 | opens Search Intel from the Token Radar row arrow | L1 | `features/live/ui/TokenRadarRow.test.tsx` |
| 397 | opens an evidence drawer from a non-token live tape event | L2 | `features/live/__tests__/liveTape.integration.test.tsx` |
| 408 | exposes a venue link for resolved radar tokens | L1 | `features/live/ui/TokenRadarRow.test.tsx` |
| 419 | keeps each Token Radar metric in stable responsive slots | L1 | `features/live/ui/TokenRadarRow.test.tsx` |
| 438 | renders valid token radar rows regardless of backend projection version metadata | L0 | `features/live/model/tokenRadarItems.test.ts` |
| 447 | renders fresh CEX token-radar market as tradeable instead of pending | L1 | `features/live/ui/TokenRadarRow.test.tsx` |
| 508 | renders CEX prices with precision and keeps DEX primary market value on market cap | L1 | `features/live/ui/TokenRadarRow.test.tsx` |
| 581 | renders token-radar timing changes from backend market baselines | L1 | `features/live/ui/TokenRadarRow.test.tsx` |
| 619 | uses Signal Lab as the trader-facing product label | L1 | `features/cockpit/ui/CockpitSideRail.test.tsx` |
| 627 | keeps Signal Lab Pulse visible in the live cockpit and opens the shared inspector | L2 | `features/live/__tests__/livePulse.integration.test.tsx` |
| 651 | routes Signal Pulse notifications into Signal Lab instead of token search | L2 | `features/notifications/__tests__/notificationNavigation.integration.test.tsx` |
| 672 | queries the compact Signal Lab Pulse as a fresh live feed | L2 | `features/live/__tests__/livePulse.integration.test.tsx` |
| 691 | switches the left rail into the Signal Lab workbench without losing the selected pulse item | L2 | `features/signal-lab/__tests__/signalLabNavigation.integration.test.tsx` |
| 721 | opens Stocks from the main navigation without the token detail layout | L2 | `features/stocks/__tests__/stocksRoute.integration.test.tsx` |
| 743 | marks the desktop watchlist as the left rail fill section | L1 | `features/cockpit/ui/CockpitSideRail.test.tsx` |
| 755 | uses watchlist clicks as a Signal Lab account lens | L2 | `features/cockpit/__tests__/watchlistNavigation.integration.test.tsx` |
| 783 | shows watched account events when an account lens has no Signal Pulse candidates | L2 | `features/signal-lab/__tests__/accountLens.integration.test.tsx` |
| 821 | renders the selected token drawer with the mock structure and no extra override controls | L1 | `features/live/ui/TokenDetailDrawer.test.tsx` |
| 844 | opens Timeline by default, requests timeline/posts, and keeps token Lab as a pointer into Signal Lab | L2 | `features/token-target/__tests__/tokenTarget.integration.test.tsx` |
| 879 | maps radar evidence count from source event ids instead of empty intent evidence | L0 | `features/live/model/tokenRadarItems.test.ts` |
| 896 | uses the resolved target symbol for identity when a mention symbol disagrees | L0 | `features/live/model/tokenRadarItems.test.ts` |
| 914 | does not fallback resolved target identity to the mention symbol | L0 | `features/live/model/tokenRadarItems.test.ts` |
| 943 | rejects token radar rows when the backend omits factor_snapshot | L0 | `features/live/model/tokenRadarItems.test.ts` |
| 952 | rejects token radar rows when the factor snapshot omits the current attention window | L0 | `features/live/model/tokenRadarItems.test.ts` |
| 979 | drives selected token detail by production windows instead of manual timeline buckets | L2 | `features/live/__tests__/tokenDetail.integration.test.tsx` |
| 1010 | opens replay focus mode by clicking a timeline bucket | L1 | `features/live/ui/TokenTimeline.test.tsx` |
| 1029 | keeps Posts as the evidence surface with explicit range controls | L1 | `features/live/ui/TokenPostsPanel.test.tsx` |
| 1056 | requests catalyst post sorting from the server | L2 | `features/token-target/__tests__/tokenPosts.integration.test.tsx` |
| 1073 | removes narrative product surface and exposes signal lab entry points | L1 | `features/live/ui/TokenDetailDrawer.test.tsx` |
| 1081 | uses the Signal Pulse read model as the only Signal Lab product source in the UI | L2 | `features/signal-lab/__tests__/signalLabPulse.integration.test.tsx` |
| 1097 | keeps settlement horizons out of the trader-facing Signal Lab and global token radar rail | L1 | `features/signal-lab/ui/SignalLabPage.test.tsx` |
| 1112 | routes Signal Lab toolbar filters into the Signal Pulse read model | L2 | `features/signal-lab/__tests__/signalLabFilters.integration.test.tsx` |
| 1142 | uses the Signal Lab cursor without duplicating aggregate summary or overlapping rows | L2 | `features/signal-lab/__tests__/signalLabPagination.integration.test.tsx` |
| 1205 | keeps live compact pulse selection independent from workbench status filters | L2 | `features/live/__tests__/livePulse.integration.test.tsx` |
| 1229 | renders Signal Pulse rows and opens the right-side inspector | L1 | `features/signal-lab/ui/SignalLabPulse.test.tsx` |
| 1264 | dedupes replay/live tape rows and token tape click does not change sort mode | L0/L2 | `features/live/model/liveTapeModel.test.ts` and `features/live/__tests__/liveTape.integration.test.tsx` |
| 1279 | shows actionable radar row context when timing has sparse market data | L1 | `features/live/ui/TokenRadarRow.test.tsx` |
| 1289 | keeps replay rows visible when websocket disconnects | L2 | `features/live/__tests__/socketReplay.integration.test.tsx` |
| 1297 | requests selected token detail by target identity | L2 | `features/live/__tests__/tokenDetail.integration.test.tsx` |
| 1318 | does not offer an audit page for unresolved token radar rows | L1 | `features/live/ui/TokenRadarRow.test.tsx` |
| 1329 | realigns the drawer when the selected token disappears after a window switch | L2 | `features/live/__tests__/liveSelection.integration.test.tsx` |
| 1343 | uses live token attribution before ambiguous cashtag matching in the tape | L0 | `features/live/model/liveTapeModel.test.ts` |
| 1363 | renders mobile task navigation with Token Radar as the default task | L1 | `features/cockpit/ui/CockpitMobileNav.test.tsx` |
| 1378 | uses the Signal Lab mobile task when cold-loading a Signal Lab route | L2 | `features/signal-lab/__tests__/signalLabRoute.integration.test.tsx` |
| 1390 | keeps mobile radar token clicks on the detail drawer without changing the search input | L2 | `features/live/__tests__/mobileLive.integration.test.tsx` |
| 1410 | switches mobile tasks without resetting window, scope, or selected token | L2 | `features/cockpit/__tests__/mobileTask.integration.test.tsx` |
| 1439 | returns mobile Radar and Tape tasks to the live cockpit after opening Signal Lab | L2 | `features/cockpit/__tests__/mobileTask.integration.test.tsx` |
| 1467 | exposes distinct responsive shell surfaces without duplicating Token Radar rows | L2 | `features/cockpit/__tests__/responsiveShell.integration.test.tsx` |
| 1479 | marks mobile task panels so CSS can show one task at a time | L1 | `features/cockpit/ui/CockpitMobileNav.test.tsx` |
| 1489 | renders Signal Lab pulse rows without nested source controls | L1 | `features/signal-lab/ui/SignalLabPulse.test.tsx` |

Deletion candidates: none. Every current App-level assertion maps to a lower-level or route-level test so the behavioral net survives the hard cut.

