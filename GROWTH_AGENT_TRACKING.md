# Growth Agent 开发跟踪矩阵

> 版本：v1.0<br>
> 更新日期：2026-11-19<br>
> 关联文档：[DEVELOPMENT_TRACKING.md](DEVELOPMENT_TRACKING.md)（Opportunity Scout 现状审计）、[business_plan.md](business_plan.md)、[Growth Agent 设计 spec](docs/superpowers/specs/2026-11-15-growth-agent-design.md)、[Phase 0 + 模块 2 实施计划](docs/superpowers/plans/2026-11-15-growth-agent-phase0-module2.md)  
> 用途：把“需求 → 架构决策 → 设计 → 实现 → 测试 → 验收”串成一条可核对的链路，防止四条流水线在开发中漏项。

---

## 0. 状态图例

| 标记 | 含义 |
|---|---|
| ✅ | 已确认 / 已完成 |
| 📝 | 设计完成（已有方案，待实现 / 待评审） |
| ⏳ | 待确认（有默认建议，等产品/技术决策） |
| 🔨 | 开发中 |
| 🧪 | 测试中 |
| 🚀 | 已上线并验证 |
| ❌ | 未开始 |
| ⏸ | 暂缓 / 不在 v1 |

---

## 1. 关键决策记录（ADR）

| ID | 决策点 | 结论 | 状态 | 日期 |
|---|---|---|---|---|
| ADR-01 | 产品定位 | 先自用（dogfooding），架构预留多租户 | ✅ | 2026-11-15 |
| ADR-02 | 第一批市场 | 出海优先：Reddit / X / Google / HN / Product Hunt | ✅ | 2026-11-15 |
| ADR-03 | 技术底座 | Supabase（Postgres/RLS/Auth）+ n8n（触发/连接器）+ Python（复杂逻辑/采集） | ✅ | 2026-11-15 |
| ADR-04 | 状态机归属 | Python 拥有业务状态机；n8n 只做触发、连接器、审批入口 | ✅ | 2026-11-15 |
| ADR-05 | 代码复用 | 抽取 `opportunity_core` 共享包（providers / signal / analyzer / domain_packs），两边共用 | ✅ | 2026-11-15 |
| ADR-06 | 语言分工 | 状态机/采集/LLM 用 Python；管理后台用 TypeScript；Go 仅在爬虫成为瓶颈时拆出 | ✅ | 2026-11-15 |
| ADR-07 | 状态存储 | `text + CHECK`，不用 Postgres enum | ✅ | 2026-11-15 |
| ADR-08 | 副作用一致性 | 业务状态 + outbox 同事务；sender 异步发送 | ✅ | 2026-11-15 |
| ADR-09 | 自动化边界 | 社媒回复人工审批+人工发送；生命周期邮件默认自动；pSEO 走 Git PR；内容二创人工审批 | ✅ | 2026-11-15 |
| ADR-10 | 落地顺序 | 模块 2 → 模块 4 → 模块 1 → 模块 3，各自独立 spec/plan | ✅ | 2026-11-15 |
| ADR-11 | 多租户边界 | 所有增长表带 `tenant_id` + `workspace_id`；Supabase RLS 兜底 | ✅ | 2026-11-15 |
| ADR-12 | n8n 写权限 | n8n 不直写业务表，只调用 Python 内部 API 和写 `delivery_log` | ✅ | 2026-11-15 |
| ADR-13 | 模块 2 默认参数 | v1 只做 Reddit+HN；**飞书**审批；阈值 80；Reddit 5 条/天、**全局 50 条/天**；**每条回复带 1 个官方链接并披露关联**；**跟进每天最多 1 次、累计最多 3 次**（安全上限，可配置） | ✅ | 2026-11-15 |
| ADR-14 | 模块 4 默认参数 | PostHog/Supabase webhook 入口；Resend v1；`quota_80` + `cancellation_save` 自动发，`activation_nudge` 飞书人工审批；30% off once/48h；1 封/24h、3 封/7 天；周一 09:00 飞书周报 | ✅ | 2026-11-15 |
| ADR-15 | 模块 1 默认参数 | DataForSEO + Google Suggest + Serper；英文优先；Vercel v1；**PR + 人工合并**；5–10 篇/周；质量分 80；前 20 篇全人工；Google 用 sitemap，Bing/Yandex 用 IndexNow | ✅ | 2026-11-15 |
| ADR-16 | 模块 3 默认参数 | GitHub Release 触发；X/小红书/PH/V2EX 四平台；**全部人工复制发布**；Playwright 截图；飞书审批；每个 Release 3 套物料 | ✅ | 2026-11-15 |
| ADR-17 | 扩展性策略 | 模块化单体 + 适配器注册表 + 配置驱动 + lookup table；按阈值拆分；不做提前微服务化 | ✅ | 2026-11-15 |

---

## 2. 需求跟踪矩阵

> 计划范围内（Phase 0 + 模块 2）完成并通过 Task 24 验收（证据见 §7）；计划外的 CORE 行与模块 1/3/4 仍未完成。

### 2.1 Growth Core（平台底座）

| ID | 需求 / 交付物 | 来源 | 设计章节 | 实现 | 测试 | 状态 | 验收标准 |
|---|---|---|---|---|---|---|---|
| CORE-01 | `tenants` / `workspaces` / `memberships` 多租户基础表 | 架构 | §2 数据模型 | `server/growth_core/migrations/0001_core.sql` | `test_migrations.py::test_migrations_are_idempotent`; `test_postgres_integration.py::test_rls_hides_other_tenant` | ✅ | 自用 1 个 tenant + 1 个 workspace；RLS 可用 |
| CORE-02 | `tenant_credentials` + Supabase Vault 加密 | 架构 | §2 | 待建 | 待建 | 📝 | 密钥不出后端；按 provider 唯一 |
| CORE-03 | `pipeline_runs` 任务队列 + 锁 + 重试 + 死信 | 架构 | §2/§5 | `growth_core/repositories/postgres.py`; `growth_core/services/worker.py` | `test_worker_outbox.py`; `test_postgres_integration.py::test_fail_task_backoff_and_dead_letter`; `::test_claim_task_skip_locked_with_two_connections` | ✅ | `SKIP LOCKED` 不重复消费；失败可重试/告警 |
| CORE-04 | `outbox_messages` 副作用队列 | 架构 | §2/§5 | `growth_core/services/outbox.py`; `growth_core/repositories/postgres.py` | `test_worker_outbox.py::test_dispatch_outbox_*`; `test_postgres_integration.py::test_outbox_retry_marks_sent` | ✅ | 状态提交与消息写入同事务；发送幂等 |
| CORE-05 | `suppression_list` + 频率上限 | 合规 | §2/§7 | `growth_core/services/ratelimit.py`; `growth_social/services/sending.py`; `followup.py` | `test_sending.py`; `test_followup.py` | ✅ | 发送前强制检查；命中即 `suppressed` |
| CORE-06 | LLM 网关 + `llm_usage` 成本台账 | 架构 | §2 | 待建 | 待建 | 📝 | 统一模型/超时/重试/成本记录；按 tenant 汇总 |
| CORE-07 | `audit_log` 审批与状态变更审计 | 合规 | §2 | `growth_core/migrations/0001_core.sql`（audit_log） | `test_approval.py`; `test_sending.py::test_mark_sent_records_delivery_and_audit` | ✅ | 每次 approve/reject/send 可追溯 |
| CORE-08 | Supabase RLS 策略 | 安全 | §7 | `growth_core/migrations/0003_rls.sql` | `test_migrations.py::test_social_tables_exist_and_status_is_constrained`; `test_postgres_integration.py::test_rls_hides_other_tenant` | ✅ | 前端 JWT 不能跨 tenant 读写 |
| CORE-09 | 观测与告警（pipeline_runs、死信、成本） | 运维 | §7 | 待建 | 待建 | 📝 | 死信/异常推送到飞书 |
| CORE-10 | `opportunity_core` 共享包抽取 | 复用 | §3 | `opportunity_core/`（models/providers） | `server/app/` 已 import；全量 pytest 通过 | 🧪 | `opportunity_core` 已抽取且 Opportunity Scout 使用；Growth 侧复用尚未接线（见 §7.3） |
| CORE-11 | n8n 基础工作流（Cron/Webhook/审批卡） | 架构 | §6 | 待建 | 待建 | 📝 | 能触发 worker 并接收审批回调 |
| CORE-12 | 内部 API 鉴权（service token） | 安全 | §7 | `growth_core/api/deps.py`; `growth_social/api.py` | `test_api_auth.py` | ✅ | 无 token 的 `/internal/*` 请求被拒绝 |
| CORE-13 | `growth_sources` 采集源配置（subreddit/query/cadence） | 模块 2 | §3.2 | `growth_core/migrations/0002_social.sql`; `growth_social/services/ingest.py` | `test_ingest.py`; `test_migrations.py` | ✅ | 可启停/调频；记录 last_run/last_error |
| CORE-14 | `outreach_messages` + `outreach_versions` 统一触达消息、版本、审批与最终文本 | 模块 2/4 | §3.4/§3.5 | `server/growth_core/migrations/0002_social.sql`（outreach_messages/versions）; `drafting.py`; `approval.py` | `test_drafting.py`; `test_approval.py` | 🧪 | 社媒侧消息/版本/审批已验证；邮件复用未实现（见 §7.3） |
| CORE-15 | `rate_limit_rules` 平台/租户频率规则 | 合规 | §3.7 | `server/growth_core/migrations/0002_social.sql`（rate_limit_rules）; `growth_core/services/ratelimit.py` | `test_sending.py`; `test_seed.py` | ✅ | 发送前强制校验；可配置 |
| CORE-16 | `user_profiles` 用户画像、时区、营销同意状态 | 模块 4 | §4.2 | 待建 | 待建 | 📝 | 邮件只发给有同意或事务性关系的用户 |
| CORE-17 | `event_rules` 生命周期触发规则（条件/延迟/模板/自动发送） | 模块 4 | §4.3 | 待建 | 待建 | 📝 | 规则可配置；命中可解释 |
| CORE-18 | `coupon_codes` Stripe 优惠码、有效期与核销 | 模块 4 | §4.6 | 待建 | 待建 | 📝 | 一用户一码；48h 过期；核销可追踪 |
| CORE-19 | `consent_log` 订阅/退订同意记录 | 合规 | §4.7 | 待建 | 待建 | 📝 | 同意来源、时间、撤回可审计 |
| CORE-20 | `user_events` 原始事件、去重、迟到事件 | 模块 4 | §4.1 | 待建 | 待建 | 📝 | `dedupe_key` 唯一；保留原始 payload |
| CORE-21 | `delivery_log` 邮件/社交投递、打开、点击回执 | 模块 2/4 | §4.5 | 待建 | 待建 | 📝 | 原始 webhook 可追溯；与 message_id 关联 |
| CORE-22 | `suppression_list` 退订/硬退信/投诉/人工拉黑 | 合规 | §4.7 | 待建 | 待建 | 📝 | 发送前强制校验；永久生效直到人工解除 |
| CORE-23 | `provider_configs` 能力-供应商配置、优先级、密钥引用 | 扩展性 | §11.2 | `server/growth_core/migrations/0001_core.sql`（provider_configs）; `growth_core/adapters/registry.py` | `test_registry.py`; `test_seed.py` | ✅ | 新增供应商不改核心；可切换/回滚 |
| CORE-24 | `tenant_quotas` 租户配额 | 扩展性 | §11.6 | 待建 | 待建 | 📝 | 超限拒绝并告警；按日/月重置 |
| CORE-25 | `tenant_features` 功能开关 | 扩展性 | §11.6 | 待建 | 待建 | 📝 | 新适配器/流水线可灰度、可回滚 |
| CORE-26 | `config_versions` 配置版本与回滚 | 扩展性 | §11.8 | `server/growth_core/migrations/0001_core.sql`（config_versions）; `growth_core/repositories/postgres.py` | `test_postgres_integration.py::test_config_rollback_restores_snapshot` | ✅ | 变更可审计；一键回滚 |
| CORE-27 | `provider_health` 供应商健康与熔断 | 扩展性 | §11.7 | 待建 | 待建 | 📝 | 故障自动降级；半开探测 |
| CORE-28 | `rate_limit_counters` 限流计数 | 扩展性 | §11.5 | `server/growth_core/migrations/0002_social.sql`（rate_limit_counters） | `test_postgres_integration.py::test_rate_limit_is_atomic_under_concurrency` | ✅ | 原子计数；跨 worker 一致 |
| CORE-29 | `prompt_templates` Prompt 版本、输出 schema、模型提示 | 扩展性 | §11.8 | `server/growth_core/migrations/0001_core.sql`（prompt_templates）; `growth_core/seed_data.py` | `test_scoring.py`（L580 断言 prompt_version == "1"）; `test_drafting.py`; `test_followup.py`; `test_seed.py` | 🧪 | Prompt 版本化与 prompt_version 记录已验证；A/B 与回滚未实现（见 §7.3） |
| CORE-30 | `scoring_rubrics` 评分卡配置化 | 扩展性 | §11.8 | `server/growth_core/migrations/0001_core.sql`（scoring_rubrics）; `growth_core/seed_data.py` | `test_scoring.py`; `test_seed.py` | ✅ | 维度/权重/阈值版本化；新增领域不改代码 |

### 2.2 模块 2：社媒痛点截流

| ID | 需求 / 交付物 | 来源 | 设计章节 | 实现 | 测试 | 状态 | 验收标准 |
|---|---|---|---|---|---|---|---|
| M2-01 | Reddit 采集（subreddit + 关键词） | 用户方案 | §3.2 | `growth_social/adapters/reddit.py`; `services/ingest.py` | `test_reddit_adapter.py`; `test_ingest.py` | 🧪 | Reddit/HN 只读采集适配器与 cadence 配置；实际 30 分钟调度由 n8n 承担且未实现（见 §7.3） |
| M2-02 | HN 采集（Algolia 公开 API） | 架构补充 | §3.2 | `growth_social/adapters/hackernews.py` | `test_hackernews_adapter.py`; `test_ingest.py` | ✅ | 与 Reddit 同一 Signal 模型 |
| M2-03 | X 采集（官方 API） | 用户方案 | §3.2 | 待建 | 待建 | ⏸ | v1 后置；取决于 API 预算/权限 |
| M2-04 | 线索去重（platform + external_id） | 架构 | §3.2 | `services/ingest.py`; postgres `upsert_lead` ON CONFLICT | `test_ingest.py::test_duplicates_do_not_enqueue_extra_score_tasks`; `test_postgres_integration.py::test_upsert_lead_dedupes` | ✅ | 同帖不重复入库 |
| M2-05 | 意图评分（LLM rubric 0–100） | 用户方案 | §3.3 | `growth_social/services/scoring.py` | `test_scoring.py` | ✅ | JSON 输出可解析；广告/同行可识别 |
| M2-06 | Golden set 校准（50 条标注帖） | 质量 | §3.3 | `tests/growth/golden/social_posts.jsonl`（50 条） | `test_prompt_regression.py::test_golden_set_precision_at_threshold`（precision ≥ 0.8） | ✅ | 阈值 80 时 precision ≥ 0.8 |
| M2-07 | 回复草稿生成（共情+干货+软提及+1 个官方链接） | 用户方案 | §3.4 | `growth_social/services/drafting.py`; `link_policy.py` | `test_drafting.py`; `test_link_policy.py` | ✅ | 每条带 1 个官方链接；价值先行；披露关联；无夸大/违规承诺 |
| M2-08 | 飞书审批卡 | 用户方案 | §3.5 | `services/approval.py`; `cards.py`; `growth_core/adapters/feishu.py` | `test_approval.py`; `test_feishu.py`; `test_drafting.py::test_success_creates_message_version_approval_outbox_card_and_audit`; `::test_card_uses_platform_publish_time_when_available` | ✅ | v1 飞书；一键打开原帖/复制/通过/拒绝/稍后；卡片含“发布时间”（`published_at`，缺失时回退 `created_at`） |
| M2-09 | 人工发送跟踪（已发送标记） | 用户方案 | §3.6 | `growth_social/services/sending.py` | `test_sending.py::test_mark_sent_transitions_and_schedules_followup`; `::test_mark_sent_stamps_send_metadata`; `::test_mark_sent_records_delivery_and_audit` | ✅ | 记录 sent_at/channel/draft_version |
| M2-10 | 跟进提醒（每天最多 1 次，累计最多 3 次） | 用户方案 | §3.6 | `growth_social/services/followup.py`; `services/feedback.py`; `api.py`（`POST /internal/v1/social/feedback`） | `test_followup.py`; `test_feedback.py` | ✅ | 回复/退订/负反馈后立即停止；feedback API 写入 replied/suppressed 并加入抑制名单 |
| M2-11 | 抑制名单 + 频率上限（全局 50/天） | 合规 | §3.7 | `sending.py`; `followup.py`; `growth_core/services/ratelimit.py` | `test_sending.py`; `test_followup.py` | ✅ | 超限/命中抑制时禁止进入发送 |
| M2-12 | Subreddit 规则检查 | 合规 | §3.7 | `growth_social/services/approval.py`（fail-closed）; `link_policy.py`; `drafting.py` | `test_approval.py::test_subreddit_rules_fail_closed_when_missing`; `test_drafting.py::test_missing_subreddit_rules_fail_closed`; `::test_subreddit_without_links_is_suppressed`; `test_link_policy.py::test_no_link_subreddit_marks_manual_only` | ✅ | 未配置/禁自推的板块一律不生成“可发送”草稿（默认 `self_promotion_allowed=false`） |
| M2-13 | 漏斗指标（发现/合格/通过/发送/回复/转化） | 运维 | §3.8 | 待建 | 待建 | 📝 | 每周自动报表 |
| M2-14 | 安全测试（广告帖、同行、封号风险） | 质量 | §3.9 | `growth_social/adapters/`（只读 GET） | `test_reddit_adapter.py`; `test_hackernews_adapter.py`; `test_social_e2e.py`; adapters grep | ✅ | 无自动发送代码路径；危险帖被拦截 |
| M2-15 | E2E（n8n → worker → 审批 → 回调） | 质量 | §3.9 | `growth_social/worker.py`; `handlers.py` | `test_social_e2e.py::test_social_flow_from_post_to_followup` | 🧪 | worker 级链路 post→lead→score→draft→card→approval→sent→follow-up 已验证；n8n 编排属 CORE-11，未实现 |

### 2.3 模块 4：生命周期触达

| ID | 需求 / 交付物 | 来源 | 设计章节 | 实现 | 测试 | 状态 | 验收标准 |
|---|---|---|---|---|---|---|---|
| M4-01 | 事件接入（PostHog / Supabase Webhook） | 用户方案 | §4.1 | 待建 | 待建 | 📝 | 事件去重、迟到事件、条件取消可处理 |
| M4-02 | 事件规则与抑制（退订/频率/黑名单） | 合规 | §4.3/§4.4 | 待建 | 待建 | 📝 | 命中抑制不发送；1 封/24h、3 封/7 天 |
| M4-03 | 个性化邮件生成（纯文本） | 用户方案 | §4.5 | 待建 | 待建 | 📝 | 一用户一封；80–120 词；含退订句 |
| M4-04 | Resend 发送 + 投递回执 | 用户方案 | §4.6 | 待建 | 待建 | 📝 | 发送成功/失败可追踪；幂等 |
| M4-05 | 打开/点击/核销归因 | 用户方案 | §4.8 | 待建 | 待建 | 📝 | delivery_log 可算漏斗；UTM 可归因 |
| M4-06 | Stripe 挽留优惠券 | 用户方案 | §4.7 | 待建 | 待建 | 📝 | 30% off once；48h 过期；核销可追踪 |
| M4-07 | 每周增长漏斗报表 | 用户方案 | §4.8 | 待建 | 待建 | 📝 | 周一 09:00 自动推送飞书 |

### 2.4 模块 1：pSEO 自动建站

| ID | 需求 / 交付物 | 来源 | 设计章节 | 实现 | 测试 | 状态 | 验收标准 |
|---|---|---|---|---|---|---|---|
| M1-01 | 关键词发现（DataForSEO/Google Suggest/Serper） | 用户方案 | §1.2 | 待建 | 待建 | 📝 | 可批量入库；来源可追溯 |
| M1-02 | 关键词过滤（KD/volume/意图/聚类） | 用户方案 | §1.3 | 待建 | 待建 | 📝 | KD<20 等规则可配置；同簇不重复 |
| M1-03 | SERP 前三名大纲提取 | 用户方案 | §1.4 | 待建 | 待建 | 📝 | 事实来源记录在 generation_meta |
| M1-04 | 结构化文章生成（痛点/步骤/对比/FAQ） | 用户方案 | §1.5 | 待建 | 待建 | 📝 | 按模板输出 Markdown/MDX |
| M1-05 | 内链自动注入 | 用户方案 | §1.7 | 待建 | 待建 | 📝 | 锚文本指向功能页/注册页；无孤儿页 |
| M1-06 | 内容质量门（重复度/事实/可读性） | 质量 | §1.6 | 待建 | 待建 | 📝 | 质量分 <80 不进入发布 |
| M1-07 | GitHub PR（按批次） | 用户方案 | §1.8 | 待建 | 待建 | 📝 | v1 PR + 人工合并；CI 通过 |
| M1-08 | Vercel/Cloudflare 构建触发 | 用户方案 | §1.8 | 待建 | 待建 | 📝 | 构建成功才标记 published；失败回滚 |
| M1-09 | Sitemap + IndexNow 收录（修正 Google Indexing API） | 用户方案 | §1.9 | 待建 | 待建 | 📝 | Google 走 sitemap；Bing/Yandex 走 IndexNow |
| M1-10 | 排名/点击/转化回流 | 用户方案 | §1.10 | 待建 | 待建 | 📝 | GSC + PostHog 数据可查 |

### 2.5 模块 3：爆款内容二创矩阵

| ID | 需求 / 交付物 | 来源 | 设计章节 | 实现 | 测试 | 状态 | 验收标准 |
|---|---|---|---|---|---|---|---|
| M3-01 | 同行爆款库（10–20 账号） | 用户方案 | §3.2 | 待建 | 待建 | 📝 | 每周抓取高互动内容；hook/情绪/节奏标签 |
| M3-02 | Hook/情绪/排版拆解 | 用户方案 | §3.3 | 待建 | 待建 | 📝 | 沉淀为 Prompt 模板库；只拆结构不抄内容 |
| M3-03 | GitHub Release / CHANGELOG 触发 | 用户方案 | §3.4 | 待建 | 待建 | 📝 | Webhook 可触发内容生成 |
| M3-04 | 三形态内容生成（X/小红书/PH/V2EX） | 用户方案 | §3.5 | 待建 | 待建 | 📝 | 同一 Release 生成三套物料 |
| M3-05 | 产品截图 + 渐变背景图 | 用户方案 | §3.6 | 待建 | 待建 | 📝 | Playwright 截真实界面；无 PII |
| M3-06 | 人工复制发布 + 审批 checklist | 用户方案 | §3.7 | 待建 | 待建 | 📝 | 品牌渠道先审后发；v1 不自动发帖 |

### 2.6 横切能力

| ID | 需求 / 交付物 | 来源 | 设计章节 | 实现 | 测试 | 状态 | 验收标准 |
|---|---|---|---|---|---|---|---|
| XC-01 | 合规策略（只读采集/人工发送/不绕登录） | 合规 | §3.7 | `growth_social/adapters/`（仅 GET，无发帖/私信代码） | `test_social_e2e.py`; adapters grep | ✅ | 代码中无自动发帖/私信路径 |
| XC-02 | 成本控制（LLM/API 预算与告警） | 运维 | §7 | 待建 | 待建 | 📝 | 按 tenant/pipeline 日预算 |
| XC-03 | 观测（结构化日志/漏斗/死信告警） | 运维 | §7 | 待建 | 待建 | 📝 | 关键失败 5 分钟内告警 |
| XC-04 | 密钥与权限（Vault/service token/RLS） | 安全 | §7 | 待建 | 待建 | 📝 | 前端不可见密钥；跨租户拒绝 |
| XC-05 | 文档（spec/plan/runbook/跟踪矩阵） | 工程 | 全篇 | `docs/growth-runbook.md`; `.env.growth.example`; spec/plan | — | 🧪 | Phase 0 + 模块 2 有 spec/plan/runbook；模块 1/3/4 尚未编写 |
| XC-06 | 扩展点契约测试（adapter/pipeline/config schema） | 工程 | §11.11 | 待建 | 待建 | 📝 | 新适配器通过同一套 fixture |
| XC-07 | 队列分池与背压 | 运维 | §11.5 | 待建 | 待建 | 📝 | 按 provider/tenant 限并发；锁超时回收 |
| XC-08 | 租户配额与功能开关 | 扩展性 | §11.6 | 待建 | 待建 | 📝 | 超限不执行；灰度可回滚 |
| XC-09 | 数据分区与归档 | 运维 | §11.9 | 待建 | 待建 | 📝 | 热表 >10M 可月分区 |
| XC-10 | 拆分阈值与 runbook | 工程 | §11.10 | 待建 | 待建 | 📝 | 达到阈值有明确动作 |
| XC-11 | Prompt/Rubric 版本化与回归 | 工程 | §11.8 | 待建 | 待建 | 📝 | 每个版本有 golden set；可回滚 |

### 2.7 实现计划与交付追踪（audit / traceability）

| ID | 交付物 | 来源 | 设计 / 计划 | 实现 | 测试 | 状态 | 验收 / 证据 |
|---|---|---|---|---|---|---|---|
| PLAN-01 | Phase 0/1 实现计划（Phase 0 平台底座 + 模块 2 社媒截流） | 设计 spec §6/§11 | [2026-11-15-growth-agent-phase0-module2.md](docs/superpowers/plans/2026-11-15-growth-agent-phase0-module2.md)（24 个任务） | `server/growth_core/`、`server/growth_social/`、`server/.env.growth.example`、`server/docs/growth-runbook.md` | `server/tests/growth/`（全量 493 passed / 1 skipped，DB env 下） | ✅ | Task 24 验收通过 2026-11-19；命令与逐项映射见 §7 |

---

## 3. 测试矩阵

| 层级 | 覆盖对象 | 工具 | 状态 | 备注 |
|---|---|---|---|---|
| 单元测试 | 状态迁移、去重、限流、抑制、Prompt JSON 解析 | pytest | ✅ | 424 growth tests passed（无 DB env），见 §7.1 |
| 集成测试 | Provider fixture → DB → 评分 → 草稿 | pytest + 本地 Postgres | ✅ | DB env 下 493 passed / 1 skipped；27 条集成用例通过 |
| Prompt 回归 | 50 条 golden set；评分分档；禁用词 | pytest | ✅ | `test_prompt_regression.py`：50 条、precision ≥ 0.8（阈值 80） |
| 安全测试 | 广告帖、同行、禁自推板块、自动发送路径 | pytest | ✅ | 只读适配器 grep + `test_link_policy.py` + `test_social_e2e.py` |
| E2E | n8n → worker → 审批卡 → 回调 → 状态 | pytest（worker 级） | 🧪 | `test_social_e2e.py` 已覆盖 worker→审批→发送→跟进；n8n/Playwright 未建（CORE-11） |
| 真实环境 | Reddit/HN 只读采集、飞书卡片 | 手工 + 日志 | ❌ | 记录限流与错误码 |
| 成本测试 | 100 条帖子的 LLM 成本 | llm_usage | ❌ | 目标 < $0.50/100 条（按模型调整） |

---

## 4. 模块验收标准（DoD）

### 4.1 模块 2（第一个上线）

- 连续 7 天每 30 分钟采集 Reddit + HN，无重复线索、无封号/限流事故。
- 50 条 golden set 上，意图评分阈值 80 的 precision ≥ 0.8。
- 至少生成 20 条草稿，人工审批通过率 ≥ 50%。
- 至少人工发送 10 条，回复率可统计。
- 代码中不存在自动发帖/私信路径；所有发送有审计记录。
- 单条合格线索的 LLM 成本可核算。

### 4.2 模块 4

- 三类事件（注册 24h 未激活、额度 80%、取消订阅）可触发。
- 退订/抑制/频率上限 100% 生效。
- 邮件打开/点击/核销可归因。
- 每周漏斗报表自动推送。

### 4.3 模块 1

- 关键词入库 → 文章生成 → PR → 构建 → 收录 全链路可跑。
- 每篇文章有事实来源与内链检查。
- 至少 10 篇真实页面被 Google 收录。
- 排名/点击数据可回流。

### 4.4 模块 3

- GitHub Release 能触发三形态内容生成。
- 截图来自真实界面，视觉模板可复用。
- 所有品牌渠道先审后发。

---

## 5. 未决问题

| # | 问题 | 影响 | 建议默认 |
|---|---|---|---|
| Q1 | v1 是否只做 Reddit + HN，X 后置？ | 采集范围/成本 | ✅ 已确认：是；X 后置到 M2.5 |
| Q2 | 审批入口用 Telegram 还是飞书？ | 模块 2/4 体验 | ✅ 已确认：飞书 |
| Q3 | 意图评分阈值 80、每日回复上限 5 是否合适？ | 线索质量/封号风险 | ✅ 已确认：阈值 80；Reddit 5/天；全局 50/天 |
| Q4 | 首条回复是否坚持不带链接？ | 转化/封号 | ✅ 已确认：都要带链接；每条 1 个官方链接 + 关联披露 + 子版规则校验 |
| Q8 | 跟进累计上限？ | 封号/骚扰风险 | 每天最多 1 次，累计最多 3 次；回复/退订/负反馈立即停止 |
| Q5 | pSEO 发布走 PR 还是直接 commit？ | 品牌/质量风险 | v1 走 PR + 人工合并 |
| Q6 | 模块 3 是否并入模块 1 的内容引擎？ | 架构复杂度 | 先独立，复用 content_queue 与截图服务 |
| Q7 | Opportunity Scout 的 Signal 是否同步到 Supabase？ | dogfooding 增量 | v1 可选；不阻塞模块 2 |

---

## 6. 变更日志

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-15 | v0.1 | 初始矩阵：ADR 1–12、Core + 四模块需求、测试矩阵、DoD、未决问题 |
| 2026-11-15 | v0.2 | 补充 `growth_sources`、`outreach_drafts`、`rate_limit_rules` 三张支撑表 |
| 2026-11-15 | v0.3 | 确认 ADR-07/08/09/12/13；模块 2 改为飞书审批、全局 50/天、每条带链接、每天最多 1 次跟进；`outreach_drafts` 升级为 `outreach_messages` + `outreach_versions`；补模块 4 支撑表 |
| 2026-11-15 | v0.4 | 确认 ADR-14；模块 4 设计完成：Resend、部分自动发送、30% off once/48h、周报飞书；补 `user_events`、`delivery_log`、`suppression_list` |
| 2026-11-15 | v0.5 | 确认 ADR-15；模块 1 设计完成：PR + 人工合并、质量分 80、5–10 篇/周；修正 Google Indexing API 不适用普通博客，改为 sitemap + IndexNow |
| 2026-11-15 | v0.6 | 确认 ADR-16；模块 3 设计完成：GitHub Release 触发、四平台三套物料、全部人工复制发布、Playwright 截图、飞书审批 |
| 2026-11-15 | v0.7 | 确认 ADR-17；补扩展性设计：适配器注册表、lookup table、Pipeline 契约、队列分池/背压、租户配额/功能开关、故障转移、配置版本、分区索引、拆分阈值；新增 CORE-23–30、XC-06–11 |
| 2026-11-15 | v0.8 | 完成 Phase 0 + 模块 2 实施计划（24 个任务，TDD 步骤，含迁移、队列/outbox、飞书审批、发送追踪、跟进与验收清单）；计划待评审，尚未开始编码 |
| 2026-11-19 | v0.9 | 补充 Phase 0/1 实现计划追踪行（PLAN-01）与 runbook / `.env.growth.example`；Phase 0 + 模块 2 状态 🔨（实现中）；完成行待 Task 24 验收后标记 ✅ 并附证据命令 |
| 2026-11-19 | v1.0 | Task 24 验收通过：Phase 0 + 模块 2 已验证行标记 ✅、部分验证行标记 🧪（CORE-10/14/29、M2-01/15、XC-05）；记录实际命令结果（468/493 backend、424 growth-only、27 integration、22 frontend、compileall、npm run check）与逐项验收映射（§7）；n8n、Vault、llm_usage、告警、配额/开关、熔断、漏斗报表与 X 适配器保持未完成 |
| 2026-11-19 | v1.1 | 最终修复轮：新增 feedback/unsubscribe API 与审计（M2-10）、ingest/scoring 入队失败恢复、同用户单次联系规则、链接形式识别加固、原始发送关闭状态门禁、subreddit 规则 fail-closed（M2-12）、审批卡发布时间（M2-08）、人工发送 operator 审计；记录修复轮实测 500/526 backend、456 growth-only、28 integration |

---

## 7. 验收证据（Task 24，2026-11-19）

环境：本地 Postgres 测试库 `postgresql://postgres@127.0.0.1:55432/growth_test`（superuser，迁移 0001–0005）。以下命令均在退出码 0 的前提下记录。

### 7.1 命令与结果

| 工作目录 | 命令 | 结果 |
|---|---|---|
| `server/` | `python -m pytest -q` | **500 passed, 27 skipped**（exit 0） |
| `server/` | `GROWTH_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/growth_test python -m pytest -q` | **526 passed, 1 skipped**（exit 0） |
| `server/` | `python -m pytest tests/growth -q`（不带 DB env） | **456 passed, 27 skipped**（exit 0） |
| `server/` | `GROWTH_TEST_DATABASE_URL=... python -m pytest tests/growth/test_postgres_integration.py tests/growth/test_repository_postgres.py tests/growth/test_migrations.py tests/growth/test_seed.py -q` | **28 passed**（exit 0） |
| `server/` | `python -m compileall -q app opportunity_core growth_core growth_social` | exit 0 |
| `web/` | `npm run check`（`tsc --noEmit` + `eslint .` + `vitest run`） | typecheck/lint 通过；**4 test files, 22 tests passed**（exit 0） |

说明：计划 Brief 中的“43 backend tests”是过时数字；本次实测后端为 500（无 DB）/ 526（有 DB）。前端 vitest 实测 22 条。

> 2026-11-19 修复轮：新增 feedback 写入路径、ingest/scoring 入队恢复、同作者联系规则、链接识别加固与 fail-closed subreddit 规则；新增迁移 `0005_audit_integration_actor.sql`（审计 actor_type 允许 `integration`）。上表为修复轮后的实测数字。

### 7.2 验收清单 → 证据映射

| 验收项 | 证据（文件::测试） |
|---|---|
| Ingest Reddit/HN mock → lead 只创建一次、去重生效 | `tests/growth/test_ingest.py::test_duplicates_do_not_enqueue_extra_score_tasks`、`::test_dedupe_key_is_exact_sha256_hex`；`test_postgres_integration.py::test_upsert_lead_dedupes` |
| 高分 → 建草稿任务；低分 → dropped；watch → 不建草稿 | `test_scoring.py::test_qualified_enqueues_exact_draft_task`、`::test_watch_and_dropped_do_not_enqueue`；阈值定义 `growth_core/seed_data.py:96`（qualified 80 / watch 60） |
| 草稿恰好 1 个官方链接、UTM、披露；缺链接/多链接被拒 | `test_link_policy.py`（`test_two_links_rejected`、`test_missing_utm_rejected`、`test_missing_disclosure_rejected`、`test_homepage_rejected`、`test_shortener_rejected`）；`test_drafting.py::test_llm_policy_violation_is_rejected`；e2e `_assert_one_official_link` |
| 飞书卡片含标题、分数、草稿、链接、警告、发布时间、approve/reject/edit/later | `test_drafting.py::test_success_creates_message_version_approval_outbox_card_and_audit`（断言 title、score 91、risk flags、正文、链接、四个按钮）；`::test_card_uses_platform_publish_time_when_available`（发布时间） |
| 审批幂等；拒绝留痕；修订生成新版本 | `test_approval.py::test_duplicate_approve_is_idempotent`、`::test_reject_transitions_to_rejected`、`::test_revise_creates_new_version_and_new_approval` |
| 发送记录 `sent_at`、`channel`、`draft_version`；重复发送被阻止 | `test_sending.py::test_mark_sent_transitions_and_schedules_followup`（sent_at）、`::test_mark_sent_stamps_send_metadata`（channel/draft_version）、`::test_mark_sent_requires_approved_status`（非 approved 拒绝） |
| 发送时强制全局 50/天、Reddit 5/天、subreddit 2/天 | `test_sending.py::_seed_rules`（50/5/2）及 `::test_mark_sent_blocks_global_daily_limit`、`::test_mark_sent_blocks_reddit_daily_limit`、`::test_mark_sent_blocks_subreddit_link_limit`；`test_postgres_integration.py::test_rate_limit_is_atomic_under_concurrency` |
| 抑制名单阻止发送与跟进 | `test_sending.py::test_mark_sent_blocks_suppressed_platform_user`；`test_followup.py::test_followup_stops_when_author_is_suppressed` |
| 跟进每天最多 1 次、累计最多 3 次；回复/负反馈即停 | `test_followup.py::test_followup_reschedules_until_one_day`、`::test_followup_stops_after_three`、`::test_followup_stops_when_lead_replied`、`::test_followup_stops_when_lead_is_closed`（replied/converted/suppressed/rejected）；`test_feedback.py`（replied/suppressed、抑制名单、幂等、404、401） |
| 同一用户只回复一次；关闭的线索不再原发 | `test_sending.py::test_mark_sent_blocks_second_original_for_same_author`、`::test_mark_sent_allows_followup_for_same_author`、`::test_mark_sent_allows_original_for_different_author`、`::test_mark_sent_blocks_original_when_lead_closed` |
| 所有链接形式都计入“恰好一条”规则 | `test_link_policy.py::test_alternate_link_forms_are_detected_and_rejected`（大写 scheme / www / 裸域名 / 协议相对）、`::test_file_extension_is_not_a_link`、`::test_duplicate_official_link_is_rejected` |
| 不存在向 Reddit/HN/任意平台发帖、评论、私信或登录的代码路径 | `growth_social/adapters/reddit.py` 与 `hackernews.py` 仅调用 `client.get`（Reddit `new.json`、HN `search_by_date`）；grep `post/comment/dm/oauth/login` 同时命中 FastAPI 入站路由装饰器（`growth_social/api.py` 的 `@protected_router.post`）与 `growth_core/adapters/feishu.py:173,210` 的飞书卡片出站 POST，但无任何发往 Reddit/HN 的出站写调用；`test_social_e2e.py` 断言 notifier 仅在 `dispatch_outbox` 时被调用（L349–451） |
| E2E 全链路 | `test_social_e2e.py::test_social_flow_from_post_to_followup`：1 lead → 1 qualified（100）→ 1 draft → 1 card → 1 approval → 1 sent → +24h 1 follow-up |
| 既有后端/前端测试保持绿色，`npm run check` 不受影响 | 见 §7.1（468/493 backend；22 frontend；exit 0） |

### 7.3 已知缺口与范围外事项

- **79/80 精确边界未单独断言**：实现使用 `score >= threshold`（`growth_social/services/scoring.py:87-91`），种子阈值为 80/60；测试覆盖 50/55/60/70/77/88/100 等相邻取值，但没有 79 与 80 的成对用例。此为测试覆盖缺口，非功能失败。
- **n8n 编排未实现**（CORE-11 保持 📝）：E2E 是 Python worker/handler 级别链路，不包含真实 n8n workflow 与 Playwright。
- **保持未完成**：CORE-02（tenant_credentials/Vault）、CORE-06（llm_usage 成本台账）、CORE-09（观测告警）、CORE-24/25（tenant_quotas/tenant_features 强制执行）、CORE-27（provider_health 熔断）、M2-13（每周漏斗报表）；M2-03（X 采集）按计划 ⏸。
- **30 分钟采集节奏尚未端到端验证**：`growth_sources.cadence_minutes` 默认存 30，但定时触发依赖尚未实现的 n8n（CORE-11）；当前只有手动/任务种子触发。
- **CORE-14 的邮件复用未验证**：`outreach_messages/versions` 由社媒链路使用；模块 4 邮件尚未实现，跨渠道复用待后续模块验证。
- **CORE-10 Growth 侧复用未接线**：`opportunity_core` 仅被 `server/app/`（Opportunity Scout）import；`growth_core`/`growth_social` 未使用，跨产品复用待后续。
- **CORE-29 仅完成版本化与记录**：`prompt_version` 已落库（`test_scoring.py` L580 断言为 `"1"`）；A/B 与一键回滚未实现。
- **XC-05 文档仅覆盖 Phase 0 + 模块 2**：模块 1/3/4 尚无 plan/runbook。
- 本次未改动任何业务代码或测试代码，仅更新本跟踪矩阵。
