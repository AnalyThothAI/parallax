# Production Notifications Phase 1/2 Design

日期：2026-05-05

状态：设计草案，等待确认后实施

范围：为 `parallax` 增加生产级通知系统的 Phase 1 和 Phase 2。Phase 1 交付网页端 in-app 通知、watchlist 红点、通知抽屉、通知 WebSocket 推送。Phase 2 在不重写核心规则的前提下接入外部通知渠道，优先通过 Apprise 统一适配 PushDeer、Telegram、WeCom Bot、WxPusher、ntfy、Gotify 等。

不在范围：Novu 全平台接入、PWA/Web Push/service worker、复杂多用户权限系统、通知工作流可视化编辑器、邮件/SMS 营销体系、自动交易执行。

## 一句话结论

通知不能是前端从表格里临时推导出来的 UI 状态，也不能直接绑定 PushDeer 或 Telegram 这种单一渠道。生产级通知的核心应该是：

```text
domain evidence -> deterministic rule evaluation -> durable notification fact
  -> in-app read model / red dots / websocket
  -> optional external delivery adapter with retries and audit
```

Phase 1 先建立自己的通知事实层和网页端体验。Phase 2 只增加投递层，不改变通知事实层。这样以后无论接 Apprise、Novu、PushDeer、Telegram、企业微信、微信类推送，核心规则和历史审计都不会被外部平台绑架。

## 第一性原理

### 1. 通知是事实，不是样式

`watchlist` 小红点、顶部铃铛、toast、外部手机推送都只是同一个通知事实的不同投影。系统必须先有可持久化、可去重、可查询、可审计的 `notification`，然后再决定它如何显示和投递。

如果只在 React 中通过 `/api/token-flow` 当前返回值做 `if score > 80 then toast`，会出现四类问题：

- 页面刷新后同一信号重复弹；
- 前端断线时丢通知；
- 无法解释“这条通知为什么出现”；
- 外部 PushDeer/Telegram 无法复用相同判定。

### 2. 规则判定必须依赖已落库的数据

当前后端已经坚持 store-first：collector 写入 evidence/entity/signal 后才发布 `/ws` live payload。通知系统必须复用这个边界。所有通知都来自 SQLite 中已提交的数据，而不是来自还没落库的内存帧。

这意味着规则引擎可以从这些稳定 read model 读取：

- `events`：watched account activity；
- `account_token_alerts`：已有 watched-account token alert；
- `event_token_attributions` + `TokenFlowService`：5m/1h token social heat、discussion quality、opportunity；
- `harness_snapshots`：closed-loop harness snapshot；
- 未来 `harness_outcomes` / `harness_credits`：结算或 credit 变更通知。

### 3. 去重比实时更重要

交易 cockpit 的通知如果噪音大，用户会很快忽略它。默认设计选择最多 5-10 秒的评估延迟，换取可解释、幂等、可恢复的通知。

每条通知必须有 `dedupe_key`。例如：

```text
watched_account_event:toly:event-123
hot_quality_token_5m:token:eth:0xabc:2026-05-05T10:35Z:social_heat_v1+discussion_quality_v1
harness_snapshot_high_score:DOG:6h:snapshot-123
```

`dedupe_key` 加唯一索引后，即使规则 worker 重启、WebSocket 重连、查询重复，也不会产生重复通知。

### 4. 读状态和通知事实分离

通知事实回答“系统发现了什么”。读状态回答“当前本地用户是否读过”。现在系统只有一个 `ws_token` 级别的本地 cockpit，不需要完整 RBAC，但仍然应该用 `notification_reads` 表预留 subscriber 边界：

```text
subscriber_key = "local"
```

这样 Phase 1 简单可用，后续如果引入多用户或 Novu，也不用重写通知事实。

### 5. 外部渠道只是投递 adapter

PushDeer、Telegram、WeCom、ntfy、Gotify 不能拥有规则语义。它们只接受已经生成的通知。Phase 2 只增加：

```text
notifications -> notification_deliveries -> AppriseDeliveryAdapter -> external provider
```

外部投递失败不会回滚通知事实，也不会影响网页端红点。

## 当前代码架构对照

### 后端

当前后端结构很适合通知系统，因为已有清晰的 read/write repository、FastAPI runtime、worker、WebSocket hub：

- `src/parallax/settings.py`：严格 Pydantic config，`extra="forbid"`。通知配置需要显式加入 `NotificationConfig`，否则用户配置会被拒绝。
- `src/parallax/api/app.py`：`CliRuntime` 集中持有 settings、repositories、workers、hub。通知需要加入 write/read repository、rule worker、delivery worker。
- `src/parallax/api/http.py`：现有 JSON API 都用 Bearer `ws_token` 鉴权。通知 API 应复用 `_authenticated_runtime()`。
- `src/parallax/api/ws.py`：`PublicWebSocketHub` 当前支持 `event` 和 `harness_update`，并按 handles/CA/symbol 做过滤。通知需要新增 `notifications` 订阅布尔字段，避免没有 `event` 的 payload 被现有 matcher 丢弃。
- `src/parallax/collector/service.py`：写库成功后发布 matched watched event。通知不应该直接塞进 collector 逻辑，避免 collector 变成业务规则中心。
- `src/parallax/pipeline/ingest_service.py`：事件入库、实体抽取、token attribution、account alert、enrichment job enqueue 在一个事务中完成。Phase 1 不把通知生成塞进该事务，避免 token-flow score 依赖后续 market observation 时出现二义性。
- `src/parallax/retrieval/token_flow_service.py`：`social_heat`、`discussion_quality`、`opportunity` 目前是查询时计算，不是表。高分 token 通知必须通过规则 worker 周期性读取 `TokenFlowService` 并物化。
- `src/parallax/storage/sqlite_schema.py`：当前 `SCHEMA_VERSION = 11`。通知表需要升到 `12`。
- `src/parallax/storage/sqlite_client.py`：`sqlite_health_check()` 有 operational probes。通知表加入后应增加 probe，确保生产启动时能发现 schema 损坏。

### 前端

当前前端是单页 cockpit：

- `web/package.json`：React 19、TanStack Query、Zustand、lucide、reconnecting-websocket。可以直接接 `sonner` 作为成熟 toast 层，也可以不引入大型 UI 框架。
- `web/src/App.tsx`：顶部状态栏、watchlist rail、Token Radar、Live Tape、Signal Lab、detail drawer 都集中在这里。Phase 1 要控制改动范围，新增 `NotificationBell`、`NotificationDrawer`、`WatchlistNotificationDot`，不要把通知逻辑散落进 token row。
- `web/src/api/useIntelSocket.ts`：当前只处理 `ready` 和 `event`。需要识别 `notification`，并把 `notifications: true` 放进 subscribe 消息。
- `web/src/api/types.ts`：新增通知 API contract 类型。
- `web/src/store/useTraderStore.ts`：当前存 UI filter 和 selection。通知 unread 计数不应放这里作为事实来源，应该由 TanStack Query cache 和后端 read state 驱动。

## 外部方案调研

### Apprise

Apprise 是最适合 Phase 2 的外部投递层。官方文档把它定位为 notification routing library，标准化 100+ 服务的发送方式，并提供 Python Library、CLI、API Server 三种形态。对本项目来说，内嵌 Python Library 是最小可行接入，因为后端已经是 Python/FastAPI，不需要额外部署 Apprise API Server。

调研要点：

- 官方说明 Apprise 用统一 URL 语法配置目的地，应用逻辑不需要学习每个 provider 的 payload。
- Python API 使用 `Apprise().add(url)` 和 `notify(title=..., body=...)`。
- `AppriseConfig` 支持本地文件、远程 URL、内存配置、tags/filtering。
- PyPI 支持列表包含 PushDeer、Telegram、WeCom Bot、WxPusher、ntfy、Gotify、ServerChan、Slack、Discord 等。
- Markdown/HTML/Text 可以通过 `body_format=NotifyFormat.MARKDOWN` 声明，Apprise 会按目标渠道能力转换。

推荐用法：

```python
from apprise import Apprise, NotifyFormat

apobj = Apprise()
apobj.add("pushdeer://pushKey")
ok = apobj.notify(
    title="DOG 5m heat 86",
    body="**DOG** social_heat=86 quality=78",
    body_format=NotifyFormat.MARKDOWN,
)
```

Phase 2 不先部署 Apprise API Server。只有当多个本地服务都要共用同一通知网关时，再改成 Apprise API Server 或远程 `AppriseConfig`。

### PushDeer

PushDeer 官方在线版的发送接口非常简单：注册设备，创建 key，然后访问 `/message/push`，支持 text/image/markdown。官方文档给出的 Markdown 形式是：

```text
https://api2.pushdeer.com/message/push?pushkey=<key>&text=标题&desp=<markdown>&type=markdown
```

也可以 POST form-urlencoded。Phase 2 不直接写 PushDeer adapter，因为 Apprise 已支持 `pushdeer://` 和 `pushdeers://`。只有 Apprise 在某个 PushDeer 自托管域名上出现兼容问题时，再添加一个很薄的 direct adapter。

### Telegram / WeCom / WxPusher / ServerChan

这些属于“个人或群聊通知渠道”。它们共同的问题是：

- 密钥、chat id、bot token、webhook key 都是 secrets；
- 消息格式差异大；
- 失败码和限速策略不同；
- 有些渠道偏 Markdown，有些只适合短文本。

因此 Phase 2 使用 Apprise URL 统一封装，不在业务代码里写多套 webhook payload。配置中只暴露 channel key、provider URL、severity filter、rule filter。

### ntfy

ntfy 适合极简自托管或公共 topic 推送。官方文档强调可以通过 HTTP PUT/POST 从任何电脑发到手机或桌面。它适合作为：

- 个人手机/桌面兜底推送；
- 开发环境验证外部通知；
- 不想依赖 Telegram/PushDeer 的自托管渠道。

注意 topic 名通常不需要预创建，但公开 topic 名应避免可猜测。生产配置中应提醒用户使用高熵 topic 或自托管鉴权。

### Gotify

Gotify 是简单的自托管消息服务器，提供 REST API、WebSocket、Web UI、Android client。它适合更强调自托管审计和本地 Web UI 的用户。Phase 2 通过 Apprise `gotify://`/`gotifys://` 接入即可。

### Novu

Novu 是成熟通知平台，有 Inbox、workflow、provider integrations、preferences、push device token 管理等。它适合多用户产品通知中心，但 Phase 1/2 不作为主路径，原因是：

- 当前项目是本地/单 cockpit token，不是多租户 SaaS；
- Novu 会引入 subscriber/workflow/environment/provider dashboard 体系；
- push 还需要管理 FCM/APNS/OneSignal 等 device token；
- 这会把“规则事实”和“投递平台”过早耦合。

Novu 保留为 Phase 3 的可选 external provider 或 replacement inbox。设计上保留 `subscriber_key`、`notification_deliveries.provider`、`payload_json`，使以后可以把本地通知事实触发到 Novu workflow。

### Browser Push / Notifications API

浏览器系统通知分两类：

- Notifications API：前台页面请求权限后显示系统通知。MDN 说明它需要 secure context，且不是所有主流浏览器都完整支持。
- Push API：需要 service worker，能在网页不在前台甚至未加载时接收服务器推送。MDN 同时提醒 PushManager subscription 要防 CSRF/XSRF，endpoint capability URL 要保密。

Phase 1/2 不接浏览器 Push。原因：

- 当前服务多用于 localhost 或内网，HTTPS/service worker/origin 权限会引入部署复杂度；
- Push API 需要订阅端点持久化、VAPID key、subscription 生命周期管理；
- 外部手机通知已有 Apprise + PushDeer/Telegram/ntfy 更直接。

Phase 1 可以在页面打开时用 Sonner toast 或系统 Notifications API 的前台通知，但不要把它设计成后台离线推送。

## 目标体验

### Phase 1：网页端 in-app

用户打开 cockpit 后：

- 顶部看到铃铛按钮，显示未读总数和最高 severity；
- 左侧 watchlist 每个 handle 可以出现小红点，表示最近 1h 有未读 watched account activity；
- 点击铃铛打开通知抽屉，看到按时间倒序排列的通知；
- 可以按 `All / Unread / Accounts / Tokens / Harness` 过滤；
- 点击通知跳转到已有搜索或详情上下文：
  - watched account activity -> `runSearch("@handle")`；
  - hot token -> select matching token if current radar list存在，否则 `runSearch("$SYMBOL")`；
  - harness snapshot -> open Signal Lab and select chain if available；
- 收到 live notification 时，前端 Query cache 更新，小红点即时变化；
- 高 severity 通知出现 toast，toast 不作为唯一记录。

默认 Phase 1 规则：

| Rule | Source | Predicate | Target | Severity | Dedup |
| --- | --- | --- | --- | --- | --- |
| `watched_account_activity` | `events` | `is_watched=1` and author in configured handles | account handle | info | per event |
| `watched_account_token_alert` | `account_token_alerts` | existing account token alert | event/token | warning | per alert |
| `hot_quality_token_5m` | `TokenFlowService(window=5m)` | `social_heat.score >= 80` and `discussion_quality.score >= 70` and `timing.chase_risk=false` | token | high | per token + 5m bucket + score versions |
| `quality_token_5m` | `TokenFlowService(window=5m)` | `discussion_quality.score >= 80` and `social_heat.score >= 65` | token | warning | per token + 5m bucket |
| `harness_snapshot_high_score` | `harness_snapshots` | `combined_score >= 0.8` | harness snapshot / asset | high | per snapshot |

`hot_quality_token_5m` 默认用 `quality >= 70` 而不是 `quality >= 80`，因为很多真正有用的早期信号可能热度先上来、文本质量略低。`quality_token_5m` 单独捕捉高质量讨论。

### Phase 2：外部投递

用户配置外部渠道后：

- 高等级通知可以发送到 PushDeer/Telegram/WeCom/ntfy/Gotify；
- 每条外部投递有可查状态：pending/running/sent/failed/dead/skipped；
- 失败自动 retry，达到 max attempts 后 dead；
- 外部渠道不可用不影响 in-app 通知；
- 默认只把 `warning` 和 `high` 以上投递到外部，`info` 只留 in-app；
- 每个规则可选择 channels；
- 每个 channel 可选择 severity threshold；
- 支持 dry run/log provider，方便验证格式。

## 数据模型

### `notification_rules`

规则配置和默认规则快照。默认规则由 migration seed 或 runtime ensure upsert 创建。

```sql
CREATE TABLE notification_rules (
  rule_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  source TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  severity TEXT NOT NULL,
  window TEXT,
  predicate_json TEXT NOT NULL DEFAULT '{}',
  target_channels_json TEXT NOT NULL DEFAULT '["in_app"]',
  cooldown_ms INTEGER NOT NULL DEFAULT 0,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);
```

字段说明：

- `source`: `event`, `account_alert`, `token_flow`, `harness_snapshot`。
- `severity`: 默认 severity，具体通知可升级或降级。
- `predicate_json`: 阈值、scope、limit、risk filters。
- `target_channels_json`: Phase 1 只有 `["in_app"]`；Phase 2 可包含 `["in_app", "pushdeer", "telegram"]`。

### `notifications`

通知事实表。

```sql
CREATE TABLE notifications (
  notification_id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL REFERENCES notification_rules(rule_id) ON DELETE CASCADE,
  dedupe_key TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  target_label TEXT NOT NULL,
  event_id TEXT,
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  action_url TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  occurrence_count INTEGER NOT NULL DEFAULT 1,
  first_seen_at_ms INTEGER NOT NULL,
  last_seen_at_ms INTEGER NOT NULL,
  expires_at_ms INTEGER,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL
);
```

`target_kind` 使用有限集合：

```text
account | token | harness_snapshot | event | system
```

`payload_json` 保存 UI 跳转和解释字段，例如：

```json
{
  "handle": "toly",
  "symbol": "DOG",
  "token_id": "token:eth:0x...",
  "scores": {
    "social_heat": 86,
    "discussion_quality": 78,
    "opportunity": 82
  },
  "reasons": ["z_score_above_3", "independent_expansion"],
  "risks": [],
  "query": "$DOG"
}
```

### `notification_reads`

读状态表。

```sql
CREATE TABLE notification_reads (
  subscriber_key TEXT NOT NULL,
  notification_id TEXT NOT NULL REFERENCES notifications(notification_id) ON DELETE CASCADE,
  read_at_ms INTEGER,
  dismissed_at_ms INTEGER,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  PRIMARY KEY(subscriber_key, notification_id)
);
```

Phase 1 使用 `subscriber_key="local"`。如果一条通知没有 read row，就视为 unread。

### `notification_deliveries`

Phase 2 外部投递状态表。

```sql
CREATE TABLE notification_deliveries (
  delivery_id TEXT PRIMARY KEY,
  notification_id TEXT NOT NULL REFERENCES notifications(notification_id) ON DELETE CASCADE,
  channel_key TEXT NOT NULL,
  provider TEXT NOT NULL,
  status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  next_run_at_ms INTEGER NOT NULL,
  last_error TEXT,
  response_json TEXT,
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(notification_id, channel_key)
);
```

状态集合：

```text
pending | running | sent | failed | dead | skipped
```

## 后端模块设计

### `storage/notification_repository.py`

唯一负责通知表读写。核心方法：

```python
class NotificationRepository:
    def upsert_rule(self, rule: NotificationRuleInput, *, commit: bool = True) -> dict: ...
    def active_rules(self, *, source: str | None = None) -> list[dict]: ...
    def insert_notification(self, notification: NotificationInput, *, commit: bool = True) -> dict | None: ...
    def list_notifications(self, *, subscriber_key: str, status: str, kind: str | None, limit: int) -> dict: ...
    def summary(self, *, subscriber_key: str, window_ms: int) -> dict: ...
    def mark_read(self, *, subscriber_key: str, notification_id: str, now_ms: int, commit: bool = True) -> bool: ...
    def mark_all_read(self, *, subscriber_key: str, before_ms: int, commit: bool = True) -> int: ...
    def enqueue_deliveries(self, *, notification: dict, channels: list[str], commit: bool = True) -> int: ...
    def claim_pending_delivery(self, *, now_ms: int) -> dict | None: ...
    def complete_delivery(self, *, delivery_id: str, response: dict | None, commit: bool = True) -> None: ...
    def fail_delivery(self, *, delivery_id: str, error: str, now_ms: int, commit: bool = True) -> None: ...
```

`insert_notification()` 使用 `dedupe_key` 唯一索引保证幂等。重复时不创建新通知，只更新 `occurrence_count` 和 `last_seen_at_ms`，但 Phase 1 默认不重复发布 WebSocket。

### `pipeline/notification_rules.py`

纯函数规则定义，不访问外部服务。负责把 domain read model 转成 `NotificationInput`。

核心 evaluator：

```python
class NotificationRuleEngine:
    def evaluate_events(self, *, since_ms: int, now_ms: int) -> list[NotificationInput]: ...
    def evaluate_account_alerts(self, *, since_ms: int, now_ms: int) -> list[NotificationInput]: ...
    def evaluate_token_flow(self, *, window: str, now_ms: int) -> list[NotificationInput]: ...
    def evaluate_harness_snapshots(self, *, since_ms: int, now_ms: int) -> list[NotificationInput]: ...
```

依赖注入：

- `EvidenceRepository`
- `SignalRepository`
- `TokenRepository`
- `HarnessRepository`
- `TokenFlowService`
- runtime settings handles

### `pipeline/notification_worker.py`

周期性 worker，类似 `MarketObservationWorker` / `EnrichmentWorker`：

```text
loop every notifications.poll_interval_seconds
  read active rules
  evaluate sources
  insert notification facts
  enqueue external deliveries for phase2 channels
  publish new in-app notifications through hub
```

为什么用 worker 而不是 ingest 内联：

- `TokenFlowService` 是窗口级 read model，不是事件内联规则；
- market observation 可能在事件后几秒改变 timing/tradeability/opportunity；
- worker 重启后可从 SQLite 恢复，不依赖进程内状态；
- collector 保持 upstream adapter 角色，不承担产品规则。

默认 `poll_interval_seconds = 5`，`token_flow_limit = 80`。这和前端当前 `/api/token-flow` 每 10 秒刷新接近，用户体验足够实时。

### `pipeline/notification_delivery.py`

Phase 2 外部投递 worker。

```python
class NotificationDeliveryWorker:
    async def run(self) -> None: ...
```

`AppriseDeliveryAdapter`：

```python
class AppriseDeliveryAdapter:
    def send(self, *, channel: NotificationChannel, notification: dict) -> DeliveryResult: ...
```

发送格式：

```text
title = "[GMGN] {severity.upper()} {notification.title}"
body = markdown body containing:
  - body summary
  - scores / reasons / risks
  - local action URL if configured
```

Phase 2 不把 Apprise URL 写入 `notification_deliveries`，只写 `channel_key`。URL 留在 config，避免 secret 进入 SQLite。

## API 设计

所有接口复用现有 Bearer token。

### `GET /api/notifications`

Query：

```text
status=unread|all|dismissed
kind=account|token|harness_snapshot|event|system
limit=50
```

Response：

```json
{
  "ok": true,
  "data": {
    "subscriber_key": "local",
    "items": [
      {
        "notification_id": "notification:...",
        "rule_id": "hot_quality_token_5m",
        "target_kind": "token",
        "target_label": "DOG",
        "severity": "high",
        "title": "DOG 5m heat 86 / quality 78",
        "body": "DOG crossed the hot-quality threshold.",
        "read_at_ms": null,
        "created_at_ms": 1777980000000,
        "payload": {
          "symbol": "DOG",
          "scores": {"social_heat": 86, "discussion_quality": 78}
        }
      }
    ],
    "unread_count": 7
  }
}
```

### `GET /api/notification-summary`

Query:

```text
window=1h
```

Response:

```json
{
  "ok": true,
  "data": {
    "window": "1h",
    "unread_total": 7,
    "highest_severity": "high",
    "by_kind": {"account": 3, "token": 4, "harness_snapshot": 0},
    "watchlist": [
      {"handle": "toly", "unread_count": 2, "latest_at_ms": 1777980000000},
      {"handle": "traderpow", "unread_count": 1, "latest_at_ms": 1777979000000}
    ]
  }
}
```

### `POST /api/notifications/{notification_id}/read`

Marks one notification read for `subscriber_key="local"`.

### `POST /api/notifications/read-all`

Body:

```json
{"kind": "account", "before_ms": 1777980000000}
```

`kind` optional. Used by drawer bulk read and watchlist section.

### `GET /api/notification-deliveries`

Phase 2 only. Returns delivery audit for debugging external channels.

## WebSocket 设计

### Subscribe message

Frontend changes from:

```json
{"type": "subscribe", "handles": ["toly"], "replay": 25}
```

to:

```json
{"type": "subscribe", "handles": ["toly"], "replay": 25, "notifications": true}
```

Backend adds:

```python
notifications: bool = False
```

to `ClientSubscription`.

### Live notification payload

```json
{
  "type": "notification",
  "notification": {
    "notification_id": "notification:hot_quality_token_5m:...",
    "rule_id": "hot_quality_token_5m",
    "target_kind": "token",
    "target_label": "DOG",
    "severity": "high",
    "title": "DOG 5m heat 86 / quality 78",
    "body": "DOG crossed the hot-quality threshold.",
    "payload": {
      "symbol": "DOG",
      "scores": {
        "social_heat": 86,
        "discussion_quality": 78,
        "opportunity": 82
      }
    },
    "created_at_ms": 1777980000000
  }
}
```

Replay remains HTTP-based. WebSocket only pushes new notifications.

## Frontend design

### Components

Create focused components:

```text
web/src/components/NotificationBell.tsx
web/src/components/NotificationDrawer.tsx
web/src/components/WatchlistNotificationDot.tsx
web/src/components/NotificationToastBridge.tsx
```

Responsibilities:

- `NotificationBell`: displays unread total and opens drawer.
- `NotificationDrawer`: filters notifications, mark read, mark all read, click actions.
- `WatchlistNotificationDot`: tiny red dot/count for each watchlist handle.
- `NotificationToastBridge`: observes live socket notifications and emits Sonner toast for `warning/high`.

### Data flow

```text
useQuery(["notification-summary", "1h"]) -> bell + watchlist red dots
useQuery(["notifications", filter]) -> drawer
useIntelSocket -> notification events -> queryClient.setQueryData / invalidate
mutation markRead -> optimistic update -> invalidate summary
```

### UI placement

Desktop:

- Bell button in `topbar`, near refresh.
- Watchlist dot inside existing `.watchlist button`.
- Drawer overlays from right, not nested inside detail drawer.

Mobile:

- Bell remains in topbar.
- Drawer full-screen sheet.
- Watchlist red dots only appear when watchlist controls are visible; main radar is not displaced.

### Sonner usage

Add dependency:

```json
"sonner": "^2.0.7"
```

Use it only for transient toast. The drawer and red dots are custom because they need domain-specific grouping and actions.

No notification fact lives only in Sonner state.

## Settings design

Extend `config.yaml`:

```yaml
notifications:
  enabled: true
  poll_interval_seconds: 5
  delivery_poll_interval_seconds: 5
  retention_days: 14
  subscriber_key: "local"
  token_flow_limit: 80
  external_min_severity: "warning"
  rules:
    watched_account_activity:
      enabled: true
      channels: ["in_app"]
    watched_account_token_alert:
      enabled: true
      channels: ["in_app"]
    hot_quality_token_5m:
      enabled: true
      channels: ["in_app"]
      social_heat_min: 80
      discussion_quality_min: 70
      opportunity_min: 0
      suppress_chase_risk: true
      cooldown_seconds: 900
    quality_token_5m:
      enabled: true
      channels: ["in_app"]
      discussion_quality_min: 80
      social_heat_min: 65
      cooldown_seconds: 900
    harness_snapshot_high_score:
      enabled: true
      channels: ["in_app"]
      combined_score_min: 0.8
  channels:
    pushdeer:
      enabled: false
      provider: "apprise"
      url: "pushdeer://pushKey"
      min_severity: "high"
    telegram:
      enabled: false
      provider: "apprise"
      url: "tgram://bot_token/chat_id"
      min_severity: "warning"
    wecom:
      enabled: false
      provider: "apprise"
      url: "wxwork://bot_key"
      min_severity: "warning"
    ntfy:
      enabled: false
      provider: "apprise"
      url: "ntfys://topic"
      min_severity: "warning"
```

`config` CLI should redact channel URLs:

```json
"notifications": {
  "enabled": true,
  "channels": [{"key": "pushdeer", "enabled": false, "provider": "apprise", "url_configured": true}]
}
```

## Retention and cleanup

Phase 1 adds `NotificationRepository.delete_expired(now_ms)` but only calls it opportunistically in worker once per hour. Default retention:

- notifications: 14 days;
- deliveries: same as notification;
- reads cascade with notification delete.

This keeps SQLite bounded without adding a new ops command.

## Testing strategy

### Unit tests

- Schema creates four notification tables and remains idempotent.
- Repository inserts notification once per `dedupe_key`.
- Repository summary groups unread by kind and watchlist handle.
- Rule engine creates:
  - watched account event notification;
  - watched account token alert notification;
  - hot quality token notification when score predicates pass;
  - no hot token notification when `timing.chase_risk=true`;
  - harness snapshot high score notification.
- Delivery worker:
  - creates delivery rows for external channels in Phase 2;
  - marks sent on adapter success;
  - retries with backoff and marks dead after max attempts.

### API tests

- Unauthorized notification endpoints return 401.
- `GET /api/notifications` returns unread/read state.
- `GET /api/notification-summary` returns watchlist counts.
- `POST /api/notifications/{id}/read` updates summary.
- `POST /api/notifications/read-all` supports kind-filtered bulk read.

### WebSocket tests

- Auth + subscribe with `notifications=true` receives live notification.
- Subscribe without notifications does not receive notification.
- Existing event replay tests still pass.
- Harness update routing unchanged.

### Frontend tests

- Bell shows unread count.
- Watchlist handle renders red dot/count from summary.
- Drawer lists unread notifications and mark read updates UI.
- Live socket notification updates query cache.
- High severity live notification calls Sonner toast once.

### Verification commands

```bash
uv run pytest
uv run ruff check .
uv run python -m compileall src tests
cd web && npm test
cd web && npm run typecheck
cd web && npm run build
```

## Risk controls

### Noise control

Defaults are conservative:

- external channels disabled by default;
- `info` never external by default;
- hot token notifications suppress chase-risk tokens;
- 5m token rules have cooldown;
- dedupe key prevents repeated notifications.

### Data correctness

Every notification stores rule id, source, target, payload, score versions, reasons, and risks. A notification can always be explained from its payload and source rows.

### Failure isolation

External delivery is async. A failed PushDeer/Telegram request only updates `notification_deliveries`; it does not break `/ws`, collector, token flow, or harness workers.

### Security

- Channel URLs are secrets and must not be exposed through `/api/bootstrap`, `/api/status`, `config` CLI, or frontend bundle.
- Browser Push is deferred because it introduces service worker subscription endpoints that must be protected as capability URLs.
- Notification APIs reuse Bearer `ws_token`.

## Rollout plan

### Phase 1 rollout

1. Add schema/repository/rule engine/worker.
2. Add notification HTTP APIs.
3. Add WebSocket notification subscription.
4. Add frontend bell/drawer/watchlist dots.
5. Enable only `in_app` channels.
6. Run full Python and web test suites.

### Phase 2 rollout

1. Add `apprise>=1.10.0`.
2. Add external channel settings with redacted config output.
3. Add `notification_deliveries` worker and Apprise adapter.
4. Add delivery audit API and CLI query.
5. Verify with `log://` or local fake adapter first.
6. Enable PushDeer or ntfy in config and validate one real delivery.

## Explicit non-goals

- No Novu service deployment in Phase 1/2.
- No service worker or browser background push in Phase 1/2.
- No rule editor UI.
- No per-user RBAC.
- No real trading actions from notifications.
- No direct provider-specific webhook code unless Apprise cannot support a required provider.

## Research references

- Apprise introduction and Python Library/API Server split: https://appriseit.com/getting-started/
- Apprise configuration and tags: https://appriseit.com/library/configuration/
- Apprise supported services including PushDeer, Telegram, WeCom Bot, WxPusher, ntfy, Gotify: https://pypi.org/project/apprise/
- Apprise message formatting and `NotifyFormat.MARKDOWN`: https://appriseit.com/getting-started/formatting/
- PushDeer official send API: https://www.pushdeer.com/official.html
- ntfy HTTP push model: https://docs.ntfy.sh/
- Gotify REST/WebSocket/Web UI model: https://gotify.net/
- Novu provider integration model: https://docs.novu.co/platform/integrations
- Novu push provider/device token model: https://docs.novu.co/platform/integrations/push
- MDN Push API service worker/security model: https://developer.mozilla.org/en-US/docs/Web/API/Push_API
- MDN Notifications API permissions/secure context: https://developer.mozilla.org/en-US/docs/Web/API/Notifications_API
