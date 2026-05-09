# Selected Token 生产级重构 Spec 与 Plan

Date: 2026-05-05

## 背景

当前右侧 selected token drawer 已经有 `Timeline / Posts / Score / Lab / Accounts` 的骨架，但还不是生产级交易分析面板。根因不是某个文案或样式错误，而是时间模型、证据模型、传播模型和分数解释模型没有被严格分离：

- Timeline 暴露 `30s / 1m / 5m` bucket 粒度，用户却真正需要 `5m / 1h / 4h / 24h` observation window。
- Heat block 中的 `mentions_5m / mentions_1h / mentions_24h` 不是稳定的多窗口事实，而是根据当前 window 临时填充。
- Timeline 只返回有帖子出现的 buckets，无法看出静默、fade、传播断层。
- Propagation 主要是窗口内作者分布，不是按时间推进的传播结构。
- Timeline 又展示帖子列表，和 Posts tab 重复。
- Score 是可解释 heuristic ledger，不是校准概率；UI 没有足够清楚地暴露数据健康度和硬门槛。

这次重构目标是根治这些语义问题，不做旧交互兼容层。

## 第一性原理

Selected token 面板只回答四个问题：

1. **Heat:** 这个 token 在当前观察周期是否异常热？
2. **Timeline:** 这个热度如何传播，是独立扩散还是单点广播/重复刷屏？
3. **Posts:** 具体证据是什么，哪些帖子参与了当前判断，历史证据在哪里？
4. **Score:** 系统为什么给出当前 decision，哪些数据不足或风险上限限制了判断？

对应边界：

- Heat 使用 observation windows：`5m / 1h / 4h / 24h`。
- Timeline 使用后端自动 bucket：`5m -> 30s`，`1h -> 5m`，`4h -> 15m`，`24h -> 1h`。
- Posts 默认展示当前 scoring window，可切 `current_window / since_ignition / all_history`。
- Score 是 deterministic ranking ledger，不显示为概率，不宣称胜率。

## Scope

### In

- 增加 `4h` 作为一等 window。
- 移除 selected token UI 中的手动 bucket 控件。
- `/api/token-social-timeline` 改为 window-first contract，返回 `bucket` 作为派生结果。
- Timeline 返回完整 zero-filled bucket series。
- Propagation summary 增加 bucket-aware fields：`peak_posts_per_bucket`、`peak_new_authors_per_bucket`、`reproduction_rate`。
- Posts 增加 `range=current_window|since_ignition|all_history`。
- Selected token drawer 增加 detail window 与 posts range 控件。
- Score tab 增加数据健康、硬门槛和风险上限的优先展示。

### Out

- 不引入 LLM live scoring。
- 不引入 Hawkes / cascade graph / embedding clustering。
- 不把 score 标成 probability。
- 不保留旧 `30s / 1m / 5m` 右侧手动 bucket UI。
- 不给旧 timeline bucket 参数写兼容分支。

## Backend Contract

### Window Model

Public windows:

```text
5m, 1h, 4h, 24h
```

Internal auto buckets:

```text
5m  -> 30s
1h  -> 5m
4h  -> 15m
24h -> 1h
```

`1m` 不再作为 public observation window 暴露。`30s`、`1m`、`5m` 不再作为 selected-token manual bucket choices 暴露。

### `/api/token-flow`

`social_heat` 必须包含真实多窗口计数，而不是当前 window 的占位填充：

```json
{
  "window": "1h",
  "mentions": 12,
  "mentions_5m": 2,
  "mentions_1h": 12,
  "mentions_4h": 27,
  "mentions_24h": 44
}
```

Acceptance:

- 当前 window 是 `5m` 时，`mentions_1h` 仍然是过去 1h 真实 distinct event 数。
- 当前 window 是 `1h` 时，`mentions_5m` 仍然是过去 5m 真实 distinct event 数。
- `4h` 作为 token radar window 可查询、可排序、可进入 detail。

### `/api/token-social-timeline`

Request:

```text
GET /api/token-social-timeline?token_id=...&window=1h&scope=all&limit=200&cursor=...
GET /api/token-social-timeline?chain=...&address=...&window=4h&scope=all&limit=200&cursor=...
```

No public `bucket` request parameter.

Response:

```json
{
  "query": {
    "token_id": "token:eth:0x...",
    "chain": "eth",
    "address": "0x...",
    "window": "1h",
    "bucket": "5m",
    "scope": "all"
  },
  "summary": {
    "posts": 42,
    "authors": 18,
    "effective_authors": 11,
    "first_seen_ms": 1777770000000,
    "latest_seen_ms": 1777773600000,
    "phase": "expansion",
    "top_author_share": 0.26,
    "duplicate_text_share": 0.08,
    "peak_posts_per_bucket": 12,
    "peak_new_authors_per_bucket": 5,
    "reproduction_rate": 1.4
  },
  "buckets": [
    {
      "start_ms": 1777770000000,
      "end_ms": 1777770300000,
      "posts": 0,
      "authors": 0,
      "new_authors": 0,
      "watched_posts": 0,
      "duplicate_text_share": 0.0,
      "price": null,
      "price_change_from_start_pct": null
    }
  ],
  "authors": [],
  "posts": [],
  "returned_count": 0,
  "has_more": false,
  "next_cursor": null
}
```

Acceptance:

- Buckets 覆盖整个 window，即使没有 posts 也返回。
- `bucket` 由 window 自动派生。
- Timeline `posts` 仅作为 marker/page payload 保留给 API，但前端 Timeline 不再渲染完整帖子列表。
- price overlay 继续使用 snapshots，没有 snapshots 时明确显示 market pending/missing。

### `/api/token-posts`

新增 query:

```text
range=current_window | since_ignition | all_history
```

Semantics:

- `current_window`: 默认，只包含当前 selected detail window 内的 posts。
- `since_ignition`: 从该 token 当前 window 内第一条有效 mention 开始，到 now。
- `all_history`: 当前本地 evidence store 内该 token 全部历史 posts，分页返回。

Acceptance:

- `all_history` 不影响当前 score。
- Posts response 返回 `query.range` 和 `score_window`，前端必须显示当前范围。

## Algorithm Spec

### Heat V2

Keep deterministic scoring. Heat score 仍然回答“异常关注度”，不是“讨论量绝对值”。

Inputs:

- current window mentions；
- real multi-window mentions；
- previous same-size window mentions；
- EWMA z-score；
- new-burst score；
- stream share；
- watched share；
- first local evidence / first watched evidence。

Required changes:

- 修正 multi-window counts。
- `mentions_4h` 加入 contract。
- `baseline_status`、`baseline_sample_count`、`zero_slot_count` 暴露到 score ledger 的 data health。

### Propagation V2

Propagation 必须时间化。

Inputs:

- complete buckets；
- per-bucket posts；
- per-bucket authors；
- per-bucket new authors；
- top-author share；
- duplicate-text share；
- watched posts；
- seed lag；
- reproduction rate。

V1 production KISS formula:

```text
reproduction_rate =
  max(new_authors in bucket[t+1] / max(active_authors in bucket[t], 1))
```

Phase rules:

- `seed`: total posts <= 1 or authors <= 1。
- `concentration`: top author share >= 0.70 or duplicate share >= 0.50。
- `fade`: latest non-empty bucket is not in the final 40% of the window, or last two non-empty buckets decline after peak.
- `expansion`: authors >= 5, effective authors >= 4, top share < 0.35, reproduction_rate >= 1。
- `ignition`: otherwise, early multi-author growth.

### Score Ledger

Score remains:

```text
0.30 heat + 0.25 quality + 0.20 propagation + 0.15 tradeability + 0.10 timing
```

But UI must display:

- score is deterministic ranking score, not probability；
- hard risks first；
- risk caps second；
- component contributions third；
- data health always visible。

## Frontend Spec

### Selected Token Header

Keep token identity, decision, opportunity score, heat/quality/spread/timing summary.

Add detail window segmented control:

```text
5m | 1h | 4h | 24h
```

Default:

- When selecting a token, detail window starts from current radar window.
- Changing detail window does not change left radar window.

### Timeline Tab

Rename section to `heat timeline`.

Show:

- auto bucket label, e.g. `auto bucket 5m`；
- phase；
- posts；
- authors；
- effective authors；
- top share；
- reproduction；
- zero-filled bars；
- watched overlay；
- new-author overlay；
- price overlay marker；
- author lanes。

Do not show full post cards in Timeline.

### Posts Tab

Show range segmented control:

```text
window | ignition | history
```

Default `window`。

Show:

- total count；
- returned count；
- current score window；
- warning for history: `history does not all participate in current score`。

### Score Tab

Top:

- data health strip；
- hard risks；
- risk caps。

Then:

- opportunity components；
- component score cards；
- contribution rows。

## Implementation Plan

1. Add docs plan.
2. Write failing backend tests for:
   - `4h` token-flow window。
   - token-flow true multi-window `mentions_5m/1h/4h/24h`。
   - timeline no longer accepts manual bucket and returns auto bucket。
   - timeline returns complete zero-filled buckets。
   - token posts supports `range=all_history` and reports `score_window`。
3. Implement backend time model.
4. Implement real multi-window mention counts.
5. Implement auto-bucket zero-filled timeline.
6. Implement bucket-aware propagation summary fields.
7. Implement token posts range contract.
8. Write failing frontend tests for:
   - selected detail window control includes `4h`。
   - timeline no longer shows manual bucket buttons。
   - timeline no longer renders full post cards。
   - posts range control includes history warning。
9. Implement frontend types/store/query/component changes.
10. Run verification:

```bash
uv run pytest tests/test_token_flow_social_heat_contract.py tests/test_token_social_timeline_service.py tests/test_token_posts_service.py tests/test_api_http.py -q
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
cd web && npm test
cd web && npm run build
```

## Rollout Notes

- This intentionally changes API/UI contract and does not preserve old selected-token bucket controls.
- Historical evidence may be large; `all_history` must remain keyset-paginated.
- If data is sparse, the UI should say sparse/pending rather than inflate certainty.
