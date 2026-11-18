# Growth Agent 运行手册（Phase 0 + 模块 2）

> 范围：Phase 0 平台底座 + 模块 2 社媒截流（Reddit / Hacker News → 评分 → 草稿 → 飞书审批 → 人工发送 → 有界跟进）。
>
> 设计：[../../docs/superpowers/specs/2026-11-15-growth-agent-design.md](../../docs/superpowers/specs/2026-11-15-growth-agent-design.md)  
> 计划：[../../docs/superpowers/plans/2026-11-15-growth-agent-phase0-module2.md](../../docs/superpowers/plans/2026-11-15-growth-agent-phase0-module2.md)

## 0. 进程模型

运行时是**两个独立进程**，二者都必须提供同一组 `GROWTH_*` 环境变量，并在 `server/` 目录下启动：

| 进程 | 命令 | 职责 |
|---|---|---|
| Worker | `python -m growth_social.worker` | 消费 `pipeline_runs`（采集、评分、草稿、跟进检查），并执行 outbox 派发；**飞书审批卡由 worker 发送** |
| API | `uvicorn growth_social.asgi:app --host 0.0.0.0 --port 8780` | 接收 n8n 内部调用与飞书回调，只写任务/状态，不投递卡片 |

只启动 API 不会产生审批卡：草稿任务把 `feishu.card` 写入 `outbox_messages`，必须由 worker 的 `dispatch_outbox` 发出。Postgres 是唯一事实来源，n8n 不直接写业务表。

以下命令默认从仓库根目录执行，先 `cd server`。

```bash
cd server
cp .env.growth.example .env.growth     # 首次；填入真实值
set -a; source .env.growth; set +a
```

代码只读取 `os.environ`，**不会自动加载 `.env` 文件**；每次开新 shell 都要重新 `source`。

必填四项：`GROWTH_DATABASE_URL`、`GROWTH_SERVICE_TOKEN`、`GROWTH_TENANT_ID`、`GROWTH_WORKSPACE_ID`。缺任意一项，API 在 import 时抛 `GrowthConfigError`，worker 启动时同样失败。

### 环境变量与实际生效位置

种子数据会把供应商地址、限流规则、Prompt、评分卡写进数据库；v1 中部分 env 字段只被 `GrowthSettings` 读取、尚未回写这些行，排障时不要误以为改 env 就生效：

| 变量 | 实际作用 |
|---|---|
| `GROWTH_DATABASE_URL` / `GROWTH_SERVICE_TOKEN` / `GROWTH_TENANT_ID` / `GROWTH_WORKSPACE_ID` | 必填；DB 连接、内部 API 鉴权、缺省租户/工作区、飞书回调租户 |
| `GROWTH_FEISHU_APP_ID` / `GROWTH_FEISHU_APP_SECRET` | 飞书应用凭证（`APP_SECRET` 通过 `secret_ref` 解析） |
| `GROWTH_FEISHU_VERIFICATION_TOKEN` | 飞书回调验签 token |
| `GROWTH_FEISHU_CHAT_ID` | 审批卡接收群 |
| `GROWTH_FEISHU_ENCRYPT_KEY` | v1 **必须留空**（见 §3） |
| `GROWTH_REDDIT_USER_AGENT` | Reddit 只读请求的 UA（`secret_ref` 直接解析） |
| `GROWTH_LLM_API_KEY` | LLM 密钥（`secret_ref` 直接解析） |
| `GROWTH_LLM_SCORING_MODEL` / `GROWTH_LLM_DRAFTING_MODEL` | 评分/草稿使用的模型；**必须设置**，否则任务以 `PROVIDER_NOT_CONFIGURED: llm model` 失败 |
| `GROWTH_PRODUCT_NAME` / `GROWTH_PRODUCT_URL` / `GROWTH_PRODUCT_DOMAIN` | 草稿中的产品名、官方链接域名与 UTM 目标；`URL`、`DOMAIN` 必填 |
| `GROWTH_FOLLOWUP_MAX_TOTAL` / `GROWTH_FOLLOWUP_MIN_INTERVAL_HOURS` | 跟进上限与最小间隔 |
| `GROWTH_WORKER_ID` / `GROWTH_WORKER_POLL_SECONDS` | worker 标识与空闲轮询间隔 |
| `GROWTH_FEISHU_BASE_URL`、`GROWTH_REDDIT_BASE_URL`、`GROWTH_HN_BASE_URL`、`GROWTH_LLM_BASE_URL`、`GROWTH_LLM_MODEL`、`GROWTH_LLM_TIMEOUT_SECONDS`、`GROWTH_GLOBAL_DAILY_LIMIT`、`GROWTH_REDDIT_DAILY_LIMIT`、`GROWTH_SUBREDDIT_LINK_DAILY_LIMIT`、`GROWTH_STALE_LOCK_SECONDS` | 已被配置对象读取，但 v1 运行路径未使用；供应商地址/限流以数据库为准（见 §2、§8） |

## 1. Supabase / Postgres

1. 在 Supabase 新建项目，从 **Project Settings → Database → Connection string (URI)** 取连接串。迁移包含 DDL 且使用 `asyncpg`，建议用 **5432 直连或 session pooler**；事务模式 pooler（6543）未验证。
2. Python 服务使用该 DSN 连接。迁移会在业务表上启用 RLS，而策略依赖 `auth.jwt()`；服务端不设置 JWT claims，因此**生产 DSN 必须使用表 owner（如 Supabase `postgres`）或具备 BYPASSRLS 的角色**。用受限角色连库时，缺少 schema `auth` 的 USAGE 会直接报权限错误；即使授权齐全，未设置 JWT claims 也会让 RLS 把查询过滤成空结果。
3. 写入 `.env.growth` 后执行迁移（幂等，可重复运行）：

```bash
cd server
set -a; source .env.growth; set +a
python -m growth_core.migrate
```

也可显式指定：`python -m growth_core.migrate --database-url "$GROWTH_DATABASE_URL"`。输出 `Applied migrations: ...` 或 `No pending migrations.`。

## 2. 初始化租户与采集源

```bash
cd server
set -a; source .env.growth; set +a
python -m growth_core.scripts.seed \
  --tenant-id 00000000-0000-0000-0000-000000000001 \
  --workspace-id 00000000-0000-0000-0000-000000000002
```

`seed` 幂等（`on conflict do nothing`），写入租户/工作区、`provider_configs`、评分卡、Prompt、配额、功能开关和限流规则；它**不会**创建 `growth_sources` 采集源，需要单独插入。

种子后的关键默认值：

- 限流（`rate_limit_rules`，channel=`social`）：全局 50 次/天、Reddit 5 次/天、同 subreddit 带链回复 2 次/天。
- 评分阈值：≥80 `qualified`（自动入队草稿）、60–79 `watch`、<60 `dropped`。
- LLM provider `openai_compatible` 的 `base_url` 为 `https://api.openai.com/v1`。用其他 OpenAI 兼容网关时改 DB 行（env 的 `GROWTH_LLM_BASE_URL` 在 v1 不覆盖它）：

```sql
update provider_configs
set config = config || '{"base_url":"https://api.deepseek.com/v1"}'::jsonb
where tenant_id = '00000000-0000-0000-0000-000000000001'
  and capability = 'llm' and provider = 'openai_compatible';
```

插入 Reddit / HN 采集源（`source_type` 必须是 `reddit` / `hackernews`；Reddit 配置键 `subreddit`、`keywords`、`limit`，HN 配置键 `query`、`limit`）：

```bash
psql "$GROWTH_DATABASE_URL" <<'SQL'
insert into growth_sources
  (tenant_id, workspace_id, source_type, platform, dedupe_key, config, cadence_minutes)
values
  ('00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000002',
   'reddit', 'reddit', 'reddit:r/SaaS',
   '{"subreddit":"SaaS","keywords":["saas","founder"],"limit":25}', 30),
  ('00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000002',
   'hackernews', 'hackernews', 'hn:saas-founder',
   '{"query":"saas founder","limit":25}', 30)
on conflict (tenant_id, dedupe_key) do nothing;
SQL
```

`cadence_minutes` 只是记录值；实际每 30 分钟触发由 n8n 负责（见 §4）。

worker 在启动时按当时已启用的源构建 `source_type → adapter` 映射（`build_social_adapters`）。新增采集源后，若是此前未启用的 `source_type`，必须重启 worker；否则 ingest 会记录 `ADAPTER_NOT_CONFIGURED: no adapter for source_type <type>`。同一 `source_type` 下增加额外采集源通常无需重启。

## 3. 飞书应用

1. 在飞书开放平台创建企业自建应用，启用机器人能力。
2. 权限（scope）：`im:message`、`im:message:send_as_bot`；发布应用版本，并把机器人拉进审批群。
3. 审批群 ID 填入 `GROWTH_FEISHU_CHAT_ID`（群设置 → 群信息中获取 `chat_id`，形如 `oc_...`）。
4. **事件与回调 → 回调配置**的请求地址设为：

```text
https://<你的 API 公网域名>/internal/v1/approvals/callback
```

飞书 URL 校验会带 `challenge` 与验证 token；API 验签通过后原样返回 `challenge`。卡片按钮回调也走同一路径。

5. 把应用的 **Verification Token** 填入 `GROWTH_FEISHU_VERIFICATION_TOKEN`（必须与飞书后台一致；留空会导致回调全部 403）。
6. **`GROWTH_FEISHU_ENCRYPT_KEY` 在 v1 必须留空。** 当前只实现签名校验路径，没有实现飞书 AES 加密事件信封的解密；一旦设置该 key，飞书发来的加密（非明文）payload 不会被解密，URL 校验无法回显 challenge，按钮回调也无法解析。等加密信封实现后再启用。
7. 回调没有 `X-Service-Token`，只靠签名 / verification token 鉴权。回调使用的租户固定取 `GROWTH_TENANT_ID`，一个 API 实例只服务一个租户。
8. 审批卡由 worker 的 outbox 派发。**worker 不运行，卡片永远不会到群里**，即使 API 正常接收回调。

## 4. n8n 工作流

每 30 分钟调用一次 ingest（Schedule Trigger + HTTP Request 节点）。该调用只把 `social.ingest` 任务写入队列，真正采集由 worker 执行；执行后新线索会自动入队评分，评分 `qualified` 会自动入队草稿。

```bash
curl -X POST "https://<你的 API 公网域名>/internal/v1/social/ingest" \
  -H "X-Service-Token: $GROWTH_SERVICE_TOKEN" \
  -H "X-Tenant-Id: $GROWTH_TENANT_ID" \
  -H "X-Workspace-Id: $GROWTH_WORKSPACE_ID" \
  -H "Idempotency-Key: ingest-$(date +%Y%m%d%H%M)"
```

n8n HTTP Request 节点对应：

- Method：`POST`
- URL：`https://<你的 API 公网域名>/internal/v1/social/ingest`
- Header `X-Service-Token`：当前实例的 `GROWTH_SERVICE_TOKEN`
- Header `X-Tenant-Id` / `X-Workspace-Id`：租户/工作区 UUID（不传时回退到进程环境里的 `GROWTH_TENANT_ID` / `GROWTH_WORKSPACE_ID`；显式传更稳）
- Header `Idempotency-Key`：`ingest-{{$now.toFormat('yyyyMMddHHmm')}}`

同一分钟内重试会命中同一幂等键，只产生一个任务；缺少 `Idempotency-Key` 返回 400 `INVALID_IDEMPOTENCY_KEY`。

重放评分/草稿（通常不需要，ingest/评分链路已自动入队）：

```bash
curl -X POST "https://<你的 API 公网域名>/internal/v1/social/score" \
  -H "X-Service-Token: $GROWTH_SERVICE_TOKEN" \
  -H "X-Tenant-Id: $GROWTH_TENANT_ID" \
  -H "X-Workspace-Id: $GROWTH_WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{"lead_id":"<lead-uuid>"}'

curl -X POST "https://<你的 API 公网域名>/internal/v1/social/draft" \
  -H "X-Service-Token: $GROWTH_SERVICE_TOKEN" \
  -H "X-Tenant-Id: $GROWTH_TENANT_ID" \
  -H "X-Workspace-Id: $GROWTH_WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{"lead_id":"<lead-uuid>"}'
```

n8n 不得直接写业务表；所有状态变更走 `/internal/v1/*`（ADR-12）。

## 5. 启动 worker 与 API

```bash
cd server
set -a; source .env.growth; set +a

# 终端 1：任务 + outbox（飞书卡片）
python -m growth_social.worker

# 终端 2：内部 API + 飞书回调
uvicorn growth_social.asgi:app --host 0.0.0.0 --port 8780
```

健康检查（无需鉴权）：

```bash
curl -s http://127.0.0.1:8780/healthz
# {"status":"ok"}
```

生产环境请用 systemd / launchd / 容器守护两个进程；API 没有开发热重载，worker 也没有内置 supervisor。

## 6. 日常审批与人工发送

1. worker 生成草稿后，飞书群收到审批卡：帖子、分数、评分理由、风险标记、subreddit 规则、草稿全文、最终链接。卡片按钮为 **Approve / Edit / Reject / Later**。
2. **Approve** 只把消息状态改为 `approved`，不会发布任何内容。**Edit** 只返回“到管理端修改”的提示；实际修改走 `POST /api/growth/social/messages/{id}/revise`，会创建新版本、过期旧卡并重新发卡。**Reject** 记录拒绝。**Later** 只提示仍待审批。
3. 人工打开原帖，复制卡片中的草稿，**在平台网页上手动粘贴发送**。
4. 发送后在管理端点“已发送”，或调用 POST 记录；这是人工动作的记账，不是自动发送：

```bash
curl -X POST "http://127.0.0.1:8780/api/growth/social/messages/<message-id>/sent" \
  -H "X-Service-Token: $GROWTH_SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel":"manual"}'
```

   `X-Tenant-Id` / `X-Workspace-Id` 可省略（回退到环境变量）。成功返回 `status: "sent"`、`sent_at`、`channel`。
5. 记录发送时会再次检查抑制名单与当日频率；超限或命中抑制的消息会被置为 `suppressed` 并返回错误（见 §8）。
6. 发送后会入队一次次日跟进检查；跟进同样要审批、同样只由人工发送，累计最多 3 次、至少间隔 24 小时，lead 回复/拒绝/抑制后停止。

**绝不自动化登录态平台会话**：代码中不存在自动发帖/评论/私信的路径。所有回复必须人工审批、人工发送；“已发送”只是人工动作的记录。

## 7. 测试

单元测试（不需要数据库）：

```bash
cd server
python -m pytest -q
```

Postgres 集成测试：

```bash
cd server
GROWTH_TEST_DATABASE_URL='postgresql://user:password@host:5432/growth_test' \
  python -m pytest tests/growth/test_postgres_integration.py \
                   tests/growth/test_repository_postgres.py \
                   tests/growth/test_migrations.py \
                   tests/growth/test_seed.py -q
```

注意事项：

- `GROWTH_TEST_DATABASE_URL` 必须指向**专用的、可随时丢弃的测试库**。`pg_repo` fixture 会调用 `truncate_all_for_tests()`，清空**所有租户**的增长数据；绝不能指向生产或共享 staging。
- 未设置 `GROWTH_TEST_DATABASE_URL` 时，数据库相关用例会 skip；发布候选必须实际跑通。
- RLS 用例会创建 `growth_test_app` 角色并授权，并在事务中 `set local role growth_test_app`；这通常要求 superuser 或对该角色有 membership，另外建角色/授权还需要 CREATEROLE 与表所有权。DSN 必须是具备这些权限的角色；受限 CI 角色会直接报错，而不是 skip。
- 迁移在测试库上幂等执行；同一测试库不要并发跑多组集成测试。

## 8. 故障排查

### 401 `invalid service token`

- 所有 `/internal/*` 与 `/api/growth/*`（飞书回调、`/healthz` 除外）都要求 `X-Service-Token` 与当前进程的 `GROWTH_SERVICE_TOKEN` 完全一致。
- 检查：header 名拼写（`X-Service-Token`）、反向代理是否丢掉自定义 header、API 与调用方是否指向同一环境。
- 进程里该变量为空时，鉴权**拒绝一切**请求（空 token 不等于“免鉴权”）。确认 `source .env.growth` 发生在启动进程的 shell 中。

### 403 飞书回调

- 设置 `GROWTH_FEISHU_ENCRYPT_KEY` 后：签名头缺失/不匹配会返回 `invalid feishu signature`；即使签名通过，v1 也不会解密加密信封，动作解析会失败并返回错误 toast。**清空该变量**，只使用 verification token 路径。
- 未设置 encrypt key 时返回 `invalid feishu token`：payload 里的 token 与 `GROWTH_FEISHU_VERIFICATION_TOKEN` 不一致。检查飞书后台 Verification Token、是否复制了尾部空白、是否把 Encrypt Key 填进了 token。
- 事件 v2 从 `header.token` 取 token，URL 校验从顶层 `token` 取；两者都必须匹配。回调地址必须是公网 HTTPS，且指向 `POST /internal/v1/approvals/callback`。

### `RATE_LIMITED`

- 记录发送时频率超限，`POST .../sent` 返回 409，消息被置为 `suppressed`，审计写入 `social.send_blocked`（含 `scope`、`scope_key`、`retry_after_seconds`）。
- 规则来自 `rate_limit_rules`（seed 默认全局 50/天、Reddit 5/天、同 subreddit 带链 2/天），计数在 `rate_limit_counters`：

```sql
select scope, scope_key, window_start, count
from rate_limit_counters
where tenant_id = '00000000-0000-0000-0000-000000000001'
order by window_start desc;
```

- 等窗口过后再发，需要新的草稿。注意 v1 以 `draft:<lead_id>` 去重：该 lead 的旧消息仍是 `suppressed` 时，重新调用 `POST /internal/v1/social/draft` 会复用旧记录而不会新建。必要时人工确认后用新的 lead 走一遍评分/草稿，或按运维流程处理旧记录。

### `SUPPRESSED`

- 命中 `suppression_list` 时，消息置 `suppressed`，`POST .../sent` 返回 409 `SUPPRESSED`；跟进检查也会停止。（频率超限是 `RATE_LIMITED`，见上一节。）
- 查看原因：

```sql
select kind, value, reason, source, created_at
from suppression_list
where tenant_id = '00000000-0000-0000-0000-000000000001'
order by created_at desc;
```

- 只有人工复核后才可移除抑制；不要为了“发出去”批量删除抑制记录。

### `pipeline_runs` 出现 `dead`

- 任务失败按 `60 * 2^attempts` 秒退避重试，默认 `max_attempts=5`，达到上限置 `dead`。`last_error` 的格式是 `{异常类名}: {消息}`，例如 `ProviderNotConfigured: PROVIDER_NOT_CONFIGURED: llm model` 或 `ProviderRateLimited: PROVIDER_RATE_LIMITED: llm rate limited`。

```sql
select id, pipeline, task_type, attempts, max_attempts, status, last_error,
       locked_at, updated_at
from pipeline_runs
where status in ('dead', 'running')
order by updated_at desc
limit 50;
```

- 修复根因（模型名、密钥、网络、数据）后，可人工重置为可领取状态。业务写入按确定幂等键去重，重跑不会重复创建草稿/审批行：

```sql
update pipeline_runs
set status = 'queued', attempts = 0, last_error = null,
    locked_at = null, locked_by = null, run_after = now()
where id = '<task-id>' and status in ('dead', 'running');
```

- v1 worker 没有自动回收崩溃遗留的 `running` 任务（`reclaim_stale_tasks` 未接入循环）。worker 崩溃后先看 `locked_at`，按上面的 SQL 人工回收。

### outbox 死信（5 次后 `dead`）

```sql
select id, topic, attempts, status, last_error, next_attempt_at, created_at
from outbox_messages
where status in ('dead', 'failed')
order by updated_at desc;
```

- 常见原因：飞书 App ID/Secret 错误、机器人不在群里、`chat_id` 错误、网络超时。先看 `last_error` 修复配置。
- 重试（同一 `feishu:<approval_id>` 幂等键不会新增 outbox 行；但若飞书已收到而本地标记失败，重试可能重发同一张卡，这是已知的崩溃窗口）：

```sql
update outbox_messages
set status = 'pending', attempts = 0, last_error = null, next_attempt_at = now()
where id = '<outbox-id>' and status = 'dead';
```

- 卡片一直不出现且 outbox 是 `pending`/`failed`：确认 **worker 进程在运行**；只有 API 进程不会派发 outbox。

## 9. 验收清单

来自设计 spec §6.11「测试与 DoD」：

- [ ] 单元：评分卡、扣分、阈值、去重、频率、抑制、链接政策。
- [ ] 集成：Reddit/HN mock → 评分 → 草稿 → 飞书回调 → 发送记录。
- [ ] 提示词回归：50 条黄金帖；共情、具体、无夸大、单链接、披露。
- [ ] 安全：广告帖、竞品帖、敏感帖被拦截；无自动发送代码路径。
- [ ] E2E：n8n → worker → 飞书审批 → 人工发送 → 跟进提醒。

DoD：

- [ ] 每周 ≥20 条合格线索。
- [ ] 审批通过率 ≥50%。
- [ ] 0 条自动发送。
- [ ] 100% 草稿有版本、审批人、最终文本。
- [ ] 频率/抑制 100% 生效。
- [ ] 链接政策 100% 执行。
