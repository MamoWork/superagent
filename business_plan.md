# Opportunity Scout 业务方案 v2

> 调研修订版 · 2026-11-06
> 结论先行：不要做“又一个 Reddit 监控 / GummySearch 替代品”，要做**本地优先的「机会发现 → 判断 → 获取」工作台**。数据源通过统一 Provider API 隔离，Agent-Reach 只是其中一个适配器；商机范围不限于软件开发，跨境电商作为一等公民。

---

## 0. 一页结论

| 维度 | 结论 |
|---|---|
| 产品定位 | 本地优先的机会研究工作台：把公开信号变成**有证据的机会判断**，再把判断变成**第一批真实对话** |
| 核心差异 | 竞品停在“帮你找到抱怨”；我们做“值不值得做 + 下一步找谁 + 怎么开口 + 结果回流” |
| 数据源架构 | 核心只依赖 `Provider API`；Agent-Reach、网页搜索、RSS、市场平台、手工导入都是可插拔适配器，**不直接写死命令行** |
| 领域范围 | 软件/SaaS、跨境电商、本地生活、内容/房产等以 `Domain Pack` 扩展；v1 先做 SaaS + 跨境两包 |
| 首要 ICP | 1–3 人跨境卖家/小工作室（付费意愿最高）+ 有主业收入的独立开发者（量大、单价低） |
| 商业模式 | 本地版免费 + Pro 买断/订阅 + 跨境 Pack 加购 + 工作室版；BYO AI Key，COGS 极低 |
| 护城河 | 不是爬虫，而是**“信号 → 判断 → 动作 → 结果”的标注数据与领域评分卡**，以及本地数据带来的切换成本 |
| 最大风险 | Reddit/平台数据授权与反爬；竞品拥挤；用户只想要免费提醒。对应策略见第 9 节 |

---

## 1. 调研说明与证据边界

- 调研时间：2026-11-04 至 2026-11-06。
- 方法：用 Agent-Reach 的 Reddit `public-web` 搜索，抓取帖子标题、摘要与部分评论；共 7 组查询、约 70 条结果。
- 边界：公开网页搜索**不等于**站内全量；部分帖子只拿到摘要；完整评论读取多次被 Reddit 反爬拦截（`PLATFORM_BLOCKED` / HTTP 429），因此下文只把**已看到的原文**当作证据，推断部分会标注“假设”。
- 已保存原始数据：`research_opp_1.json` ~ `research_opp_4.json`、`research_crossborder_1.json` ~ `research_crossborder_3.json`。

---

## 2. 场景全景：从“发现”到“获取”的 8 个环节

```
信号发现 → 信号判断 → 证据留存 → 机会决策 → 线索定位 → 触达跟进 → 成交复盘 → 持续监测
   ①          ②          ③          ④          ⑤          ⑥          ⑦          ⑧
```

真正的痛点不是“找不到信息”，而是**信息太多、判断太贵、动作断链**。下面按环节拆。

---

## 3. 场景痛点清单（含证据）

### P0 · 决定产品生死

#### P1 信号发现靠手工，跨站、跨语言、跨平台

- 用户要手动在 Reddit 搜 `struggling with`、`need an easier way to`、`best tool for`、`any recommendations for`、`can't find a solution for`。
  - 证据：[How I Use Reddit to Find SaaS Ideas](https://www.reddit.com/r/indiehackers/comments/1fxbweb/how_i_use_reddit_to_find_saas_ideas_my_two_methods/)
- 一套 48 小时验证流程里，光“需求信号研究”就要花 2–3 小时，在 Reddit（`site:reddit.com`）、Facebook 群、Indie Hackers、垂直论坛之间来回搜。
  - 证据：[48-hour validation framework](https://www.reddit.com/r/SideProject/comments/1phg4mv/i_validate_startup_ideas_in_single_weekends_now/)
- 跨境选品同样靠手工：要按关键词拉前 15 名 + 5 个广告位，共 20 个 listing，逐个看 BSR、评论、评分、价格、A+ 内容、视频、品牌备案；作者说批量工具能“每个对比周期省约 1 小时”。
  - 证据：[Amazon product comparison framework](https://www.reddit.com/r/AmazonProductIdeas/comments/1swoxlx/how_i_do_amazon_product_comparison_before/)

**产品回应**：按 Domain Pack 预置查询模板，多源并行采集，自动去重/聚类；定时任务代替人工蹲守。

#### P2 工具只给“抱怨清单”，不给“值不值得做”

这是整个赛道最大的空档，也是本产品最该切入的位置。

- “GummySearch 关停后，一批替代品出现，但都有同一个问题：**它们只列抱怨，不告诉你哪些真的值得做**。”
  - 证据：[What I learned building a Reddit research tool after GummySearch shut down](https://www.reddit.com/r/SaaS/comments/1s525f7/what_i_learned_building_a_reddit_research_tool/)
- 原 GummySearch 做不到的四件事：判断痛点是否值得做、竞品解决到什么程度、写出 build brief、以及最后的行动。
  - 证据：[I've been building an upgraded version of gummysearch](https://www.reddit.com/r/SideProject/comments/1rw4p5k/ive_been_building_an_upgraded_version_of/)
- 已有竞品 DemandDrop 明确主打“按频次、挫败强度、付费意愿打分，输出排名报告 + 竞品格局 + MVP 规格 + 发布 playbook”。
  - 证据：[Roast my AI-powered Reddit research tool](https://www.reddit.com/r/roastmystartup/comments/1s520wm/roast_my_aipowered_reddit_research_tool_for/)
  - 含义：**“打分 + 报告”已经不是空白**，仅靠这个会被快速同质化。真正的差异必须继续往“线索 + 触达 + 结果回流”走。

**产品回应**：每个机会必须输出 `build / verify / drop` 结论、证据等级、反证、下一步实验；没有证据链接的判断不允许出现。

#### P3 伪需求：用户说的 ≠ 用户做的

- “别问别人会不会用，他们会撒谎；去 Reddit 搜**正在抱怨**的人。”
  - 证据：[I validated my SaaS idea in 3 days using Reddit](https://www.reddit.com/r/ProductHunters/comments/1p14vcy/i_validated_my_saas_idea_in_3_days_using_reddit/)
- “陌生人不请自来的抱怨是最诚实的信号；如果他们**一边抱怨一边还在为这件事花钱**，就是绿灯。”
  - 证据：[How did you validate your idea before building?](https://www.reddit.com/r/Entrepreneurs/comments/1srtog3/how_did_you_validate_your_idea_before_building/)
- “停止访谈，开始观察：去客户已经在的地方，看他们**现在**在抱怨什么。”
  - 证据：[What's your go-to process for validating an idea early on?](https://www.reddit.com/r/startups/comments/1r5nehe/whats_your_goto_process_for_validating_an_idea/)
- 落地页 + 广告一次测 4 个变量（创意、文案、定向、落地页），最后只有一个二元信号，很多创始人因此浪费几个月。
  - 证据：[Repeatable low cost validation protocol](https://www.reddit.com/r/Entrepreneurs/comments/1tbr1a0/repeatable_low_cost_business_idea_validation/)

**产品回应**：把“行为信号”做成评分维度，而不是只看提及次数：
1. 已经在付费（订阅、工具、外包、广告）
2. 已经在用 workaround（Excel、手工、截图、反复复制）
3. 有紧急/高频抱怨（时间、金钱、客户流失）
4. 正在主动找替代品（“GummySearch alternative”“is there a tool for X”）
5. 有预算角色（老板、代理商、卖家、团队负责人）

#### P4 证据碎片化，结论不可复核

- 手工搜索的结果散落在浏览器标签、表格和笔记里；跨境卖家研究多个产品时“用表格、备忘录、书签，越研究越乱”。
  - 证据：[How Do You Track Products and Performance When Starting Amazon FBA?](https://www.reddit.com/r/AmazonFBA/comments/1rqu48u/how_do_you_track_products_and_performance_when/)
- GummySearch 关停后，用户不得不“重建整套 setup”，说明把研究流程绑在单一 SaaS 上很脆弱。
  - 证据：[GummySearch is shutting down, so I tested a few alternatives](https://www.reddit.com/r/microsaas/comments/1rloo4r/gummysearch_is_shutting_down_so_i_tested_a_few/)

**产品回应**：本地 SQLite 保存原始信号、引用、时间、作者公开信息与快照；每条结论可点回原文；支持导出 JSON/CSV/Markdown brief。

#### P5 平台依赖是结构性风险：Reddit-only 工具会死

- GummySearch 关停的原因是无法与 Reddit 达成 API 商业授权。
  - 证据：[GummySearch replacement](https://www.reddit.com/r/indiehackers/comments/1p0xs5s/gummysearch_replacement/)
- 本次调研自身也遇到 Reddit 正文读取被拦截、RSS 429。说明“单平台 + 抓取”不可持续。

**产品回应**：Provider API 抽象 + 多源降级 + 官方 API 优先 + 用户手工导入兜底。Reddit 只是“社区信号”之一，不是命脉。

---

### P1 · 决定付费转化

#### P6 从“痛点”到“具体的人”断链

- 冷启动获客的实操是：Hunter.io 建名单、领英/推特私信、WhatsApp 群、Reddit 社区、转介绍；全是手工。
  - 证据：[First 100 customers with cold emails](https://www.reddit.com/r/SaaS/comments/1hksdux/how_i_got_my_first_100_customers_with_cold_emails/)
  - 证据：[How did you get your first 100 customers?](https://www.reddit.com/r/SaaS/comments/1j5hpsq/how_did_you_get_your_first_100_customers/)
- “先选一个极窄的人群，再把分发当成每天的系统。”
  - 证据：[first 100 users using X, cold email, Product Hunt](https://www.reddit.com/r/micro_saas/comments/1rdurp7/how_i_got_my_first_100_users_for_my_new_saas/)
- Brex 的经验：找到“问题最极端的那个群体”，再触达。
  - 证据：[How top B2B SaaS got their first 100 customers](https://www.reddit.com/r/SaaS/comments/1e6dlxl/i_studied_how_top_b2b_saas_companies_got_their/)

**产品回应**：机会卡一键转线索卡：平台、原帖、原话、时间、公开身份、痛点标签；不抓私人联系方式，不自动私信。

#### P7 个性化触达与跟进成本高，且容易变成 spam

- 冷邮件要一封封个性化，作者用 AI 辅助才规模化。
  - 证据：[First 100 customers with cold emails](https://www.reddit.com/r/SaaS/comments/1hksdux/how_i_got_my_first_100_customers_with_cold_emails/)
- Reddit 上“早期回复 ‘Is there a tool for X?’ 转化意外地好”，但问题是必须**一直盯着**。
  - 证据：[I built an alternative to gummysearch for finding paying customers on Reddit](https://www.reddit.com/r/microsaas/comments/1rkfzul/i_built_an_alternative_to_gummysearch_for_finding/)
- 已有产品主打“AI 找到有购买意图的人并自动触达”，说明自动化触达是竞品方向，但也是平台风控与品牌风险最高的地方。
  - 证据：[How I'd get my first 100 SaaS users](https://www.reddit.com/r/micro_saas/comments/1sp8czt/how_id_get_my_first_100_saas_users_no_audience_no/)

**产品回应**：只做**草稿**，用对方原话生成上下文；发送必须人工；内置频率限制、抑制名单、跟进提醒；绝不自动发帖/私信。

#### P8 工具碎片化 + 订阅疲劳

- 独立开发者认为 GummySearch 的 $29/$59 定价“付不起”，于是自己做替代品。
  - 证据：[I've built an app to find profitable startup idea on Reddit](https://www.reddit.com/r/indiehackers/comments/1k1dsc0/ive_build_an_app_to_find_profitable_startup_idea/)
- 另一条：“多数找相关帖子的工具又臃肿又贵得离谱。”
  - 证据：[Built a free tool to research reddit keywords](https://www.reddit.com/r/indiehackers/comments/1l1uj6n/built_a_free_tool_to_research_reddit_keywords/)
- 房产经纪人三年后的软件栈 $224/月，其中 PropPromote $99/月；说明垂直人群有真实软件预算，但也被订阅切得很碎。
  - 证据：[My $224/mo software stack after 3 years as an agent](https://www.reddit.com/r/RealEstateTechnology/comments/1mtqj03/my_224mo_software_stack_after_3_years_as_an_agent/)
- 跨境卖家同时用 SellerAmp、Keepa 等，工具各管一段。
  - 证据：[what tools do you use to do product research?](https://www.reddit.com/r/AmazonFBA/comments/1d4robm/what_tools_do_you_use_to_do_product_research/)

**产品回应**：本地优先、BYO AI Key、一个工作台聚合多源；定价低于“再买一个 SaaS”的心理门槛；Provider 机制允许用户接自己已付费的工具，而不是替换它们。

---

### 跨境专章：被低估的高价值场景

跨境商机的付费意愿、决策成本和信息分散度都高于“独立开发找点子”，而且痛点更具体、更容易量化 ROI。

#### C1 选品判断靠手工矩阵，标准散落在 SOP 里

- 低竞争标准：直接竞品少于一页、评论少于 100、关键词有人搜但没人卖；高潜标准：低评论产品月销 > $10k、有捆绑/差异化空间。
  - 证据：[My Personal Amazon Product Research SOP](https://www.reddit.com/r/AmazonFBA/comments/1mpt4u0/heres_my_personal_amazon_product_research_sop_free/)
- 对比矩阵要逐项记录价格、评论数、评分、星级分布、BSR、图片数、A+、视频、品牌备案；大多数人做到一半就放弃。
  - 证据：[How I do Amazon product comparison before launching anything](https://www.reddit.com/r/AmazonProductIdeas/comments/1swoxlx/how_i_do_amazon_product_comparison_before/)

#### C2 多产品追踪混乱，隐藏成本导致误判

- 新手用表格、备忘录、书签追踪多个产品，容易混乱；真正要算的是需求、竞争、售价、平台费、运费、仓储和潜在利润。
  - 证据：[How Do You Track Products and Performance When Starting Amazon FBA?](https://www.reddit.com/r/AmazonFBA/comments/1rqu48u/how_do_you_track_products_and_performance_when/)

#### C3 供应商真假难辨，中间商加价 300–400%

- Alibaba 上很多“制造商”其实是中间商：不是工厂直连、加价 300–400%、沟通出错、交期更慢；真正工厂不会英语、不在西方平台。
  - 证据：[Stop being scammed by Alibaba "manufacturers"](https://www.reddit.com/r/ClothingStartups/comments/1shl55u/stop_being_scammed_by_alibaba_manufacturers_i/)
- 识别真工厂要看生产流程照片/视频、国际认证、审计报告、Verified Supplier、Trade Assurance、样品。
  - 证据：[Finding REAL suppliers](https://www.reddit.com/r/Alibaba/comments/1jyw0mi/finding_real_suppliers/)
  - 证据：[Thinking of Buying from Alibaba?](https://www.reddit.com/r/Alibaba/comments/1kzqkpp/thinking_of_buying_from_alibaba_heres_what_you/)

#### C4 信号分散在 Amazon / TikTok / Google Trends / 1688 / Reddit

- 选品要看趋势、评论、广告、内容热度、供应价、物流与合规；每个平台一个工具，最后靠人拼。
- 这是 Opportunity Scout 最能提供价值的地方：**不是替代某个平台，而是把跨平台证据拼成一张可决策的机会卡**。

**跨境机会卡建议字段**：

| 维度 | 指标 | 数据来源（可插拔） |
|---|---|---|
| 需求 | 搜索趋势、评论增速、TikTok 播放/互动、社区抱怨频次 | Google Trends、TikTok Creative Center、Amazon 公开页、Reddit |
| 竞争 | 首页直接竞品数、评论门槛、价格带、广告密度、品牌集中度 | Amazon 公开页 / SP-API（用户授权）/ Keepa |
| 利润 | 采购价 + 头程 + 关税 + 平台费 + 退货 + 尾程，目标毛利率 | 1688/Alibaba 公开价、物流报价、汇率 API |
| 供应 | 工厂/贸易商识别、MOQ、样品周期、认证、审计报告 | Alibaba/1688 公开页、用户上传的报价单 |
| 合规 | CE/FCC/FDA、电池/液体、商标/专利风险 | 公开数据库、用户问卷 |
| 结论 | `小单测试 / 继续验证 / 放弃` + 下一步动作 | AI 汇总，必须附证据 |

**获取动作**：供应商询盘草稿（中英双语、MOQ/样品/认证问题清单）、TikTok 达人/社区种子名单、小预算广告测试清单。全部人工发送。

> 假设待验证：跨境卖家的付费意愿高于独立开发者。需要用 10 次访谈 + 10 份付费 brief 验证，不能只靠“工具很贵”推断。

---

## 4. 竞品地图与定位

| 类型 | 代表 | 强项 | 缺口 |
|---|---|---|---|
| Reddit 关键词监控 | F5Bot、Reddinbox、Reddalyze | 便宜/免费、提醒快 | 只给提醒或清单，缺判断与下一步 |
| AI 机会报告 | DemandDrop、各类 GummySearch 替代 | 打分、报告、竞品格局 | 报告与执行断链；同质化快 |
| 市场研究 | SparkToro、GummySearch（已关停） | 受众/社区洞察 | 贵、偏营销、不是获取闭环 |
| 跨境选品 | Jungle Scout、Helium 10、Keepa、SellerAmp | 数据深、平台绑定 | 各管一段、订阅贵、缺社区/内容侧信号 |
| 手工方案 | 表格 + 浏览器书签 + ChatGPT | 免费、灵活 | 不可复用、不可追踪、易断 |

**定位语**：

> 对一人公司和小工作室：Opportunity Scout 是本地优先的机会研究工作台。它把分散的公开信号变成带来源的机会判断，再把判断变成第一批真实对话。与 GummySearch 类工具不同，它不止告诉你“有人在抱怨”，还告诉你值不值得做、下一步找谁、怎么开口，以及结果如何回流。

**2×2 判断**：

- 横轴：监控/清单 ←→ 判断/闭环
- 纵轴：通用 ←→ 垂直（跨境/房产/本地服务）
- 空位：**判断 + 闭环 + 垂直 Pack + 本地优先**。只做左下（监控）会被免费工具打死；只做右上（通用报告）会被 DemandDrop 等挤死。

---

## 5. 产品方案 v2

### 5.1 总体架构

```
┌─────────────────────────────────────────────┐
│  UI（本地 Web / Tauri 壳）                    │
│  新建采集 · 机会分析 · 获取闭环 · 定时任务     │
└──────────────────┬──────────────────────────┘
                   │ HTTP/JSON（只认 API，不认 CLI）
┌──────────────────▼──────────────────────────┐
│  Local API（FastAPI）                        │
│  /providers /runs /opportunities /leads      │
│  /schedules /outreach /exports /settings     │
│  Job Queue · Scheduler · AI Orchestrator     │
└───────┬──────────────────────┬──────────────┘
        │                      │
┌───────▼─────────┐   ┌────────▼──────────────┐
│ Provider Registry│   │ AI Provider Registry   │
│ 适配器插件        │   │ OpenAI 兼容/Anthropic/ │
│                 │   │ Ollama                 │
└───────┬─────────┘   └───────────────────────┘
        │
┌───────▼─────────────────────────────────────┐
│ Adapters                                     │
│ agent-reach · public-web · rss · hn ·        │
│ marketplace · trends · manual-import · mcp   │
└─────────────────────────────────────────────┘
```

**硬规则**：UI 和业务核心**永远不直接调用** `agent-reach ...`，也不解析它的 stdout。只有 `AgentReachAdapter` 知道命令行、参数和错误码；未来换成 MCP、HTTP 服务或另一个采集工具，只换适配器。

### 5.2 Provider API 契约

**列表**：

```http
GET /api/v1/providers
```

```json
{
  "providers": [
    {
      "id": "agent-reach.reddit",
      "name": "Reddit",
      "group": "community",
      "capabilities": ["search", "read"],
      "auth": "none",
      "status": "ready",
      "cost": "free",
      "rate_limit": { "requests": 10, "window_seconds": 60 }
    },
    {
      "id": "hackernews",
      "name": "Hacker News",
      "group": "community",
      "capabilities": ["search"],
      "auth": "none",
      "status": "ready",
      "cost": "free"
    },
    {
      "id": "google.trends",
      "name": "Google Trends",
      "group": "trends",
      "capabilities": ["trends", "search"],
      "auth": "none",
      "status": "ready",
      "cost": "free"
    },
    {
      "id": "amazon.creators",
      "name": "Amazon 商品",
      "group": "marketplace",
      "capabilities": ["search"],
      "auth": "api_key",
      "status": "not_configured",
      "cost": "byo_key"
    }
  ]
}
```

**发起采集**：

```http
POST /api/v1/runs
```

```json
{
  "workspace_id": "ws_default",
  "domain_pack": "crossborder",
  "direction": "Amazon 宠物饮水机细分，低评论高客单的机会",
  "keywords": ["pet water fountain", "stainless steel", "quiet"],
  "provider_ids": ["agent-reach.reddit", "hackernews", "google.trends"],
  "time_range_days": 90,
  "limit_per_provider": 20,
  "ai_profile_id": "deepseek"
}
```

返回 `run_id`；进度用 SSE：`GET /api/v1/runs/{id}/events`。

**统一信号模型**（所有适配器必须归一化到这个结构）：

```json
{
  "id": "sig_01",
  "provider_id": "agent-reach.reddit",
  "source_type": "post",
  "source_url": "https://www.reddit.com/...",
  "title": "...",
  "quote": "用户原话，必须保留",
  "author_public": "u/...",
  "published_at": "2026-05-24T00:00:00Z",
  "metrics": { "upvotes": 9, "comments": 22, "price": null },
  "raw_ref": "local://signals/sig_01.json"
}
```

**适配器接口**（Python 伪代码）：

```python
class SourceProvider(Protocol):
    id: str
    capabilities: set[Capability]

    async def health(self) -> Health: ...
    async def search(self, query: SearchQuery) -> list[Signal]: ...
    async def read(self, url: str) -> Document: ...


class AgentReachAdapter(SourceProvider):
    """唯一知道 agent-reach CLI/MCP 细节的类。"""

    async def search(self, query: SearchQuery) -> list[Signal]:
        try:
            raw = await self.client.call("reddit.search", query)
        except ProviderError as e:
            raise self.map_error(e)  # NEED_LOGIN / RATE_LIMITED / ...
        return [normalize_reddit(item) for item in raw.items]
```

**错误映射**：适配器把平台错误统一成 `PROVIDER_NEEDS_AUTH`、`PROVIDER_RATE_LIMITED`、`PROVIDER_BLOCKED`、`PROVIDER_TIMEOUT`、`PROVIDER_UNAVAILABLE`；UI 只根据这些状态渲染“需登录 / 限流 / 暂停 / 重试”，不出现平台专属逻辑。

**配置驱动**：数据源以 `/providers` 的实际注册表为准。前端保留 `sourceCatalog` 目录用于展示未来适配器，但只有 API 状态为 `ready` / `degraded` 的源可选；未接入的源显示为“未接入 Provider API”并禁用。API 离线时显示真实离线状态与重试入口，不退回 mock，写操作禁用。

### 5.3 Domain Pack：把“行业知识”产品化

每个 Pack 是一个 manifest，定义查询模板、推荐源、评分卡、输出结构和合规约束。

```yaml
id: crossborder
name: 跨境电商
query_templates:
  - "{product} amazon reviews complaints"
  - "{product} tiktok shop viral"
  - "{product} alibaba supplier price"
  - "{product} reddit worth it"
recommended_sources:
  - marketplace.amazon.public
  - trends.google
  - social.tiktok.creative
  - supplier.alibaba.public
  - agent-reach.reddit
scorecard:
  demand: 0.25
  competition: 0.20
  margin: 0.25
  sourcing: 0.15
  compliance: 0.10
  confidence: 0.05
output_schema: crossborder_opportunity_v1
```

v1 建议只做两个 Pack：

1. **SaaS / 独立开发**：Reddit、HN、GitHub、Product Hunt、网页搜索；评分看痛点频次、付费信号、竞品饱和度、24h 可行性。
2. **跨境电商**：Amazon Creators API、Google Trends、TikTok Creative Center、1688/Alibaba 官方 API、Reddit；评分看需求、竞争、利润、供应、合规。

后续 Pack：本地生活、房产营销、内容创作、招聘/人才、B2B 外贸。Pack 是增长杠杆，也是收费点。

### 5.4 闭环：机会 → 验证 → 线索 → 触达 → 复盘

1. **机会卡**：结论、评分、证据、反证、风险、下一步。
2. **验证实验**：从模板生成（访谈 5 人、落地页 + $100 广告、样品单、供应商询盘、社区发帖测试），记录结果。
3. **线索池**：把原帖作者/评论者转成线索卡；展示公开上下文和原话。
4. **触达草稿**：基于对方原话生成，人工修改、人工发送；记录发送时间与渠道。
5. **跟进**：提醒、状态流转、拒绝/退订名单。
6. **复盘**：回复率、有效对话、付费转化；结果回流到评分卡校准。

### 5.5 合规与信任

- 只读采集公开内容；不自动发帖、评论、点赞、私信。
- 不替用户登录，不保存密码/Cookie；需要登录的源由用户本人完成。
- 优先官方 API；遵守 robots、限流与平台条款；不做“换账号绕过”。
- 本地存储默认不上传；API Key 放系统钥匙串；导出可删除。
- 触达前人工确认；内置抑制名单与频率上限。
- 每条 AI 结论必须能点回原文；无来源的判断标记为“推断”。

---

## 6. ICP 与付费意愿

### 6.1 目标客户

| 优先级 | ICP | 特征 | 痛点 | 付费逻辑 |
|---|---|---|---|---|
| A | 1–3 人跨境卖家/小工作室 | Amazon FBA、TikTok Shop、独立站；月 GMV $10k–100k；已为 2+ 工具付费 | 选品靠手工矩阵、供应商难验证、利润算不清 | 一次错判库存损失远大于工具费；按 Pack 付费 |
| B | 有主业收入的独立开发者 | 预发布到 $5k MRR；愿意为 AI/开发工具付费 | 不知道做什么、验证慢、第一批用户难 | 低价买断/月费；量大 |
| C | 小代理/工作室 | 房产营销、内容代运营、获客服务 | 客户多、研究重复、报告要交付 | 按工作区/席位，可转嫁客户 |
| 非目标 | 纯免费党、课程受众、企业采购 | 只要免费提醒/不愿动手 | — | 获客成本高、留存差 |

### 6.2 付费信号（已有证据）

- 独立开发者认为 $29–59/月“付不起”，但会为“更便宜”的替代品买单 → 价格必须显著低于 GummySearch。
- 房产经纪人月软件支出可达 $224，其中单一营销工具 $99/月 → 垂直人群有预算，关键是把价值说清楚。
- 跨境卖家同时使用多个付费工具 → 不是没有预算，而是工具太碎；聚合 + 决策有付费空间。

### 6.3 定价建议

| 版本 | 价格 | 包含 | 目的 |
|---|---|---|---|
| Free（本地） | $0 | 每天 3 次采集、2 个源、1 个工作区、手动运行 | 降低试用门槛，形成口碑 |
| Pro | $12/月 或 $99 买断（首发 $49） | 无限采集、定时任务、获取闭环、全部通用源、导出 | 主力转化 |
| Cross-border Pack | +$19/月 或 +$129 买断 | 市场平台源、利润测算、供应商短名单、合规清单 | 高价值加购 |
| Studio | $39/月 | 5 个工作区、3 席位、共享机会库、白标报告 | 小代理/工作室 |

- BYO AI Key，AI 成本由用户承担，毛利高。
- 买断制迎合“订阅疲劳”，但定时任务/云同步可留作订阅钩子。
- 首发策略：前 100 名 $49 终身 Pro，换访谈和案例；跨境 Pack 先卖 10 份预售再开发。

---

## 7. 获客策略（GTM）

### 7.1 用产品自己获客（dogfood loop）

1. 用 Opportunity Scout 扫描 “GummySearch alternative”“how to validate SaaS idea”“Amazon product research” 等话题。
2. 找到正在抱怨/求推荐的人，人工回复有价值的内容（不是广告），附一份免费机会 brief。
3. 把对方反馈回流到产品和案例。
4. 公开发布“我用它找到了什么”，形成内容飞轮。

> 这条链路本身就是产品 demo：发现 → 判断 → 线索 → 人工触达 → 转化。

### 7.2 渠道优先级

| 渠道 | 动作 | 预期 |
|---|---|---|
| SEO | “GummySearch alternative”“GummySearch shut down”“validate SaaS idea Reddit”“Amazon product research without Jungle Scout”“跨境选品工具” | 高意图长尾，复利 |
| 社区 | r/indiehackers、r/SideProject、r/microsaas、r/AmazonFBA、r/Alibaba、知无不言、卖家之家 | 早期种子与反馈 |
| 发布 | Product Hunt、Show HN、小红书/即刻 | 一次性峰值 |
| 内容 | 对比页、免费扫描器、案例拆解、跨境选品复盘 | 建立信任 |
| 合作 | 选品代理、货代、独立开发者 newsletter、跨境服务商 | 借渠道 |

### 7.3 免费钩子

- 网页版“Reddit 痛点扫描器”：输入关键词，返回 10 条带链接的抱怨 + 一个粗略评分。
- 跨境版“选品机会卡生成器”：输入产品词，返回需求/竞争/利润粗算 + 3 个供应商链接。
- 免费结果加水印/限制导出，引导下载本地版。

---

## 8. 护城河

| 层次 | 内容 | 可复制性 |
|---|---|---|
| 数据 | 公开信号本身 | 高，不是护城河 |
| 判断 | 领域评分卡、反证规则、证据分级 | 中，需要持续校准 |
| 闭环 | 机会 → 线索 → 触达 → 结果 | 中高，迁移成本高 |
| 标注数据 | 哪些信号最终带来回复/付费 | **高**，越用越准 |
| 本地数据 | 用户的历史、模板、导出、客户 | 高，切换成本 |
| 信任 | 只读、本地、人工发送、合规 | 中高，竞品难兼顾 |

**关键动作**：从第一天就记录“机会 → 实验 → 触达 → 结果”，在用户同意下做匿名聚合，形成“什么样的信号值得做”的基准。这是长期壁垒，也是 AI 报告类竞品最难补的。

---

## 9. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| Reddit/平台 API 授权变化 | 单源断供 | Provider 抽象、多源、官方 API 优先、手工导入兜底、不做数据转售 |
| 平台反爬/风控 | 采集失败 | 限流、退避、不换账号/后端；失败如实展示；优先公开网页与 RSS |
| 竞品拥挤（GummySearch 替代品） | 同质化 | 不打“监控”卖点，打“判断 + 闭环 + 跨境 Pack + 本地优先” |
| AI 幻觉/错误判断 | 信任崩塌 | 引用强制、证据分级、置信度、人工确认；无来源不给结论 |
| 用户只想免费 | 付费转化低 | 免费钩子 + 买断 + 跨境 ROI 测算；用预售验证再投入 |
| 跨境数据合规/平台条款 | 法律风险 | 官方 API/用户授权；不抓非公开数据；法律复核 |
| 范围蔓延 | 做不完 | v1 只做 2 个 Pack；明确非目标 |
| 本地应用分发/更新 | 体验差 | Tauri 签名安装包、自动更新、崩溃日志（可选匿名） |

---

## 10. MVP 范围与里程碑

### Phase 0（第 1 周）：跑通“证据 → 判断”

- Local API + SQLite + Job Queue。
- Provider Registry + 2 个适配器：`AgentReachAdapter`、`PublicWebAdapter`（含搜索 API）。
- 新建采集 → 采集 → 去重 → AI 分析 → 机会卡（带来源链接）。
- 导出 JSON/Markdown。
- **验收**：输入一个方向，5 分钟内得到 ≥3 条带原文链接的机会卡。

### Phase 1（第 2–3 周）：闭环

- 定时任务、采集历史、机会库。
- 线索池、状态流转、CSV 导出。
- 触达草稿 + 人工发送记录 + 跟进提醒。
- 合规设置（只读、抑制名单、频率）。
- **验收**：一个机会可以走完 机会 → 线索 → 草稿 → 已发送 → 已回复。

### Phase 2（第 4–6 周）：跨境 Pack

- Amazon 公开页/用户授权数据、Google Trends、TikTok Creative Center、1688/Alibaba 公开页。
- 利润计算器（采购 + 头程 + 关税 + 平台费 + 退货）。
- 供应商短名单 + 询盘草稿（中英）。
- 合规/认证检查清单。
- **验收**：输入一个产品词，输出一张可决策的跨境机会卡；10 个卖家试用，≥4 人愿意付 $49 预售。

### Phase 3（第 7 周+）

- 更多 Provider（官方 API、海关数据、MCP 工具）。
- 团队/工作室版、白标报告、云同步（可选）。
- 评分卡校准与基准数据。

### 明确不做（v1）

- 不自动发帖/评论/私信。
- 不做全量爬虫农场/绕过登录。
- 不做完整 CRM、客服系统、ERP。
- 不做移动 App。
- 不做企业 SSO/复杂权限。
- 不做“万能商机”，只做 2 个 Pack。

---

## 11. 验证指标与止损线

### 11.1 访谈（前 2 周）

- 10 个跨境卖家 + 10 个独立开发者/小代理。
- 关键问题：上一次选品/找点子花了多久？用了哪些工具？花了多少钱？最后怎么判断？错判损失多少？
- 通过标准：≥6/10 能说出具体的“手工拼信息 + 判断没把握”的经历。

### 11.2 Concierge MVP（第 3–4 周）

- 人工为 20 个用户各做 1 份机会 brief，收 $49（可退）。
- 观察：是否真的去联系供应商/做落地页/约访谈。
- 通过标准：≥8/20 产生真实动作；≥5 人愿意继续付费。

### 11.3 产品指标

| 指标 | 目标 |
|---|---|
| 首次价值时间 | < 5 分钟 |
| 激活率（首次运行并保存 ≥1 机会） | ≥ 50% |
| 机会“值得验证”率（用户标记） | ≥ 30% |
| 每周触达动作 | ≥ 3 次/活跃用户 |
| 4 周留存 | ≥ 30% |
| 免费 → 付费 | ≥ 8% |
| 定时任务启用率 | ≥ 25% |

### 11.4 止损线

- 100 个激活用户后，付费 < 5 人 → 重新审视定价/ICP。
- 用户只用免费扫描器、不保存机会、不做触达 → 产品价值不成立。
- 跨境 Pack 预售 < 5 份 → 暂停该 Pack，回到 SaaS 场景。
- 数据源持续不可用且无替代 → 暂停采集型功能，转“手工导入 + 分析”工具。

---

## 12. 待确认的产品决策

1. 本地壳用 Tauri 还是纯本地 Web（浏览器打开 localhost）？
2. Provider API 是否对外开放，允许第三方写适配器？
3. Reddit 数据策略：只用公开网页，还是申请官方 API/商业授权？
4. 跨境数据预算：Keepa/SimilarWeb/海关数据等付费源先接哪个？
5. 定价币种与首发优惠：$49 终身是否可持续？
6. 是否把“结果回流/评分校准”作为 Pro 功能，避免免费用户贡献数据？

---

## 13. 当前实现进度（2026-11-06）

已落地在 `server/`：

- Provider API + Registry + 统一错误码。
- `AgentReachProvider`：Reddit（public-web）与 Web 搜索；核心不直接调用 CLI。
- 成熟开源适配器：`RssProvider`（feedparser）、`HackerNewsProvider`（Algolia 公开 API）、`GoogleTrendsProvider`（pytrends）、`AmazonCreatorsProvider`（官方 Creators API，BYO Key）。未配置的来源在 API 与 UI 中都明确显示 `not_configured`，不能勾选。
- Run / Signal / SQLite 持久化 / 去重。
- 证据 brief（Markdown）+ 手工信号补录。
- `crossborder` / `saas` / `general` 领域包 manifest（评分维度、权重、输出 schema）。
- AI Analyzer：OpenAI 兼容 / Anthropic / Ollama；服务端按评分卡计算加权分与结论，模型只能引用本次 Run 的 `signal_id`，伪造引用会被丢弃。
- 定时任务：APScheduler + SQLite 持久化，支持 cron、启停、立即执行，进程重启自动恢复。
- React + TypeScript + Vite 前端：新建采集、机会分析、采集历史、定时任务、机会库、获取闭环、设置共 7 个页面；数据全部来自真实 API，无 mock / 演示模式。
- 机会库 / 获取闭环持久化：`saved_opportunities` 表保存分析快照与阶段（`saved` → `validating` → `contacted` → `replied` → `won` / `dropped`），不使用浏览器存储；触达模板在本地拼装并明确标注“非 AI 生成”，只复制不发送。
- macOS 桌面打包：PyInstaller 生成 `Opportunity Scout.app` 与 `.dmg`，后端同源托管 UI，数据写入 `~/Library/Application Support/OpportunityScout/`，设置页可退出服务。
- Concierge CLI + 43 个后端测试 + 22 个前端测试（Vitest）。
- 真实运行样例：`server/briefs/run_98bac940d660.md`（跨境）、`run_6f83d227cad3.md`（SaaS）。

已验证（2026-11-06）：后端 43 个测试通过；前端 `npm run check`（TypeScript + ESLint + 22 个 Vitest 测试）与 `npm run build` 通过。生产模式下 FastAPI 同源托管 `web/dist`：`/` 与 `/results/<run_id>` 深链返回注入运行时配置的 index，`/assets/*` 带 immutable 缓存头，未知 `/api/*` 返回 JSON 404。无头浏览器跑通 7 个页面与 404 路由；断网时显示「API 未连接」、写操作禁用，无 mock / 演示数据，控制台无错误。真实网络下 Hacker News、Google Trends、RSS（Ars Technica / TechCrunch）均能通过 `/api/v1/runs` 返回带源链接的信号。打包后的 `.app` / `.dmg` 已在本机验证：启动、SPA 深链、运行时令牌注入、数据目录初始化、机会库 API、带令牌退出服务均正常。Amazon 适配器只用单测验证了凭证缺失与字段归一化，尚未用真实 Creators API Key 跑过；AI 分析链路使用本地假模型服务验证过引用校验与降级逻辑，尚未用真实 Key 跑过。

未落地：1688 / Alibaba（官方 Open Platform 需资质且无成熟 OSS 客户端，暂不抓页面）、Keepa（付费 Key，未接入）、Domain Pack 完全配置化、系统级后台常驻/开机自启/桌面通知、真实 AI Key 的端到端验证。Concierge 测试的执行清单见 `server/CONCIERGE_TEST.md`，需要真实用户参与。

---

## 14. 证据索引

### 独立开发 / 机会发现

- [How I Use Reddit to Find SaaS Ideas](https://www.reddit.com/r/indiehackers/comments/1fxbweb/how_i_use_reddit_to_find_saas_ideas_my_two_methods/)
- [48-hour validation framework](https://www.reddit.com/r/SideProject/comments/1phg4mv/i_validate_startup_ideas_in_single_weekends_now/)
- [How I actually find SaaS ideas that people will pay for](https://www.reddit.com/r/SideProject/comments/1tkt1vj/how_i_actually_find_saas_ideas_that_people_will/)
- [This is how we find a $1M SaaS idea](https://www.reddit.com/r/indiehackers/comments/1hyrqdq/this_is_how_we_find_a_1m_saas_idea/)
- [How do you figure out what people actually want to pay for?](https://www.reddit.com/r/indiehackers/comments/1l8srmy/how_do_you_figure_out_what_people_actually_want/)
- [Validate demand for a new app/idea](https://www.reddit.com/r/Startup_Ideas/comments/1sjx7ry/how_do_you_validate_demand_for_a_new_appidea/)
- [I validated my SaaS idea in 3 days using Reddit](https://www.reddit.com/r/ProductHunters/comments/1p14vcy/i_validated_my_saas_idea_in_3_days_using_reddit/)

### 工具与竞争

- [GummySearch replacement](https://www.reddit.com/r/indiehackers/comments/1p0xs5s/gummysearch_replacement/)
- [GummySearch alternatives tested](https://www.reddit.com/r/microsaas/comments/1rloo4r/gummysearch_is_shutting_down_so_i_tested_a_few/)
- [What I learned building a Reddit research tool](https://www.reddit.com/r/SaaS/comments/1s525f7/what_i_learned_building_a_reddit_research_tool/)
- [Upgraded GummySearch](https://www.reddit.com/r/SideProject/comments/1rw4p5k/ive_been_building_an_upgraded_version_of/)
- [DemandDrop roast](https://www.reddit.com/r/roastmystartup/comments/1s520wm/roast_my_aipowered_reddit_research_tool_for/)
- [GummySearch alternative in a week](https://www.reddit.com/r/SideProject/comments/1ox3hd0/i_made_a_gummysearch_alternative_in_a_week/)
- [Free Reddit keyword tool](https://www.reddit.com/r/indiehackers/comments/1l1uj6n/built_a_free_tool_to_research_reddit_keywords/)

### 获客 / 触达

- [First 100 customers with cold emails](https://www.reddit.com/r/SaaS/comments/1hksdux/how_i_got_my_first_100_customers_with_cold_emails/)
- [First 100 customers](https://www.reddit.com/r/SaaS/comments/1j5hpsq/how_did_you_get_your_first_100_customers/)
- [First 100 users with X, cold email, PH](https://www.reddit.com/r/micro_saas/comments/1rdurp7/how_i_got_my_first_100_users_for_my_new_saas/)
- [First 100 SaaS users](https://www.reddit.com/r/micro_saas/comments/1sp8czt/how_id_get_my_first_100_saas_users_no_audience_no/)
- [Alternative to GummySearch for paying customers](https://www.reddit.com/r/microsaas/comments/1rkfzul/i_built_an_alternative_to_gummysearch_for_finding/)
- [How top B2B SaaS got first 100](https://www.reddit.com/r/SaaS/comments/1e6dlxl/i_studied_how_top_b2b_saas_companies_got_their/)

### 跨境 / 选品 / 供应链

- [Amazon Product Research SOP](https://www.reddit.com/r/AmazonFBA/comments/1mpt4u0/heres_my_personal_amazon_product_research_sop_free/)
- [Amazon product comparison framework](https://www.reddit.com/r/AmazonProductIdeas/comments/1swoxlx/how_i_do_amazon_product_comparison_before/)
- [Tracking products and performance](https://www.reddit.com/r/AmazonFBA/comments/1rqu48u/how_do_you_track_products_and_performance_when/)
- [Product research tools](https://www.reddit.com/r/AmazonFBA/comments/1d4robm/what_tools_do_you_use_to_do_product_research/)
- [Stop being scammed by Alibaba manufacturers](https://www.reddit.com/r/ClothingStartups/comments/1shl55u/stop_being_scammed_by_alibaba_manufacturers_i/)
- [Finding REAL suppliers](https://www.reddit.com/r/Alibaba/comments/1jyw0mi/finding_real_suppliers/)
- [Thinking of Buying from Alibaba](https://www.reddit.com/r/Alibaba/comments/1kzqkpp/thinking_of_buying_from_alibaba_heres_what_you/)

### 垂直付费信号

- [My $224/mo software stack as an agent](https://www.reddit.com/r/RealEstateTechnology/comments/1mtqj03/my_224mo_software_stack_after_3_years_as_an_agent/)
- [TikTok/Reel Realtor Captions](https://www.reddit.com/r/RealEstatePhotography/comments/1tmf5my/tiktokreel_realtor_captions/)
- [Running a real estate marketing agency in Texas](https://www.reddit.com/r/AIContentAutomators/comments/1pq7k2x/running_a_real_estate_marketing_agency_in_texas/)
