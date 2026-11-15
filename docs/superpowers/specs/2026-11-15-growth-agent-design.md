# Growth Agent 增长闭环设计

- **状态**：Approved for planning（2026-11-15 评审通过；第一份实现计划覆盖 Phase 0 + 模块 2）
- **日期**：2026-11-15
- **范围**：Opportunity Scout 之上的四条增长流水线：社媒截流、生命周期触达、pSEO、内容二创
- **关联文档**：
  - [GROWTH_AGENT_TRACKING.md](../../../GROWTH_AGENT_TRACKING.md)
  - [DEVELOPMENT_TRACKING.md](../../../DEVELOPMENT_TRACKING.md)
  - [business_plan.md](../../../business_plan.md)

---

## 1. 背景与目标

Opportunity Scout 已经是一个可用的本地机会研究工作台：Provider Registry 采集公开信号，AI Analyzer 按评分卡输出 `build / verify / drop`，机会库和获取闭环已经落库。它解决的是“发现机会”，但还没有解决“把机会变成增长”。

Growth Agent 要补上四条流水线：

1. **模块 2：社媒截流** —— 在 Reddit / HN 找到高意图求助帖，生成共情回复，人工审批后手动发送。
2. **模块 4：生命周期触达** —— 基于注册、配额、取消事件，发一对一的创始人邮件，挽回流失。
3. **模块 1：pSEO** —— 批量发现低竞争关键词，生成结构化文章，走 PR 发布并跟踪收录。
4. **模块 3：内容二创** —— 把 GitHub Release 变成 X / 小红书 / Product Hunt / V2EX 物料。

### 1.1 产品定位

**先自用，架构预留多租户。** v1 只服务一个租户 / 一个工作区；所有增长表从第一天带 `tenant_id` + `workspace_id`，RLS 兜底，避免以后迁移。

### 1.2 市场优先级

**出海优先**：Reddit、X、Google、Hacker News、Product Hunt。中文平台（知乎、小红书、V2EX、即刻、5118）作为第二阶段。

### 1.3 成功指标

| 模块 | 指标 | v1 目标 |
|---|---|---|
| 模块 2 | 每周合格线索数 | ≥ 20 |
| 模块 2 | 人工审批通过率 | ≥ 50% |
| 模块 2 | 回复率 | ≥ 15% |
| 模块 4 | 激活邮件 7 日激活提升 | 相对基线 +10% |
| 模块 4 | 取消挽留率 | ≥ 8% |
| 模块 4 | 退订率 | < 2% |
| 模块 4 | 投诉率 | < 0.1% |
| 模块 1 | 每周发布文章数 | 5–10 篇 |
| 模块 1 | 发布后 14 天收录率 | ≥ 60% |
| 模块 3 | 每个 Release 物料产出时间 | < 5 分钟 |
| 模块 3 | 单条物料互动率 | 相对基线 +20% |

这些是启动目标，不是承诺；前 4 周按真实数据校准。

### 1.4 非目标

- 不自动发帖、不自动评论、不自动私信、不自动点赞。
- 不抓取登录后内容，不使用用户密码 / Cookie 爬虫。
- 不购买邮件名单，不做群发。
- 不承诺 Google 即时收录。
- 不复制竞品文案；只拆解结构，重新创作。
- v1 不做完整多租户计费、团队权限和自助注册。

---

## 2. 设计原则

1. **确定性工程包住不确定运营。** 采集、去重、评分、状态、重试、审计由代码保证；文案和判断由 LLM 提供，但必须经过结构化校验。
2. **人在回路。** 社媒回复、内容发布、pSEO 合并、激活邮件都需要人工审批或人工执行。
3. **只读公开数据。** 采集只走官方 API 或公开页面；不绕过登录、验证码、反爬。
4. **幂等优先。** 每个外部事件、任务、消息都有唯一键；重复投递不产生重复副作用。
5. **可审计。** 谁在什么时候批准了什么、发了什么、结果如何，都能追溯。
6. **最小权限。** n8n 不直写业务表；密钥只在后端 / Vault；前端不接触 AI / 平台密钥。
7. **YAGNI。** v1 只做 Reddit + HN、只做英文 pSEO、只做人工发布；X API、中文平台、自动合并后置。

---

## 3. 总体架构

```text
┌──────────────────────────────────────────────────────────────┐
│ 外部事件源                                                   │
│ PostHog / Supabase Webhook / Stripe / GitHub / Resend        │
│ Reddit / HN / DataForSEO / Serper / Search Console           │
└───────────────────────────┬──────────────────────────────────┘
                            │ webhook / poll
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ n8n（自托管）                                                 │
│ cron、webhook 验签、飞书卡片、连接器、周报触发                │
│ 不直写业务表；只调用 Python /internal/*，写 delivery_log 原始回执 │
└───────────────────────────┬──────────────────────────────────┘
                            │ service token
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ Python FastAPI Worker                                        │
│ 状态机、去重、评分、LLM 调用、爬取、发送、质量门、内链图谱     │
│ 复用 opportunity_core：providers / signal / analyzer         │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
                ▼                              ▼
┌──────────────────────────────┐   ┌───────────────────────────┐
│ Supabase Postgres            │   │ 外部 API                   │
│ Auth / RLS / Vault / Storage │   │ DataForSEO / Serper        │
│ Realtime / Backups           │   │ Reddit / HN / Resend       │
└──────────────────────────────┘   │ Stripe / GitHub / GSC      │
                                   └───────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────┐
│ Admin UI（可选，v1 最小）                                     │
│ React / TypeScript：审批队列、任务状态、漏斗看板、配置         │
└──────────────────────────────────────────────────────────────┘
```

### 3.1 组件职责

| 组件 | 负责 | 不负责 |
|---|---|---|
| **Supabase Postgres** | 单一事实源、RLS、Auth、Vault、Storage、Realtime | 业务状态机、LLM 调用 |
| **n8n** | cron、webhook 入口、飞书卡片、平台连接器、周报触发 | 业务表写入、评分、内容生成 |
| **Python Worker** | 状态机、幂等、评分、生成、质量门、发送、审计 | UI、长期定时（交给 n8n） |
| **Admin UI** | 人工审批、配置、看板 | 直接调用外部平台密钥 |
| **`opportunity_core`** | Provider 适配、Signal 模型、Analyzer 评分卡 | 增长业务表、平台发布 |

### 3.2 为什么 Python 拥有状态机

增长流程的核心是“多步、可重试、有副作用”的状态机：发现 → 评分 → 草稿 → 审批 → 发送 → 跟进 → 转化。Python 在爬取、LLM SDK、数据处理和现有 `opportunity_core` 复用上最成熟；TypeScript 只做 Admin UI；Go 只在未来需要独立高并发爬虫时引入。状态机集中在 Python，避免 n8n 工作流和业务代码各维护一套状态。

### 3.3 n8n 边界

- n8n **可以**：接收 webhook、验签、归一化、定时触发、发飞书卡片、调用 Python `/internal/*`、写 `delivery_log` 原始回执。
- n8n **不可以**：直接更新 `social_leads`、`outreach_messages`、`content_queue`、`growth_keywords` 等业务表；不可以直接调用 LLM 生成最终文案；不可以保存平台密钥到工作流明文。
- 所有业务写入通过 Python `/internal/*`，带 `X-Service-Token` 和 `tenant_id`。

---

## 4. 多租户与安全

### 4.1 租户模型

- 所有增长表带 `tenant_id uuid not null` + `workspace_id uuid not null`。
- `tenants`、`workspaces`、`memberships` 三张基础表。
- v1 只创建一个 tenant + workspace；多租户能力通过字段和 RLS 预留。

### 4.2 RLS

```sql
create policy tenant_isolation on social_leads
  using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
```

- 服务角色（Python Worker）使用 service role key，绕过 RLS，但必须在应用层强制带 `tenant_id`。
- 匿名 / 普通用户只能看到自己 tenant 的数据。
- 所有 `INSERT` 强制 `tenant_id` 来自 JWT，不接受客户端传入。

### 4.3 密钥管理

| 密钥 | 存放 |
|---|---|
| Supabase service role | Python Worker 环境变量 |
| DataForSEO / Serper / Resend / Stripe / GitHub App | Supabase Vault，按 tenant 加密 |
| 飞书 bot token / signing secret | Supabase Vault |
| AI API key | Supabase Vault 或 Worker 环境变量 |
| 前端 | 不接触任何平台密钥 |

### 4.4 审计

- `audit_log`：`tenant_id`、`actor_type`（user/service/n8n）、`actor_id`、`action`、`entity_type`、`entity_id`、`before`、`after`、`created_at`。
- 审批、发送、发布、退订、优惠券核销必须写审计。
- 审计日志只追加，不更新、不删除。

---

## 5. 通用数据模型与机制

### 5.1 通用列

所有核心业务表：

```sql
id uuid primary key default gen_random_uuid(),
tenant_id uuid not null,
workspace_id uuid not null,
status text not null,
version int not null default 1,
created_at timestamptz not null default now(),
updated_at timestamptz not null default now()
```

状态用 `text + CHECK`，不用数据库 enum，便于演进：

```sql
status text not null check (status in (...))
```

平台、渠道、内容类型这类**快速变化**的维度不用 `CHECK`，改用 lookup table + 应用层校验（见 11.3），避免每加一个平台就改迁移。

### 5.2 任务队列 `pipeline_runs`

```sql
id uuid primary key,
tenant_id uuid not null,
pipeline text not null,          -- social / lifecycle / pseo / repurpose
task_type text not null,
payload jsonb not null,
status text not null,            -- queued / running / succeeded / failed / dead
idempotency_key text not null unique,
priority int not null default 100,
run_after timestamptz not null default now(),
locked_at timestamptz,
locked_by text,
attempts int not null default 0,
max_attempts int not null default 5,
last_error text,
created_at timestamptz not null default now(),
updated_at timestamptz not null default now()
```

取任务：

```sql
update pipeline_runs
set status = 'running', locked_at = now(), locked_by = $worker
where id = (
  select id from pipeline_runs
  where status = 'queued' and run_after <= now()
  order by priority, run_after
  for update skip locked
  limit 1
)
returning *;
```

索引：`(status, priority, run_after)`、`(tenant_id, status)`。v1 用一张表 + `pipeline`/`task_type` 逻辑分池；达到 11.10 的阈值再拆物理队列。

- 失败指数退避：`run_after = now() + interval '1 minute' * 2^attempts`。
- 超过 `max_attempts` → `dead`，告警飞书。
- 同一 `idempotency_key` 只允许一个任务。

### 5.3 Outbox

业务状态和外部副作用分开：

```sql
outbox_messages (
  id uuid primary key,
  tenant_id uuid not null,
  topic text not null,             -- email.send / feishu.card / github.commit
  payload jsonb not null,
  status text not null,            -- pending / sending / sent / failed / dead
  idempotency_key text not null unique,
  attempts int not null default 0,
  next_attempt_at timestamptz not null default now(),
  last_error text,
  created_at timestamptz not null default now()
)
```

- 业务事务同时写业务表和 `outbox_messages`。
- Sender 独立进程 / 协程轮询，调用外部 API，成功后标记 `sent`。
- 外部 API 必须支持幂等键；不支持时用本地状态 + 去重表兜底。

### 5.4 频率与抑制

- `rate_limit_rules`：`tenant_id`、`channel`、`scope`（global / platform / subreddit / user）、`window_seconds`、`max_count`、`enabled`。
- `suppression_list`：`tenant_id`、`email` / `platform_user`、`reason`（unsubscribe / hard_bounce / complaint / manual）、`source`、`created_at`。
- 发送前强制检查：抑制、频率、同意状态、平台规则。

### 5.5 状态机约定

- 每次状态变更：`UPDATE ... SET status = $next, version = version + 1 WHERE id = $id AND status = $expected`。
- 受影响行数为 0 → 并发冲突，重新读取或放弃。
- 每次变更写 `audit_log` 和 `pipeline_runs`（如适用）。
- 状态机定义在 Python 枚举 + 迁移 CHECK 约束，两边保持一致。

---

## 6. 模块 2：社媒截流

### 6.1 目标

在 Reddit / HN 发现“真实求助、有明确痛点、可能是目标用户”的帖子，生成有帮助的回复草稿，人工审批后手动发送。v1 只做 Reddit + HN；X 后置到 M2.5。

### 6.2 采集

| 来源 | 方式 | 频率 |
|---|---|---|
| Reddit | 官方 API / 公开 JSON；按 subreddit + 关键词 | 30 分钟 |
| Hacker News | Algolia 公开 API；按 query / tag | 30 分钟 |

- 只读公开内容；不登录、不抓取私密社区。
- `growth_sources` 配置：`source_type`、`subreddit` / `query`、`cadence`、`enabled`、`last_run_at`、`last_error`。
- 去重：`platform + platform_post_id` 唯一。
- 存原始帖子：标题、正文、作者公开名、URL、发布时间、指标（score / comments）、subreddit 规则快照。

### 6.3 意图评分

评分卡（0–100）：

| 维度 | 权重 | 判断 |
|---|---|---|
| 真实求助 | 30 | 在问怎么做，不是纯吐槽/新闻 |
| 痛点具体 | 25 | 有场景、有约束、有失败尝试 |
| 买家角色 | 20 | 创始人/运营/开发者/卖家等目标角色 |
| 产品匹配 | 15 | 我们的产品能实际解决 |
| 回复安全 | 10 | 不是敏感话题、不是版规禁区 |

扣分：

| 情况 | 扣分 |
|---|---|
| 广告/自我推广帖 | −50 |
| 已有完整解决方案 | −20 |
| 超过 90 天 | −20 |
| 重复线索 | −30 |
| 竞品员工/明显钓鱼 | −50 |

阈值：

- `≥ 80`：qualified，进入草稿。
- `60–79`：watch，只记录，不生成。
- `< 60`：drop。

评分用便宜模型；草稿用更强模型。评分结果存 `score`、`score_reasons`、`model`、`prompt_version`。

### 6.4 草稿生成

结构：

1. 共情：复述对方的具体问题，不模板化。
2. 免费价值：给一个可执行建议、检查清单或判断标准。
3. 软提及：只有在相关时才提产品，披露 “I built this”。
4. **一个官方链接**：深链到具体功能页 / 指南，不是首页。
5. 结尾：邀请继续讨论，不硬推。

硬约束：

- 每条回复**必须带 1 个官方链接**（用户确认）。
- 链接放在价值段之后，不放在第一句。
- 禁止短链、联盟跳转、多个链接、虚假案例。
- 不承诺收益、不冒充普通用户、不贬低竞品。
- 语言跟随原帖；英文帖英文回复。

### 6.5 链接政策与防封

链接会提高被版主/自动风控拦截的概率，因此同时执行：

| 约束 | 规则 |
|---|---|
| 单链接 | 每条回复最多 1 个官方链接 |
| 深链 | 指向具体功能/指南，不指向首页 |
| 归因 | UTM：`utm_source=reddit` / `hn`，`utm_medium=reply`，`utm_campaign=<lead_id>` |
| 披露 | 明确说明关联关系 |
| 版规 | 发送前检查 subreddit 规则；禁自推的板块标记 `manual_only`，必须人工改写 |
| 频率 | 同一 subreddit 带链接回复 ≤ 2 条/天 |
| 熔断 | 帖子被删/被踩/被举报 → 停用该模板 7 天，人工复盘 |
| 发送 | 始终人工复制发送，不自动操作账号 |

### 6.6 飞书审批

飞书卡片字段：

- 原帖标题、subreddit / HN、发布时间、链接
- 意图分、评分理由、风险标记
- 草稿全文、链接、UTM
- 版规检查结果
- 按钮：通过、修改、拒绝、稍后

审批回调：

- 签名校验 + `approval_id` 幂等。
- 通过 → `approved`，生成最终文本和 `approved_by`。
- 修改 → 新建 `outreach_versions`，旧版本保留。
- 拒绝 → `rejected`，记录原因。

### 6.7 人工发送与跟进

- 人工复制发送后，在飞书卡片或 Admin UI 点“已发送”，记录 `sent_at`、`channel`、`draft_version`。
- 跟进：**每天最多 1 次，累计最多 3 次**；回复/退订/负反馈立即停止。
- 每次跟进必须补充新信息（新示例、新检查项），不能只“顶一下”。
- 跟进也遵守单链接、披露、版规、频率约束。

### 6.8 频率与抑制

- Reddit 5 条/天；全局 50 条/天。
- 同一用户 / 同一帖只回复一次。
- 抑制名单：退订、明确拒绝、版主警告、重复骚扰。
- 超限时任务进入 `suppressed`，不进入发送队列。

### 6.9 状态机

```text
discovered → scored → qualified → draft_ready → approved → sent → replied → converted
     │           │          │            │
     └→ dropped  └→ watch   └→ suppressed└→ rejected
```

### 6.10 数据表

| 表 | 作用 |
|---|---|
| `growth_sources` | Reddit/HN 采集源配置 |
| `social_leads` | 帖子、评分、状态、去重键 |
| `outreach_messages` | 统一触达消息（channel=social/email） |
| `outreach_versions` | 草稿版本、审批、最终文本 |
| `rate_limit_rules` | 平台/租户频率 |
| `suppression_list` | 退订/拒绝/拉黑 |
| `delivery_log` | 发送/回复/点击回执 |

### 6.11 测试与 DoD

- 单元：评分卡、扣分、阈值、去重、频率、抑制、链接政策。
- 集成：Reddit/HN mock → 评分 → 草稿 → 飞书回调 → 发送记录。
- 提示词回归：50 条黄金帖；共情、具体、无夸大、单链接、披露。
- 安全：广告帖、竞品帖、敏感帖被拦截；无自动发送代码路径。
- E2E：n8n → worker → 飞书审批 → 人工发送 → 跟进提醒。

DoD：

- 每周 ≥20 条合格线索。
- 审批通过率 ≥50%。
- 0 条自动发送。
- 100% 草稿有版本、审批人、最终文本。
- 频率/抑制 100% 生效。
- 链接政策 100% 执行。

---

## 7. 模块 4：生命周期触达

### 7.1 目标

用三个事件驱动一对一邮件：激活、扩容、取消挽留。不做群发、不买名单。

### 7.2 事件入口

```text
PostHog Webhook ─┐
Supabase DB Hook ─┼→ n8n（验签/归一化）→ Python /internal/events
Stripe Webhook ──┘                         │
                                           ├→ user_events（幂等）
                                           └→ 规则评估（每 5 分钟）
```

关键事件：

| 事件 | 用途 |
|---|---|
| `user_signed_up` | 激活提醒 |
| `core_action_completed` | 取消待发激活提醒 |
| `quota_80_percent` | 扩容/升级提醒 |
| `subscription_canceled` | 挽留邮件 + 优惠券 |
| `email_unsubscribed` | 抑制 |
| `email_bounced` / `email_complained` | 抑制 |

- `dedupe_key = source + event_id`，重复事件丢弃。
- 延迟消息按 `occurred_at + delay` 计算 `scheduled_at`。
- 条件变化时取消待发消息（例如用户完成核心动作）。

### 7.3 用户画像与同意

`user_profiles`：

- `user_id`、`email`、`name`、`company`、`role`、`plan`、`locale`、`timezone`
- `marketing_consent`、`consent_source`、`last_active_at`、`lifecycle_stage`、`unsubscribed_at`

`consent_log`：

- `user_id`、`consent_type`、`action`（granted/revoked）、`source`、`created_at`
- 只追加，不更新。

政策：

- 事务性邮件（账单、安全、配额）可不需要营销同意。
- 激活/挽留邮件按营销邮件处理：有同意或合法利益 + 明确退订。
- 取消挽留邮件带退订；不隐藏取消入口。
- 硬退信、投诉、退订 → `suppression_list`，永久生效直到人工解除。

### 7.4 规则

| rule_key | 触发 | 条件 | 延迟 | v1 发送 |
|---|---|---|---|---|
| `activation_nudge` | `user_signed_up` | 24h 内无 `core_action_completed` | 24h | 飞书审批 |
| `quota_warning` | `quota_80_percent` | 套餐有效、未退订 | 0 | 自动 |
| `cancellation_save` | `subscription_canceled` | 未领券、未退订 | 0 | 自动 |
| `winback_7d` | 7 天未活跃 | 可选，M4.4 | 7d | 审批 |

- 频率：同一用户 24h 内最多 1 封；7 天内最多 3 封。
- 发送前检查：同意、抑制、频率、优惠券有效期。
- 规则评估每 5 分钟；事件到达时也可即时评估。

### 7.5 邮件生成

- 纯文本优先，创始人语气，80–120 词，主题 3–6 个词，一个 CTA。
- 输入：事件、画像、套餐、语言、时区、真实使用事实、产品事实。
- 硬约束：
  - 不编造使用数据；
  - 不制造虚假紧迫感；
  - 不承诺收益；
  - 不贬低竞品；
  - 必须包含退订说明；
  - 取消挽留必须提供“暂不需要”入口。
- 输出 JSON：`subject`、`body_text`、`cta_text`、`cta_url`、`reason`、`risk_flags`。
- 每次生成/修改新增 `outreach_versions`，不覆盖；只有 `approved` 版本可发送。
- 飞书卡片：用户上下文、规则、预览、风险标记、通过/修改/拒绝/稍后。

### 7.6 发送与合规

- v1 用 **Resend**；量上来后切 SES。
- 子域 `mail.<domain>`；SPF、DKIM、DMARC；先预热。
- `List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click`。
- Python Worker 发送，outbox + 幂等键。
- 重试：429/5xx 指数退避，最多 5 次；4xx 不重试；死信告警飞书。
- 退信/投诉 webhook → `suppression_list`。
- 退订链接带签名 token，无需登录，1 分钟内生效。
- 打开像素仅参考；点击用重定向 + UTM。

### 7.7 取消挽留与优惠券

- Stripe 优惠券：**30% off，duration=once，48h 过期，一用户一码，限用 1 次**。
- 邮件包含原因调查（太贵/缺功能/太复杂/换工具/其他）+ 优惠券 + “暂不需要”入口。
- 原因点击 → 签名端点 → `user_events`。
- Stripe 核销 webhook → `coupon_codes.redeemed_at`，归因到邮件版本。
- 不自动扣费、不隐藏取消入口、不重复发券。

### 7.8 归因与周报

- UTM：`utm_source=lifecycle`、`utm_medium=email`、`utm_campaign=<rule_key>`、`utm_content=<message_id>`。
- 每条规则漏斗：planned → sent → delivered → opened → clicked → converted → unsubscribed。
- 每周一 09:00 飞书周报：
  - 发送、打开、点击、转化/挽回；
  - 优惠券领取/核销/挽回金额；
  - 退订率、投诉率、退信率；
  - 最好/最差 3 条邮件 + 下周建议。

### 7.9 状态机

```text
ingested → evaluated → planned → [pending_approval] → scheduled
→ sending → sent → delivered → opened → clicked → converted

旁路：pending_approval / skipped / suppressed / failed / expired / unsubscribed
```

`pending_approval` 只用于 `auto_send=false` 的规则（v1 的 `activation_nudge`）；审批通过后回到 `scheduled`，拒绝则 `skipped`。

### 7.10 数据表

| 表 | 作用 |
|---|---|
| `user_events` | 原始事件、去重、迟到事件 |
| `user_profiles` | 画像、时区、同意状态 |
| `event_rules` | 触发规则、延迟、自动发送 |
| `outreach_messages` | 统一触达消息（channel=email） |
| `outreach_versions` | 邮件版本、审批、最终文本 |
| `consent_log` | 同意/撤回审计 |
| `coupon_codes` | Stripe 优惠码、有效期、核销 |
| `suppression_list` | 退订/硬退信/投诉/拉黑 |
| `delivery_log` | 投递/打开/点击回执 |

### 7.11 测试与 DoD

- 单元：规则匹配、延迟、条件取消、同意、抑制、优惠券过期、幂等。
- 集成：PostHog → 事件 → 消息 → Resend mock → 回执；Stripe 测试券 → 核销。
- 提示词回归：30 个黄金场景；长度、语气、无虚构、退订句。
- 安全：0 封发往抑制/退订；退订 1 分钟内生效；未启用规则不发送。
- E2E：注册 → 24h 无动作 → 飞书审批 → Resend 测试 → 打开/点击 → 周报。

DoD：

- 事件到消息 < 5 分钟（不含人为延迟）。
- 100% 消息有版本、审批/自动规则、provider id。
- 0 封发往抑制/退订用户。
- 退订 1 分钟内生效。
- 优惠券核销可端到端追踪。
- 周报按时送达飞书。
- 退信率 < 2%，投诉率 < 0.1%。

---

## 8. 模块 1：pSEO 自动建站

### 8.1 目标

每周稳定产出 5–10 篇高意图英文页面，解决真实痛点，带产品 CTA，可索引、可度量。不做内容农场。

### 8.2 关键词发现

| 来源 | 用途 |
|---|---|
| DataForSEO | 搜索量、KD、CPC、关键词创意 |
| Google Suggest | 长尾/真实搜索词 |
| Serper.dev | Google 前 10、PAA、相关搜索 |
| Search Console | 已有曝光、排名 5–20 的快赢词 |
| 产品/客服/销售 | 真实痛点、竞品名、集成名 |

- `5118` 暂不做；中文站后再接。
- `growth_keywords` 存来源、volume、KD、CPC、intent、SERP 快照、`dedupe_key`。

### 8.3 过滤与意图

硬过滤：

- KD < 20（可配置）
- 月搜索量 ≥ 50；长尾 ≥ 20
- 语言 = 目标市场
- 无竞品商标侵权风险
- YMYL 默认人工审核

意图：信息型 / 商业型 / 交易型。优先级：交易型 > 商业型 > 信息型。按 SERP 前 10 重合度聚类，一个聚类一篇，避免关键词自食。

机会分：

```text
score = log(volume) * 0.3
      + intent_weight * 0.25
      + product_fit * 0.25
      + quick_win_bonus * 0.2
      - kd_penalty - serp_competition_penalty
```

### 8.4 SERP 与 brief

- Serper 取前 3–5 名：标题、URL、摘要、H2/H3、字数、内容类型。
- 提取 PAA、相关搜索。
- `content_briefs`：主/次关键词、意图、读者、必覆盖章节、对比表维度、FAQ、来源、内链候选、目标字数 1200–2000、语气、禁用表达。

### 8.5 内容生成

结构：

```text
H1（主关键词）
开场：痛点 + 承诺
为什么会出现这个问题
解决步骤
方案对比表（选项/优点/缺点/适合谁）
FAQ（≥3，来自 PAA）
产品 CTA
来源列表
```

MDX frontmatter：

```yaml
title, description, slug, primary_keyword, secondary_keywords,
intent, author, published_at, updated_at, canonical,
og_image, faq, sources, internal_links, generation_meta
```

LLM 约束：

- 不编造数据；数字必须有来源，否则删除。
- 不伪造评价/案例。
- 不构成医疗/金融/法律建议。
- 主关键词密度 0.5%–1.5%。
- 产品提及只在相关段落，披露关联。
- 英文可读性 Flesch 50–70。

### 8.6 质量门

| 检查 | 规则 |
|---|---|
| 事实 | 数字/统计必须有来源 URL |
| 重复 | 与现有页面余弦相似度 < 0.85；shingle 重合 < 20% |
| 结构 | 1 个 H1、≥3 个 H2、FAQ ≥3、商业意图有对比表 |
| 链接 | ≥2 内链、≥2 权威外链、无死链 |
| SEO | title ≤60 字符、description 140–160、slug 小写连字符、图片 alt |
| 可读性 | 句长、段落、被动语态 |
| 风险 | YMYL、竞品商标、绝对化承诺 → 人工 |

质量分 0–100：**≥80 可发布，60–79 修改，<60 拒绝**。前 20 篇全人工审核；v1 全部人工合并。自动合并只在质量门稳定后单独评估，且要求 ≥90 分、无风险标记。

### 8.7 内链

- 建内容图谱：标题、slug、关键词、embedding。
- 每篇 2–5 个链接：1–2 个产品/功能页，2–3 个相关文章。
- 锚文本自然、多样；不精确匹配堆叠。
- Hub/spoke：新文章链回 hub，hub 链到新文章。
- 不允许孤儿页；发布后死链检查，死链阻断发布。

### 8.8 发布

独立营销站仓库（Next.js/Astro + MDX），不往应用仓库提交内容。GitHub App 权限：`contents:write`、`pull_requests:write`、`checks:read`。

流程：

1. 建分支 `pseo/<batch-id>`。
2. 提交 `.mdx` + sitemap 配置。
3. 开 PR：关键词、质量分、预览 URL。
4. CI：build、死链、lint、重复度。
5. **人工按批次合并（v1）**。
6. 合并触发 Vercel/Cloudflare 部署。
7. 部署成功 → `published`；失败 → 回滚 + 飞书告警。

同一时间只允许一个发布批次。

### 8.9 收录

**重要修正：Google Indexing API 只支持 `JobPosting` 和 `BroadcastEvent`，不支持普通博客文章。** 不要对普通页面调用，否则会失败。

| 引擎 | 做法 |
|---|---|
| Google | Search Console 提交 sitemap；URL Inspection API 查状态；内链 + sitemap 是可靠路径；不承诺即时收录 |
| Bing / Yandex | IndexNow 提交 URL + key |
| 其他 | 不买“秒收录”，不买链接 |

`indexing_events` 记录引擎、提交时间、状态、响应。发布 14 天未收录 → `index_check_due`，检查内链、质量、sitemap。

### 8.10 度量与复投

- Search Console API：曝光、点击、CTR、平均排名。
- PostHog：页面浏览、CTA 点击、注册、试用。
- CTA 链接带 UTM；页面元数据带 `content_id`。
- 周报：发布、收录、曝光、点击、注册、Top 页面、低 CTR 页面。
- 复投：排名下降/CTR 低 → 改 title/meta、补内链、更新数据。

### 8.11 数据表与状态机

| 表 | 作用 |
|---|---|
| `growth_keywords` | 关键词、来源、KD、volume、intent、SERP |
| `content_briefs` | brief 版本、大纲、来源、内链候选 |
| `content_queue` | 统一内容主记录（content_type=pseo_article） |
| `content_versions` | Markdown、模型、prompt 版本、质量分 |
| `content_sources` | 事实来源、引用、抓取时间 |
| `content_links` | 内链/外链、锚文本、类型 |
| `publish_events` | commit、PR、部署状态、错误 |
| `indexing_events` | 引擎、提交状态、响应 |
| `seo_metrics` | 每日曝光/点击/CTR/排名 |

```text
discovered → filtered → planned → drafting → review → approved
→ scheduled → publishing → published → indexed → measured

旁路：rejected / failed / paused / archived / index_check_due
```

`indexed` 不是必然状态；14 天未收录转 `index_check_due`，28 天后 `measured`。

### 8.12 测试与 DoD

- 单元：关键词过滤、意图、slug、去重、内链、frontmatter。
- 集成：DataForSEO/Serper/GitHub/Vercel/IndexNow mock。
- 提示词回归：20 个 brief；结构、事实、无堆词、内链、CTA。
- 质量门：重复、死链、缺来源、薄内容、YMYL。
- E2E：关键词 → brief → 草稿 → PR → 预览 → 合并 → 部署 → sitemap → 收录检查。
- 真实环境：staging 发 1 篇，验证构建、sitemap、回滚。
- 成本：每篇 API + LLM 成本；日/周预算告警。

DoD：

- 每周 20 个候选词，产出 5–10 篇。
- 100% 文章有来源、frontmatter、内链、质量分。
- 构建通过、无死链。
- 发布页进入 sitemap。
- 收录状态可追踪，不承诺即时收录。
- 无来源数字不出现。
- v1 合并前人工批准。
- 每篇成本可追踪。

---

## 9. 模块 3：内容二创矩阵

### 9.1 目标

一次 GitHub Release / CHANGELOG 更新，5 分钟内生成三套物料：X/即刻 build-in-public、小红书/公众号痛点复盘、Product Hunt/V2EX 发布帖。只拆结构，不抄内容；v1 人工复制发布。

### 9.2 爆款库

10–20 条公开高互动帖子，字段：

- `platform`、`author`、`url`、`text`、`metrics`
- `hook_type`：反常识/代价/失败/数字/前后对比/清单/争议/故事
- `emotion`：挫败/释然/惊讶/野心/好奇
- `rhythm`：短句/空行/列表/加粗/emoji 密度
- `why_it_worked`、`captured_at`

采集：官方 API 或人工整理公开页面；不抓登录后内容；每周刷新，优先互动增速。

### 9.3 Hook / 情绪 / 节奏

| Hook | 模板 | 示例 |
|---|---|---|
| 反常识 | 大家都以为 X，其实 Y | “Everyone thinks SEO is about volume. It's about intent.” |
| 代价 | 我花了 X 小时，你不用 | “I spent 40 hours on this so you don't have to.” |
| 失败 | 我们搞砸了，后来改了 X | “Our launch flopped. Here's what we changed.” |
| 数字 | 3 个数字改变了路线 | “3 numbers that changed our roadmap.” |
| 前后对比 | Before / After | “Before: 6 hours. After: 20 minutes.” |
| 清单 | X 件我希望早知道的事 | “5 things I wish I knew before building.” |
| 争议 | 不讨喜但真实 | “Unpopular opinion: most pSEO advice is wrong.” |
| 故事 | 客户一句话，我们重做了 X | “A customer told us X. We rebuilt Y.” |

情绪弧线：痛点 → 转折 → 结果 → 可复用经验 → 轻 CTA。节奏按平台调整。

### 9.4 触发

```text
GitHub Release published
        │ webhook
        ▼
n8n 验签/归一化 → Python /internal/content/from-release
        │
        ├→ release body、CHANGELOG diff、关联 PR
        ├→ 提取事实：新功能、修复、数字、场景
        └→ 生成 3 个 variant + 配图任务
```

支持飞书手动触发。CHANGELOG 更新走同一条管线，但人工选版本，避免每次 commit 都触发。

### 9.5 三形态

**A. X / 即刻：build-in-public**

- 1 条主贴，必要时 3–7 条 thread。
- hook → 背景 → 改了什么 → 为什么重要 → 一个教训 → CTA。
- 每条 ≤280 字符；最多 2 个 hashtag。
- 主贴不放链接；链接放第一条回复或主页。
- 数字必须来自 Release 或可核对来源。

**B. 小红书 / 公众号：痛点复盘**

- 标题：痛点 + 结果，20 字内。
- 个人故事 → 3–5 个可执行点 → 产品轻提及 → CTA。
- 小红书 600–1000 字，封面 3:4；公众号 1000–2000 字。
- 不夸大、不写“必看/震惊/第一名”；披露广告关系。

**C. Product Hunt / V2EX：发布帖**

- PH：名称、tagline ≤60 字符、description ≤260 字符、首评、topics、图片、launch offer。
- V2EX：标题、正文、真实 build 故事、求反馈，不硬卖。
- 不刷票、不互投。

### 9.6 截图与配图

- Playwright 打开真实产品界面，demo 账号 + 固定 viewport。
- 尺寸：X/PH 1280×800；小红书 1080×1440；OG 1200×630。
- 渐变背景：品牌色、64px 内边距、24px 圆角、轻阴影、可选标题。
- PNG + WebP；自动 alt text。
- 只截真实 UI；隐藏邮箱/姓名/密钥；功能没上线不截。
- 视觉 QA：无裁切、无过期界面、无 PII。

### 9.7 审批与发布

- 飞书卡片：3 个 variant + 配图 + 事实来源 + 风险标记。
- 按钮：通过/修改/拒绝/定时提醒。
- **v1 全部人工复制发布**；系统给 checklist：
  - X：主贴 + 回复链接
  - 小红书：标题/正文/封面/话题
  - PH：tagline/description/首评/图片
  - V2EX：标题/正文/节点
- 发布后人工点“已发布”，记录 URL 和时间。
- 后续可接 X API，但需单独评估预算、规则、封号风险；小红书/V2EX 仍人工。

### 9.8 数据表与状态机

| 表 | 作用 |
|---|---|
| `inspiration_posts` | 爆款库、hook/情绪/节奏标签 |
| `hook_patterns` | Prompt 模板库 |
| `content_queue` | 统一内容主记录 |
| `content_versions` | variant 版本、模型、prompt |
| `content_assets` | 截图、封面、尺寸、alt |
| `content_metrics` | 曝光/互动/点击/注册 |

```text
idea → drafting → review → approved → scheduled
→ publishing → published → measured

旁路：failed / rejected / archived
```

### 9.9 测试与 DoD

- 单元：Hook 选择、平台字数、事实提取、UTM、图片尺寸。
- 集成：GitHub Release → 3 variant → 飞书审批 → 发布记录。
- 提示词回归：20 个 Release；hook、语气、事实、平台适配。
- 视觉回归：尺寸、无 PII、渐变模板、无裁切。
- E2E：Release → 生成 → 审批 → 人工发布 → 指标回流。
- 真实环境：1 个真实 Release，人工发 X/PH 草稿。

DoD：

- 10–20 条爆款标签化。
- 1 个 Release 5 分钟内生成 3 套物料。
- 100% 通过平台限制、事实校验、无 PII。
- 发布前人工审批。
- UTM + 指标可追踪。
- v1 无自动发帖代码路径。

---

## 10. 横切能力

### 10.1 飞书集成

- 自建应用 / bot；`app_id` + `app_secret` 存 Vault。
- 卡片回调验签；`approval_id` 幂等。
- 卡片模板：审批卡、周报卡、告警卡。
- 发送失败重试 3 次，仍失败写 `dead` + 邮件/短信兜底（后续）。

### 10.2 错误处理

| 类型 | 处理 |
|---|---|
| 4xx（参数/权限） | 不重试，记录错误，告警 |
| 429 / 5xx | 指数退避重试，最多 5 次 |
| 超时 | 重试；外部副作用用幂等键 |
| LLM 输出不合规 | 重试一次；仍失败转人工 |
| 部署失败 | 回滚 commit，告警 |
| 死信 | 飞书告警，人工处理 |

### 10.3 观测

- `pipeline_runs`：任务状态、耗时、重试、死信。
- `delivery_log`：发送/投递/打开/点击。
- `audit_log`：审批、发送、发布、退订、核销。
- 成本：每次 LLM / API 调用记录 token、费用、模块、任务。
- 每日健康检查：队列积压、失败率、死信、预算。

### 10.4 成本控制

- 评分用便宜模型；草稿/文章用强模型。
- pSEO 每篇预算上限；超限暂停。
- 模块 2 每日 50 条上限；模块 4 每用户频率上限。
- 周报展示单位成本（每线索、每封邮件、每篇文章）。

### 10.5 合规

- 只读公开内容；不绕过登录/验证码。
- 社媒回复人工发送；披露关联；遵守版规。
- 邮件：同意、退订、抑制、SPF/DKIM/DMARC、物理地址（如适用）。
- 不购买名单；不刷票；不伪造评价。
- 数据保留：原始帖子/邮件内容保留 12 个月；审计日志保留 24 个月；可配置。

### 10.6 部署

| 组件 | v1 部署 |
|---|---|
| Supabase | Cloud（Postgres/Auth/Storage/Vault） |
| n8n | 自托管 Docker（小 VPS） |
| Python Worker | 同一 VPS，Docker Compose；Playwright 依赖打进镜像 |
| Admin UI | Vercel（可选） |
| 内容站 | Vercel / Cloudflare Pages |
| 备份 | Supabase 每日备份；n8n 工作流导出到 git；内容仓库 git |

### 10.7 测试策略

| 层级 | 范围 |
|---|---|
| 单元 | 状态机、评分、去重、频率、抑制、优惠券、质量门 |
| 集成 | Supabase + n8n + Python + 外部 API mock |
| 提示词回归 | 50 条社媒帖、30 个邮件场景、20 个 pSEO brief、20 个 Release |
| 安全 | 无自动发送路径；抑制/退订；密钥不泄漏；PII 不进入截图 |
| E2E | 四条流水线各一条完整链路 |
| 真实环境 | Reddit/HN 只读、Resend sandbox、Stripe test、飞书测试群、staging 内容站 |
| 成本 | 每次运行记录 token/API 费用，超预算告警 |

---

## 11. 扩展性与规模化

### 11.1 扩展原则

- **先模块化单体，后拆分。** v1 一个 Python 部署单元，但内部按 `growth_core` + 四个模块包严格分层；只有触发 11.10 的阈值才拆服务。
- **能力适配器化。** 采集、关键词、SERP、LLM、邮件、通知、发布、索引全部走接口 + 注册表；新增供应商不改核心流程。
- **配置优先于代码。** 采集源、规则、频率、供应商选择、租户开关放数据库；常规变更不发版。
- **核心字段强类型，扩展字段 JSONB。** 需要查询/过滤的字段建列；供应商特有字段进 `metadata` + `schema_version`。
- **快速变化的枚举用 lookup table，稳定状态用 CHECK。** 平台/渠道可扩展；状态机状态变更必须走迁移，保持刻意。
- **每个扩展点有契约测试。** 适配器、流水线、配置 schema、迁移都要有可重复的测试。

### 11.2 能力适配器与注册表

| 能力 | 接口 | v1 | 后续 |
|---|---|---|---|
| 社媒来源 | `SourceAdapter` | Reddit、HN | X、知乎、小红书、V2EX、即刻 |
| 关键词 | `KeywordProvider` | DataForSEO、Google Suggest | 5118、Ahrefs、Semrush |
| SERP | `SerpProvider` | Serper | DataForSEO SERP、Brave |
| LLM | `LLMProvider` | Anthropic / OpenAI 兼容 | DeepSeek、Ollama、本地模型 |
| 邮件 | `EmailProvider` | Resend | SES、Postmark |
| 通知 | `Notifier` | 飞书 | Telegram、Slack、邮件 |
| 发布 | `Publisher` | GitHub + Vercel | Cloudflare Pages、GitLab |
| 平台格式 | `PlatformFormatter` | X、小红书、PH、V2EX | 即刻、LinkedIn、公众号 |
| 收录 | `IndexingProvider` | Sitemap + IndexNow | GSC API、Bing API |

注册表示意：

```python
ADAPTERS: dict[tuple[str, str], type] = {}

def register(capability: str, name: str):
    def deco(cls):
        ADAPTERS[(capability, name)] = cls
        return cls
    return deco
```

`provider_configs` 选择能力对应的供应商和优先级；新增适配器 = 新类 + 注册 + 一行配置，核心流程不改。

适配器统一契约：

- `health()`、`capabilities()`、`validate_config()`
- 统一错误码：`PROVIDER_NOT_CONFIGURED` / `PROVIDER_AUTH` / `PROVIDER_RATE_LIMITED` / `PROVIDER_TIMEOUT` / `PROVIDER_BAD_OUTPUT` / `PROVIDER_UNAVAILABLE`
- 所有外部调用带 `idempotency_key` 或可重试标记
- 配置用 JSON Schema 校验，记录 `config_schema_version`
- 契约测试：同一套 fixture 跑所有实现

### 11.3 数据模型扩展策略

| 变化 | 扩展方式 | 是否迁移 |
|---|---|---|
| 新平台（X/小红书） | `platform_registry` + `content_variants` + formatter | 否 |
| 新邮件商 | `provider_configs` + adapter | 否 |
| 新事件类型 | `event_name` text + `event_rules` | 否 |
| 新规则动作 | action handler 注册表 | 否 |
| 新状态 | 状态机 + CHECK + 迁移 | 是（刻意） |
| 新供应商字段 | `metadata jsonb` + `schema_version` | 否 |
| 新查询维度 | 新列 + 索引 | 是 |

约定：

- `platform_registry`、`channel_registry`、`content_type_registry` 三张 lookup 表，应用启动时加载缓存。
- `content_queue` 只存公共字段；平台差异放 `content_variants`（一个 content 多行）。
- `outreach_messages` 只存公共字段；邮件/社交差异放 `metadata` 和 `outreach_versions`。
- `event_rules.action_json` 用 JSON Schema 校验；动作处理器按 `action_type` 注册。
- `user_events` 存 `event_schema_version`；未知字段进 `metadata`，不拒绝；webhook 原始 payload 保留，便于回放和补字段。
- 配置表带 `version`、`updated_by`；`config_versions` 存 diff，支持回滚。
- 迁移用 Alembic expand/contract：先加列/表，再双写，最后删旧字段；不允许一步破坏性迁移。

### 11.4 Pipeline 插件契约

每个流水线实现同一个协议：

```python
class Pipeline(Protocol):
    name: str
    state_machine: StateMachine

    async def plan(self, trigger: Trigger) -> list[Task]: ...
    async def execute(self, task: Task) -> TaskResult: ...
    async def compensate(self, task: Task) -> None: ...
    def metrics(self) -> list[MetricDef]: ...
```

- `PIPELINES` 注册表按 `name` 查找；worker 不关心具体模块。
- 共享服务放 `growth_core`：队列、outbox、限流、抑制、审计、LLM、通知、配置。
- 模块包：`growth_social`、`growth_lifecycle`、`growth_pseo`、`growth_repurpose`；依赖方向只能指向 `growth_core`，模块之间不直接 import。
- 新增第五条流水线 = 新包 + 状态机 + 任务 + 表 + UI 卡片；核心队列/outbox/审批不用改。
- `opportunity_core` 继续负责 Provider/Signal/Analyzer；`growth_core` 负责增长通用能力，两者不混。
- 现有 `ideas_pool/server` 先作为 `growth_worker` 的宿主，逐步抽出 `growth_core`；`opportunity_core` 从 `server/app/providers`、`services/analyzer`、`schemas` 抽包。v1 不强制拆独立仓库，先在同一仓库内按包分层。
- Admin UI v1 复用 `web` 的路由和设计令牌，新增 `/growth/*` 页面；不新建前端仓库。

### 11.5 队列与 Worker 扩展

- v1 一张 `pipeline_runs` 表，按 `pipeline` + `task_type` 逻辑分池。
- Worker 池：
  - `api`：FastAPI，轻量请求。
  - `pipeline`：评分、生成、发送。
  - `browser`：Playwright 截图，CPU/内存重，独立部署。
  - `scheduler`：n8n / cron。
- 背压：每个 provider / tenant 有最大并发；`provider_concurrency` 配置；超限排队，不打爆外部 API。
- 限流：v1 Postgres token bucket（`rate_limit_counters` 原子 upsert）；量上来后切 Redis。
- 至少一次投递；所有 handler 幂等；worker 崩溃后锁超时自动回收。
- 优雅停机：停止取新任务，释放锁，未完成任务重新入队。
- 任务优先级：交互式审批/发送优先，批量 pSEO 后置。

### 11.6 多租户配额与功能开关

- `tenant_quotas`：`tenant_id`、`metric`（llm_tokens / emails / social_replies / pseo_articles / crawl_requests）、`period`、`limit`、`used`、`reset_at`。
- `tenant_features`：`tenant_id`、`feature_key`、`enabled`、`config_json`。
- 执行前检查配额；超限返回 `quota_exceeded`，飞书通知，不重试。
- 每租户独立限流和 provider 配置，避免“吵闹邻居”。
- v1 单租户也建表、建策略，避免以后补丁式改造。

### 11.7 Provider 故障转移

- `provider_configs` 按能力配置优先级，例如邮件 Resend → SES，SERP Serper → DataForSEO。
- 熔断器：closed / open / half-open；连续失败阈值、冷却时间、半开探测。
- `provider_health` 记录延迟、错误率、限流命中；健康检查失败自动降级。
- 失败转移必须幂等：发送类操作先用消息状态 + provider idempotency key 防重复；不确定是否成功时不盲目重发。
- 非幂等操作不做自动转移，转人工。

### 11.8 配置与版本

- 配置表：`provider_configs`、`growth_sources`、`event_rules`、`rate_limit_rules`、`tenant_features`。
- `prompt_templates`：按模块/任务存 prompt 版本、输出 JSON Schema、模型提示；生成时记录 `prompt_version`；支持 A/B 和回滚。
- `scoring_rubrics`：模块 2 意图评分、模块 1 质量分等评分卡配置化；维度/权重/阈值版本化；新增垂直领域只加配置，不改代码。
- 每张配置表带 `version`、`updated_by`、`updated_at`；`config_versions` 存前后 diff。
- JSON Schema 校验；非法配置拒绝保存。
- 内部 API 走 `/internal/v1/*`；适配器和 webhook 契约带版本；破坏性变更双版本并行，确认无调用方后下线。
- 新适配器/新流水线用 feature flag 灰度，先单租户开，再全量。
- Admin UI 修改配置必须写审计；支持一键回滚。

### 11.9 数据分区与索引

- 达到 11.10 阈值后，按月分区：`user_events`、`delivery_log`、`seo_metrics`、`pipeline_runs`。
- 必备索引：
  - `pipeline_runs(status, priority, run_after)`
  - `social_leads(tenant_id, platform, status, created_at)`
  - `outreach_messages(tenant_id, channel, status, scheduled_at)`
  - `content_queue(tenant_id, content_type, status)`
  - `user_events(tenant_id, event_name, occurred_at)`
  - 唯一 `(tenant_id, dedupe_key)` / `(tenant_id, idempotency_key)`
- 冷数据归档到对象存储；原始内容保留 12 个月、审计 24 个月。
- 监控慢查询、表膨胀、索引命中率；每月 review。

### 11.10 扩展触发阈值

| 信号 | 阈值 | 动作 |
|---|---|---|
| 队列延迟 | 持续 > 5 分钟 | 加 worker / 拆分队列 |
| 任务量 | > 100k/天 | 按 pipeline 拆 worker 池 |
| Playwright CPU | 持续 > 70% | 独立 browser worker |
| 租户数 | > 50 | 分区、配额、RLS 审计 |
| 热表行数 | > 10M | 月分区 + 归档 |
| n8n 执行 | > 10k/天 | n8n queue mode + Redis |
| DB 连接 | > 80% | PgBouncer / Supabase pooler |
| LLM 成本 | > 预算 80% | 模型路由、批处理、暂停低优任务 |

这些阈值是“拆分信号”，不是 v1 要做的事；提前定义是为了避免拍脑袋微服务化。

### 11.11 扩展性测试

- 适配器契约测试：每个 `SourceAdapter` / `EmailProvider` / `Publisher` 跑同一套 fixture。
- Pipeline 契约测试：`plan → execute → compensate` 在重复执行、超时、崩溃下行为一致。
- 配置 schema 测试：非法配置被拒绝；版本回滚可用。
- 迁移测试：expand/contract 两阶段，旧代码在新 schema 下仍可运行。
- 混沌测试：provider 超时、429、重复 webhook、worker 崩溃、锁超时。
- 负载测试：按预期峰值的 10 倍压队列和限流。
- 成本测试：按 tenant/pipeline 记录单位成本，超预算告警。

---

## 12. 实施顺序与里程碑

按用户确认的优先级：**模块 2 → 模块 4 → 模块 1 → 模块 3**。

| 阶段 | 内容 | 预估 | 验收 |
|---|---|---|---|
| Phase 0 | Supabase schema、RLS、`pipeline_runs`、outbox、飞书、`opportunity_core` 抽包、适配器注册表、`provider_configs`、`tenant_quotas` / `tenant_features`、`config_versions` | 4–6 天 | 一条测试任务跑通队列+outbox+飞书；新增一个 mock adapter 不改核心代码；配置回滚可用 |
| Phase 1 | 模块 2：Reddit/HN 采集、评分、草稿、飞书审批、发送记录、跟进 | 5–7 天 | 每周 20 条合格线索；0 自动发送 |
| Phase 2 | 模块 4：事件、规则、邮件、Resend、优惠券、周报 | 5–7 天 | 三类事件端到端；退订 1 分钟生效 |
| Phase 3 | 模块 1：关键词、brief、生成、质量门、PR、部署、IndexNow | 9–12 天 | 5–10 篇/周；构建通过；收录可追踪 |
| Phase 4 | 模块 3：爆款库、Hook、Release 触发、三形态、截图、人工发布 | 9–12 天 | 1 个 Release 5 分钟出 3 套物料 |

Phase 0 是硬前提；没有队列、outbox、幂等和审计，后面四条流水线都会重复造轮子。每个 Phase 单独出实现计划；第一份实现计划覆盖 **Phase 0 + Phase 1（模块 2）**，完成并通过验收后再排下一份。

---

## 13. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Reddit/HN 封号 | 渠道损失 | 人工发送、频率上限、版规检查、单链接、披露、熔断 |
| 内容质量差 | 品牌/SEO 受损 | 质量门、前 20 篇人工、5–10 篇/周、不追量 |
| LLM 编造事实 | 信任/合规 | 引用校验、数字必须有来源、提示词回归 |
| 邮件进垃圾箱 | 触达失败 | 子域预热、SPF/DKIM/DMARC、低量、抑制、投诉处理 |
| 优惠券滥用 | 收入损失 | 一用户一码、48h、限用 1 次、Stripe 校验 |
| 多租户复杂度 | 开发拖慢 | v1 单租户；字段 + RLS 预留；不提前做计费 |
| n8n 工作流膨胀 | 难维护 | 业务逻辑全在 Python；n8n 只做编排 |
| API 成本超预算 | 不可持续 | 模型路由、预算上限、周报单位成本 |
| Google 收录慢 | pSEO 见效慢 | 不承诺即时；sitemap + 内链 + 质量；14 天检查 |

---

## 14. 待确认项

这些不阻塞 Phase 0，但需要在对应阶段前定：

1. **X API 预算/档位**：模块 2 的 X 接入（M2.5）需要；v1 不做。
2. **Admin UI 范围**：v1 是否只做飞书卡片，还是加一个最小 React 审批队列。
3. **Opportunity Scout Signal 同步**：v1 是否把本地 SQLite 的 Run/Signal 同步到 Supabase，作为模块 2/1 的输入；建议 v1 可选，不阻塞。
4. **数据保留期**：建议原始内容 12 个月、审计 24 个月；可按合规要求调整。
5. **邮件物理地址**：CAN-SPAM 要求；需产品主体地址。
6. **Product Hunt 发布时间**：建议太平洋时间 00:01；需人工确认。
7. **n8n 托管**：建议与 Python Worker 同一台 VPS，Docker Compose；后续再拆。
8. **是否初始化 git**：当前 `ideas_pool` 不是 git 仓库；spec 已写入文件但未提交。需要决定是否初始化 git 以纳入版本管理。

---

## 附录 A：ADR 索引

完整 ADR 表在 [GROWTH_AGENT_TRACKING.md](../../../GROWTH_AGENT_TRACKING.md)。本 spec 采用的决策：

| ADR | 决策 |
|---|---|
| ADR-01 | 先自用，架构预留多租户 |
| ADR-02 | 出海优先 |
| ADR-03 | Supabase + n8n + Python |
| ADR-04 | Python 拥有状态机 |
| ADR-05 | 抽 `opportunity_core` 共享包 |
| ADR-06 | Python 状态机 / TS Admin UI / Go 仅未来高并发爬虫 |
| ADR-07 | `text + CHECK` 状态 |
| ADR-08 | Outbox |
| ADR-09 | 自动化边界：不自动发帖/评论/私信 |
| ADR-10 | 顺序 2 → 4 → 1 → 3 |
| ADR-11 | 多租户字段 + RLS |
| ADR-12 | n8n 不直写业务表 |
| ADR-13 | 模块 2 默认参数 |
| ADR-14 | 模块 4 默认参数 |
| ADR-15 | 模块 1 默认参数 |
| ADR-16 | 模块 3 默认参数 |

## 附录 B：内部 API

所有接口带 `X-Service-Token`、`X-Tenant-Id`、`X-Workspace-Id`；幂等键放 header 或 body。

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/internal/events` | 接收 PostHog/Supabase/Stripe 事件 |
| POST | `/internal/social/ingest` | 触发 Reddit/HN 采集 |
| POST | `/internal/social/score` | 批量评分 |
| POST | `/internal/social/draft` | 生成回复草稿 |
| POST | `/internal/approvals/callback` | 飞书审批回调 |
| POST | `/internal/email/generate` | 生成生命周期邮件 |
| POST | `/internal/email/send` | 发送/重试 |
| POST | `/internal/email/events` | Resend 投递/退订回执 |
| POST | `/internal/seo/keywords/discover` | 关键词发现 |
| POST | `/internal/seo/content/generate` | brief + 文章生成 |
| POST | `/internal/seo/publish` | 开 PR / 触发部署 |
| POST | `/internal/content/from-release` | Release 触发二创 |
| POST | `/internal/metrics/sync` | GSC/PostHog/平台指标回流 |
| GET | `/healthz` | 健康检查 |

## 附录 C：状态机汇总

```text
模块 2：
discovered → scored → qualified → draft_ready → approved → sent → replied → converted
旁路：dropped / watch / suppressed / rejected

模块 4：
ingested → evaluated → planned → [pending_approval] → scheduled → sending → sent
→ delivered → opened → clicked → converted
旁路：pending_approval / skipped / suppressed / failed / expired / unsubscribed

模块 1：
discovered → filtered → planned → drafting → review → approved
→ scheduled → publishing → published → indexed → measured
旁路：rejected / failed / paused / archived / index_check_due

模块 3：
idea → drafting → review → approved → scheduled
→ publishing → published → measured
旁路：failed / rejected / archived
```
