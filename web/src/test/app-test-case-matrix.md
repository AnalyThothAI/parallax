# App Test Case Matrix

Source: `web/src/App.test.tsx`

Purpose: Task 0 inventory before splitting the monolithic App test. Levels follow the target pyramid:

- L0: pure model/mapper/unit test
- L1: component or hook test
- L2: route integration with mocked API/socket infrastructure
- L3: Playwright golden path
- Delete: remove only when the assertion is duplicated or obsolete, with reason

No Task 0 deletion candidates were identified.

| Line | Test | Target | Notes |
|---:|---|---|---|
| 234 | renders radar rows with mock-aligned semantic fields and selected state | L2 | Live route cold-load integration |
| 265 | patches visible token-radar rows with websocket market updates | L2 | Live route plus socket cache patch |
| 305 | routes text search into the Search Intel page instead of the old evidence drawer | L3 | Golden path: topbar search submit |
| 337 | routes cashtag input to Search Intel instead of selecting the current radar token | L2 | Search route intent routing |
| 359 | routes bare uppercase input through Search Intel without local token matching | L2 | Search normalization routing |
| 380 | selects Token Radar rows into the drawer and drills into Search Intel from the drawer action | L2 | Live drawer route integration |
| 413 | opens Search Intel from the Token Radar row arrow | L2 | Radar row navigation |
| 437 | opens an evidence drawer from a non-token live tape event | L2 | Live tape interaction |
| 448 | exposes a venue link for resolved radar tokens | L1 | Token radar row/detail component |
| 459 | keeps each Token Radar metric in stable responsive slots | L1 | Token radar row component layout contract |
| 478 | renders valid token radar rows regardless of backend projection version metadata | L2 | Token radar route compatibility |
| 487 | renders fresh CEX token-radar market as tradeable instead of pending | L2 | Live route market rendering |
| 548 | renders CEX prices with precision and keeps DEX primary market value on market cap | L2 | Live route market display |
| 621 | renders token-radar timing changes from backend market baselines | L2 | Live route timing display |
| 659 | uses Signal Pulse as the trader-facing product label | L1 | Shell/navigation component copy |
| 667 | keeps Signal Pulse visible in the live cockpit and opens the shared inspector | L2 | Live cockpit plus pulse inspector |
| 691 | routes Signal Pulse notifications into the queue instead of token search | L2 | Notification route integration |
| 712 | queries the compact Signal Pulse as a fresh live feed | L2 | Query params/API contract |
| 731 | switches the left rail into the Signal Pulse workbench without losing the selected pulse item | L2 | Signal Pulse route state |
| 761 | opens Stocks from the main navigation without the token detail layout | L3 | Golden path: stocks navigation |
| 783 | marks the desktop watchlist as the left rail fill section | L1 | Cockpit side rail component |
| 795 | uses watchlist clicks as a first-class account file | L2 | Watchlist routing |
| 823 | shows watched account events when an account lens has no Signal Pulse candidates | L2 | Signal Pulse account fallback |
| 861 | renders the selected case drawer with the mock structure and no extra override controls | L2 | Live selected case drawer |
| 884 | opens Timeline by default, requests timeline/posts, and keeps token Lab as a pointer into Signal Pulse | L2 | Token detail integration |
| 919 | maps radar evidence count from source event ids instead of empty intent evidence | L0 | Token radar mapper |
| 936 | uses the resolved target symbol for identity when a mention symbol disagrees | L0 | Token radar mapper |
| 954 | does not fallback resolved target identity to the mention symbol | L0 | Token radar mapper |
| 983 | rejects token radar rows when the backend omits factor_snapshot | L0 | Token radar validation |
| 992 | rejects token radar rows when the factor snapshot omits the current attention window | L0 | Token radar validation |
| 1019 | drives selected case detail by production windows instead of manual timeline buckets | L2 | Token detail route/API integration |
| 1050 | opens replay focus mode by clicking a timeline bucket | L2 | Timeline interaction |
| 1069 | keeps Posts as the evidence surface with explicit range controls | L2 | Token posts panel integration |
| 1096 | requests catalyst post sorting from the server | L2 | Token posts query params |
| 1113 | removes narrative product surface and exposes Signal Pulse entry points | L1 | Shell/live component contract |
| 1121 | uses the Signal Pulse read model as the only Signal Pulse product source in the UI | L2 | Signal Pulse data source integration |
| 1137 | keeps settlement horizons out of the trader-facing Signal Pulse and global token radar rail | L1 | Signal Pulse UI copy/surface |
| 1152 | routes Signal Pulse toolbar filters into the Signal Pulse read model | L2 | Signal Pulse URL/API state |
| 1182 | uses the Signal Pulse cursor without duplicating aggregate summary or overlapping rows | L2 | Signal Pulse pagination |
| 1245 | keeps live compact pulse selection independent from workbench status filters | L2 | Live/Signal Lab state isolation |
| 1269 | renders Signal Pulse rows and opens the right-side inspector | L2 | Signal Pulse route integration |
| 1304 | dedupes replay/live tape rows and token tape click does not change sort mode | L2 | Live tape model plus route state |
| 1319 | shows actionable radar row context when timing has sparse market data | L1 | Token radar row component |
| 1329 | keeps replay rows visible when websocket disconnects | L2 | Live route disconnected state |
| 1337 | requests selected case detail by target identity | L2 | Token detail API params |
| 1358 | does not offer an audit page for unresolved token radar rows | L2 | Unresolved target routing |
| 1369 | realigns the drawer when the selected case disappears after a window switch | L2 | Live route selection state |
| 1383 | uses live token attribution before ambiguous cashtag matching in the tape | L2 | Live tape attribution |
| 1403 | renders mobile task navigation with Token Radar as the default task | L1 | Mobile nav component |
| 1418 | uses the Signal Pulse mobile task when cold-loading a Signal Pulse route | L2 | Signal Pulse mobile route state |
| 1430 | keeps mobile radar token clicks on the detail drawer without changing the search input | L2 | Mobile live interaction |
| 1450 | switches mobile tasks without resetting window, scope, or selected case | L2 | Mobile route/local state split |
| 1479 | returns mobile Radar and Tape tasks to the live cockpit after opening Signal Pulse | L2 | Mobile shell route ownership |
| 1507 | exposes distinct responsive shell surfaces without duplicating Token Radar rows | L1 | Responsive shell component |
| 1519 | marks mobile task panels so CSS can show one task at a time | L1 | Mobile shell component |
| 1529 | renders Signal Pulse rows without nested source controls | L1 | Signal Pulse component contract |
