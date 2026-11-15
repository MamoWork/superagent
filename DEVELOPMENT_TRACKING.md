# Opportunity Scout 开发跟踪矩阵

> 审计日期：2026-11-14  
> 代码基线：`/Volumes/work/workspace/superAgent/ideas_pool`（当前目录不是 git 仓库）  
> 审计范围：需求文档、原型、后端、前端、测试、构建/打包产物、本地 SQLite 数据  
> 复现命令与结果见第 8 节。

---

## 0. 结论摘要

### 0.1 一句话结论

**核心工作台已经可用，但还不是完整的 v1。**“采集 → 证据 → AI 判断 → 收藏 → 阶段跟踪 → 复制触达模板”这条主链路已经跑通；缺口集中在**多机会卡、真实 AI/Amazon 验证、获取闭环的发送与跟进、跨境 Pack 的决策工具、E2E 自动化**。

### 0.2 完成度总览

| 维度 | 完成度 | 判断依据 |
|---|---:|---|
| 功能开发（核心工作台 Phase 0+1） | **73%** | Provider、Run、AI 分析、机会库、阶段看板、定时任务、桌面打包均已实现 |
| 功能开发（完整 v1，含跨境 Pack） | **55%** | 跨境 Pack 只完成数据源骨架，利润/供应/合规工具未实现 |
| 自动化测试 | **65%** | 后端 43 个测试较完整；前端仅 22 个测试，页面/Hook 基本未覆盖；无 E2E |
| 真实环境验证 | **35%** | 测试用假模型；真实 AI Key、真实 Amazon Key 均未验证 |
| 用户与商业验证 | **5%** | Concierge 目标 10 人，实际 0 人；访谈目标 20 人，实际 0 人 |
| 文档与原型 | **90%** | 需求、原型、README、Concierge 清单齐全；本文补齐跟踪矩阵 |

### 0.3 五个最重要的发现

1. **“单 Run 单机会”与原型/验收标准不一致。** 原型 `OPPS` 在一个结果页展示 4 张机会卡；生产实现每个 Run 只产出 1 个 `OpportunityAnalysis`（1 张机会卡）。而 Phase 0 验收要求“5 分钟内得到 ≥3 条带原文链接的机会卡”。这是需要产品决策的需求歧义。
2. **AI 判断链路只有假模型测试。** 引用校验、加权评分、无引用降级都有单测，但没有用真实 Key 跑过；当前目录也没有 `.env`，AI 默认未配置。
3. **获取闭环只完成了“草稿”，没有“动作记录”。** 有 3 种触达模板和阶段看板，但没有发送时间/渠道记录、跟进提醒、抑制名单、频率上限、结果回流；`saved_opportunities` 是“机会快照”，不是“线索/联系人”。
4. **跨境 Pack 的核心交付物基本未实现。** Amazon Creators 适配器有代码但无真实 Key 验证；TikTok Creative Center、1688/Alibaba、Keepa、利润计算器、供应商短名单、中英询盘、合规清单均未实现。
5. **E2E 基建是坏的。** `package.json` 有 `npm run e2e`，但 `web/e2e/` 为空、无 Playwright 配置；`npx playwright test --list` 会误抓 Vitest 文件并报 `TypeError`。README 中“无头浏览器跑通 7 个页面”是手工验证，不可自动复现。

---

## 1. 需求基线与范围说明

### 1.1 需求文档

| 文档 | 作用 | 状态 |
|---|---|---|
| [business_plan.md](business_plan.md) | 当前产品需求基线（v2）：定位、痛点、Provider 架构、Domain Pack、闭环、Phase 0–3、验收指标 | 现行 |
| [selected_project.md](selected_project.md) | 最早的 24 小时 MVP 选题：短视频自动字幕 CaptionSnap | **已废弃**，文首已注明被 Opportunity Scout 取代；不计入本项目完成度 |
| [server/CONCIERGE_TEST.md](server/CONCIERGE_TEST.md) | 跨境 Pack 的 Concierge 用户测试流程与通过标准 | 未执行 |
| [server/README.md](server/README.md) | 实现声明、启动方式、API、测试说明 | 与代码基本一致，但“真实环境验证”部分需打问号 |
| [web/README.md](web/README.md) | 前端结构、构建、约束 | 与代码一致 |
| 本文 | 需求 → 原型 → 功能 → 测试的跟踪矩阵 | 新增 |

### 1.2 v1 范围（来自 business_plan）

- Phase 0：Local API + SQLite + Provider Registry + 采集/去重 + AI 分析 + 机会卡 + JSON/Markdown 导出。
- Phase 1：定时任务、历史、机会库、线索/状态/CSV、触达草稿、人工发送记录、跟进提醒、合规设置。
- Phase 2：跨境 Pack（Amazon、Google Trends、TikTok Creative Center、1688/Alibaba）+ 利润计算器 + 供应商短名单 + 询盘草稿 + 合规清单。
- Phase 3：更多 Provider、团队/工作室、白标、云同步、评分卡校准（不计入 v1 验收）。

### 1.3 明确不做（已遵守）

- 不自动发帖/评论/私信 ✅
- 不做全量爬虫、不绕过登录 ✅
- 不做完整 CRM/客服/ERP ✅
- 不做移动 App ✅
- 不做企业 SSO/复杂权限 ✅

---

## 2. 状态图例与完成度口径

| 标记 | 含义 |
|---|---|
| ✅ | 已完成：代码可运行，有自动化测试或明确运行证据 |
| 🟡 | 部分完成：主链路可用，但关键子能力缺失 |
| 🟠 | 骨架/未验证：有代码或占位，但未证明可用 |
| ❌ | 未实现 |
| 🧪 | 仅有单元测试或仅手工验证，未做真实环境/端到端验证 |

完成度按“需求验收点”估算，不按代码行数。阶段权重：Phase 0 = 30%，Phase 1 = 35%，Phase 2 = 35%。

---

## 3. 需求 → 原型 → 功能 → 测试 跟踪矩阵

### 3.1 数据采集与 Provider

| ID | 需求（来源） | 原型 | 实现 | 测试 | 状态 | 完成度 / 缺口 |
|---|---|---|---|---|---|---|
| A1 | Provider API + Registry + 统一错误码（BP §5.2） | P1/P7 | [registry.py](server/app/providers/registry.py)、[base.py](server/app/providers/base.py)、[providers.py](server/app/api/providers.py) | `test_api.py::test_list_providers`；`test_agent_reach_adapter.py` | ✅ | 100%。9 类错误码已归一化 |
| A2 | Agent-Reach 仅存在于适配器，核心不解析 CLI（BP 硬规则） | P1/P7 | [agent_reach.py](server/app/providers/agent_reach.py) | 4 个适配器测试 | ✅ | 100% |
| A3 | RSS / HN / Google Trends / Amazon Creators 适配器（README） | P1 | [rss.py](server/app/providers/rss.py)、[hackernews.py](server/app/providers/hackernews.py)、[google_trends.py](server/app/providers/google_trends.py)、[amazon_creators.py](server/app/providers/amazon_creators.py) | `test_oss_providers.py`（11 个） | 🟡🧪 | 90%。Amazon 仅验证“缺凭证”和字段归一化，**无真实 Key 跑通** |
| A4 | Run / Signal / SQLite / 去重（BP Phase 0） | P1/P2/P5 | [runs.py](server/app/services/runs.py)、[db.py](server/app/db.py) | `test_api.py::test_run_and_brief` | ✅ | 100%。同步执行，稳定可用 |
| A5 | SSE 进度 `/runs/{id}/events` + Job Queue（BP §5.2、§5.1） | P0 | 未实现；前端用同步 POST + 客户端步骤动画 | 无 | ❌ | 0%。长任务会一直占住请求；进度不是真实后端事件 |
| A6 | 手工信号补录（BP C4、README） | P0 | API：`POST /api/v1/runs/{run_id}/signals`；**无前端入口** | `test_api.py::test_manual_signal_can_be_added` | 🟡 | 60%。后端可用，UI 缺失，跨境手工导入兜底不完整 |
| A7 | 1688 / Alibaba 官方 Open Platform（BP Phase 2） | P1 目录占位 | 无适配器；仅 [sourceCatalog.ts](web/src/data/sourceCatalog.ts) 中显示“需官方 Open Platform” | 无 | ❌ | 0% |
| A8 | Keepa（BP Phase 2 / 风险表） | P1 目录占位 | 无适配器；仅目录占位 | 无 | ❌ | 0% |
| A9 | TikTok Creative Center（BP Phase 2） | P0 | 无适配器；仅 Domain Pack 的 query hint 提到 “tiktok shop viral” | 无 | ❌ | 0% |
| A10 | 多源降级 + 手工导入兜底（BP P5） | P1/P7 | Provider 错误会进入 `stats.provider_errors` 并展示；手工 API 存在但无 UI | `test_api.py` 部分覆盖 | 🟡 | 60%。有错误展示，无自动降级编排 |

### 3.2 AI 分析与判断

| ID | 需求（来源） | 原型 | 实现 | 测试 | 状态 | 完成度 / 缺口 |
|---|---|---|---|---|---|---|
| B1 | Domain Pack：crossborder / saas / general（BP §5.3） | P1 | [domain_packs.py](server/app/domain_packs.py) | `test_api.py::test_domain_packs_are_exposed` | 🟡 | 80%。三个 Pack 已可用，但**硬编码在 Python 中，未配置化** |
| B2 | 启发式证据 brief（Markdown，不伪造结论） | P2 | [analysis.py](server/app/services/analysis.py)、`GET /runs/{id}/brief` | `test_api.py::test_run_and_brief` | ✅ | 100%。含来源分布、错误、关键词、原文引用 |
| B3 | AI Analyzer：OpenAI 兼容 / Anthropic / Ollama（BYO Key） | P2 | [analyzer.py](server/app/services/analyzer.py) | `test_analyzer.py`（5 个） | ✅🧪 | 90%。多厂商抽象完成；**测试用假模型服务，真实 Key 未验证** |
| B4 | 服务端按评分卡加权算分与 build/verify/drop（BP P2） | P2 | `_finalize()` in [analyzer.py](server/app/services/analyzer.py) | `test_analysis_scores_and_resolves_citations` | ✅ | 100%。分数不由模型自由发挥 |
| B5 | 引用强制：只能引用本次 Run 的 signal_id，URL 服务端回填，伪造引用丢弃 | P2 | `_resolve_citations()` | `test_no_citation_never_builds` 等 | ✅ | 100%。无引用时不会出现 build；置信度 <5 降级为 verify |
| B6 | 机会输出字段：one_liner/thesis/目标客户/付费意愿/风险/下一步/缺失信息 | P2 | [schemas.py](server/app/schemas.py) `OpportunityAnalysis` | `test_analyzer.py` | ✅ | 100%。**但每个 Run 只产出 1 个机会，不是多张机会卡** |
| B7 | 真实 AI Key 端到端验证与评分卡校准（BP §11、README） | P2 | 代码具备 | 无真实环境测试 | ❌🧪 | 0%。当前无 `.env`，AI 默认未配置 |
| B8 | Markdown 分析/证据导出到 UI（BP Phase 0 “导出 JSON/Markdown”） | P2 | API 有 `/analysis.md`、`/brief`；UI 只提供“导出 JSON” | `test_analyzer.py::test_analysis_api` | 🟡 | 70%。Markdown 只能走 API，前端无下载按钮 |

### 3.3 获取闭环

| ID | 需求（来源） | 原型 | 实现 | 测试 | 状态 | 完成度 / 缺口 |
|---|---|---|---|---|---|---|
| C1 | 定时任务：cron CRUD、启停、立即执行、重启恢复、不补跑（BP Phase 1） | P4 | [scheduler.py](server/app/services/scheduler.py)、[schedules.py](server/app/api/schedules.py)、[SchedulesPage.tsx](web/src/features/schedules/SchedulesPage.tsx) | `test_scheduler.py`（4 个） | ✅ | 100% |
| C2 | 采集历史（BP Phase 1） | P5 | [HistoryPage.tsx](web/src/features/history/HistoryPage.tsx)、`GET /runs` | 无页面级测试 | ✅🧪 | 95%。功能可用，无专门测试 |
| C3 | 机会库：保存分析快照，未分析返回 409，重复保存保留创建时间（BP Phase 1） | P6 | [library.py](server/app/services/library.py)、[LibraryPage.tsx](web/src/features/library/LibraryPage.tsx) | `test_library.py`（5 个） | ✅ | 100% |
| C4 | 闭环阶段看板：saved → validating → contacted → replied → won/dropped（BP §5.4） | P3 | [PipelinePage.tsx](web/src/features/pipeline/PipelinePage.tsx)、`PATCH /library/{run_id}` | `test_library.py` | ✅ | 100%。阶段只能手工改 |
| C5 | 线索池：原帖作者/评论者 → 线索卡，展示公开上下文与原话（BP §5.4） | P3（原型有 3 条 LEADS） | **无独立线索实体**；`SavedOpportunity` 是机会快照，citation 里只带作者公开信息 | `test_library.py` | 🟡 | 50%。机会→闭环是“机会快照→阶段”，不是“人→线索”；无联系人、无去重、无分配 |
| C6 | 触达草稿：基于对方原话，3 种语气，人工修改/发送，明确标注非 AI 生成（BP P7） | P3 | [outreach.ts](web/src/lib/outreach.ts)、[OutreachDialog.tsx](web/src/features/pipeline/OutreachDialog.tsx) | `outreach.test.ts`（4 个用例，`it.each` 3 种语气） | ✅ | 100%。只复制，不发送 |
| C7 | 人工发送记录：发送时间、渠道、联系人（BP Phase 1） | P0 | 无字段、无 UI、无 API | 无 | ❌ | 0% |
| C8 | 跟进提醒（BP Phase 1） | P0 | 无 | 无 | ❌ | 0% |
| C9 | 抑制名单 + 频率上限（BP §5.5、Phase 1） | P7 | 仅设置页静态文案“始终禁用/始终启用”，无数据与校验 | 无 | 🟡 | 10%。合规姿态有，机制没有 |
| C10 | 拒绝/退订语义（BP §5.4） | P3 | 只有 `dropped` 阶段，无抑制/退订语义 | 无 | 🟡 | 40% |
| C11 | 结果回流到评分卡校准（BP §5.4、§8） | P0 | 无 | 无 | ❌ | 0% |
| C12 | 导出：Run JSON / 闭环 CSV / 机会库导出（BP Phase 0、Phase 1） | P3/P5/P6 | [download.ts](web/src/lib/download.ts)、[csv.ts](web/src/lib/csv.ts)、各页面导出按钮 | 仅工具函数测试，无导出内容测试 | ✅🧪 | 90% |

### 3.4 前端与交付

| ID | 需求（来源） | 原型 | 实现 | 测试 | 状态 | 完成度 / 缺口 |
|---|---|---|---|---|---|---|
| D1 | React + TypeScript + Vite，7 个页面，真实 API，无 mock（README） | P1–P7 | [router.tsx](web/src/app/router.tsx)、[features/](web/src/features/) | `npm run check` 通过；22 个 Vitest | ✅ | 100% |
| D2 | API 离线时显示真实离线状态、写操作禁用（README） | P7/P0 | [useBackend.ts](web/src/hooks/useBackend.ts)、[StateViews.tsx](web/src/components/StateViews.tsx) | `sourceCatalog.test.ts` 覆盖离线目录；无页面级测试 | ✅🧪 | 90% |
| D3 | 原型迁移与设计令牌复用（web/README） | 全部 | [legacy/opportunity_scout_prototype.html](legacy/opportunity_scout_prototype.html) → React；CSS 类名/令牌沿用 | 无视觉回归测试 | ✅ | 100%。原型已归档，不参与构建 |
| D4 | macOS 桌面打包 `.app` + `.dmg`（README） | P0 | [packaging/](server/packaging/)、[desktop.py](server/app/desktop.py) | 无自动化；BP 记录手工验证 | ✅🧪 | 95%。产物存在：`server/dist/Opportunity Scout.dmg`（107 MB） |
| D5 | Concierge CLI（README） | P0 | [cli.py](server/app/cli.py) | 无 CLI 测试 | ✅🧪 | 90%。有 2 份真实 brief 样例 |
| D6 | E2E 自动化（README 声称“无头浏览器跑通 7 个页面”） | P0 | `web/e2e/` 为空，无 `playwright.config.ts` | `npm run e2e` 不可用 | ❌ | 0%。脚本存在但基建是坏的 |
| D7 | 前端页面/组件测试 | P0 | 仅 4 个测试文件 | 22 个测试 | 🟡 | 30%。页面、Hook、API client、弹窗、路由均无测试 |
| D8 | 构建产物与源码同步 | P0 | `web/dist` 14:50；`.dmg` 14:52；最后源码改动 14:48 | 已核对时间戳 | ✅ | 100%。产物不落后于源码 |
| D9 | 文档完整性 | P0 | README、business_plan、CONCIERGE_TEST | 人工核对 | ✅ | 90%。缺跟踪矩阵（本文补齐） |

### 3.5 跨境 Pack（Phase 2）

| ID | 需求（来源） | 原型 | 实现 | 测试 | 状态 | 完成度 / 缺口 |
|---|---|---|---|---|---|---|
| E1 | Amazon Creators API 真实数据（BP Phase 2） | P1 | [amazon_creators.py](server/app/providers/amazon_creators.py) | `test_oss_providers.py` 中 2 个 | 🟡🧪 | 60%。代码完成，真实 Key 未验证 |
| E2 | Google Trends（BP Phase 2） | P1 | [google_trends.py](server/app/providers/google_trends.py) | 2 个 helper/依赖测试；BP 记录真实网络手工验证 | ✅🧪 | 100% 功能，90% 验证 |
| E3 | 利润计算器：采购 + 头程 + 关税 + 平台费 + 退货 + 尾程（BP Phase 2） | P0 | 无 | 无 | ❌ | 0%。只有评分卡里的 `margin` 维度 |
| E4 | 供应商短名单（工厂/贸易商识别、MOQ、样品、认证）（BP Phase 2） | P0 | 无 | 无 | ❌ | 0% |
| E5 | 中英双语询盘草稿（MOQ/样品/认证问题清单）（BP Phase 2） | P0 | 无；只有通用英文触达模板 | 无 | ❌ | 0% |
| E6 | 合规/认证检查清单（CE/FCC/FDA、电池/液体、商标/专利）（BP Phase 2） | P0 | 无；只有 `compliance` 评分维度 | 无 | ❌ | 0% |
| E7 | 跨境机会卡：需求/竞争/利润/供应/合规 + 结论 + 下一步（BP §C4） | P2 | AI 分析覆盖 6 个维度，但利润/供应/合规只有文本判断，无结构化数据 | `test_analyzer.py` | 🟡 | 40%。有“判断”，缺“可计算、可核对”的跨境数据 |
| E8 | 跨境验收：产品词 → 可决策机会卡；10 个卖家试用，≥4 人付 $49（BP Phase 2） | P0 | 未执行 | 无 | ❌ | 0% |

### 3.6 验证与商业化

| ID | 需求（来源） | 原型 | 实现 | 测试 | 状态 | 完成度 / 缺口 |
|---|---|---|---|---|---|---|
| F1 | Concierge 测试：10 个卖家，≥6 有手工拼信息经历、≥4 产生动作、≥3 愿付费（CONCIERGE_TEST） | P0 | 有 CLI 与 2 份 brief 样例；**未执行用户测试** | 无 | ❌ | 5%。资产只有 CLI + 样例 |
| F2 | 产品指标：首次价值时间、激活率、机会验证率、周触达、4 周留存、免费→付费（BP §11.3） | P0 | 无埋点、无统计 | 无 | ❌ | 0% |
| F3 | 定价/支付/授权（BP §6.3） | P0 | 无 | 无 | ❌ | 0%。属于 Phase 3/商业化，不在当前代码范围 |
| F4 | 多工作区/席位/白标（BP Studio 版） | P0 | 只有 `workspace_id` 字段，无切换/权限/席位 | 无 | 🟡 | 10% |
| F5 | 20 人访谈验证（BP §11.1） | P0 | 未执行 | 无 | ❌ | 0% |
| F6 | 止损线监控（BP §11.4） | P0 | 未执行 | 无 | ❌ | 0% |

---

## 4. 原型跟踪

### 4.1 原型清单

| 原型 | 位置 | 规模 | 覆盖 | 状态 | 与实现关系 |
|---|---|---|---|---|---|
| 单文件 HTML 原型 | [legacy/opportunity_scout_prototype.html](legacy/opportunity_scout_prototype.html) | 2,596 行 | 7 个视图 + 真实 API 接入 + mock 回退 | 已归档 | 当前 React 应用由它迁移；CSS 类名/设计令牌沿用；不参与构建/打包 |
| React Web 应用 | [web/src/](web/src/) | 30 个 tsx + 24 个 ts | 7 个路由 + 404 + 错误页 | 生产实现 | 迁移完成，无 mock |
| macOS 桌面壳 | [server/packaging/](server/packaging/) | PyInstaller spec + 图标 + 构建脚本 | `.app` / `.dmg` | 已产出 | 后端同源托管 `web/dist` |
| 设计稿/Figma | — | — | — | 未发现 | 原型的视觉即设计基线 |

### 4.2 原型页面 → 当前路由

| 原型视图 | 原型 ID | 当前路由 | 组件 | 状态 |
|---|---|---|---|---|
| 新建采集 | `view-new` | `/` | [NewRunPage.tsx](web/src/features/new/NewRunPage.tsx) | ✅ |
| 机会分析 | `view-results` | `/results/:runId` | [ResultsPage.tsx](web/src/features/results/ResultsPage.tsx) | ✅ |
| 结果索引 | 原型无 | `/results` | [ResultsIndexPage.tsx](web/src/features/results/ResultsIndexPage.tsx) | ✅ 新增 |
| 获取闭环 | `view-pipeline` | `/pipeline` | [PipelinePage.tsx](web/src/features/pipeline/PipelinePage.tsx) | ✅ |
| 定时任务 | `view-schedules` | `/schedules` | [SchedulesPage.tsx](web/src/features/schedules/SchedulesPage.tsx) | ✅ |
| 采集历史 | `view-history` | `/history` | [HistoryPage.tsx](web/src/features/history/HistoryPage.tsx) | ✅ |
| 机会库 | `view-library` | `/library` | [LibraryPage.tsx](web/src/features/library/LibraryPage.tsx) | ✅ |
| 设置 | `view-settings` | `/settings` | [SettingsPage.tsx](web/src/features/settings/SettingsPage.tsx) | ✅ |
| 404 | 原型无 | `*` | [NotFound.tsx](web/src/app/NotFound.tsx) | ✅ 新增 |

### 4.3 原型与实现的差异

| 差异 | 原型 | 生产实现 | 影响 |
|---|---|---|---|
| 机会卡数量 | 一个结果页 4 张 `OPPS` 卡 | 每个 Run 1 个 `OpportunityAnalysis` / 1 张卡 | **高**：与 Phase 0 验收“≥3 条机会卡”冲突 |
| 线索池 | 3 条 `LEADS`，含姓名与草稿 | 无独立线索实体，只有机会快照 + 阶段 | **高**：闭环的“人”这一层缺失 |
| 数据模式 | API 未连接时回退 mock | 无 mock，离线只读 | 中：更真实，但原型演示能力丢失 |
| 进度展示 | 模拟步骤动画 | 仍是客户端步骤动画（同步 POST） | 中：进度不反映后端真实阶段 |
| 多工作区 | 无 | 无 | 低：原型也没有 |
| 触达记录 | 无 | 无 | 高：闭环未完成 |

---

## 5. 测试跟踪矩阵

### 5.1 自动化测试清单

**后端：`python3 -m pytest -q` → 43 passed（3.01s）**

| 测试文件 | 数量 | 覆盖范围 | 缺口 |
|---|---:|---|---|
| [test_agent_reach_adapter.py](server/tests/test_agent_reach_adapter.py) | 4 | 归一化、平台错误映射、可执行文件缺失、健康检查 | 无真实 CLI 调用 |
| [test_analyzer.py](server/tests/test_analyzer.py) | 5 | 加权评分、引用回填、伪造引用丢弃、无引用降级、API/Markdown | 假模型；无真实厂商 API |
| [test_api.py](server/tests/test_api.py) | 6 | Provider 列表、Run/brief、手工信号、未知源/未知 Pack 拒绝、Pack 暴露 | 无 `GET /runs` 列表、`GET /runs/{id}` 的独立断言 |
| [test_library.py](server/tests/test_library.py) | 5 | 保存需分析、404/409、更新/删除、重复保存、非法阶段 | 无并发/快照一致性测试 |
| [test_oss_providers.py](server/tests/test_oss_providers.py) | 11 | RSS 解析/过滤/限流、HN 归一化/回退、Trends helper、Amazon 凭证/字段 | 全部 mock，无真实网络/真实 Key |
| [test_scheduler.py](server/tests/test_scheduler.py) | 4 | CRUD、非法 cron、立即执行、禁用任务 | 无重启恢复、无自动触发时序测试 |
| [test_ui.py](server/tests/test_ui.py) | 8 | SPA 深链、资源缓存、API 404、缺 dist、文档、令牌注入 | 无浏览器真实渲染 |

**前端：`npm run check` → typecheck + lint + 4 files / 22 tests passed**

| 测试文件 | 数量 | 覆盖范围 | 缺口 |
|---|---:|---|---|
| [SourcePicker.test.tsx](web/src/components/SourcePicker.test.tsx) | 4 | 只允许已连接源、增删、全选/清空 | 无键盘/无障碍测试 |
| [sourceCatalog.test.ts](web/src/data/sourceCatalog.test.ts) | 9 | 离线、ready/degraded、目录合并、未知源、保留已选 | 无 API 集成 |
| [helpers.test.ts](web/src/lib/helpers.test.ts) | 5 | 时间范围、cron 标签、排序 | 无格式化边界（时区/空值） |
| [outreach.test.ts](web/src/lib/outreach.test.ts) | 4（含 `it.each` 3 语气） | 3 种语气、无引用回退 | 无发送记录/抑制逻辑（因为未实现） |

### 5.2 E2E 与集成测试

| 项目 | 状态 | 证据 |
|---|---|---|
| `web/e2e/` 测试 | ❌ 空目录 | `ls web/e2e` 为空 |
| Playwright 配置 | ❌ 不存在 | 无 `playwright.config.ts` |
| `npm run e2e` | ❌ 不可用 | `npx playwright test --list` 误抓 Vitest 文件并报 `TypeError: Cannot read properties of undefined (reading 'config')` |
| README“无头浏览器跑通 7 个页面” | 🧪 仅手工声明 | 仓库内无可复现脚本 |
| 真实网络 Provider（HN/Trends/RSS） | 🧪 仅 BP 手工记录 | 本次未复验 |
| 真实 AI Key | ❌ 未验证 | 无 `.env`；测试用假模型 |
| 真实 Amazon Key | ❌ 未验证 | 仅凭证缺失/字段归一化单测 |
| 桌面 `.app` 启动 | 🧪 仅 BP 手工记录 | 产物存在，本次未启动 |

### 5.3 覆盖缺口（按模块）

| 模块 | 自动化覆盖 | 风险 |
|---|---|---|
| Provider 适配器 | 高（全部 mock） | 真实平台行为/限流未验证 |
| Run 执行/去重 | 中 | 无并发、超时、部分失败组合测试 |
| AI 分析 | 中高（假模型） | 真实模型输出漂移、提示词校准未验证 |
| 机会库/阶段 | 高 | 无并发更新、快照版本测试 |
| 定时任务 | 中 | 进程重启恢复、时区、错过执行未测 |
| 前端页面 | **低** | 7 个页面无组件/交互测试 |
| 前端 Hook/API client | **低** | 错误分支、竞态、轮询未测 |
| 桌面打包 | 无 | 启动、端口顺延、令牌退出未自动化 |
| CLI | 无 | 参数解析、brief 输出未测 |
| 合规/抑制/频率 | 无 | 功能本身未实现 |

---

## 6. 验收标准对照

### 6.1 Phase 验收

| 阶段 | 验收标准（BP §10） | 状态 | 说明 |
|---|---|---|---|
| Phase 0 | 输入一个方向，5 分钟内得到 ≥3 条带原文链接的机会卡 | 🟡 | 采集/引用/链接可用；但**每个 Run 只产出 1 个机会**，且真实 AI Key 未验证 |
| Phase 1 | 机会 → 线索 → 草稿 → 已发送 → 已回复 | 🟡 | 机会 → 草稿 → 阶段可手工走到 replied；**无发送记录/提醒/线索实体** |
| Phase 2 | 产品词 → 可决策跨境机会卡；10 个卖家试用，≥4 人付 $49 | ❌ | 跨境决策工具未实现；0 个卖家试用 |
| Phase 3 | 更多 Provider、团队版、白标、云同步、评分校准 | ❌ | 未开始 |

### 6.2 产品指标（BP §11.3）

| 指标 | 目标 | 当前 |
|---|---:|---|
| 首次价值时间 | < 5 分钟 | 未测量 |
| 激活率（首次运行并保存 ≥1 机会） | ≥ 50% | 未测量；本地库 0 条 `saved_opportunities` |
| 机会“值得验证”率 | ≥ 30% | 未测量 |
| 每周触达动作 | ≥ 3 次/活跃用户 | 未测量；无发送记录 |
| 4 周留存 | ≥ 30% | 未测量 |
| 免费 → 付费 | ≥ 8% | 未测量；无支付 |
| 定时任务启用率 | ≥ 25% | 未测量；本地库 0 条 schedules |

### 6.3 本地数据库证据（`server/data/opportunity_scout.db`）

| 表 | 行数 | 说明 |
|---|---:|---|
| `runs` | 4 | 均为 2026-11-06；2 个 crossborder、1 个 saas、1 个 crossborder |
| `signals` | 10 | 真实 brief 样例对应的信号 |
| `analyses` | 1 | 仅 1 次 AI 分析落库 |
| `schedules` | 0 | 定时任务未真实使用 |
| `saved_opportunities` | 0 | 闭环/机会库未真实使用 |

> 结论：仓库里有“真实采集样例”，但没有“真实闭环使用样例”。机会库、阶段看板、触达模板目前只有测试覆盖，没有真实数据验证。

---

## 7. 未完成项与优先级 Backlog

### P0 — 阻塞 v1 验收

| # | 事项 | 对应需求 | 建议动作 |
|---|---|---|---|
| 1 | 统一“单机会 vs 多机会卡”的产品定义 | A4/B6/Phase 0 验收 | 要么把 `OpportunityAnalysis` 改为 `Opportunity[]`（一个 Run 多个候选机会），要么把 Phase 0 验收改为“每个 Run 1 张卡”；原型与生产必须一致 |
| 2 | 用真实 AI Key 跑通 2 个 Pack 端到端 | B7 | 配置 `.env`，至少跑通 crossborder + saas 各 3 个方向；记录评分稳定性与引用准确率 |
| 3 | 补齐获取闭环的“动作记录” | C7/C8/C9/C10 | 新增 `outreach` 表：contact、channel、sent_at、follow_up_at、suppressed；UI 增加“标记已发送 / 跟进提醒 / 加入抑制名单” |
| 4 | 手工信号补录 UI | A6 | 在 ResultsPage 增加“补录信号”弹窗，调用现有 `POST /signals` |
| 5 | 修复 E2E 基建 | D6 | 增加 `playwright.config.ts`，配置 `testDir: './e2e'`，写 7 页冒烟 + 离线态测试 |
| 6 | 增加前端页面/Hook 测试 | D7 | 至少覆盖 NewRunPage 表单校验、ResultsPage 分析/导出、PipelinePage 阶段更新、LibraryPage 删除 |

### P1 — 跨境 Pack 验收

| # | 事项 | 对应需求 | 建议动作 |
|---|---|---|---|
| 7 | 利润计算器 | E3 | 输入采购价/头程/关税/平台费/退货/尾程，输出毛利与盈亏平衡；结果写入机会快照 |
| 8 | 供应商短名单 | E4 | 支持手工/API 导入供应商，字段：工厂/贸易商、MOQ、样品周期、认证、审计 |
| 9 | 中英双语询盘草稿 | E5 | 基于供应商字段生成 MOQ/样品/认证问题清单，仍只复制不发送 |
| 10 | 合规/认证检查清单 | E6 | 按品类给出 CE/FCC/FDA、电池/液体、商标/专利检查项 |
| 11 | Amazon 真实 Key 验证 | E1 | 用真实 Creators API 凭证跑一次搜索，确认字段/限流/错误映射 |
| 12 | TikTok / 1688 / Keepa 适配器 | A7/A8/A9 | 优先 1688 官方 Open Platform（需资质）；TikTok/Keepa 先做目录状态与手工导入 |

### P2 — 规模化与体验

| # | 事项 | 对应需求 | 建议动作 |
|---|---|---|---|
| 13 | Domain Pack 配置化 | B1 | 把 query templates / scorecard / output schema 移到 YAML/JSON，支持用户自定义 Pack |
| 14 | SSE / Job Queue | A5 | `POST /runs` 立即返回 run_id，`GET /runs/{id}/events` 推送真实阶段；长任务不占请求 |
| 15 | 多工作区/席位/白标 | F4 | workspace 切换、成员、共享机会库；Studio 版基础 |
| 16 | 指标埋点与止损线 | F2/F6 | 本地事件表：run_created、analysis_saved、outreach_copied、stage_changed；不采集隐私 |
| 17 | 定价/支付/授权 | F3 | Phase 3 再做；当前可先做 license/试用限制 |
| 18 | 结果回流校准 | C10 | 把 won/dropped 与评分卡维度关联，形成“什么信号值得做”的基准 |

### 风险与工程卫生

| 风险 | 说明 | 建议 |
|---|---|---|
| 无 git 仓库 | 无法追溯需求→代码→测试的提交历史 | 初始化 git，提交当前基线并打 tag `audit-2026-11-14` |
| 单文件原型与生产双份维护 | 原型已归档，但仍可能被误改 | 在 README/原型顶部标注“只读归档”；CI 不构建 |
| 文档声明超前于验证 | README/BP 有“已验证”表述，但 E2E/真实 Key 不可复现 | 在文档中区分“已单测”/“已手工验证”/“未验证” |
| 数据源不稳定 | Reddit 反爬、Trends 限流 | 保持 Provider 错误可见；补多源降级与手工导入 UI |
| 平台条款 | 触达模板可能被滥用 | 保持“只复制不发送”；后续加抑制名单与频率上限 |

---

## 8. 证据与复现

### 8.1 本次实际执行的命令

```bash
# 后端测试
cd ideas_pool/server
python3 -m pytest -q
# → 43 passed in 3.01s

# 前端检查（typecheck + lint + vitest）
cd ideas_pool/web
npm run check
# → typecheck 通过
# → eslint 通过
# → Test Files 4 passed (4)
# → Tests 22 passed (22)

# E2E（失败）
cd ideas_pool/web
npx playwright test --list
# → TypeError: Cannot read properties of undefined (reading 'config')
# → 误抓 src/components/SourcePicker.test.tsx

# 本地数据库
sqlite3 ideas_pool/server/data/opportunity_scout.db ".tables"
# → analyses saved_opportunities signals runs schedules
# → runs=4, signals=10, analyses=1, schedules=0, saved_opportunities=0

# 产物时间戳
stat web/dist/index.html server/dist/*.dmg
# → 2026-11-06 14:50 / 14:52
# 最后源码改动：2026-11-06 14:48
```

### 8.2 未复验项

以下项目来自 README/business_plan 的手工记录，本次审计未重新执行：

- 真实网络下 HN / Google Trends / RSS 的端到端采集。
- 真实 AI Key 的分析质量与评分卡校准。
- 真实 Amazon Creators API Key。
- 打包后的 `.app` 启动、端口顺延、SPA 深链、退出服务。
- 无头浏览器对 7 个页面的手工巡检。

### 8.3 审计限制

- 目录不是 git 仓库，无法用提交历史核对“需求→实现”的演进。
- 未读取任何 `.env` / 密钥；当前目录也未发现 `.env`。
- 未修改任何业务代码或构建产物；本文档是唯一新增文件。
- 完成度为基于代码与测试的估算，不是合同意义上的验收结论。

---

## 9. 建议的下一步（按顺序）

1. **先做产品决策**：一个 Run 产出 1 个机会还是多个机会？这决定 schema、UI、Phase 0 验收口径。
2. **用真实 AI Key 跑 3 个方向**，把评分、引用、降级行为记录成基线。
3. **补齐闭环的“已发送/跟进/抑制”**，否则“获取闭环”名不副实。
4. **补手工信号 UI**，让跨境场景的“人工整理 → 补录 → 分析”真正可用。
5. **修 E2E + 页面测试**，把 README 里的手工验证变成可重复的 CI 门槛。
6. **再做跨境 Pack 的利润/供应/合规三件套**，然后执行 CONCIERGE_TEST 的 10 人测试。

> 建议在完成 1–5 后，再把 Phase 1 标记为“完成”；完成 6–12 后，再把 Phase 2 标记为“完成”。当前更准确的对外表述是：**“核心研究工作台可用，获取闭环与跨境 Pack 仍在开发中。”**
