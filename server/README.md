# Opportunity Scout · Local API

本地优先的机会研究工作台后端骨架。核心目标只有一个：**把数据源隔离在 Provider API 后面**，让 Agent-Reach、网页搜索、RSS、市场平台、手工导入可以随时替换或新增，而主流程和 UI 不需要改。

当前完成度：

- ✅ Provider API + Registry + 错误归一化
- ✅ `AgentReachProvider`（Reddit / Web），核心不直接调用 CLI
- ✅ 成熟开源适配器：`feedparser` RSS、Hacker News（Algolia 公开 API）、Google Trends（pytrends）、Amazon Creators API
- ✅ Run / Signal / SQLite 持久化 / 去重
- ✅ 证据 brief（Markdown）+ 手工信号补录
- ✅ AI Analyzer：OpenAI 兼容 / Anthropic / Ollama，按评分卡输出 `build / verify / drop`
- ✅ 引用校验：模型只能引用本次采集的 signal_id，URL 由服务端回填
- ✅ 定时任务：APScheduler + SQLite 持久化，重启自动恢复
- ✅ React + TypeScript Web 前端：7 个页面、真实 API 数据、无 mock 回退
- ✅ 机会库 / 获取闭环持久化：`saved_opportunities` SQLite 表 + `/api/v1/library`
- ✅ macOS 桌面打包：PyInstaller `.app` + `.dmg`，双击启动并自动打开浏览器
- ✅ Concierge CLI + 测试
- ⏳ Domain Pack 完全配置化、1688 官方 API 接入、系统级后台/通知

## Growth Agent（Phase 0/1）

社媒痛点截流模块（Reddit / HN → 评分 → 草稿 → 飞书审批 → 人工发送）。完整部署与运维步骤见 [docs/growth-runbook.md](docs/growth-runbook.md)，环境变量模板见 [.env.growth.example](.env.growth.example)。

运行时需要两个进程，均从 `server/` 目录启动，并先手动加载环境变量（代码不会自动读取 `.env` 文件）：

```bash
cd server
cp .env.growth.example .env.growth     # 首次；填入真实值
set -a; source .env.growth; set +a

# 任务 worker：采集、评分、草稿、跟进，以及 outbox（飞书审批卡由它发送）
python -m growth_social.worker

# 内部 API：n8n 调用与飞书回调入口，默认 8780
uvicorn growth_social.asgi:app --host 0.0.0.0 --port 8780
```

`GROWTH_DATABASE_URL`、`GROWTH_SERVICE_TOKEN`、`GROWTH_TENANT_ID`、`GROWTH_WORKSPACE_ID` 四项必填；只启动 API 不会发送审批卡，worker 必须同时运行。

## 开源组件

不自研底层基础设施，优先复用成熟项目：

| 组件 | 用途 | 说明 |
|---|---|---|
| FastAPI / Pydantic | API 与结构化输出 | 已有 |
| OpenAI Python SDK | OpenAI 兼容模型客户端 | 覆盖 OpenAI、DeepSeek、Qwen、Moonshot、OpenRouter、Ollama、vLLM 等 |
| httpx | Anthropic Messages API | 不额外引入 SDK |
| APScheduler | 定时任务 | 本地进程内调度，避免 Celery/Redis |
| Agent-Reach | 社区 / 网页信号 | 通过唯一适配器隔离 |
| feedparser | RSS / Atom | 纯 Python 解析器，适配用户自选订阅源 |
| pytrends | Google Trends | 非官方公开接口，可能限流 |
| python-amazon-paapi | Amazon Creators API | 官方商品搜索，需自己的凭证 |

AI 分析不绑定厂商：`OPPORTUNITY_AI_MODEL` + 可选 `OPPORTUNITY_AI_BASE_URL` 即可切换。

## 架构

```
React Web UI / CLI
   │  HTTP / JSON
   ▼
FastAPI  /api/v1  (+ serves web/dist)
   │
   ├── Provider Registry
   │     ├── agent-reach.reddit   ← 唯一知道 Agent-Reach CLI 的适配器
   │     ├── agent-reach.web
   │     ├── rss                  ← feedparser
   │     ├── hackernews           ← Algolia HN 公开 API
   │     ├── google.trends        ← pytrends
   │     └── amazon.creators      ← 官方 Creators API（BYO Key）
   │
   ├── Run Service（采集、归一化、去重、落库）
   ├── Library Service（机会库快照、阶段、备注）
   ├── Evidence Analyzer（启发式证据包）
   ├── AI Analyzer（OpenAI 兼容 / Anthropic / Ollama，按 Pack 评分卡）
   └── SQLite（runs / signals / analyses / schedules / saved_opportunities）
```

硬规则：`app/providers/agent_reach.py` 是唯一调用 `agent-reach` 命令的地方。API、服务层、CLI 和未来的 UI 都不解析它的 stdout，也不依赖它的错误码。平台错误会统一映射为：

`PROVIDER_NOT_CONFIGURED` / `PROVIDER_NEEDS_AUTH` / `PROVIDER_RATE_LIMITED` / `PROVIDER_BLOCKED` / `PROVIDER_TIMEOUT` / `PROVIDER_BUSY` / `PROVIDER_UNAVAILABLE` / `PROVIDER_BAD_OUTPUT` / `PROVIDER_ERROR`

## 快速启动

```bash
cd server
python3 -m pip install -r requirements.txt   # 当前环境已具备
uvicorn app.main:app --reload --port 8765
```

打开 <http://127.0.0.1:8765/docs> 查看交互式 API 文档。

生产模式需要先构建前端，构建产物由 FastAPI 同源托管：

```bash
cd ../web
npm ci
npm run build
cd ../server
uvicorn app.main:app --port 8765
# 浏览器打开 http://127.0.0.1:8765/
```

前端独立开发时，Vite 在 5173 端口运行，并把 `/api` 代理到 8765：

```bash
cd web
npm run dev          # http://127.0.0.1:5173
```

默认数据源：

- `agent-reach.reddit`（`--backend public-web`）
- `agent-reach.web`（Agent-Reach 默认 Exa 后端）
- `hackernews`（Algolia 公开 API，无需配置）
- `google.trends`（默认 `OPPORTUNITY_TRENDS_GEO=US`；优先用关键词字段的第一个词，未填时从方向里取前两个实词）
- `rss` / `amazon.creators`（注册但默认 `not_configured`，配置后启用）

通过环境变量调整：

```bash
export AGENT_REACH_CHANNELS="reddit,web,v2ex"
export AGENT_REACH_BIN="/Users/you/.local/bin/agent-reach"
export AGENT_REACH_TIMEOUT=90
export OPPORTUNITY_SCOUT_DB="/path/to/opportunity_scout.db"

# RSS / Atom 订阅源，逗号分隔；未设置时该来源显示“未配置”
export OPPORTUNITY_RSS_FEEDS="https://feeds.arstechnica.com/arstechnica/index,https://techcrunch.com/feed/"
export OPPORTUNITY_TRENDS_GEO="US"
export OPPORTUNITY_HTTP_TIMEOUT=25

# Amazon Creators API（在亚马逊联盟后台申请凭证）
export OPPORTUNITY_AMAZON_CREDENTIAL_ID="..."
export OPPORTUNITY_AMAZON_CREDENTIAL_SECRET="..."
export OPPORTUNITY_AMAZON_TAG="yourtag-20"
export OPPORTUNITY_AMAZON_VERSION="3.1"
export OPPORTUNITY_AMAZON_COUNTRY="US"
```

Amazon 与 RSS 的密钥/地址都只从环境变量读取，不写入 SQLite，也不通过 API 返回。1688 没有成熟的开源客户端，本项目不抓取它的页面；需要接入时走官方 Open Platform 授权。

### 配置 AI 引擎（BYO Key）

AI 分析默认关闭。密钥只从环境变量读取，不写入数据库。任选一种：

```bash
# OpenAI
export OPPORTUNITY_AI_MODEL="gpt-4.1-mini"
export OPENAI_API_KEY="sk-..."

# DeepSeek / Qwen / Moonshot / OpenRouter 等 OpenAI 兼容服务
export OPPORTUNITY_AI_MODEL="deepseek-chat"
export OPPORTUNITY_AI_BASE_URL="https://api.deepseek.com/v1"
export OPPORTUNITY_AI_API_KEY="..."

# Ollama（本地）
export OPPORTUNITY_AI_MODEL="ollama:qwen2.5:14b"
# 默认连接 http://127.0.0.1:11434/v1，无需 Key

# Anthropic
export OPPORTUNITY_AI_MODEL="anthropic:claude-sonnet-4-5"
export ANTHROPIC_API_KEY="sk-ant-..."
```

其他可调项：

```bash
export OPPORTUNITY_AI_TIMEOUT=120
export OPPORTUNITY_AI_MAX_SIGNALS=40
export OPPORTUNITY_AI_MAX_CHARS_PER_SIGNAL=1200
export OPPORTUNITY_AI_MAX_TOTAL_CHARS=30000
```

`GET /api/v1/ai/status` 可查看当前是否配置、使用哪个模型，不会返回密钥。

### Web 前端

前端代码在 `../web`，页面包括：新建采集、机会分析、获取闭环、定时任务、采集历史、机会库、设置。所有数据来自本地 API：

- 只有状态为 `ready` / `degraded` 的来源可勾选；`not_configured` 会显示缺失的配置项，未注册的来源显示“未接入 Provider API”。
- 未配置 AI 时，采集完成只渲染公开信号证据，不生成机会结论。
- 历史记录、定时任务、机会库都直接读写本机 SQLite。
- 设置页只展示后端环境变量配置，不收集 API Key。
- 调度器只在 API 进程存活时运行，退出后不补跑。
- API 未启动时显示真实的离线状态与重试入口，**没有 mock 或演示模式**；写操作在离线时禁用。

前端命令：

```bash
cd web
npm run check     # typecheck + lint + vitest
npm run build
npm run gen:api   # 后端 schema 变更后重新生成 src/api/schema.d.ts
```

### 桌面版（macOS）

打包后会生成 `dist/Opportunity Scout.app` 和 `dist/Opportunity Scout.dmg`：

```bash
cd server
python3 -m pip install -r requirements.txt -r requirements-build.txt
./packaging/build_macos.sh
open "dist/Opportunity Scout.app"
```

双击 `.app` 后会：

1. 启动本地 FastAPI（默认 `127.0.0.1:8765`，端口被占用时自动顺延）；
2. 由后端直接托管构建后的 React Web 应用，打开默认浏览器；
3. 数据库、日志和配置文件写入 `~/Library/Application Support/OpportunityScout/`；
4. 设置页显示真实数据库路径，并提供“退出本地服务”按钮。

首次运行会生成 `env.example`。复制为 `.env` 后填写 AI / RSS / Amazon / Agent-Reach 配置，重启应用生效：

```bash
cd ~/Library/Application\ Support/OpportunityScout
cp env.example .env
open -e .env
```

说明：

- 当前在本机 arm64 上构建，产物是 arm64 单架构；Intel 机器需在对应 Python 环境重新执行打包。
- 未使用 Apple Developer ID 签名（ad-hoc）。从网络下载后首次打开需右键 → 打开；本机自行构建的 `.app` 可直接运行。
- Agent-Reach 仍是可选外部工具，不会打进应用；打包版会把 `~/.local/bin`、`/opt/homebrew/bin`、`/usr/local/bin` 加入 PATH，已安装即可被识别。
- UI 与 API 同源，无需再单独启动 `python3 -m http.server`。

## 核心 API

### 列出领域包

```bash
curl http://127.0.0.1:8765/api/v1/domain-packs
```

当前包含 `crossborder`、`saas`、`general`。每个 Pack 声明查询提示、评分维度与输出 schema；AI Analyzer 接入后直接消费这份 manifest。

### 列出数据源

```bash
curl http://127.0.0.1:8765/api/v1/providers
```

### 发起一次采集

```bash
curl -X POST http://127.0.0.1:8765/api/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "domain_pack": "crossborder",
    "direction": "Amazon 宠物饮水机细分，低评论高客单的机会",
    "keywords": ["pet water fountain", "stainless steel"],
    "provider_ids": ["agent-reach.reddit", "agent-reach.web"],
    "limit_per_provider": 10,
    "time_range_days": 90
  }'
```

返回的 Run 包含归一化后的 `signals`。每个 signal 都有 `source_url`、`quote`、`author_public`、`published_at`，可直接点回原文。

### 获取证据 brief

```bash
curl http://127.0.0.1:8765/api/v1/runs/<run_id>/brief
```

输出 Markdown：来源分布、数据源错误、关键词信号、高优先级原文引用。**这是启发式证据包，不是 AI 机会判断**；不会伪造结论。

### 调用 AI 分析

```bash
curl -X POST http://127.0.0.1:8765/api/v1/runs/<run_id>/analyze \
  -H 'Content-Type: application/json' \
  -d '{}'
```

返回 `OpportunityAnalysis`：

- `verdict`：`build / verify / drop`
- `score`：0-100，由 Domain Pack 权重确定，不由模型自由发挥
- `dimension_scores`：逐维度分数、理由、引用
- `next_actions / risks / missing_information`
- `citations`：服务端按 `signal_id` 回填真实 URL

规则：

- 模型只能引用本次 Run 中的 `signal_id`，编造的引用会被丢弃。
- 没有任何可核对引用时，结论不会出现 `build`。
- 证据置信度低于 5/10 时，`build` 会降级为 `verify`。
- `GET /api/v1/runs/<run_id>/analysis` 读取已保存结果。
- `GET /api/v1/runs/<run_id>/analysis.md` 导出 Markdown。

### 定时任务

创建每天 09:00 的跨境采集（5 段 cron）：

```bash
curl -X POST http://127.0.0.1:8765/api/v1/schedules \
  -H 'Content-Type: application/json' \
  -d '{
    "domain_pack": "crossborder",
    "direction": "Amazon 宠物饮水机细分",
    "keywords": ["pet fountain"],
    "provider_ids": ["agent-reach.reddit"],
    "limit_per_provider": 10,
    "cron": "0 9 * * *"
  }'
```

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/schedules` | 列表，含 `next_run_at` |
| POST | `/api/v1/schedules` | 新建 |
| PATCH | `/api/v1/schedules/{id}` | 改 cron / 启停 / 参数 |
| DELETE | `/api/v1/schedules/{id}` | 删除 |
| POST | `/api/v1/schedules/{id}/run` | 立即执行一次 |

说明：

- 调度在 FastAPI 进程内运行，适合本地单机；不需要 Redis / Celery。
- 任务定义存 SQLite，进程重启后自动重新注册。
- 错过的执行不会补跑；同一任务不会并发执行。
- 配置了 `OPPORTUNITY_AI_MODEL` 时，定时采集完成后会自动调用 AI 分析。
- 设置 `OPPORTUNITY_SCHEDULER_ENABLED=0` 可只保留接口、不启动调度线程。

### 机会库 / 获取闭环

只有已经生成 AI 分析的 Run 才能保存（否则返回 409）。保存的是分析快照，之后重新分析不会改写已归档内容；再次保存同一 Run 会刷新快照，但保留创建时间。

```bash
curl -X POST http://127.0.0.1:8765/api/v1/library \
  -H 'Content-Type: application/json' \
  -d '{"run_id": "<run_id>", "stage": "saved", "notes": ""}'
```

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/library` | 列表 |
| POST | `/api/v1/library` | 保存 / 刷新快照 |
| GET | `/api/v1/library/{run_id}` | 单条 |
| PATCH | `/api/v1/library/{run_id}` | 更新 `stage` / `notes` |
| DELETE | `/api/v1/library/{run_id}` | 删除 |

`stage` 取值：`saved`、`validating`、`contacted`、`replied`、`won`、`dropped`。闭环看板与机会库共用这份数据；触达模板由前端按快照拼装，**不是 AI 生成，也不会自动发送**。

### 手工补录信号

跨境场景里，Amazon / 1688 / 供应商报价等数据可以先人工整理，再补进同一个 Run：

```bash
curl -X POST http://127.0.0.1:8765/api/v1/runs/<run_id>/signals \
  -H 'Content-Type: application/json' \
  -d '{
    "provider_id": "manual",
    "source_url": "https://example.com/supplier",
    "title": "Supplier quote",
    "quote": "MOQ 500, sample in 7 days, unit price $4.20."
  }'
```

## Concierge CLI（不启动服务也能跑）

```bash
cd server
python -m app.cli providers
python -m app.cli run \
  --direction "Amazon 宠物饮水机细分，低评论高客单的机会" \
  --keywords "pet water fountain, stainless steel" \
  --providers agent-reach.reddit,agent-reach.web \
  --pack crossborder \
  --limit 10
```

会在 `server/briefs/` 下生成 `<run_id>.json` 和 `<run_id>.md`。这就是第一轮 concierge 测试的交付物：拿真实公开信号做一份可核对的机会证据包，再人工判断是否值得做。

采集后直接分析：

```bash
python -m app.cli run \
  --direction "..." \
  --pack crossborder \
  --analyze
```

或对已有 Run 单独分析：

```bash
python -m app.cli analyze --run <run_id>
```

会额外生成 `<run_id>.analysis.json` 和 `<run_id>.analysis.md`。

## 测试

```bash
cd server
python -m pytest -q
```

测试覆盖：

- Agent-Reach 适配器：正常归一化、平台错误映射、可执行文件缺失、健康检查。
- 开源适配器：RSS 解析/按查询词过滤/限流映射、HN 归一化与回退链接、Trends 关键词压缩与趋势表过滤、Amazon 凭证缺失与字段归一化。
- API：数据源列表、Run 创建、brief 生成、手工信号补录、未知数据源拒绝、`has_analysis` 状态、SPA 运行时配置注入与 `/api/v1/app/info`。
- 机会库：保存快照、重复保存保留创建时间、阶段更新、404 / 409。
- 前端托管：`/` 与深链返回注入后的 index、`/assets/*` 长缓存、未知 `/api/*` 返回 JSON 404。
- AI Analyzer：加权评分、引用回填、伪造引用丢弃、无引用降级、API 与 Markdown 导出。
- 定时任务：CRUD、非法 cron 拒绝、立即执行生成 Run、禁用任务不执行。
- 所有测试使用临时 SQLite，不触碰真实数据。

## 下一步

1. **1688 / Alibaba**：官方 Open Platform 需要企业资质与签名，没有成熟 OSS 客户端；先不抓页面，等有授权后写独立适配器。
2. **Domain Pack manifest**：把查询模板、评分权重、输出 schema 从代码移到可编辑配置。
3. **系统级调度**：菜单栏常驻、开机自启、桌面通知；当前调度只在 API 进程内运行。
4. **本地检索**：数据量上来后接 `sqlite-vec` + 本地 embedding，做去重和跨 Run 语义检索。
5. **真实 AI 验证**：配置真实 Key 跑一轮，校准评分卡与提示词。
