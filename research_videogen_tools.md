# AI 生视频：官方能力边界、开发者痛点与产品机会

- 项目：Opportunity Scout
- 调研日期：2026-11-11（以下所有价格、规格、条款均以该日抓取的官方页面为准）
- 范围：Sora 2、Runway Gen-4/Gen-4.5、Veo 3/3.1、Kling 2.x/4.0、Hailuo 02/MiniMax H3、Luma Ray3/Ray3.2、Pika、Wan 2.x/3.0、HunyuanVideo、Midjourney Video、LTX Studio/LTX-2.5、Higgsfield、HeyGen、Synthesia
- 增补范围（2026-11-11）：AI 生成广告素材/投放创意，含 Creatify、Arcads、Icon、Pencil、AdCreative.ai、AdGen、Captions、Meta Advantage+、Google PMax、TikTok Symphony/Smart+；平台 AI 披露政策与广告 API；详见 **§七**。
- 结论一句话：**模型能力在 2026 年已经跨过“能看”门槛，真正卡住生产的是“生成前后的工程”**——异步任务、失败计费、并发排队、多模型编排、素材版本、审核与授权。前者会随模型迭代消失，后者不会。广告场景进一步放大了这一点：**合规、版本、审核、归因比“再生成一条”更值钱**。

---

## ① 方法与证据边界

### 1.1 怎么做的

| 证据类型 | 具体来源 | 用途 | 局限 |
|---|---|---|---|
| 官方能力/价格 | 厂商文档、模型卡、changelog、pricing、API reference（Runway Dev、Vertex AI、Kling、MiniMax、Luma、Pika、Alibaba、Lightricks、Midjourney、HeyGen、Synthesia、OpenAI Help Center） | 表格中的时长、分辨率、音频、参考输入、价格、许可 | 部分页面是 JS 单页应用，只能取到 llms.txt/定价页/二手官方页 |
| 官方运行状态 | status.runwayml.com incidents JSON | 量化上游故障、审核误判 | 只覆盖 Runway 这一个聚合层，不代表原厂 SLA |
| 开发者一手反馈 | GitHub issues（ComfyUI-WanVideoWrapper、HunyuanVideo、lumaai-python）、HN、V2EX、linux.do、NodeSeek、App Store 评论、创作者复盘 | 痛点存在性与原话 | 论坛人群有偏；GitHub issue 多为开源/自托管 |
| 中文创作者反馈 | 另见 `research_videogen_cn.md`（约 520 条文本、58 条原话） | 抽卡成本、排队、一致性、交付 | 小红书登录墙，个体商家/女性创作者覆盖不足 |

### 1.2 证据分级

- **A 级**：官方文档原文、官方定价页、官方 status page、GitHub issue 原文。
- **B 级**：开发者/创作者第一人称长文、App Store 真实评论、论坛一手帖。
- **C 级**：媒体转述、第三方评测（只用于量级交叉验证，不单独证明痛点存在）。
- **D 级**：推断，文中明确标注“推断”。

### 1.3 范围校正：任务清单里的五个型号已经过时

这是本次调研最重要的前置发现。若按原清单做对比，会把“已停服/已下架”的模型当成可选项。

| 原清单型号 | 2026-11-11 状态 | 证据 |
|---|---|---|
| Sora 2 | **完全停服**。Sora Web/App 2026-04-26 下线；Sora API 2026-09-24 下线；官方明确“没有一对一的替代 API” | OpenAI Help Center《What to know about the Sora discontinuation》；OpenAI API 文档 deprecation notice |
| Veo 3.1 Preview（Gemini API） | **2026-10-22 关停**；迁移到 Gemini Omni Flash（`gemini-omni-1.2-flash`）或 Vertex/Enterprise 上的 Veo 3.1 GA | Google AI Studio deprecations / Gemini API 文档 |
| Hailuo 02 | 已被 **MiniMax H3（Hailuo 3）** 取代；H3 为当前主力 | Runway Dev《MiniMax H3 API》2026-11-09 |
| Kling 2.x | 已被 **Kling 4.0 / 4.0 Flash** 取代；4.0 支持 3–30s、音频、首/中/尾帧 | Runway Dev《Kling 4.0 API》 |
| Runway Gen-4 | 仍在目录中，但主力已切到 **Gen-4.5**（2–10s）与 **Aleph 2.0**（视频编辑） | Runway Dev models/pricing |

> 因此下文以“当前可用的替代型号”为主表；Sora 只作为“供应商停服风险”的案例，不再作为能力选项。

### 1.4 口径说明（避免误读）

1. **价格是官方挂牌价，不含税、不含代理加价**。Runway Dev 是聚合层，其价格可能高于原厂；表中同时给“原厂价”与“Runway 转售价”时会标注。
2. **“时长”指单次请求的最大输出时长**，不是“可拼接的总时长”。拼接是工程问题，见 ③。
3. **“一致性机制”只记录官方提供的机制**（首尾帧、参考图、角色参考、多镜头），不评价实际效果；效果证据见 ③。
4. 标注“未确认”的格子，表示官方页面未给出、或页面无法核验；**没有用估算填补**。
5. 所有 URL 的读取日期均为 **2026-11-11**；GitHub/论坛引用另标原帖日期。

---

## ② 官方能力对比

### 2.1 生成模型主表（当前可用）

> 价格单位：美元/秒（除特别注明）。所有数字读取于 2026-11-11。来源列的 `[O*]` / `[G*]` 对应第 ⑥ 节证据索引的完整 URL。

| # | 模型（当前版本） | 单次时长 | 分辨率 / fps | 原生音频 | 参考图 / 首尾帧 / 多镜头一致性 | API 与接入 | 官方价格 | 商用 / 许可 | 审核 / 地区限制 | 来源 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Runway Gen-4.5** | 2–10s（整数秒） | 720p（1280:720 / 720:1280）；fps 未确认 | 无原生音频（音频由 ElevenLabs 等独立模型提供） | 支持参考图；首尾帧/角色一致性以 Runway 参考输入与 Aleph 编辑为主；多镜头需拼接 | 有；异步任务 + 轮询，**无 webhook** | $0.12/s；5s=$0.60 | Runway 服务条款；API 商用需遵守其条款 | 输出经 SAFETY 审核；`SAFETY.INPUT.*` 不退款 | [O1][O2] |
| 2 | **Runway Aleph 2.0** | 输出跟随输入视频长度 | 输出分辨率匹配输入；ProRes/PNG/10-bit 可选 | 否 | 关键帧引导的 in-context 视频编辑；用于改镜头、换元素、延长 | 有；异步轮询 | $0.28/s；单次最低 $0.56 | 同上 | 同上 | [O1][O2] |
| 3 | **Google Veo 3.1** | 4 / 6 / 8s；参考图生视频仅 8s | 720p / 1080p / 4K；24fps | **是**（对白、音效、环境声同次生成） | 首帧、首尾帧、最多 3 张 asset reference；支持 extend；单 prompt 最多 4 条输出 | 有；Vertex AI / Gemini Enterprise；Gemini API 的 Preview 已于 2026-10-22 关停 | $0.40/s（含音频，720p/1080p）；4K $0.60/s；无音频 $0.20/s | Google Cloud 条款；C2PA/SynthID 溯源 | 区域可用性、内容安全策略；Preview 已关停 | [O5][O6] |
| 4 | **Gemini Omni 1.2 Flash** | 3–10s（Runway API 约束） | 360p 草稿 / 720p / 1080p / 4K 超分 | **是** | 图像、视频、音频参考；首尾帧；对话式编辑；最多 3 秒视频参考 | 有；Gemini API / Vertex / Runway | Runway 转售 $0.02/s（360p）、$0.07（720p）、$0.10（1080p）、$0.21（4K）；官方 token 计费未换算 | Google 条款 | 区域与安全策略；作为 Veo 3.1 Preview 的迁移目标 | [O8][O1] |
| 5 | **Kling 4.0** | 3–30s | 720p / 1080p；支持 21:9；fps 未确认 | **是**（对白、音效） | 首帧、中间帧、尾帧；最多 10 张图（帧+参考）；参考视频；视频编辑；prompt 最长 26,000 字符 | 有；Kling 官方 API / Runway Dev | 官方预付：$500/3250 units（约 $0.154/unit），$2,000/13,135，$8,000/53,640；Runway：$0.157/s 720p、$0.235/s 1080p（限时 8 折） | 用户引述 2025 版 ToS 4.6：“without our written permission, you may not use ... for any commercial purposes”；**2026 现行条款未逐条核验** | 预付包 180 天有效、不滚存；并发 20；内容审核 | [O9][O10][G18] |
| 6 | **MiniMax H3（Hailuo 3）** | 5–15s | 768p / 2K；支持 21:9 | **是** | 首帧/尾帧；最多 9 图 + 3 视频 + 3 音频，合计 12 个参考文件；参考音频可定声音 | 有；MiniMax 官方 / Runway Dev | 官方：$0.08/s（768p）、$0.13/s（2K）；**输入视频按输出同价计费**；Runway：$0.10 / $0.15 | 未确认（以 MiniMax 条款为准） | 内容审核；并发未确认 | [O11][O12] |
| 7 | **Luma Ray3.2** | 5s / 10s 两档 | 360p / 540p / 720p / 1080p；HDR、HDR+EXR；fps 未确认 | 未确认（官方页面未强调原生音频） | 首尾帧、角色参考（单图跨镜头）、视频转视频、Reframe | 有；Luma API / SDK | 100 credits/5s（720p）、400 credits/5s（1080p）；视频转视频 72 credits/s（720p）、144 credits/s（1080p）；**每 credit 美元价未确认** | 订阅含 Commercial use（官方 pricing 页列出） | 内容审核；区域未确认 | [O13][O14] |
| 8 | **Pika H3 Flex** | 3–15s（整秒） | 480p / 768p / 1080p / 2K / 4K；24fps；11 种画幅 | **是**（立体声 32kHz；可导出对白/音乐/音效三条 stem） | 最多 12 个参考（9 图 + 3 视频 + 3 音频）；首尾帧；参考视频；prompt 8,000 字符 | 有；Pika API Club | API：$0.07/s（1080p）、$0.16/s（4K）；上线期 5 折；参考视频按“输入秒数+输出秒数”计费 | **开放权重**；具体 license 未确认 | 托管端审核；本地推理无平台审核 | [O15][O16] |
| 9 | **Alibaba Wan 3.0** | 2–30s（单次直出） | 480p / 720p / 1080p；30fps | **是**（语音、环境声、音效同次生成） | 文生、首尾帧、图像/视频/音频参考；最多 20 个参考资产；多镜头 | 有；Alibaba Cloud / Runway Dev | Runway：$0.05 / $0.10 / $0.20 per s（480/720/1080）；Prime 1080p $0.28/s | 未确认（Wan 3.0 为 API 模型；开源权重最新可核验为 Wan 2.2，Apache 2.0） | 内容审核；区域未确认 | [O17][O18] |
| 10 | **HunyuanVideo 1.5** | 未确认（支持多时长/多分辨率） | 480p / 720p；1080p 超分；fps 未确认 | 否（官方未提原生音频） | 文生/图生；开源可 LoRA；无官方多镜头机制 | 自托管；8.3B 参数；最低 14GB 显存（开启 offload） | 开源免费（权重+代码） | Tencent Hunyuan Community License；**原 HunyuanVideo 许可明确排除欧盟、英国、韩国**；1.5 是否沿用未逐条核验 | 地域限制（至少旧版）；本地部署无平台审核 | [O19][O20] |
| 11 | **Midjourney Video** | 5s | SD / HD；fps 未确认 | 否 | 仅“首帧图 + 文本”，支持 `--loop`、`--end`；无跨镜头机制 | **无公开 API**（仅 Web/Discord） | Basic $10、Standard $30、Pro $60、Mega $120 /月；视频并发 1/3/6/12；队列上限 10 | 付费订阅可商用；**年营收 >$1M 的公司必须买 Pro/Mega** | ToS 明确“不保证质量、稳定性、uptime 或可靠性” | [O22][O23][O24] |
| 12 | **LTX-2.5** | 未确认（支持 native multi-shot） | 最高 4K（3840×2176）；24fps | **是**（音视频同步生成） | 原生多镜头；首尾帧；音频参考；开放权重 | 有（LTX API）；具体端点/价格未确认 | Studio：$15/$35/$125 每月（年付 $12/$28/$100）；API 单价未确认 | 代码 Apache 2.0；**模型 LTX-2.x Community License：年营收 ≥$10M 需商业许可** | 社区许可限制商业规模；托管端审核 | [O25][O26][O27] |
| 13 | **Seedance 2.5（参考项，字节）** | 最长 30s | 480p / 720p / 1080p（2.0 支持 4K）；fps 未确认 | **是** | 大量图像/视频/音频参考；多镜头 | 有；Runway / 火山引擎 | Runway：$0.20 / $0.30 / $0.68 per s；最短 4s；视频参考另计 $0.10–0.34/s | 未确认（以字节条款为准） | 内容审核；Runway 曾出现 Seedance 审核误判事故 | [O1][O34] |

**表内关键结论**

1. **“30 秒一次直出”已经商品化**：Kling 4.0（30s）、Wan 3.0（30s）、Seedance 2.5（30s）都在 2026 年做到；但**“30 秒内多镜头叙事一致”仍未成为可依赖的默认能力**（见 ③）。
2. **原生音频成为分水岭**：Veo 3.1、Gemini Omni、Kling 4.0、MiniMax H3、Pika H3、Wan 3.0、LTX-2.5、Seedance 2.5 都有；Runway Gen-4.5、Midjourney、HunyuanVideo 1.5 没有。
3. **价格跨度 10 倍以上**：同样 1080p 输出，从 Pika $0.07/s、Wan $0.20/s、Veo $0.40/s 到 Kling 4K $0.43/s、Seedance 2.0 4K $1.50/s。**“同模型不同渠道价差 5–10 倍”是开发者的一手观察**，见 ③ P0-4。
4. **开放权重在 2026 年明显进步**：HunyuanVideo 1.5 把最低显存从旧版 60GB 降到 14GB（offload），Pika H3 Flex、LTX-2.5 也开放权重；但“能跑”和“能生产”仍是两件事（见 ③ P0-7）。

### 2.2 平台 / 数字人表（不是通用生成模型）

| 平台 | 能力边界 | API | 价格（2026-11-11） | 并发 / 限制 | 商用 / 备注 |
|---|---|---|---|---|---|
| **HeyGen** | 数字人视频、翻译、口型同步、批量；25fps；单场景最长 30 分钟；最高 4K（Pro） | 有；v3 API；**webhook**、批量 100 条、批量状态查询 | Creator $29/月（600 credits）、Pro $49/月（1,000）、Business $149/月（1,500） | Pay-as-you-go 并发 10；Enterprise 20；可 burst +50，按 1.5× 计费；超限 429 + `Retry-After` | 需肖像授权；商用按订阅 |
| **Synthesia** | 数字人视频、翻译、交互头像；企业培训场景强 | 有；v2 Video API + 新 API；API key scope/过期管理 | Starter $19/月（1,250 credits）、Creator $89/月（6,000）；Enterprise 定制 | 429 `concurrency_limit` / `rate_limited`；402 `quota_exceeded`；具体并发数未确认 | 商用按订阅；企业合规/审计强 |
| **Higgsfield** | 聚合 100+ 模型的创意 UI（Veo、Kling、Wan、Seedance 等），含预设运镜/特效 | 未确认（llms.txt 未见公开 API 入口） | 年付折算 $19/$35/$65 每月；月付原价未确认；credits 制 | 未确认 | 更偏“创作工具”而非 API 基础设施 |
| **LTX Studio** | 故事板/分镜/剪辑一体化；底层 LTX-2.5 | 模型 API 有；Studio 本身未确认 | $15/$35/$125 每月（年付 $12/$28/$100） | 未确认 | 适合“从剧本到成片”的团队工作流 |

### 2.3 计费机制的六个“坑”（官方原文）

这一节单独列出，因为它是开发者最容易低估的部分。

1. **按输出秒计费，但输入视频也要钱。**
   - Runway Kling 4.0：使用输入视频时，“billed seconds are the output plus the longer of the input and the output”（输出 + 输入/输出中较长者）。
   - MiniMax H3：输入视频按**输出分辨率同价**计费（$0.13/s at 2K）。
   - Pika H3：参考视频按“输入秒数 + 输出秒数”计费。
2. **失败不一定退款。**
   - Runway：`SAFETY.INPUT.*` 失败**不退 credits**，且官方建议“不要重试”。
   - 剪映 AI 对口型：6 条全废、1,080 积分不退（中文一手案例，见 ③）。
3. **最低消费。**
   - Runway Aleph 2.0：单次最低 56 credits（$0.56）。
   - Runway Seedance 2.5：单次最低 80 credits（$0.80）。
   - MiniMax H3：最少 5 秒。
4. **预付包会过期。**
   - Kling：180 天有效，**不滚存、不延期**；并发 20。
5. **参考图/关键帧按件加价。**
   - Runway Gemini Omni 1.2：每张参考图 +$0.01；输入视频 +$0.01/s。
   - MiniMax H3：每张参考图/关键帧 +$0.02。
6. **“无限”只存在于订阅层的 Relax 模式。**
   - Midjourney：只有 Pro/Mega 有“无限 SD 视频（Relax）”；视频并发仍限制为 3（Relax）。

### 2.4 多镜头一致性的官方机制对比

| 机制 | 谁提供 | 实际边界 |
|---|---|---|
| 首帧 + 尾帧 | Veo 3.1、Kling 4.0、MiniMax H3、Pika H3、Wan 3.0、Luma Ray3、LTX-2.5 | 只能约束“起点/终点”，中间过程仍可能漂移；Veo 参考图生视频只支持 8s |
| 中间帧 | Kling 4.0（first/middle/last） | 比首尾帧强，但中间帧本身要先生成，仍是抽卡 |
| 角色/主体参考图 | Luma（单图角色参考）、Pika（12 参考）、Kling（10 图）、Wan（20 资产）、MiniMax（12 文件） | 单人物有效；多人物同框、多参考图时模型会“降智”（中文一手反馈） |
| 参考视频（动作/运镜/风格） | Kling 4.0、MiniMax H3、Pika H3、Wan 3.0、Gemini Omni | 解决“动作像”，不解决“脸是同一个” |
| 原生多镜头 | LTX-2.5、Wan 3.0（多镜头）、Seedance 2.5 | 官方声称支持，但跨 30–60 集的角色一致性仍未被验证 |
| 视频编辑/续写 | Runway Aleph 2.0、Kling 4.0、Gemini Omni、Pika | 适合“改一个镜头”，不适合“批量重做” |

**一句话**：官方机制已经覆盖“单次生成内的参考约束”，但**没有一家提供“跨次生成、跨集、可审计的角色身份”**。这正是工程层的机会。

---

## ③ 开发者 / 集成痛点清单

> 排序按“是否直接阻断生产/直接亏钱”。每条尽量给官方原文或一手链接；中文社区原话来自 `research_videogen_cn.md`，保留原始措辞。

### P0-1 异步任务：一个“没有 webhook 的世界”

**事实（官方）**

- Runway 的所有生成端点都是异步的：返回 task `id`，客户端轮询 `GET /v1/tasks/{id}`，直到 `SUCCEEDED` / `FAILED`。任务状态包括 `PENDING`、`THROTTLED`、`CANCELLED`、`RUNNING`、`FAILED`、`SUCCEEDED`。
- **在 Runway 270,984 字节的 API reference 中，`webhook` 出现 0 次**；没有 webhook 注册端点、没有回调签名、没有事件类型。
- Runway 官方文档明确提醒：输出 URL 是**临时的**，“Download and store anything you intend to keep”。

**为什么疼**

- 生产系统必须自己实现：轮询调度、指数退避、任务去重、超时、断点恢复、并发池、失败重试、结果落盘。每一家厂商的状态机还不一样。
- `THROTTLED` 是一个“非失败但也不在跑”的状态；如果客户端只按 `PENDING/RUNNING` 处理，就会误判超时。
- 没有 webhook 意味着“生成完成”这件事无法事件驱动；长任务（Wan 3.0 30s 中位 14 分 19 秒）只能靠猜轮询间隔。

**一手证据**

- GitHub `lumalabs/lumaai-python` #153（2025-04-19）：调用 `client.generations.list(limit=100, offset=0)` **稳定返回 500**；作者贴出完整复现代码，SDK 版本 1.0.2 与 1.7.3 均复现。原文：
  > “When attempting to list generations using the Python SDK, I'm consistently receiving a 500 Internal Server Error response.”
  > https://github.com/lumalabs/lumaai-python/issues/153
- HN Show HN《Self-hosted gateway for video generation APIs (Sora/Runway/Kling)》（2025-10-08）：作者的理由就是“不想为每个 provider 做一套集成”：
  > “Built this to test AI video providers without separate integrations for each. It's a local gateway that uses your API keys to call Sora, Runway, and Kling through one endpoint.”
  > https://news.ycombinator.com/item?id=45512871
- Reddit r/n8n（2026-03-10）：用中转商 KIE 接 Sora 2 的自动化流程，三天后任务永久卡住，作者丢了客户：
  > “Then it stops. One video fails with an error. Next one too. After three days, jobs wait forever... Now 15 days gone. I miss deadlines. Clients leave. Lost $50.”
  > https://www.reddit.com/r/n8n/comments/1rpo4l7/sora_2_on_kie_ai_broke_my_work_need_a_new_tool/
- Sora 停服后，r/OpenAI（2026-09-28）用户统计：**70 个聚合/转售页面里仍有 31 个把 Sora 列为可选模型**。这说明抽象层不仅缺“统一”，还缺“下线感知/健康检查”：
  > “70 of them listed Sora... 31 still offer Sora as a model you can pick”
  > https://www.reddit.com/r/OpenAI/comments/1wsf2ih/the_sora_api_was_due_to_shut_down_sept_24_i/

**工程含义**：webhook/事件层是明确的空白。谁先把“统一任务模型 + 回调 + 幂等 + 重试”做成基础设施，谁就拿到多模型工作流的入口。

---

### P0-2 失败与计费：失败不退款、输入双重计费、积分过期

**官方原文（Runway）**

> “Unlike other failures, credits are not refunded for `SAFETY.INPUT.*` failures. You should not retry these generations.”
> —— Runway《Handle Task Failures》，https://docs.dev.runwayml.com/guides/task-failures

同一页还说：`SAFETY.INPUT.TEXT` 可能在“请求里根本没有 promptText”时出现，**错误码不可靠，只能当诊断信息，不要直接展示给用户**。这意味着：开发者既不能靠错误码做精准重试，也不能靠它做用户提示。

**一手证据（中文）**

> “6条任务跑完，成片的嘴没有一条对得上音。她去找客服。平台甩回一行字，渲染完成，积分不退。”
> “SVIP每月配额3200积分……这一次任务烧掉1080积分，一个月配额的三分之一，换回6条废片。”
> —— 什么值得买（引黑猫投诉 #17402257225），2026-10-17
> https://post.smzdm.com/p/a5rxo6x7/

**英文一手证据（同一模式）**

> “a 8s generation failed at 87% of completion and… voiloà 4$ pulverized.”
> —— u/nickthblde, OpenAI Community, 2025-10-07
> https://community.openai.com/t/sora-2-api-charges-money-on-failed-run-at-100-progress/1361332

> “I paid for $50 in credits and have already lost several credits with no actual video produced... credits are just compute requests”
> —— u/devjordan, OpenAI Community, 2025-11-08（预生成审核拦截也扣费）
> https://community.openai.com/t/credits-charged-for-pre-compute-moderation-blocks/1365628

> “I just burned through 10-15k of credits making vids. Videos didn't generate, and I deleted the failed generations. Looking at my remaining credits.....it's wayyyyy lower. Hence, there are no refunds.”
> —— u/WHiteMage_BLackMage, r/leonardoai, 2026-08-10
> https://www.reddit.com/r/leonardoai/comments/1vkztv5/no_refunds_for_videos/

**量化可用率（B/C 级，用于量级而非精确统计）**

- 38 次生成 / 6 条可用（英文社区单帖自述）；
- 2,591 次生成 / 1 部短片（厂商自述，作为上限量级）；
- 180 条 5 秒商品片 / 19 条可直接上架 = **10.6%**（imai.lol，2026-10-29）；
- Runway Pro：5 条 <10s 视频耗尽月额度；15 秒用掉近一半 credits（Reddit，2026-08/09）。

**计费叠加的三个真实场景**

1. **视频转视频**：Kling 4.0 输出 10s、输入 20s，按 20s 计费（输出 + 较长者），不是 10s。
2. **参考视频**：Pika H3 输入 15s + 输出 15s = 30s 计费。
3. **失败重试**：Runway `SAFETY.INPUT.*` 不退款；重试还可能再次失败。

**产品含义**：需要在调用前给出“最坏情况报价”，而不是“单价 × 输出秒数”。这是 FinOps 产品的核心。

---

### P0-3 并发 / 排队 / 限流：钱不是瓶颈，队列才是

**官方数字**

| 厂商 | 并发/队列限制 | 证据 |
|---|---|---|
| Kling | 预付包并发 **20**；180 天不滚存 | https://kling.ai/dev/pricing |
| Midjourney | 视频并发：Basic **1**、Standard **3**、Pro **6**（Fast）/3（Relax）、Mega **12**/3；队列上限 **10** | Midjourney《Comparing Plans》 |
| HeyGen | PAYG 并发 **10**；Enterprise **20**；burst 最多 **+50**，按 **1.5×** 计费；超限 429 + `Retry-After` | https://developers.heygen.com/docs/usage-limits |
| Synthesia | 429 `concurrency_limit` / `rate_limited`；402 `quota_exceeded`；具体并发数未确认 | https://developers.synthesia.io/docs/errors |
| Runway | 任务可进入 `THROTTLED`；具体并发配额未在公开页给数值 | Runway API reference |

**一手证据（中文，排队是 2026 年最强烈的情绪）**

> “上午充了50块钱500积分开始生成，结果告诉我要排队。排队人数是6位数，等了一下午，预计还需等待10小时，完全没动。”
> —— linux.do @hxcqwaaaa，2026-08-10，https://linux.do/t/topic/2730648

> “生成一个seedance2.0模型的视频需要等待8-12个小时……排队的时候排名不一定是一直减少的，是会增加的……十几分钟前排在7万多名，十几分钟后排到8万名。”
> —— linux.do @oheyrvi，2026-03-06，https://linux.do/t/topic/1700553

> “一个10秒的镜头需要排上48小时。”
> —— 腾讯新闻《一位 AI 短剧导演的效率实验》，2026-05-18，https://news.qq.com/rain/a/20260518A082X800

**英文一手证据：付费/“无限”套餐同样被节流**

> “going from 20 minutes in the queue to 30, to 50 and now I'm at a little over an hour for every video.”
> —— u/ResponsibleFix66（Runway Unlimited）, r/runwayml, 2026-05-08
> https://www.reddit.com/r/runwayml/comments/1t71pm3/brutal_throttling/

> “Some of my video tasks stayed in the Unlimited queue for 6–10+ hours. Some tasks took 12–24 hours.”
> —— u/Ordinary_Ad1942（Loova Max, $712.80/年）, r/generativeAI, 2026-06-12
> https://www.reddit.com/r/generativeAI/comments/1u3o9cc/my_loova_max_annual_experience_unlimited_queued/

> “I'm frequently instantly getting 'Failed - We noticed some unusual activity' error when using the Fast [Lower Priority] mode... forcing me to either spend credits or go to the Lite mode”
> —— u/Sephy_winz（Google Ultra）, r/VEO3, 2026-05-08
> https://www.reddit.com/r/VEO3/comments/1t6zp65/constant_we_noticed_some_unusual_activity_errors/

> “48+ Hours Video Generation Que”
> —— u/AltraVR, r/civitai, 2025-06-08（23 赞）
> https://www.reddit.com/r/civitai/comments/1l6f5b1/48_hours_video_generation_que/

**为什么这是工程问题而不是模型问题**：排队来自算力供给与调度，不来自模型能力。多模型路由（把任务导向当前不排队的供应商）在技术上完全可行，且已有商业验证（见 P0-4）。

---

### P0-4 多模型编排：请求体是“按模型变化”的，不是“按端点变化”的

这是本次调研发现的**最强官方证据**。Runway 官方文档直接把它称为“破坏大多数集成的错误”：

> “The mistake that breaks most integrations: on generation endpoints the request body is almost always a discriminated union keyed on `model`. The valid `ratio` values, the allowed `duration` values, the prompt length limit, and which optional fields exist **all change depending on the model you pick**.”
> “Never carry a `ratio` or `duration` from one model to another, and never guess.”
> —— Runway Dev docs, https://docs.dev.runwayml.com/ (2026-11-11)

官方举的三个例子：

- `gen4.5`：ratio 只有 `1280:720` / `720:1280`，duration 2–10 整数，prompt 1,000 字符，ratio 和 duration **必填**。
- `gemini_omni_flash`：同样两种 ratio，但 duration 3–10，prompt 4,000 字符，ratio/duration **非必填**。
- `seedance2`：24 种 ratio（最高 4K），duration 4–15，prompt 3,500 字符，额外有 `audio`、`references`、`referenceVideos`、`referenceAudio`。

**这意味着**：一个“统一视频 API”不能只做字段映射；必须为每个模型维护**能力矩阵 + 参数 schema + 价格函数 + 失败语义**。这是持续维护的苦活，也是壁垒。

**市场信号**

- HN 2026-09-11 的 VideoRouter 自述：
  > “There are now many providers serving the same underlying video models, but prices can differ by 5–10× depending on the provider. VideoRouter gives you one API and routes each request across 100+ v…”
  > https://news.ycombinator.com/item?id=49667080
- HN 2026-04-14 的 `ai-video-creator` skill：把 ByteDance Seedance 2.0、Kling 3.0、Veo 3.1、Grok Imagine、Wan 2.7、Runway 等放在“一个统一 API”后面。
- Runway 自己已经从“模型厂”变成“聚合层”：同时提供 Runway、Kling、Seedance、Veo、Wan、MiniMax、Gemini 等模型，并提供 Model Router（按成本/质量/延迟自动选模型）。**厂商自己承认“多模型编排”是需求**。

**为什么疼**

- 每个模型的 duration 合法值不同（2–10、3–10、4–15、5–15、3–30），前端无法做一个统一滑块。
- 每个模型的 ratio 集合不同；一个非法 ratio 会在提交时才报错，浪费一次任务创建。
- 每个模型的参考图数量/计费方式不同；成本预估必须按模型分支。
- 模型会下线/改名（Sora、Veo Preview 就是例子），抽象层必须能“热替换”。

---

### P0-5 输出与后处理：临时 URL、格式不统一、元数据缺失

**官方事实**

- Runway：输出 URL 临时，必须自行下载转存；输出格式以 mp4 为主，ProRes/EXR 等专业格式按模型另计。
- Pika：可输出 mp4 + 三条 WAV（对白/音乐/音效），这是少见的“音频 stem”能力。
- Luma：支持 HDR、16-bit EXR，适合调色/合成。
- 各家帧率不同：Veo 24fps、Pika 24fps、Wan 30fps、HeyGen 25fps；混剪时帧率/色彩空间/音频采样率都要转。

**一手证据（中文）**

> “图片一个站，视频一个站。这个模型适合这个镜头，另一个模型可能又更适合下一段。来回切久了……最离谱的是，我本来只是想做条视频，最后浏览器标签页先开了十几个。”
> “好不容易抽到一段满意的，回头又忘了刚才到底是哪个模型跑的。”
> —— V2EX，2026-10-14，https://www.v2ex.com/t/1248756

> “素材生成后呢？你还得把它拖进PR里，加字幕、调色、做转场、配音乐、套模板……反正后面还有‘一万件事’。”
> —— 知乎，2026（厂商向，但描述了真实工作流），https://zhuanlan.zhihu.com/p/2066553515024062268

**英文一手证据：帧率是硬伤**

> “as soon as you process something through the model, it comes back in 24 fps… It throws off the entire sync: audio / lipsync / editing timeline / overall timing”
> —— u/h3rve, r/generativeAI, 2026-05-07（25fps 广播/广告交付）
> https://www.reddit.com/r/generativeAI/comments/1t67zac/25_fps_users_how_are_you_dealing_with/

> “the AI clip has replaced the original clip in timeline with edited parts etc, but nothing matches cause the AI clip is longer than original clip.”
> —— u/Robeloto, r/premiere, 2026-01-16
> https://www.reddit.com/r/premiere/comments/1qec88n/upscaled_ai_clip_does_not_match_the_original_clip/

> “short answer: fine for the rough cut, falls apart on revisions, and you cannot hand the output straight to a client.”
> —— u/Express_Map9176, r/VideoEditors, 2026-09-04
> https://www.reddit.com/r/VideoEditors/comments/1w7achv/can_you_actually_use_ai_editing_on_paid_client/

**工程缺口**：没有统一的“生成元数据”标准（模型、版本、seed、prompt、参考图、时长、分辨率、审核结果、成本）。这导致：
- 无法复现一条好镜头；
- 无法做 A/B 对比；
- 无法把“哪条能商用”带到后期/审片；
- 无法做资产版本管理。

---

### P0-6 审核误判与合规：错误码不可靠，规则不透明

**官方/平台证据**

- Runway status page：2026-10-06 “Elevated Seedance moderation errors”；2026-08-19 “Increased ratio of Seedance safety system false positives”。原文：
  > “We're experiencing an issue with Seedance generations that may lead to an increased number of rejected generations.”
  > https://status.runwayml.com
- Runway 失败文档：`SAFETY.INPUT.TEXT` 可能在无 promptText 时出现；错误码只能当诊断，不要展示给用户。
- Runway：`SAFETY.INPUT.*` 不退款，且不要重试。

**一手证据（中文）**

> “模型能生成、平台判违规；人脸越来越严、敏感词不可预测、IP 角色被拒、封号；B 端出现‘模型审核与平台审核不统一，整部剧重做’。”
> —— 中文社区调研综合（A/B 级来源见 `research_videogen_cn.md` P0-5）

**合规/许可的“隐藏地雷”**

| 模型 | 条款要点 | 风险 |
|---|---|---|
| HunyuanVideo | 许可明确排除 **欧盟、英国、韩国**（旧版 LICENSE.txt 原文：“THIS LICENSE AGREEMENT DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA”） | 在这些地区商用/分发可能直接违约；1.5 是否沿用未确认 |
| LTX-2.x | 年营收 ≥ **$10,000,000** 需单独商业许可 | 成长型公司容易踩线 |
| Midjourney | 年营收 > **$1,000,000** 的公司必须买 Pro/Mega | 企业采购容易买错档 |
| Runway | `SAFETY.INPUT.*` 不退款 | 批量任务成本不可控 |
| Kling | 预付包 180 天过期、不滚存 | 预算浪费 |
| Sora | API 已停服，无一对一替代 | 迁移成本 + 供应商风险 |

**“付了钱≠能商用”：一手证据**

> “specifically, without our written persmission, you may not use or make modifications to the output for any commercial purposes”
> —— 用户引述 Kling ToS 4.6，u/beantorres, r/KlingAI_Videos, 2025-06-10（2026 现行条款未逐条核验）
> https://www.reddit.com/r/KlingAI_Videos/comments/1l7wkpy/who_owns_the_output_is_it_copyrighted/

> “Today I used Flow with Veo quality to generate a video, and it cost 100 credits. After the video was generated, I noticed a Veo watermark in the bottom-right corner.”
> —— u/Due_Entrepreneur1546, r/GeminiAI, 2026-07-19（消费级 Flow 的可见水印；Vertex API 走 SynthID/C2PA，不等同）
> https://www.reddit.com/r/GeminiAI/comments/1v0t7i8/google_ai_pro_veo_watermark_can_paid_users_remove/

> “If you're delivering generated output, there are licensing implications the client genuinely needs to know about.”
> —— u/Madmahi25, r/aitubers, 2026-08-25
> https://www.reddit.com/r/aitubers/comments/1vxx62e/we_lost_a_pitch_to_an_agency_quoting_a_tenth_of/

**结论**：商用授权不是“一个布尔值”，而是“模型条款 × 接入渠道（官方/聚合/消费级 App）× 地区 × 营收阈值 × 是否带水印”的五维矩阵。采购和创作者都缺一个可查询的“权利台账”。

---

### P0-7 开源自托管：VRAM、速度、质量的三重落差

**旧版痛点（仍然是大量用户的现实）**

- Wan 2.2 14B：官方 README 要求 **80GB VRAM**；5B 版本 24GB；5s 720p 生成 <9 分钟。
- HunyuanVideo（2024 版）：720p 需 **60GB**，544p 需 45GB，官方推荐 80GB。
- GitHub `ComfyUI-WanVideoWrapper` #680（2025-06-21）：
  > “So i have a 3090 and 16gb of system ram, im getting 64gb tomorrow. Big issue im facing atm is NO MATTER THE MODEL I TRY to load from the 14b version i always OOM especially when i try to load a Lora i oom... i tired block swapping and that also fails.”
  > https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/680
  评论区进一步指出：文本编码器不量化就会 OOM；加载 LoRA 会“杀死 VRAM”；wrapper 的 LoRA 处理比原生节点低效。
- HunyuanVideo #152（2024-12-25）：
  > “HunyuanVideo has already integrated with diffusers, I was able to run 544(width) x 960(height) x 81(frames) on RTX 3090 in ~30 minutes.”
  > “Just tried 100 frames, took 38 minutes.”
  > https://github.com/Tencent-Hunyuan/HunyuanVideo/issues/152

**2026 年的进步（不能忽视的反证）**

- HunyuanVideo 1.5：8.3B，最低 **14GB**（offload），480p I2V step-distilled 在 RTX 4090 上 **75 秒** 一条。
- Wan 2.2 5B：24GB 可跑；LTX-2.5 支持 FP8 + CPU/disk offload。
- Pika H3 Flex 开放权重（基于 MiniMax H3 后训练）。

**结论**：开源模型“能跑”的门槛在快速下降，但“稳定产出可用镜头”的门槛没有同比下降。自托管的痛点从“显存不够”转向“调参、量化、队列、质量验收”。这仍然是工程机会，但竞争者是 ComfyUI/Replicate/fal，而不是模型厂。

---

### P0-8 供应商停服：Sora 不是孤例

- Sora Web/App：2026-04-26 停服；Sora API：2026-09-24 停服；官方：“No one-to-one replacement API is available.”
- Veo 3.1 Preview（Gemini API）：2026-10-22 关停，迁移到 Gemini Omni Flash 或 Vertex GA。
- Hailuo 02 → MiniMax H3；Kling 2.x → 4.0；Runway Gen-4 → Gen-4.5。
- Runway status page 过去 12 个月 **50 起**事故，近 90 天 **12 起**；包括 2026-11-02 Kling 全系（4.0/3.0/O3）因上游故障大面积失败，官方建议“换一个视频模型”。

**产品含义**：任何“单模型深度绑定”的产品都有停服风险；抽象层 + 多供应商 fallback 不是“nice to have”，是生存能力。

---

### P0-9 转售商/中转层：比原厂更不稳定，且没有 SLA

很多团队并不直接接原厂，而是通过聚合器/中转商（KIE、Freepik、Loova、第三方“无限套餐”）接入。这一层的风险在原厂之上再叠加一层：

> “Then it stops. One video fails with an error. Next one too. After three days, jobs wait forever... Now 15 days gone. I miss deadlines. Clients leave. Lost $50.”
> —— u/gobhalla（n8n + KIE 转售 Sora 2）, r/n8n, 2026-03-10
> https://www.reddit.com/r/n8n/comments/1rpo4l7/sora_2_on_kie_ai_broke_my_work_need_a_new_tool/

> “the 'unlimited' thing is basically a lie... after you use it for a while, you hit this 'battery' system where you get throttled and then locked out entirely until you pay an extra $5”
> —— u/Gold-Alternative9327, r/generativeAI, 2026-03-16
> https://www.reddit.com/r/generativeAI/comments/1rvaj50/my_honest_experience_with_higgsfield_after_4/

> “All my generations with that model get stuck, and nothing generates.”
> —— u/EdgarRRojas（Kling 3.0 via Freepik）, r/Freepik_AI, 2026-02-06
> https://www.reddit.com/r/Freepik_AI/comments/1qxm1c6/kling_30_working/

**为什么这是产品机会而不是“避坑指南”**：企业需要的是**供应商健康检查 + 自动降级 + 退款/对账**，而不是一张“哪些中转商靠谱”的静态名单。中转层越繁荣，这个需求越大。

---

### P1 其他真实但非阻断的痛点

1. **定价不透明**：credits、units、订阅、预付包、代理加价并存；同一模型不同渠道价差 5–10×；Luma 的“每 credit 美元价”在定价页未直接给出。
2. **商业授权碎片化**：订阅层、API 层、开源许可、地区排除、营收阈值四套逻辑；采购很难一次买对。
3. **交付协作断裂**：客户一句“再改改”= 整段重抽；修改 7–9 轮是常态（中文一手复盘）。
4. **素材/版本管理缺失**：标签页十几个、忘了哪个模型跑的、不知道哪条能商用。
5. **审核与平台规则不一致**：模型能生成、平台判违规；整部剧重做。
6. **数字人合规**：肖像权、真人克隆、平台封号/限流；HeyGen/Synthesia 都需要授权链路。

---

## ④ 模型能力问题 vs 工程问题

判断规则：**如果“换一个更好的模型”就能解决，是模型能力问题；如果“换模型后仍然要写同样的胶水代码”，是工程问题。**

| 问题 | 类型 | 判断依据 | 12–24 个月会怎样 |
|---|---|---|---|
| 30 秒以上、多镜头、角色不漂移 | **模型能力**（正在改善） | Kling 4.0/Wan 3.0/Seedance 2.5 已做到 30s；跨集一致性仍无解 | 原生 30–60s 会普及；跨集身份仍需资产层 |
| 物理规律、复杂交互、多人打斗 | **模型能力** | 需要世界模型/物理先验 | 缓慢改善，产品层只能规避 |
| 原生 4K、60fps | **模型能力** | Veo 4K、Pika 4K 已有；60fps 未确认 | 2 年内普及 |
| 原生中文小字/Logo 精确渲染 | **模型能力** | 字符级监督问题 | 厂商主战场；工具层应做后期合成 |
| 多说话人/侧脸/运动口型 | **模型能力** | 音画对齐 + 人脸建模 | 改善但难完美 |
| 导演级运镜理解 | **模型能力** | 多模态空间推理 | 2027 年前难产品化 |
| 异步任务编排、重试、幂等 | **工程** | 每家 API 都是异步 + 轮询；Runway 无 webhook | 不会自动消失；越晚做越痛 |
| 失败退款/成本预估 | **工程/商业** | 计费规则由厂商定，但“预估/对账/告警”是工程 | 厂商不会主动做中立层 |
| 并发/排队/多供应商路由 | **工程** | 排队是算力调度问题 | 需求长期存在 |
| 多模型 schema/能力矩阵 | **工程** | 官方明确“request body per-model” | 模型越多越痛 |
| 输出转存/格式/元数据 | **工程** | URL 临时、格式不一 | 长期存在 |
| 素材/版本/审片 | **工程** | 与模型无关 | 长期存在 |
| 审核误判/合规预检 | **工程 + 规则** | 规则不透明、错误码不可靠 | 规则会变，工具长期有价值 |
| 开源自托管运维 | **工程** | VRAM/量化/队列 | 工具链会成熟，但仍有服务空间 |

**给产品团队的一句话**：**不要在“模型会变好的地方”建护城河；要在“模型变好也不会消失的胶水层”建护城河。**

---

## ⑤ 可产品化机会（按市场规模排序）

> 排序依据：付费意愿 × 用户基数 × 是否被模型厂吞并的风险。不是技术难度排序。

### 机会 1（最大）：多模型视频 API 网关 / 路由层

**做什么**
- 一套统一 schema，抹平 Runway/Kling/Veo/Wan/MiniMax/Pika/Seedance 的请求体差异；
- 统一任务模型：创建、轮询、**webhook/回调**、幂等键、重试、断点恢复；
- 能力矩阵：每个模型支持哪些 duration/ratio/参考图/音频/编辑；
- 成本感知路由：按“成本/质量/延迟/排队”选模型，支持 fallback；
- 输出统一转存 + 元数据（模型、seed、prompt、成本、审核结果）。

**证据**
- Runway 官方：“request body is per-model, not per-endpoint”“the mistake that breaks most integrations”；
- Runway API 无 webhook，只有轮询；
- Runway status 近 90 天 12 起事故，上游 Kling 故障时官方建议换模型；
- HN VideoRouter：“prices can differ by 5–10×”；
- HN mediagateway：开发者自己写 gateway 来避免“每个 provider 一套集成”；
- Sora 停服后仍有 31/70 个聚合页面把 Sora 列为可选模型（r/OpenAI, 2026-09-28）——说明“下线感知 + 健康检查”是刚需；
- KIE 中转商故障导致 n8n 用户 15 天无法交付、客户流失（r/n8n, 2026-03-10）。

**为什么现在**
- 模型数量从 2025 年的 5–6 个变成 2026 年的 20+ 个；企业不可能自建所有集成。
- 模型生命周期缩短（Sora 2 发布到 API 停服约 12 个月、Veo 3.1 Preview 约 1 年关停），抽象层价值上升。
- 原生“Model Router”只有 Runway 等少数平台提供，且绑定自家生态；中立层仍是空白。

**壁垒**：能力矩阵的维护速度、失败语义的积累、成本数据的规模、客户工作流绑定。
**风险**：Runway/Replicate/fal 等平台向上下游扩张；模型厂自己做统一 API。
**定价**：按调用量抽 3–8%，或订阅 $99–$999/月；企业版按并发/ SLA。

---

### 机会 2（最大之一）：视频 FinOps / 成本与配额守卫

**做什么**
- 调用前“最坏情况报价”：输出秒数 + 输入视频 + 参考图 + 最低消费 + 失败概率；
- 预算/配额：项目、镜头、客户三级预算；超限阻断或降级到便宜模型；
- 失败对账：哪些失败退款、哪些不退款、哪些是审核误判；
- **失败计费申诉/退款凭证**：自动生成“失败任务 + 扣费记录 + 官方条款”的对账单，供平台客服/信用卡争议使用；
- 浪费分析：废片率、每可用镜头成本、模型/分辨率的 ROI；
- 预付包/积分到期提醒（Kling 180 天、Midjourney 月度）。

**证据**
- Runway `SAFETY.INPUT.*` 不退款；
- Kling 180 天不滚存、并发 20；
- MiniMax/Pika/Runway 输入视频双重计费；
- 中文一手：一条 46 秒成片总花费约 309 元，折合每秒近 7 元，是页面单价数倍；180 条商品片仅 19 条可直接上架（10.6%）；
- Sora API：8 秒生成在 87% 失败，$4 照扣；预生成审核拦截也扣 credits（OpenAI Community, 2025-10/11）；
- Leonardo：10–15k credits 生成失败、删除失败任务后余额仍被扣，官方“无退款”（r/leonardoai, 2026-08-10）；
- Veo/Flow：Fast 模式频繁“unusual activity”失败，用户被迫花更多 credits 走高质量通道（r/VEO3, 2026-05-08）。

**为什么现在**
- 2026 年视频单价虽下降，但“抽卡次数”上升；真实成本与账面单价脱节。
- 财务/采购开始介入 AI 工具预算；需要可审计的成本账。
- 模型/渠道价差 5–10×，路由省钱空间大。

**壁垒**：跨厂商计费规则库 + 真实账单数据；一旦接入财务流程，迁移成本高。
**风险**：厂商自己提供成本面板（但只覆盖自家）；需要与网关/工作流绑定。
**定价**：按管理支出的 1–3%，或 $49–$499/月。

---

### 机会 3：镜头级资产 / 版本 / 审片协作（中立层）

**做什么**
- 角色/场景/道具“资产卡”，带多角度参考、版本、授权状态；
- 镜头级生成记录：模型、参数、seed、参考图、成本、评分、是否采用；
- 客户审片链接：逐镜标注、版本对比、修改意见分类（小改/重做）；
- 与 NLE 打通：Premiere/Resolve/剪映的标记、EDL/XML、素材命名规范；
- 合同/报价模板：修改次数、重做单价、交付标准。

**证据**
- V2EX 一手：“标签页十几个”“忘了哪个模型跑的”；
- 中文复盘：客户改 7–9 轮，整段重抽；
- Runway 输出 URL 临时、格式不一；
- 各家元数据不统一，无法复现好镜头。

**为什么现在**
- 2026 年团队从“玩”转向“交付”，需要可审计的生产流程；
- 模型厂不会做跨模型的项目管理；
- NLE 厂商（Adobe/Blackmagic）不会做多模型生成记录。

**壁垒**：资产数据 + 客户审片关系 + 与 NLE 的深度集成。
**风险**：Notion/飞书表格的低价替代；需要先证明“省时间”而非“省积分”。
**定价**：$19–$99/seat/月；团队版 $199–$999/月。

---

### 机会 4：合规预检与许可证管理（垂直但高价值）

**做什么**
- 生成前：扫 prompt/参考图（人脸、明星脸、IP 角色、品牌 Logo、敏感词）；
- 生成后：扫画面（人脸相似度、Logo 变形、文字乱码、版权素材）；
- 许可证：按模型/地区/营收阈值判断“能否商用”；生成可审计的授权记录；
- 输出“可投/需改/不可用”与修改建议。

**证据**
- Runway Seedance 审核误判事故（2026-08-19、2026-10-06）；
- Hunyuan 地域排除、LTX $10M、Midjourney $1M；
- 中文一手：“模型审核与平台审核不统一，整部剧重做”。

**为什么现在**
- 2026 年 AI 视频进入品牌/广告/短剧交付，合规成为采购门槛；
- 平台规则不透明且频繁变化，企业需要“预检”而不是“事后救火”。
**风险**：规则库维护成本；准确率要求高；不要定位成“绕过审核”。
**定价**：按项目/席位；企业合规版 $500–$5,000/月。

---

### 机会 5：开源自托管运维层（中等）

**做什么**
- 显存/量化/offload 自动配置；模型/分辨率/时长的可行性检查；
- 队列、批处理、失败重试、GPU 利用率；
- 质量验收：人脸漂移、闪烁、音画不同步的自动检测；
- 一键部署 ComfyUI/HunyuanVideo/Wan/LTX 工作流。

**证据**
- Wan 14B 80GB、Hunyuan 旧版 60GB、3090 OOM、38 分钟/100 帧；
- Hunyuan 1.5 降到 14GB，但调参仍复杂；
- Pika H3/LTX-2.5 开放权重，自托管需求上升。

**风险**：ComfyUI/Replicate/fal 已占据；价格战；模型迭代快。
**定价**：按 GPU 小时或订阅。

---

### 机会 6：垂直一致性流水线（漫剧/短剧/电商）

**做什么**
- 角色圣经 + 镜头级参考绑定 + 自动质检（脸/服装/道具/光位漂移）+ 失败镜头重生成；
- 针对漫剧/短剧的 30–60 集资产库；
- 针对电商的商品保真（Logo/中文小字/尺寸/颜色）。

**证据**
- 中文一手：第三个镜头开始“换人”；多参考图“降智”；“目前基本无解”；
- 电商：180 条实测仅 10.6% 可直接上架。

**风险**：与模型厂“角色一致性”功能正面竞争；护城河在“跨集资产 + 质检”，不在单次生成。
**建议**：不要单独做，合并进机会 1/3。

---

### 不建议做（会被模型迭代掉）

| 方向 | 原因 |
|---|---|
| “保证一次过”的生成器 | 概率生成本质决定；承诺不可信 |
| 30 秒以上长叙事一次成片 | 模型正在快速进步，工具层拼接会被原生能力替代 |
| 让模型精确渲染中文小字/Logo | 字符级监督是厂商主战场；应做后期合成 |
| 通用“AI 视频编辑器” | 剪映/Adobe/Runway 都在做；无中立层优势 |
| 纯“提示词模板”社区 | 低壁垒、易被模型/平台内置 |

---

## ⑥ 证据索引

> 读取日期：2026-11-11。官方页面可能随版本更新；价格为当日挂牌价。

### 6.1 官方能力 / 价格 / 条款

| 编号 | 来源 | URL |
|---|---|---|
| O1 | Runway Dev Pricing（“Prices current as of 2026-11-11”） | https://dev.runway.com/pricing |
| O2 | Runway Dev Models / API docs（per-model request body、无 webhook、临时 URL） | https://docs.dev.runwayml.com/ ; https://dev.runway.com/models |
| O3 | Runway《Handle Task Failures》（SAFETY.INPUT 不退款） | https://docs.dev.runwayml.com/guides/task-failures |
| O4 | Runway status page（50 起事故；Kling/Seedance 故障） | https://status.runwayml.com |
| O5 | Vertex AI Veo 3.1 模型卡（4/6/8s、24fps、4K、音频、C2PA） | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate |
| O6 | Vertex AI Veo pricing（$0.40/$0.20、4K $0.60） | https://cloud.google.com/vertex-ai/generative-ai/pricing |
| O7 | Gemini API Veo 3.1 Preview 关停（2026-10-22） | https://ai.google.dev/gemini-api/docs/video |
| O8 | DeepMind Gemini Omni 1.2（参考、编辑、1080p/4K） | https://deepmind.google/models/gemini-omni/ |
| O9 | Kling API pricing（$500/3250 units、180 天、并发 20） | https://kling.ai/dev/pricing |
| O10 | Runway《Kling 4.0 API》（3–30s、首/中/尾帧、10 图、26k 字符、$0.157/$0.235） | https://dev.runway.com/learn/kling-4-0-api |
| O11 | MiniMax pricing（H3 $0.08/$0.13、输入视频同价） | https://www.minimax.io/pricing |
| O12 | Runway《MiniMax H3 API》（5–15s、12 参考、$0.10/$0.15） | https://dev.runway.com/learn/minimax-h3-api |
| O13 | Luma pricing（Ray3.2 credits、HDR、1080p） | https://lumalabs.ai/pricing |
| O14 | Luma Ray3 页面（角色参考、关键帧、HDR/EXR） | https://lumalabs.ai/ray3 |
| O15 | Pika H3 Flex（3–15s、4K、24fps、32kHz、12 参考、开放权重、$0.07/$0.16） | https://pika.art/pika-h3-flex |
| O16 | Pika pricing（plans、credits、commercial license） | https://pika.art/pricing |
| O17 | Runway《Wan 3.0 API》（2–30s、30fps、20 参考、$0.05–$0.28） | https://dev.runway.com/learn/wan-3-0-api |
| O18 | Alibaba Wan 3.0 页面（30s、多参考） | https://wan.video/ |
| O19 | HunyuanVideo-1.5 GitHub（8.3B、14GB、75s/4090） | https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5 |
| O20 | HunyuanVideo LICENSE（EU/UK/韩国排除） | https://github.com/Tencent-Hunyuan/HunyuanVideo/blob/main/LICENSE.txt |
| O21 | Wan 2.2 GitHub（Apache 2.0、80GB/24GB、<9min） | https://github.com/Wan-Video/Wan2.2 |
| O22 | Midjourney Video 文档（5s、SD/HD、参数） | https://docs.midjourney.com/hc/en-us/articles/37460773864589-Video |
| O23 | Midjourney Comparing Plans（$10/$30/$60/$120；视频并发 1/3/6/12；队列 10） | https://docs.midjourney.com/hc/en-us/articles/27870484040333-Comparing-Midjourney-Plans |
| O24 | Midjourney ToS（>$1M 营收需 Pro/Mega；不保证稳定性） | https://docs.midjourney.com/hc/en-us/articles/32083055291277-Terms-of-Service |
| O25 | LTX-2 GitHub（LTX-2.5、4K 24fps、音频、开放权重） | https://github.com/Lightricks/LTX-2 |
| O26 | LTX-2.x Community License（$10M 阈值） | https://github.com/Lightricks/LTX-2/blob/main/LICENSE-2_x |
| O27 | LTX pricing（Studio $15/$35/$125） | https://ltx.studio/pricing |
| O28 | HeyGen usage limits（并发 10/20、burst +50、429） | https://developers.heygen.com/docs/usage-limits |
| O29 | HeyGen pricing（$29/$49/$149） | https://www.heygen.com/pricing |
| O30 | Synthesia pricing（$19/$89） | https://www.synthesia.io/pricing |
| O31 | Synthesia API errors（429/402） | https://developers.synthesia.io/docs/errors |
| O32 | OpenAI Help Center《Sora discontinuation》（2026-04-26 / 2026-09-24） | https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation |
| O33 | OpenAI Sora 2 发布页（“As of April 26, 2026, the Sora product is no longer available.”） | https://openai.com/index/sora-2/ |
| O34 | Runway《Seedance 2.5》catalog（30s、480/720/1080、参考预算） | https://dev.runway.com/models |
| O35 | Higgsfield pricing（$19/$35/$65） | https://higgsfield.ai/pricing |

### 6.2 开发者一手证据（GitHub / HN）

| 编号 | 来源 | URL | 日期 |
|---|---|---|---|
| G1 | lumaai-python #153：`generations.list()` 稳定 500 | https://github.com/lumalabs/lumaai-python/issues/153 | 2025-04-19 |
| G2 | ComfyUI-WanVideoWrapper #680：3090 加载 14B 必 OOM | https://github.com/kijai/ComfyUI-WanVideoWrapper/issues/680 | 2025-06-21 |
| G3 | HunyuanVideo #152：3090 544×960×81 帧约 30 分钟；100 帧 38 分钟 | https://github.com/Tencent-Hunyuan/HunyuanVideo/issues/152 | 2024-12-25 |
| G4 | HN：Self-hosted gateway for video generation APIs | https://news.ycombinator.com/item?id=45512871 | 2025-10-08 |
| G5 | HN：VideoRouter“同模型不同渠道价差 5–10×” | https://news.ycombinator.com/item?id=49667080 | 2026-09-11 |
| G6 | HN：ai-video-creator 统一 API skill | https://news.ycombinator.com/item?id=47764596 | 2026-04-14 |
| G7 | OpenAI Community：8s 生成 87% 失败，$4 照扣 | https://community.openai.com/t/sora-2-api-charges-money-on-failed-run-at-100-progress/1361332 | 2025-10-07 |
| G8 | OpenAI Community：预生成审核拦截也扣 credits | https://community.openai.com/t/credits-charged-for-pre-compute-moderation-blocks/1365628 | 2025-11-08 |
| G9 | r/n8n：KIE 转售 Sora 故障 15 天，客户流失 | https://www.reddit.com/r/n8n/comments/1rpo4l7/sora_2_on_kie_ai_broke_my_work_need_a_new_tool/ | 2026-03-10 |
| G10 | r/OpenAI：Sora 停服后 31/70 个聚合页仍列 Sora | https://www.reddit.com/r/OpenAI/comments/1wsf2ih/the_sora_api_was_due_to_shut_down_sept_24_i/ | 2026-09-28 |
| G11 | r/runwayml：Unlimited 队列从 20 分钟涨到 1 小时+ | https://www.reddit.com/r/runwayml/comments/1t71pm3/brutal_throttling/ | 2026-05-08 |
| G12 | r/generativeAI：Loova Max 排队 6–10h/12–24h | https://www.reddit.com/r/generativeAI/comments/1u3o9cc/my_loova_max_annual_experience_unlimited_queued/ | 2026-06-12 |
| G13 | r/VEO3：Fast 模式“unusual activity”失败，被迫花 credits | https://www.reddit.com/r/VEO3/comments/1t6zp65/constant_we_noticed_some_unusual_activity_errors/ | 2026-05-08 |
| G14 | r/leonardoai：10–15k credits 失败不退款 | https://www.reddit.com/r/leonardoai/comments/1vkztv5/no_refunds_for_videos/ | 2026-08-10 |
| G15 | r/generativeAI：25fps 交付遇到模型 24fps，音画/时间线全乱 | https://www.reddit.com/r/generativeAI/comments/1t67zac/25_fps_users_how_are_you_dealing_with/ | 2026-05-07 |
| G16 | r/premiere：AI 片段长度与时间线不匹配 | https://www.reddit.com/r/premiere/comments/1qec88n/upscaled_ai_clip_does_not_match_the_original_clip/ | 2026-01-16 |
| G17 | r/VideoEditors：AI 剪辑只能粗剪，修订/交付不行 | https://www.reddit.com/r/VideoEditors/comments/1w7achv/can_you_actually_use_ai_editing_on_paid_client/ | 2026-09-04 |
| G18 | r/KlingAI_Videos：引述 Kling ToS 4.6 限制商用 | https://www.reddit.com/r/KlingAI_Videos/comments/1l7wkpy/who_owns_the_output_is_it_copyrighted/ | 2025-06-10 |
| G19 | r/GeminiAI：Flow 付费生成仍带 Veo 水印 | https://www.reddit.com/r/GeminiAI/comments/1v0t7i8/google_ai_pro_veo_watermark_can_paid_users_remove/ | 2026-07-19 |
| G20 | r/Freepik_AI：Kling 3.0 通过 Freepik 全部卡住 | https://www.reddit.com/r/Freepik_AI/comments/1qxm1c6/kling_30_working/ | 2026-02-06 |

### 6.3 中文社区一手证据（摘自 `research_videogen_cn.md`）

| 编号 | 来源 | URL | 日期 |
|---|---|---|---|
| C1 | 界面新闻《那个下午，我变成了一个「缝合怪」导演》 | https://m.jiemian.com/article/14095484.html | 2026（未标日） |
| C2 | NodeSeek：1 分钟成片 28 元 + 排队 | https://www.nodeseek.com/post-30155-1 | 2026-06-28 |
| C3 | 什么值得买：剪映对口型 6 条废片、1080 积分不退 | https://post.smzdm.com/p/a5rxo6x7/ | 2026-10-17 |
| C4 | App Store 即梦评论：翻倍涨价、排队一天、积分不退 | https://apps.apple.com/cn/app/id6503676563?see-all=reviews | 2026-05-11 |
| C5 | V2EX：第三个镜头开始换人、忘了哪个模型跑的 | https://www.v2ex.com/t/1248756 | 2026-10-14 |
| C6 | linux.do：三视图垫图，多参考图就废 | https://linux.do/t/topic/3104358 | 2026-11-01 |
| C7 | V2EX：即梦会员排队 9 小时 / 3 小时 | https://www.v2ex.com/t/1194838 | 2026-02-28 |
| C8 | linux.do：Seedance 2.0 排队 8–12 小时、排名会倒退 | https://linux.do/t/1700553 | 2026-03-06 |
| C9 | 腾讯新闻：10 秒镜头排 48 小时 | https://news.qq.com/rain/a/20260518A082X800 | 2026-05-18 |
| C10 | 刘盛雄：4 天改 7 轮、2400 元商单 | https://liushengxiong.com/zh/post/4-tian-gai-le-7-lun-zhong-yu-jiao-fu-le-2400-yuan-ai-shipin-shang-dan/ | 2026-06-30 |
| C11 | imai.lol：180 条商品片仅 19 条可直接上架（10.6%） | https://www.imai.lol/ai-video-generation-ecommerce-product-benchmark/ | 2026-10-29 |
| C12 | 财联社：Seedance 排队、会员倒卖、翻倍续费 | https://www.cls.cn/detail/2296174 | 2026-02-26 |
| C13 | TVLab：客户改 9 轮、整段重抽 | https://ask.tvlab.ai/questions/10010000000001228 | 2026-11-04 |

### 6.4 证据缺口（明确不编）

- Sora 2 的历史规格（分辨率/fps/参考输入）未在停服后官方页面保留，本报告不列具体数字；只把它作为“停服风险”案例。
- Luma 每 credit 的美元价、LTX API 单价、Synthesia 具体并发数、Higgsfield 是否有公开 API：官方页面未给出，标“未确认”。
- Kling 4.0 的 fps、商用授权细则：官方 API 页面未给出，标“未确认”。
- HunyuanVideo 1.5 是否沿用旧版“EU/UK/韩国排除”条款：未逐条核验，文中明确标注。
- Discord/私域群的一手反馈未纳入（无法公开检索/引用）。

---

# 七、广告场景专项（2026-11-11 增补）

> 本节把范围从“AI 视频生成”收窄到“AI 生成广告素材 / 投放创意”。新增证据编号 O36–O72、G21–G33、C14–C26；所有价格、配额、政策均以官方页面为准，查询日 **2026-11-11**。官方页面未写的，标“未确认”，不做推算。

## 7.0 先给结论

1. **广告场景的瓶颈已经不在“能不能生成一条视频”**。对 UGC 口播、图文快剪、数字人讲解这类主流效果广告，模型能力已够用；真正卡住投放团队的是**批量变体、跨平台适配、审核前置、素材版本/归因、肖像与版权**这五件事。
2. **平台政策在 2026 年明显收紧**：TikTok 把“AI 生成/合成/操纵媒体”的广告免责声明列为**强制**；Google 从 2026 年 7 月起支持 AI 标签，欧盟/印度/纽约有法定披露要求，并在欧盟、印度、纽约、加州、韩国、越南显示广告上的可见 overlay；Meta 用 C2PA 自动识别并打“AI info”，特定地区还要求广告主自披露。合规从“法务边缘事项”变成“投放前必须过的工序”。
3. **“产品真实还原”仍是模型能力问题**，短期无解；**“合规、版本、审核、归因”是工程/工作流问题**，可产品化。两者不要在同一个产品里混为一谈。
4. 最值得做的不是“又一个 AI 广告生成器”，而是**广告素材的合规预检 + 跨平台版本/审核/归因层**；其次是**带成本上限和本地化的批量生成网关**。

## 7.1 广告素材/投放创意工具：官方能力、价格、API 与导出

| 工具 | 类型与核心能力 | 官方价格（查询日 2026-11-11） | 批量/本地化 | API | 导出/平台适配 | 商用/授权 | 证据 |
|---|---|---|---|---|---|---|---|
| **Creatify** | URL→视频广告、AI Avatar（Aurora）、Boreal 视频模型、Ad Clone、模板、HTML 互动广告；面向电商/效果广告 | 自助 $10/55 credits、$38/280、$66/730；高阶 1,500–6,100 credits；**credits 2 个月过期（未用可再滚 1 个月）**；免费版带水印 | 单条最长 2–10 分钟（按档）；多模型 Playground；本地化能力未在定价页量化 | 有 REST API；API 单独订阅 **$99/500 credits、$299/2,000 credits**；URL→Video 5 credits/30s、Boreal-H3 0.13–0.53 credits/s | 输出视频；具体比例/编码未在定价页列明（未确认） | 未确认（按订阅条款） | O36、O37、O38 |
| **Arcads** | 1,000+ AI Actors、自定义 Avatar、UGC 口播、Veo/Seedance/Kling 多模型、翻译/换角/口型 | 套餐 8,000/16,000/48,000/96,000/192,000 credits；**美元价未公开（应用内显示）**；Starter/Creator 不滚存，Pro 及以上全额滚存；失败自动退 credits | 800 credits/条 2 分钟口播；Veo 3.1 8s=800；Seedance 2.5 5s=210/520；Translate 240/30s/语言 | 有 external API：`/v2/videos/generate`、webhook、credits 查询 | 视频输出；面向 Meta/TikTok UGC 投放 | 未确认（按订阅条款） | O39、O40 |
| **Icon** | 人类 UGC 广告（明确“no AI / 100% real”）+ Admaker 2.0（brief、剪辑、Adspy、Creative Library、一键 Meta 发布） | **$1,000/6 条人类 UGC**（2 creators × 3 ads）；12–16 天交付；先审 6 个脚本再付款；不满意全额退款 | 人类拍摄，不适合日更批量；无多语言批量证据 | **IconAPI** 仅 Agency Whitelabel，量价定制 | 人类成片；一键发布到 Meta；其他平台未确认 | 最终广告、原始素材、B-roll 归客户，含 full usage rights | O41 |
| **Pencil** | AI 营销 OS：文本/图片/视频/广告创意 Agent、性能评分、投放/追踪；面向品牌与代理 | Core **$14/月 50 generations**；Growth **$55/月 250**；Pro 定制/不限量；**generations 不滚存**；Auto Resize 每格式 1 credit | 支持 40+ 语言文本；一次生成多比例 1:1、9:16、4:5、16:9、1.91:1；批量 feeds（Pro） | **无公开生成 API**；提供 Meta/Google/YouTube/DV360/TikTok/LinkedIn 广告账户连接 | 可直接导出到广告账户或下载印刷/数字格式 | Pro 含 IP assignment、“no train”、indemnification；Core/Growth 未确认 | O42 |
| **AdCreative.ai** | AI 图片/横幅/UGC 视频、品牌套件、竞品洞察、Ad Creative Insight；偏静态素材 | Starter **$39/20 credits/1 brand**（$89/50/2、$139/85/2、$189/120/2）；Pro **$249/300 credits/10 brands**（$339/450、$400/600）；Ultimate **$999 起** | credits 制；品牌数受限；批量与本地化未在定价页量化 | 有 REST API（生成、进度、编辑、下载）；**必须先配置 webhook/RabbitMQ 通知通道，否则拒绝生成** | 图片/横幅下载；广告平台集成 | 未确认 | O43、O44 |
| **AdGen** | 产品 URL/图片→10 张广告图（9:16+1:1），含 headline/primary text/CTA；同名产品多，本节取 tryadgen.me | **$29/50 assets、$79/150、$199/500**；年付 10× 月付；Starter 含 commercial rights | 每 pack 10 张、3 个 angle；**仅图片，不做视频**；API 仅 Agency 档 | Agency $199 档含 API | 下载 9:16/1:1/4:5；面向 Meta/IG/TikTok | Starter 明确含 commercial rights | O45 |
| **HeyGen** | 数字人视频、翻译、口型同步、批量；广告口播/本地化常用 | Creator $29/600 credits、Pro $49/1,000、Business $149/1,500 | 批量 100 条；翻译/多语言；25fps；单场景 30 分钟；4K（Pro） | v3 API + **webhook** + 批量状态查询 | MP4；多比例未确认 | 商用按订阅；需肖像授权 | O28、O29 |
| **Synthesia** | 企业数字人视频、翻译、交互头像；强合规/审计 | Starter $19/1,250 credits、Creator $89/6,000；Enterprise 定制 | 企业批量/多语言；具体并发未确认 | v2 Video API；429 `concurrency_limit`/`rate_limited`、402 `quota_exceeded` | MP4；企业分发 | 商用按订阅；企业合规强 | O30、O31 |
| **Captions** | AI 演员/数字分身、AI 剪辑、批量短视频、配音/字幕；Mirage Avatar X | Max **$24.99/月 500 credits**；Frontier **$69.99/月 1,400 credits**；Tesseract 企业定制 | 批量把长视频切成多条；AI Actors；多语言未量化 | **Mirage API**：Avatar X **$0.15/s**（6s 取整）、字幕 $0.15/min；**视频生成仅 2 RPM/组织** | MP4；9:16 等社媒比例 | 未确认 | O46、O47 |
| **Meta Advantage+ creative** | 平台内建 AI 增强：Add animation、AI music、overlays、video effects、background generation、text generation（最多 5 组）、translations、video subtitles、video touch-ups（裁/扩到 9:16/4:5） | 无单独工具费（随广告投放）；具体资格按账户/地区 | 自动生成多版本；可按版位扩展比例；翻译/字幕 | 平台内建；Marketing API 可建 creative，生成式增强的 API 覆盖未确认 | 直接在 Meta 版位投放 | 受 Meta 广告条款与 AI 标签约束 | O48 |
| **Google Performance Max 素材生成** | 输入 URL → 生成/建议 headline、description、图片、logo、视频；无视频时自动生成视频；支持人物/面部（仅成人） | 无单独工具费（随投放）；生成式 AI 逐步全球开放，敏感类目/URL 不适用 | 文本资产语言**跟随落地页语言**；图片 1.91:1/1:1/4:5；视频 16:9/1:1/9:16，≥10s | 平台内建；Google Ads API 可上传 asset，生成接口未确认 | 直接进入 PMax asset group | **生成资产不保证过审**；受 Google Ads 政策约束 | O55、O56 |
| **TikTok Symphony / Smart+** | Symphony Creative Studio：产品信息→TikTok 原生视频、2,000+ 数字人、翻译/配音/口型、脚本、图生视频、字幕移除、Refresh ads；Smart+：自动组合、最多 50 个 asset group、Recommended Creatives、Automatic Enhancements（resize/画质/翻译/配音） | 无单独公开定价（随投放；未确认）；Smart+ 部分功能需账户资格 | 批量合成；多语言数字人/配音；按 creative material ID 出报表 | **Symphony API**（视频生成、Avatar、Dubbing、脚本、图生视频等；需申请，文档在 Lark）；Smart+ 走 Ads API | 9:16 原生；自动扩展版位 | 受 TikTok 广告政策与 AI 免责声明约束 | O60、O61、O62 |

**读表要点**

- **“便宜”与“可批量”不是一回事**：Captions API 视频生成只有 **2 RPM/组织**，意味着 50 条变体光排队就至少 25 分钟；TikTok `/ad/create` Basic 档 5 QPS、`/creative/smart_video/create` 仅 1 QPS/30 QPM/5,000 QPD（O69）。批量投放的真实瓶颈在**平台侧配额**，不在模型单价。
- **“生成”与“投放”仍是两套系统**：Creatify/Arcads/Captions 生成 MP4，Pencil/Icon 能直接接广告账户；多数工具不返回平台审核状态，也不把“素材 ID—广告 ID—花费/CPA”打通。
- **人类 UGC 仍是价格锚**：Icon $1,000/6 条 ≈ **$166.7/条**，12–16 天；AI 口播可做到几美元到几十美元一条，但下面 G21–G33 的一手反馈说明“像 AI”会直接吃掉效果。

## 7.2 平台政策约束：AI 披露、标签与审核

### 7.2.1 Meta：自动“AI info”+ 特定地区自披露，不是所有广告一刀切

- Meta 会对**使用 Meta 生成式 AI 工具**（Background Generation、Image Generation、Add Animation 等）或**第三方生成式 AI 工具**创建/显著编辑的广告，自动打 **AI info** 标签；第三方内容通过 **C2PA** 等元数据识别。标签在广告三点菜单的“About this ad”里，由 Meta 自动施加，广告创建流程会提前提示（O49）。
- 在**欧洲区域、加州、纽约、印度、台湾**等地区，Meta 会给广告主**自披露**生成式 AI 使用的机会；若自披露，标签显示在广告旁。台湾/韩国若检测到 Meta GenAI 工具生成的 photorealistic 人物，也可能自动加标（O49）。
- **社会议题/选举/政治广告**是另一套硬要求：只要包含 photorealistic 的 AI 生成/编辑人物、事件或真实声音，**必须**在 Ads Manager 披露；该要求单独成页（O49 页面明确链接到 SIEP 专页，O50）。
- 被拒广告可在 Business Support Home 申诉；Meta 目标 **48 小时内**给结果；重复/严重违规可能限制账户（O51）。
- **对广告主的含义**：普通商品广告没有“所有 AI 素材都必须手动勾选”的统一开关，但**自动标签已经发生**；在欧盟/加州/纽约/印度/台湾做投放，自披露与本地法规要单独配置。靠“去掉 C2PA 元数据”规避标签，属于高风险做法，不建议产品化。

### 7.2.2 TikTok：广告侧对 AI 合成媒体是**强制免责声明**

- TikTok Ads Manager 的广告免责声明分为 suggested / mandatory；**mandatory 明确包括 AI-generated、synthetic、manipulated media**（完全 AI 生成，或真实素材被 AI 显著修改）。广告主需使用 **AI-generated content disclaimer**，在 in-feed 视频底部显示标签（O63）。
- 自然内容侧：使用“AI-generated content”开关后，视频会显示“Disclosed by creator as AI-generated”；**标签发布后不能编辑/移除**；未披露的 AI 内容可能被下架（O64）。
- TikTok Shop 的 AIGC 规则更细：禁止用 AI 伪造商品效果/尺寸/材质/数量/功能、禁止未经授权模仿他人身份/声音、禁止虚假“专家”背书；要求对完全/显著 AI 生成内容主动披露（O65）。
- 广告审核通常 **24 小时内**；修改 creative 会触发重审；被拒可编辑或走 Advertiser Support 申诉（O66）。官方列出的常见拒因包括：**知识产权未授权、创意与落地页不一致、夸大/无法证明的效果**（O67）。
- **对广告主的含义**：TikTok 是三大平台里对“AI 广告”披露最硬的——不是“建议”，是**mandatory**。批量生成工具如果不自动带上免责声明/标签，投放端就要人工补，规模一大必漏。

### 7.2.3 Google Ads：2026 年 7 月起 AI 标签区域化强制，生成资产不保证过审

- 2026 年 7 月起，Google 允许在图片/视频创意中直接加文字/视觉 AI 标签，也提供 **AI label setting**；带标签的资产会在 My Ad Center 的“How this ad was made”里披露。欧盟、印度、纽约的法规要求此类披露；**欧盟、印度、纽约、加州、韩国、越南**的投放还会在广告上显示**可见 overlay**（O53、O54）。
- 标签一旦由 Google 施加（例如法律要求或跨平台信号），**不能被覆盖**；使用 Google 全自动素材生成时，Google 可能代广告主加标签（O54）。
- 选举广告仍需在 campaign 设置里勾选“Altered or synthetic content”（O53）。
- PMax 生成式 AI 会从 URL 生成 headline/description/图片/logo/视频；没有视频时可能自动生成视频；**生成资产不保证通过 Ads Policy**，可能因与其他资产组合或当地法规被拒（O55、O56）。
- 被拒广告可在 Policy Manager 查看原因、修改后重审或申诉；**每条广告最多 3 次申诉**，同一广告重复申诉需间隔 24 小时；2026-07-21 起超过 6 个月的旧决定不能再直接申诉（O57）。
- **对广告主的含义**：Google 的标签是“区域化合规 + 资产级元数据”问题；同一个素材投不同国家，可能需要不同标签策略。PMax 自动生成视频还会带来“素材来源不可控”的审计问题。

### 7.2.4 三大平台共性拒因（广告场景）

| 类别 | 典型表现 | 平台依据 |
|---|---|---|
| **未披露 AI/合成媒体** | TikTok 广告缺 mandatory AI disclaimer；Google 在强制标签地区无标签；Meta 政治/选举广告未勾选 | O63、O54、O50 |
| **虚假/夸大效果** | 护肤品“瞬间去皱”、清洁剂“一秒除锈”、AI 生成不可能的产品效果 | O65、O67 |
| **创意与落地页不一致** | 视频里是 A 产品，落地页是 B；折扣/价格/规格不一致 | O67、O57 |
| **知识产权/肖像侵权** | 未授权品牌、音乐、影视片段；AI 模仿真人声音/面孔 | O65、O67 |
| **landing page 问题** | 打不开、不可抓取、destination mismatch | O57 |
| **受限行业/地区** | 金融、健康、政治、赌博等特殊类目缺资质/本地许可 | O57、O50 |

## 7.3 广告主/开发者集成痛点（P0-A1～P0-A7）

### P0-A1 批量变体：平台配额比模型价格更早卡死

- Captions Mirage API 的视频生成限额是 **2 RPM/组织**（O47）；50 条变体至少 25 分钟，且这还只是“提交请求”，不含生成与失败重试。
- Pencil Core/Growth 每月 **50/250 generations**，用完只能升级或等下月，**不滚存**；Auto Resize 每新增一个格式再扣 1 credit（O42）。
- Arcads Starter 8,000 credits，按 800 credits/条 2 分钟口播算，**一个月约 10 条**；Pro 才滚存（O39）。
- Creatify credits **2 个月过期**；API Starter 500 credits，URL→Video 5 credits/30s，约 **100 条 30 秒视频**（O36、O37）。
- TikTok `/ad/create` Basic 档 **5 QPS、150 QPM、86,400 QPD**；`/creative/smart_video/create` 仅 **1 QPS、30 QPM、5,000 QPD**（O67）。
- 批量工作流本身也不稳：AI UGC 工具“通常很快，但忙的时候会彻底爬行或卡住，口型质量每次渲染都时好时坏”（G31，r/AI_UGC_Marketing，2026-06-25）；Arcads 被吐槽“里面没有编辑器，所以没有字幕、音乐……”（G32，同帖）。
- 更隐蔽的是“生成 50 条，没人检查”：投放者说“人们用 AI 喷出 50 个变体，但在花钱之前没人确认每个是否真的成立”（G30）。
- 国内千川侧的另一面：有投放者“刚用 AI 工具批量生成了 200 条素材，投进去跑了 8 小时，消耗不到 50 块”（C15）——不是产能不够，是**素材跑不出去**。
- **结论**：做“一次生成 100 条变体”的产品，必须把**平台配额、credits 过期、失败退款、并发上限**纳入调度；否则 demo 很顺，一上量就排队/超预算。

### P0-A2 多语言本地化：文本能翻，不等于广告能投

- Pencil 支持 **40+ 语言**的文本生成（O42）；TikTok Symphony 支持 2,000+ 数字人、翻译/配音/口型（O60）；Meta 有 translations、video subtitles（O48）；Google PMax 的文本资产语言**跟随落地页语言**，要换语言得换落地页（O55）。
- 真正的坑在**市场合规与创意适配**：同一句“疗效/最低价/第一”在不同国家是不同监管；9:16 的口播节奏、字幕长度、货币/促销节点都要改。工具只给“翻译”，不给“本地化合规”。
- 卖家侧的原话更直接：“AI 翻译能解决字幕，但解决不了口型、俚语和当地场景，东南亚用户一眼看出是‘中国视频换了张皮’”（C21，访谈转述，证据等级 C）。
- **产品机会**：把“语言/市场/品类”作为三维规则表，生成前做 claim 替换、字幕长度检查、禁用语检查；这不是模型能力，是规则工程。

### P0-A3 素材版本/A-B：平台各有一套 ID，生成侧没有“素材谱系”

- TikTok Smart+ 已支持按 **creative material ID**（video/image/catalog/text）出创意级报表，并自动组合高效素材（O61）；Google PMax 按 asset group/asset 组织素材（O56）；Meta Advantage+ 会自动生成/增强多版本（O48）。
- 但生成工具（Creatify/Arcads/Captions 等）输出的是 MP4/图片，**不保证保留“父素材—变体—平台广告 ID”的映射**；一旦平台自动 resize/翻译/加音乐，素材谱系就断了。
- 结果：复盘时只知道“这条 CPA 低”，不知道“它是哪个 script/actor/voice/模型/版本的哪一个变体”；下次无法复现。
- 国内品牌侧已经出现“审核过一份原稿，不能保证看过所有投放版本”的问题（C14）；同时模板台词被 6–8 个品牌反复复用，AI 批量素材“长得都一样”（C20）。
- **产品机会**：以“广告素材图（asset graph）”为核心，记录 script→shot→render→variant→platform ad ID→spend/CPA；平台自动增强也要回写。

### P0-A4 广告平台 API 对接：三套限流、三套审核状态、三套错误码

- **Meta Marketing API**：按 ad account 计分，读 1 分/写 3 分；开发档最大 **60 分**、Full access **9,000 分**，300 秒衰减，触顶封 **300 秒/60 秒**；mutation 另有 **100 QPS/ad account/app**，同一对象编辑 **30 秒 1 次**；错误码 17/613 及子码（O52）。
- **TikTok Ads API**：应用级 Basic **10 QPS/600 QPM/864,000 QPD**；超限返回 **40100**，QPM 超限需等 **5 分钟**，QPD 超限等次日 UTC 0 点；`/ad/create` 5 QPS，creative 生成 1 QPS（O69）。
- **Google Ads API**：OAuth2 + developer-token + login-customer-id；PolicySummary 返回 `approval_status`、`policy_topic_entries[]`、`review_status`；申诉每条广告最多 3 次、间隔 24 小时（O58、O59、O57）。
- **结论**：跨 Meta/TikTok/Google 的投放工具，必须做**统一队列、令牌桶、指数退避、幂等键、审核状态机**；这不是“接个 API”能解决的。

### P0-A5 审核前置：平台不给你“预审沙箱”

- Meta 被拒后只能改/申诉，目标 **48 小时**给结果；编辑/删除被拒广告不会消除违规记录，严重或重复违规可能限制投放（O51）。
- Google 明确说，生成式 AI 产出的资产**不保证过审**，可能因资产组合或当地法规被拒（O55）。
- TikTok 广告审核通常 24 小时，修改 creative 会触发重审；官方公开的是审核 FAQ 与最佳实践，未发现可编程的预审接口（O66、O70）。
- **现状**：团队只能靠“人肉经验 + 被拒后复盘”。英文投放侧的原话：纯 AI 口播素材被拒时，“Meta 除了‘违反政策’之外不给清晰解释”（G26，r/FacebookAds，2025-12-09）；有人总结出“全 AI talking-head 会被当作 manipulated media 标记，混入几个真实镜头、把独白打断、控制在 10–12 秒内通常能过”（G27，同帖，属投放者经验而非平台规则）；也有人改成两个机位交替后过审（G28，2025-12-10）。
- 国内一线更直观：“凌晨一点，投手老周盯着后台发懵：三条正跑量的 AI 数字人素材，被复审拦下直接停投。计划断档、消耗归零。”（C16，公众号，证据等级 B）；“投放素材一被拒，跑量直接断流，预算冻在账户里。”（C23）
- 审核人力也跟不上：“一条 AI 广告几块钱，谁会花几十块钱请人审核？”（C24）——当生成成本降到几块钱，人工审核反而成了最贵的一环。英文侧同样：“审片和挑最好的版本，可能比写一个扎实脚本、找 2–3 个好 UGC 创作者更耗时”（G33）。
- 这就是为什么“审核前置”是一个独立产品，而不是生成器的附属功能。

### P0-A6 归因与性能反馈：创意级报表有了，生成侧闭环没有

- TikTok Smart+ 已能按 creative material ID 看表现（O61）；Meta/Google 也有创意/资产级报表。但多数生成工具**不消费**这些数据，只负责“生成更多”。
- 结果是“生成—投放—复盘—再生成”靠人拉 Excel；哪些 script/actor/voice 真正带来 CPA 改善，无法自动回到生成策略。有投放者指出，应该“按 argument（论点）层级读表现，而不是只按文件层级读”，否则会误判“广告死了”而盲目再发一版（G29）。
- 隐私与同意（尤其欧盟）让跨平台归因更碎；工具若承诺“自动优化”，需要明确数据来源与合法性。跨境场景里，归因/合规出问题可以直接导致“账号被直接关闭……最终损失约 15 万美金”（C18）。
- 只看点击/下单也不够：“测试一批 AI 素材时，除了比较点击率和下单成本，还应追踪退款、投诉及复购；评估口碑，则需要另设消费者调查，不能拿点击率代替。”（C25）
- **产品机会**：把平台报表拉回素材图，做“创意特征→表现”的归因，再反哺生成；这是广告场景相对通用视频工具的真正差异化。

### P0-A7 肖像/版权/授权链：AI 广告的“隐形炸弹”

- TikTok 明确禁止未经授权模仿他人身份、 likeness、声音；禁止虚假专家背书（O65）；广告拒因也列了 IP 未授权（O67）。
- Meta 对政治/选举广告要求 AI 披露，并用 C2PA 自动识别第三方 AI 内容（O49、O50）。
- 数字人平台（HeyGen/Synthesia/Captions/Arcads）都要求肖像授权，但**授权范围（期限、地区、品类、二次剪辑、跨平台）**通常散落在合同/上传条款里，批量生成时很难逐条追踪。
- 商品侧也一样：分销/代运营用 AI 素材挂别人的商品链接，出现“他们觉得发自己账号上想咋弄咋弄，但链接挂的是我的商品啊”（C17）；还有消费者对 AI 面膜广告的直接反应——“太假了，这面膜广告的效果，一惊一乍的”（C19）。
- **产品机会**：素材级“权利台账”（model release、音乐/字体/品牌授权、AI 模型商用条款、地区限制），并与投放账户/地区绑定；这比“生成质量提升 10%”更能阻止下架/索赔。

## 7.4 广告场景下的“模型能力 vs 工程/工作流”判断

| 问题 | 归类 | 广告场景判断 |
|---|---|---|
| 产品颜色/材质/logo/文字在生成中失真 | **模型能力** | 短期无解；对美妆、服饰、3C、食品等“产品即卖点”的品类是硬伤，不能靠工作流绕过 |
| 同一演员/同一场景跨镜头不换脸 | **模型能力** | 多镜头一致性仍不稳定；广告需要“同一个人讲 3 个卖点”，比单条炫技更难 |
| 多语言口型/语气/文化梗 | **模型能力+数据** | 翻译容易，口型与本地表达难；小语种质量差距大 |
| 手部/产品交互/使用演示 | **模型能力** | 仍容易穿模；产品演示类广告不宜全 AI |
| 9:16 裁切/版位扩展 | **工程** | Meta/Google/TikTok 都有自动扩展，但会裁掉卖点/字幕；需要按版位重排，不是简单 resize |
| 批量变体/成本上限/失败重试 | **工程** | 平台配额、credits 过期、2 RPM 等都能通过调度/预算层解决 |
| 审核前置/申诉/标签 | **工程+规则** | 可产品化；但平台不透明，需要持续维护规则库 |
| 素材版本/AB/归因 | **工程** | 最大空白；平台报表已具备，缺的是跨平台素材图与回流 |
| 肖像/版权/商用授权 | **工程+法务** | 可产品化；需要合同结构化与地区规则 |
| “AI 感”导致信任/疲劳 | **模型能力+创意** | G21–G33 表明观众能识别通用 AI 演员；不是纯技术问题，选角/脚本/真人混剪更关键 |

国内投放侧对素材寿命的描述是“短的三天，长的也就一两周”（C22）；模板台词又被 6–8 个品牌复用（C20）。这意味着**“生成更多”不等于“跑得更好”**，迭代速度与差异化比单条质量更影响结果。

另一个信号：央视市场研究 2026 年对 200+ 家企业营销中高层的调查显示，**94.1% 的广告主已投入 AI 营销，但 60.3% 对成效的评价仍是“一般”**（C26）。采用率很高、价值感很低，缺口正好落在工作流而非“生成”。

**广告场景的单独判断（与通用视频生成分开）：**

- **UGC 口播/图文快剪/数字人讲解**：模型能力已“够用”，竞争点是**合规、批量、版本、归因**。这类需求占效果广告大头，适合工程型产品。
- **产品演示/对比/使用效果**：模型能力仍是瓶颈；AI 生成容易夸大或失真，正好撞上 TikTok/Google 的“虚假效果”红线。短期更适合“真人拍摄 + AI 后期”，而不是端到端生成。
- **品牌 TVC/高质感大片**：模型能力+创意判断都还不够；广告主不会把主视觉交给不可控生成。
- **受监管行业（健康、金融、政治）**：合规权重高于生成质量；产品必须先解决披露、资质、地区限制，否则生成越快越危险。

## 7.5 广告专项机会排序（按“痛点强度 × 可产品化 × 付费意愿”）

### 机会 1（最值得做）：广告素材合规预检 + 权利台账

**做什么**：在生成后、投放前，对每条素材做：
- 平台规则检查：TikTok AI 免责声明、Google 地区 AI 标签、Meta 政治/选举披露；
- 内容检查：产品与落地页一致性、夸大/绝对化用语、健康/金融敏感 claim、未授权品牌/音乐/字体；
- 权利检查：肖像/声音授权范围、AI 模型商用条款、地区限制、到期日；
- 自动写入 C2PA/AI 标签元数据，并生成“投放地区→标签策略”的配置。

**为什么现在**：TikTok 已把 AI 广告免责声明列为 mandatory（O63）；Google 2026-07 起区域强制标签（O53）；Meta 用 C2PA 自动识别（O49）。三件事叠加，合规从“可选”变“必过”。

**谁付费**：代理公司、出海投放团队、MCN、品牌方法务/投放；按素材条数或账户订阅收费。

**壁垒**：规则库 + 平台审核案例库 + 权利合同结构化；不是模型。

### 机会 2（市场最大）：跨平台素材版本/A-B/归因层

**做什么**：一个“广告素材图”系统：
- 统一 asset ID，记录 script→shot→actor/voice→render→variant→platform ad ID；
- 拉取 Meta/TikTok/Google 的审核状态、花费、CPA/ROAS；
- 按 creative material ID/asset 维度做 A/B 与 fatigue 预警；
- 把“哪类脚本/演员/声音/模型赢”反哺生成。

**为什么现在**：TikTok Smart+ 已支持 creative-level reporting（O61），Google 有 asset reporting，Meta 有 Advantage+ 自动变体（O48）；数据基础具备，但工具侧仍是断点。G21–G33 说明“AI 广告疲劳更快”，更需要快速淘汰/迭代。

**谁付费**：中大型投放团队、代理、DTC 品牌；按 ad account/素材量订阅。

**壁垒**：跨平台连接器 + 素材谱系 + 归因模型；比“再做一个生成器”更难被替代。

### 机会 3（现金流好）：带成本上限和本地化的批量广告视频网关

**做什么**：面向 SMB/代理的“广告视频 API 路由器”：
- 接 Creatify/Arcads/Captions/HeyGen/Synthesia/TikTok Symphony 等；
- 统一任务、轮询/webhook、失败重试、credits 余额/过期提醒；
- 按平台规格（9:16/1:1/4:5、时长、字幕安全区）自动出片；
- 按市场做语言/货币/禁用语/claim 替换；
- 硬预算上限，超支熔断。

**为什么现在**：Captions 2 RPM、TikTok creative 1 QPS、Arcads 800 credits/条、Creatify credits 2 个月过期——批量投放的“配额/成本”痛点非常具体（O47、O67、O39、O36）。

**谁付费**：出海 SMB、代理、MCN；按生成条数/订阅。

**壁垒**：多供应商接入 + 配额调度 + 成本优化；容易被上游降价挤压，需要靠工作流/合规增值。

### 机会 4（难度高、潜力大）：产品真实还原的广告生成管线

**做什么**：以商品 catalog 为源，锁定产品颜色/材质/logo/包装，生成“产品演示/对比/使用场景”广告；与真人拍摄或 3D 资产混合。

**为什么难**：产品保真仍是模型能力问题；一旦失真就触发“虚假效果”拒审（O65）。短期更适合“AI 背景/场景 + 真实产品合成”，而不是纯生成。

**判断**：不建议作为第一个产品；可作为机会 1/2 的增值模块，等模型能力再进一步。

### 不建议做

- **“又一个通用 AI 广告生成器”**：Creatify/Arcads/Pencil/AdCreative/Captions 已拥挤，价格战且平台自带生成（Meta/Google/TikTok）。
- **帮客户规避 AI 标签/去 C2PA**：平台明确自动识别、标签不可移除，违规风险高，不是可持续产品。
- **纯“AI 演员库”**：G21–G33 显示观众对通用 AI 演员的信任/疲劳问题；没有选角/脚本/投放闭环，很难差异化。

## 7.6 广告场景证据索引

### 7.6.1 官方工具/平台文档（O36–O67）

| 编号 | 来源 | URL | 查询日 |
|---|---|---|---|
| O36 | Creatify pricing | https://creatify.ai/pricing | 2026-11-11 |
| O37 | Creatify API billing（$99/500、$299/2,000、按 API 计 credits） | https://docs.creatify.ai/billing | 2026-11-11 |
| O38 | Creatify API intro（URL→Video、Avatar、模板） | https://docs.creatify.ai/ | 2026-11-11 |
| O39 | Arcads pricing help（8k–192k credits、800/条、失败退款、滚存） | https://help.arcads.ai/en/articles/17595066-how-does-arcads-pricing-work | 2026-11-11 |
| O40 | Arcads external API（videos/generate、webhook、credits） | https://external-api.arcads.ai/docs | 2026-11-11 |
| O41 | Icon pricing（$1,000/6 人类 UGC、12–16 天、退款） | https://icon.com/pricing | 2026-11-11 |
| O42 | Pencil pricing（$14/50、$55/250、不滚存、40+ 语言、Pro IP assignment） | https://trypencil.com/pricing | 2026-11-11 |
| O43 | AdCreative.ai pricing（$39/20 credits 起、Pro $249/300） | https://www.adcreative.ai/ | 2026-11-11 |
| O44 | AdCreative API（生成/进度/编辑/下载；强制通知通道） | https://api-docs.adcreative.ai/docs/features/adcreative-api | 2026-11-11 |
| O45 | AdGen/tryadgen pricing（$29/50、$79/150、$199/500、API） | https://tryadgen.me/pricing | 2026-11-11 |
| O46 | Captions pricing（$24.99/500、$69.99/1,400） | https://captions.ai/pricing | 2026-11-11 |
| O47 | Captions Mirage API pricing/rate limit（$0.15/s、2 RPM） | https://captions.ai/help/docs/api/pricing；https://captions.ai/help/docs/api/rate-limiting | 2026-11-11 |
| O48 | Meta Advantage+ creative（AI 增强清单） | https://www.facebook.com/business/help/297506218282224/ | 2026-11-11 |
| O49 | Meta AI info 标签（C2PA、自动标签、地区自披露） | https://business.facebook.com/business/help/1009525374368348/ | 2026-11-11 |
| O50 | Meta 政治/选举广告 AI 披露（mandatory） | https://www.facebook.com/business/help/1486382031937045/ | 2026-11-11 |
| O51 | Meta 被拒广告/申诉（48 小时、重复违规限制） | https://www.facebook.com/business/help/www/1210227555661027/ | 2026-11-11 |
| O52 | Meta Marketing API rate limits（60/9,000 分、100 QPS、1 edit/30s） | https://developers.facebook.com/docs/marketing-api/overview/rate-limiting | 2026-11-11 |
| O53 | Google AI labeling（2026-07 起、EU/IN/NY/CA/KR/VN） | https://support.google.com/adspolicy/answer/17257106?hl=en | 2026-11-11 |
| O54 | Google AI label setting（overlay、不可覆盖、SynthID/C2PA） | https://support.google.com/google-ads/answer/17140115?hl=en | 2026-11-11 |
| O55 | Google PMax 生成式 AI 资产（文本/图片/logo/视频；不保证过审） | https://support.google.com/google-ads/answer/14150602?hl=en | 2026-11-11 |
| O56 | Google PMax 资产规格（1.91:1/1:1/4:5；16:9/1:1/9:16，≥10s） | https://support.google.com/google-ads/answer/17091269?hl=en | 2026-11-11 |
| O57 | Google 被拒/申诉（3 次上限、24h、6 个月限制） | https://support.google.com/adspolicy/answer/9338593?hl=en | 2026-11-11 |
| O58 | Google Ads API PolicySummary（approval/review/policy topics） | https://developers.google.com/google-ads/api/reference/rpc/v26/PolicySummary | 2026-11-11 |
| O59 | Google Ads API call structure（OAuth2/developer-token/login-customer-id） | https://developers.google.com/google-ads/api/docs/concepts/call-structure | 2026-11-11 |
| O60 | TikTok Symphony Creative Studio（生成/数字人/配音/剪辑） | https://ads.tiktok.com/creative/creativestudio/home/en | 2026-11-11 |
| O61 | TikTok Smart+（50 asset groups、creative material ID 报表、自动增强） | https://ads.tiktok.com/resources/help/article/about-updates-to-smart-plus | 2026-11-11 |
| O62 | TikTok Symphony API（视频/avatar/dubbing/script/图生视频） | https://ads.tiktok.com/creative/creativeCenter/tools/api | 2026-11-11 |
| O63 | TikTok 广告免责声明（AI 合成媒体 mandatory） | https://ads.tiktok.com/resources/help/article/about-ad-disclaimers-in-tiktok-ads-manager?lang=en | 2026-11-11 |
| O64 | TikTok 自然内容 AI 标签（不可移除、未披露可下架） | https://www.tiktok.com/creator-academy/en/article/ai-generated-content-label | 2026-11-11 |
| O65 | TikTok Shop AIGC 规则（禁止商品失真/冒充/虚假专家） | https://seller-us.tiktok.com/university/essay?knowledge_id=491489038501663 | 2026-11-11 |
| O66 | TikTok 广告审核 FAQ（24h、修改重审） | https://ads.tiktok.com/resources/help/article/ad-review-faq?lang=en | 2026-11-11 |
| O67 | TikTok 广告拒因（IP/一致性/夸大） | https://ads.tiktok.com/business/en-US/blog/common-tiktok-ad-rejection-reasons | 2026-11-11 |

### 7.6.2 广告平台 API/审核补充（O68–O72）

| 编号 | 来源 | URL | 查询日 |
|---|---|---|---|
| O68 | Meta effective_status webhook（审核拒绝/恢复可订阅） | https://developers.facebook.com/documentation/ads-commerce/marketing-api/ads-webhooks/effective-status/ | 2026-11-11 |
| O69 | TikTok Ads API rate limits（Basic 10 QPS/600 QPM/864k QPD；40100） | https://business-api.tiktok.com/portal/docs/rate-limits/v1.3 | 2026-11-11 |
| O70 | TikTok 广告审核最佳实践（语言/媒体/一致性/授权） | https://ads.tiktok.com/help/article?aid=12081 | 2026-11-11 |
| O71 | Google Ads API 速率/配额说明（入口页；具体配额以账户为准） | https://developers.google.com/google-ads/api/docs/start | 2026-11-11 |
| O72 | Meta 广告审核说明（48 小时/申诉；登录后可见） | https://developers.facebook.com/docs/marketing-api/ad-review/ | 2026-11-11 |

### 7.6.3 一手投放反馈（G21–G33 / C14–C26）

| 编号 | 来源 | 原话（保留英文） | URL | 日期 |
|---|---|---|---|---|
| G21 | r/PPC：HeyGen B2B 测试，一周后信任崩塌 | “I tested HeyGen for a B2B client in IT. CTR was decent for the first few days, but dropped visibly after a week. People quickly realize it's AI and trust breaks.” | https://www.reddit.com/r/PPC/comments/1pj88je/is_anyone_actually_seeing_legit_performance_from/ | 2025-12-10 |
| G22 | r/FacebookAds：通用 AI 演员被一眼识破 | “Everyone can see the same re-used generic talking heads from all the popular ai ugc tools and immediately scrolls on it.” | https://www.reddit.com/r/FacebookAds/comments/1mduf7a/is_ai_ugc_working_for_you_or_are_you_seeing/ | 2026-02-21 |
| G23 | r/FacebookAds：AI 素材疲劳快约 30%，同 SKU 真人 ROAS 高 1.8× | “creative fatigue hits AI ads ~30% faster. The same avatar/structure that wins at week 1 burns by week 3-4... we saw 1.8x higher ROAS on retargeting with human vs AI for the same SKU.” | https://www.reddit.com/r/FacebookAds/comments/1rlvjrg/i_tested_ai_ads_vs_human_ugc_with_100k_in_3/ | 2026-03-08 |
| G24 | r/PPC：成功真人脚本换 AI avatar 全扑 | “I tested by using a very successful script from a real person video and had a couple avatars do it... they all flopped. In my opinion they lack some kind of biological charisma/influence element we can pick up on.” | https://www.reddit.com/r/PPC/comments/1lpo9rr/anyone_running_paid_ads_with_aigenerated/ | 2025-07-03 |
| G25 | r/AI_UGC_Marketing：20 秒以上微表情缺失 | “In anything longer than twenty seconds, the lack of micro-expression variation becomes noticeable to attentive viewers... AI visuals with generic music is basically a neon sign saying AI ad.” | https://www.reddit.com/r/AI_UGC_Marketing/comments/1smu3jr/what_i_learned_running_15_ai_ugc_campaigns_the/ | 2026-04-16 |
| G26 | r/FacebookAds：纯 AI 口播被拒，Meta 不给清晰解释 | “The ads contain only AI-generated footage, with an AI person talking continuously throughout the video. No real actors, no UGC. Meta doesn't provide a clear explanation beyond 'policy violation'.” | https://www.reddit.com/r/FacebookAds/comments/1picn8j/ | 2025-12-09 |
| G27 | r/FacebookAds：投放者经验——混真实镜头、打断独白、10–12 秒内更易过 | “meta flags full ai talking-heads as manipulated media, so mix in a few real shots + break the monologue and it normally passes... keep it under 10–12 sec and break the ai talking flow... add 1–2 real b-roll shots or product shots between the ai parts and it usualy passes.” | https://www.reddit.com/r/FacebookAds/comments/1picn8j/ | 2025-12-09 |
| G28 | r/FacebookAds：两个机位交替后过审 | “instead of keeping the camera fixed the whole time on the AI avatar speaking on stage to an audience, I alternated clips from two different angles, and they were approved.” | https://www.reddit.com/r/FacebookAds/comments/1picn8j/ | 2025-12-10 |
| G29 | r/FacebookAds：按 argument 层级读表现，而非文件层级 | “arguments fatigue, not just creatives. read performance at the file level and you think the ad died so you ship another version. read it at the argument lev[el]...” | https://www.reddit.com/r/FacebookAds/comments/1w3siss/ | 2026-09-01 |
| G30 | r/FacebookAds：50 个变体没人检查就花钱 | “people use AI to spit out 50 variations but nobody's checking whether each one actually holds up before it spends... deciding which ones are real and different still takes a human who knows the account.” | https://www.reddit.com/r/FacebookAds/comments/1w3siss/ | 2026-09-01 |
| G31 | r/AI_UGC_Marketing：排队/卡住、口型时好时坏 | “it's usually quick but can totally crawl or get stuck when it's busy, lip-sync quality is hit or miss render to render” | https://www.reddit.com/r/AI_UGC_Marketing/comments/1uf0n09/ | 2026-06-25 |
| G32 | r/AI_UGC_Marketing：Arcads 无内置编辑器 | “there's no editor inside it so no captions, music or...” | https://www.reddit.com/r/AI_UGC_Marketing/comments/1uf0n09/ | 2026-06-25 |
| G33 | r/PPC：审片/挑选迭代比写脚本、找创作者更耗时 | “To make a generated ad feel truly native, you usually need way more iterations - so many that just reviewing and picking the best ones could take longer than writing a solid script, finding 2–3 good UGC creators...” | https://www.reddit.com/r/PPC/comments/1lpo9rr/ | 2025-08-28 |

| 编号 | 来源 | 原话（保留中文） | URL | 日期 |
|---|---|---|---|---|
| C14 | 21经济网/钛媒体：审核原稿≠审核所有投放版本 | “开启相关功能后，品牌面对的已经是一批不断组合、调整的内容，审核过一份原稿，不能保证看过所有投放版本。” | https://www.21jingji.com/article/20261013/herald/74acb1021d33e1ff06a9b3d5a38aac55.html | 2026-10-13 |
| C15 | 有米云：200 条 AI 素材，8 小时消耗不到 50 元 | “他刚用 AI 工具批量生成了 200 条素材，投进去跑了 8 小时，消耗不到 50 块。” | https://www.youcloud.com/blog/3648/ | 2026-08-28 |
| C16 | 微信公众号“千川研习社”：复审停投，计划断档 | “凌晨一点，投手老周盯着后台发懵：三条正跑量的 AI 数字人素材，被复审拦下直接停投。计划断档、消耗归零。” | 搜狗微信检索，无稳定原文链接；证据等级 B | 2026-11-06 |
| C17 | 新浪财经/雷科技：AI 素材挂他人商品链接 | “他们觉得发自己账号上想咋弄咋弄，但链接挂的是我的商品啊。” | https://finance.sina.com.cn/roll/2026-10-16/doc-inivmprk1632155.shtml | 2026-10-16 |
| C18 | 腾讯新闻：跨境账号关闭，损失约 15 万美元 | “账号被直接关闭……最终损失约15万美金（约合人民币103万元）。” | https://news.qq.com/rain/a/20260427A061O600 | 2026-04-27 |
| C19 | 北京日报：消费者一眼识破 AI 面膜广告 | “太假了，这面膜广告的效果，一惊一乍的。” | https://news.bjd.com.cn/2026/11/09/12023416.shtml | 2026-11-09 |
| C20 | 有米云：模板台词被 6–8 个品牌复用 | “有米有数 YouClaw 对 250 条护肤素材的追踪发现，‘不必行色匆匆’‘断崖式衰老’这类模板台词被 6 到 8 个品牌反复复用，AI 批量生产的素材‘长得都一样’。” | https://www.youcloud.com/blog/3648/ | 2026-08-28 |
| C21 | 雨果跨境卖家访谈转述：翻译解决不了口型/俚语/场景 | “AI 翻译能解决字幕，但解决不了口型、俚语和当地场景，东南亚用户一眼看出是‘中国视频换了张皮’。” | https://www.cifnews.com/article/185489 | 2026-04-27（证据等级 C，转述） |
| C22 | 人人都是产品经理：AI 素材寿命“三天到一两周” | “素材寿命‘短的三天，长的也就一两周’。” | https://www.woshipm.com/marketing/6360228.html | 2026-09-11 |
| C23 | ByeRisk：素材被拒，跑量断流、预算冻结 | “投放素材一被拒，跑量直接断流，预算冻在账户里。” | https://www.byerisk.com/blog/ad-placement-rejection-2026-6-rules-deep-dive | 2026-05-28（服务商内容，C 级） |
| C24 | 新京报快评：AI 广告几块钱，没人花几十块审核 | “一条AI广告几块钱，谁会花几十块钱请人审核？” | https://finance.sina.cn/2026-08-09/detail-inimtpwi8690404.d.html | 2026-08-09（B 级） |
| C25 | 21经济网/钛媒体：归因不能只看点击/下单 | “测试一批AI素材时，除了比较点击率和下单成本，还应追踪退款、投诉及复购；评估口碑，则需要另设消费者调查，不能拿点击率代替。” | https://www.21jingji.com/article/20261013/herald/74acb1021d33e1ff06a9b3d5a38aac55.html | 2026-10-13（专家观点，B 级） |
| C26 | 21经济网/钛媒体引央视市场研究：94.1% 已用 AI，60.3% 评价“一般” | “94.1%的受访广告主已投入AI营销应用，但60.3%对成效的评价仍是‘一般’。” | https://www.21jingji.com/article/20261013/herald/74acb1021d33e1ff06a9b3d5a38aac55.html | 2026-10-13（二手引用调研，B 级） |

> 说明：G21–G33、C14–C26 是投放者/媒体经验，不是对照实验；G23 的“30%/1.8×”、C15 的“200 条/50 元”都是单一案例自述，不能当行业均值。G27 的“混真实镜头/10–12 秒”是投放者经验，不是 Meta 官方规则，不能当合规建议。C16 仅有公众号标题/摘要，证据等级 B；C21 为访谈转述，证据等级 C；C23 为服务商内容，C 级。它们共同指向一个产品事实：**“去 AI 感”“可审核”“可追溯”“快速迭代”是广告创意层的真需求**，而不是单纯“更高分辨率”。

### 7.6.4 广告场景证据缺口（明确不编）

- Creatify/Arcads/Icon/AdCreative/Captions 的**商用授权细则**（是否含买断、地区、二次剪辑、AI 模型训练限制）：官方定价页未逐条列出，标“未确认”。
- Arcads 各档**美元价**：官方只给 credits，价格在应用内；第三方文章有 $110/$220 等说法，本报告不采用。
- AdGen 同名产品多（tryadgen.me / adgenstudio.com / adgenai.co），本节采用 tryadgen.me；其他同名产品的价格/能力未合并。
- Pencil 是否有**公开生成 API**：官方帮助中心只有广告账户连接权限说明，未见生成 API 文档，按“无公开生成 API”处理。
- TikTok Symphony 的**单独定价/最低消费**：官方页面未给，标“未确认”。
- 三大平台审核的**可编程预审接口**：未发现公开 sandbox，按“平台不提供预审沙箱”处理；若未来开放，需重核。
- 广告素材“AI 感”的量化阈值（观众识别率、疲劳周期）：无官方/同行评审数据，G21–G33 只作定性证据。
