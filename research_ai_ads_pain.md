# AI 生成广告：痛点调研终稿

> 调研日期：2026-11-11
> 主题：**AI 生成广告素材 / 投放创意**（不是通用 AI 生视频；通用视频能力作为底层背景）
> 方法：4 路并行调研 + 交叉验证，全部结论附一手原话或官方文档链接
> 来源报告：
> - `research_ai_ads_en.md` — 英文广告市场（Reddit 9 帖全文/195 条评论 + 20 余帖片段）
> - `research_ai_ads_cn.md` — 中文广告市场（36 个核心来源，约 40 条引述/数据）
> - `research_videogen_tools.md` — 官方能力边界与开发者痛点（含 §七 广告场景专项，1029 行）
> - `research_videogen_en.md` / `research_videogen_cn.md` — 通用 AI 生视频痛点（作为底层能力背景）

---

## 0. 一页结论

### 0.1 最重要的判断

**广告场景的瓶颈已经从「生成一条视频」转移到「生成之后」：合规、批量、版本、审核、归因。**

模型能力（真实感、商品保真、跨镜头一致性）仍是硬约束，但主流效果广告（UGC 口播、图文快剪、数字人讲解）已经「够用」。真正让投放团队亏钱、停投、返工的，是生成之后那一堆工程与规则问题。

一个关键反差数据：

> “94.1%的受访广告主已投入AI营销应用，但60.3%对成效的评价仍是‘一般’。”
> —— 21 经济网/钛媒体，引用央视市场研究 2026 年对 200+ 家企业营销中高层的调查，2026-10-13
> https://www.21jingji.com/article/20261013/herald/74acb1021d33e1ff06a9b3d5a38aac55.html

采用率极高、价值感很低——缺口不在「能不能生成」，而在「生成完能不能用、能不能过审、能不能追溯、能不能迭代」。

### 0.2 痛点总排序（跨中英文、跨平台交叉验证）

| 排序 | 痛点 | 证据强度 | 性质 | 是否可产品化 |
|---|---|---|---|---|
| 1 | **合规审核与拒审/封号**（AIGC 标识、虚假效果、敏感行业、账户级处罚） | 强：中英文 + 三平台官方政策 | 平台规则 + 工程 | **高** |
| 2 | **批量同质化与创意疲劳**（50 条变体 = 平台眼里 1 条素材） | 强：中英文一手 | 策略 + 平台机制 | **高** |
| 3 | **工作流割裂与版本失控**（审过原稿 ≠ 审过所有投放版本） | 强：中文一手 + 英文 + 平台 API | 工程 | **高** |
| 4 | **商品保真与品牌一致性**（同一商品跨镜头变成另一件商品） | 强：中英文一手 + 平台规则/判例 | 模型 + 工作流 | 中高 |
| 5 | **真实感与数字人信任**（AI 脸/口型被识破，CTR 一周衰减） | 强：中英文一手 | 模型 + 创意 | 低（不要硬做生成） |
| 6 | **投放前决策/审片瓶颈**（生成变便宜，判断没有） | 中强：英文一手 + 中文 | 工作流 | **高** |
| 7 | **成本与配额失真**（废片、失败不退、credits 过期、平台限流） | 强：官方定价 + 一手吐槽 | 工程 | 中高 |
| 8 | **归因残缺**（只知道素材死了，不知道哪个论点死了） | 中：英文一手 + 平台 API | 数据接入 | 中高 |
| 9 | **肖像/版权/音乐授权链** | 中：中文一手 + 平台政策；英文样本无一手 | 工程 + 法务 | 中高 |
| 10 | **本地化**（翻译了字幕，翻译不了口型、俚语、文化） | 中：中文一手；英文样本不足 | 模型 + 规则 | 中 |

### 0.3 最值得做的机会（按「痛点强度 × 可产品化 × 付费意愿」）

1. **投放前创意质检层（Pre-flight Creative QA）+ 合规/权利台账** —— 四个 P0 的交汇点：论点去重、商品一致性、合规预审、版本留痕。
2. **跨平台素材图 / 版本 / A-B / 归因层** —— 市场最大、壁垒最高；把「素材 ID → 广告 ID → 花费/CPA/ROAS」打通。
3. **带成本上限和本地化规则的批量广告视频网关** —— 现金流好、门槛低，但容易被上游降价挤压。
4. **商品保真 + 真实感素材工厂** —— 难度高、潜力大，建议作为前两项的增值模块，而非第一个产品。

**明确不建议做**：又一个通用 AI 广告生成器；帮客户去 AI 标签/去 C2PA；纯 AI 演员库。

---

## 1. 调研说明与证据边界

### 1.1 四路调研的样本与失败记录

| 调研线 | 有效样本 | 失败/缺口（可复现） |
|---|---|---|
| 英文广告市场 | 9 个 Reddit 帖全文 + 195 条评论；20 余帖片段；官方定价页核对 | Reddit 搜索/HTML 被封锁，只能走单帖 RSS；TikTok/Google 政策、本地化、版权**证据不足**；Twitter 需登录 |
| 中文广告市场 | 36 个核心来源，约 40 条引述/数据 | 腾讯广告/快手磁力/拼多多一手商家原话不足；无广告后台数据；「频次」是语料编码非统计；小红书/知乎/公众号全文缺失 |
| 技术/工具层 | 12 个广告工具/平台的官方价格、API、商用条款；Meta/TikTok/Google 官方政策页 | Arcads 美元价、TikTok Symphony 单独定价、部分商用授权细则**未确认**，文中已标注 |
| 通用生视频背景 | 英文 314 个独立 Reddit thread + 83 条证据索引；中文约 520 条文本/58 条原话 | 小红书 0 直接样本；B 站评论受 412 限流；Runway Help 被 Cloudflare 拦截 |

### 1.2 必须打折扣的地方

- **频次不是统计**：所有「≥N 条讨论」都是语料编码结果，不是随机抽样或行业均值。
- **单案例数字不能当行业均值**：例如「AI 素材疲劳快 30%」「同真人比 1.8× ROAS」「200 条素材 8 小时消耗 50 元」都是单一用户自述。
- **投放者经验 ≠ 平台规则**：例如「混真实镜头、压到 10–12 秒更容易过审」是投放者总结，不是 Meta 官方规则，不能作为合规建议。
- **厂商内容污染**：中文搜索中大量「AI 视频一致性 / 素材管理」结果是工具厂商 SEO 文章，只作「行业在卖什么」的信号，不作痛点证据。
- **幸存者偏差**：成功案例爱发声，失败者不发声；本调研刻意多取评论区、失败/亏损侧。

---

## 2. 痛点清单（P0 / P1 / P2）

### P0-1 合规审核与账号风险：素材不是「生成完」，而是「过审完」

**痛点**：AIGC 标识、广告法极限词、化妆品/保健食品功效、医疗/金融/教育敏感词、AI 换脸肖像、低俗擦边——任何一项都可能触发拒审、停投、下架、扣分、封号。2026 年平台从「抽检」转向「投放前主动识别」，投手拿到的不是修改建议，而是直接断流。

**频次信号**：中文约 18 个独立来源（高频）；英文 3 帖 + 三平台官方政策；技术层有完整政策页。

**关键证据**：

> “投放素材一被拒，跑量直接断流，预算冻在账户里。”
> —— ByeRisk 博客，2026-05-28（服务商内容，C 级）
> https://www.byerisk.com/blog/ad-placement-rejection-2026-6-rules-deep-dive

> “凌晨一点，投手老周盯着后台发懵：三条正跑量的 AI 数字人素材，被复审拦下直接停投。计划断档、消耗归零。”
> —— 微信公众号「千川研习社」，2026-11-06（B 级，仅标题/摘要）

> “I've been testing some AI-generated ads where the entire video is created with AI... Meta keeps rejecting them... No real actors, no UGC. Meta doesn't provide a clear explanation beyond 'policy violation'.”
> —— u/Delicious_Tank6519, r/FacebookAds, 2025-12-09
> https://www.reddit.com/r/FacebookAds/comments/1picn8j/

**平台侧规模数据**：

- 巨量引擎 2025 年全年前置拦截违规素材**超百亿条**、关停风险账户**超 400 万个**，单日处置黑产账户峰值**突破 20 万个**。来源：上海证券报，2026-02-05（A 级）
- 抖音生活服务 2026 年一季度处置**超 80 万条 AIGC 违规带货内容**，涉及肖像侵权、虚假宣传、低俗营销。来源：北京商报，2026-05-27（A 级）
- Meta：未标记的写实 AI 内容由 MARS 多模态审核系统识别，面临广告拒审、政策违规记录、账户限制；结合 C2PA 元数据。来源：白鲸出海，2026-09-16（B 级）
- TikTok Ads：**AI-generated / synthetic / manipulated media 的免责声明是 mandatory**，不是 suggested。来源：TikTok Ads Manager 官方帮助页（O63）
- Google Ads：2026-07 起支持 AI 标签，欧盟/印度/纽约/加州/韩国/越南显示可见 overlay；生成资产**不保证过审**。来源：Google Ads 官方政策页（O53–O56）

**为什么难**：

1. 规则多层叠加：广告法 + 平台审核 + 行业资质 + AIGC 标识 + 跨境当地法规，任何一层都能单独否决。
2. 审核标准不透明且动态变化；同一素材在不同账户、不同时段结果可能不同。
3. 生成速度远快于审核速度：一条 AI 广告几块钱，人工审核几十块。
4. 处罚是账户级的：停投、扣分、封禁，甚至影响整个店铺/主体。

> “一条AI广告几块钱，谁会花几十块钱请人审核？”
> —— 新京报快评，2026-08-09
> https://finance.sina.cn/2026-08-09/detail-inimtpwi8690404.d.html

---

### P0-2 批量同质化与创意疲劳：素材越多，越不值钱

**痛点**：AI 把「从 0 到 1 做一条素材」的成本打到接近零，但「从 1 到 100 条」全都长得一样。平台算法和用户同时免疫模板化内容，批量生成几百条，消耗却跑不动；素材寿命被压缩到几天到两周。

**频次信号**：英文 7 帖/10+ 评论；中文约 9 个独立来源；技术层有平台机制佐证。

**关键证据**：

> “meta doesnt reward volume. it rewards variance. 50 creatives that are the same ad with a different background is ONE creative to the system. it reads content semantically now, it sees the same message and it learns nothing. you just paid for the noise.”
> —— u/Popular-Cap-9013, r/FacebookAds, 2026-08-31（自称 10 年投放、$10M 花费）
> https://www.reddit.com/r/FacebookAds/comments/1w3siss/

> “creative fatigue hits AI ads ~30% faster. The same avatar/structure that wins at week 1 burns by week 3-4... we saw 1.8x higher ROAS on retargeting with human vs AI for the same SKU.”
> —— u/paxtonpro, r/FacebookAds, 2026-03-08（单一案例自述）
> https://www.reddit.com/r/FacebookAds/comments/1rlvjrg/

> “他刚用 AI 工具批量生成了 200 条素材，投进去跑了 8 小时，消耗不到 50 块。”
> —— 有米云，2026-08-28（B 级，服务商追踪数据）
> https://www.youcloud.com/blog/3648/

> “同一句台词，在多个品牌、多个产品间反复出现。‘不必行色匆匆，不必光芒四射’这句文案，至少出现在 6 条不同素材里；‘断崖式衰老’这个钩子，出现在至少 8 条素材里。”
> —— 有米云，2026-08-28
> https://www.youcloud.com/blog/3648/

> “现在信息流素材的生命周期，短的三天，长的也就一两周。”
> —— 人人都是产品经理，2026-09-11
> https://www.woshipm.com/marketing/6360228.html

**为什么难**：

1. 同质化的根源不是「假」，是「像」：模板台词、无具体时间地点、人物场景同质。
2. 批量生成会自我强化：系统奖励当期转化，团队继续复制跑量模板，直到所有人内卷。
3. 创意产能被误认为「素材数量」；真正的瓶颈是差异化创意。
4. 平台反同质化：低质模板化素材即使过审，也可能被降低分发权重。

**这是本次调研最值得做产品的一条**：工具解决「生成量」，平台（Meta Andromeda 语义检索）奖励「论点差异」。用户已经自发用 spreadsheet、swap test、one-sentence rule 做「论点去重」，说明需求真实且未被工具覆盖。

---

### P0-3 商品保真与品牌一致性：AI 把商品改成了「另一个东西」

**痛点**：AI 生成/修改商品图时，改变颜色、材质、尺寸、数量、功能、使用效果；或把 A 商品的特征套到 B 商品上。消费者收到货不对板，轻则退货差评，重则投诉、判罚、下架、封号。跨境场景更严重：达人用 AI 视频挂商家的商品链接，商家无法控制内容，也无法快速删除。

**频次信号**：英文 4 帖集中讨论（2026-05 后）；中文约 12 个独立来源（高频）；平台规则与法院判例均有。

**关键证据**：

> “Generated 8 variations of the same product ad last month. Same product used every time, same colour, same spec details in the prompt. Six of the eight outputs showed something that was clearly not the same item... For categories where the visual detail drives the buying decision, this isn't a minor issue.”
> —— u/sushi_will, r/AI_UGC_Marketing, 2026-09-18
> https://www.reddit.com/r/AI_UGC_Marketing/comments/1wjr9h3/

> “他们觉得发自己账号上想咋弄咋弄，但链接挂的是我的商品啊。”
> —— 新浪财经/雷科技，具名商家许婉仪，2026-10-16
> https://finance.sina.com.cn/roll/2026-10-16/doc-inivmprk1632155.shtml

> “戒指戴在手指上，手指必须清晰逼真。消费者遇到的那种一眼假‘六指’广告图，在饰品行业中就完全无法交差。”
> —— 北京日报，具名商家林沐昀，2026-11-09
> https://news.bjd.com.cn/2026/11/09/12023416.shtml

**规则/判例**：

- TikTok Shop 2026-09-16 更新 AIGC 卖家指引：AI 素材必须真实反映实际商品，不能虚构功能、材质、数量、颜色或使用效果；菲越率先执行。
- 广州一服装店用 AI 图卖货，还谎称「实物拍摄」，被法院判**退一赔三**（2026-03-12）。

**解读**：这是「静默废片」——不会报错，只会让商品看起来不对。用户目前靠人眼逐条比对，六成废片率意味着 credits 与实际可用素材的成本被严重低估。

---

### P0-4 真实感与数字人信任：用户一眼识破，转化就没了

**痛点**：AI 数字人/口播/换脸被用户识破后，广告不仅不转化，还会反噬品牌信任。数字人直播黄金时段转化率显著低于真人；平台还会以「可能引起公众混淆的形象」为由禁播。

**频次信号**：英文 6 帖/12+ 评论（跨 4 个子版）；中文约 8 个独立来源。

**关键证据**：

> “I tested HeyGen for a B2B client in IT. CTR was decent for the first few days, but dropped visibly after a week. People quickly realize it's AI and trust breaks.”
> —— u/Gelu_Bumerang, r/PPC, 2025-12-10
> https://www.reddit.com/r/PPC/comments/1pj88je/

> “the second a real person sees it close up it screams generated. and my audience is mostly 25-40s who absolutely clock that stuff.”
> —— u/mesmerlord, r/FacebookAds, 2026-06-10
> https://www.reddit.com/r/FacebookAds/comments/1u215y0/

> “太假了，这面膜广告的效果，一惊一乍的。”
> —— 北京日报，消费者蕾蕾，2026-11-09
> https://news.bjd.com.cn/2026/11/09/12023416.shtml

> “我不认为所有的电商产品都可以用AI生成图片、视频。像我比较关注的童装，现在越来越多那种‘AI小孩’当模特，满脸假笑，看着有点恐怖。”
> —— 北京日报，消费者宝妈多多，2026-11-09

> “数字人直播在‘垃圾时段’（如凌晨）ROI可达真人直播的3倍，但黄金时段转化率仅为真人的60%。”
> —— B站专栏，2025-06-16（C 级，未给原始出处）

**关键边界**（来自 15 个 campaign 的实操复盘）：

> “AI UGC works reliably for: brand awareness top-of-funnel content, product demonstration with simple interaction, lifestyle context shots, testimonial-style content where the hook is the claim rather than the person's credibility. AI UGC struggles with: content where the purchase decision depends on trusting a specific real person's experience...”
> —— u/siddomaxx, r/AI_UGC_Marketing, 2026-04-16
> https://www.reddit.com/r/AI_UGC_Marketing/comments/1smu3jr/

**产品含义**：不要在「更像人」上硬做产品。可操作的方向是「短、切、混真实 B-roll」——这是 workaround，也是未来产品的结构模板。

---

### P0-5 工作流割裂与版本失控：审过原稿 ≠ 审过所有投放版本

**痛点**：生成在 A 工具、剪辑在 B 工具、审核在 C 表格、投放在 D 平台、数据在 E 后台。素材一旦进入批量生成/自动组合，品牌审过的「原稿」和实际投放的「版本」之间出现巨大缝隙；谁改了什么、哪个版本跑了多少、为什么被拒，无法追溯。

**频次信号**：中文约 7 个独立来源（中高频）；英文审片/决策瓶颈 4 帖；技术层有平台 API 佐证。

**关键证据**：

> “开启相关功能后，品牌面对的已经是一批不断组合、调整的内容，审核过一份原稿，不能保证看过所有投放版本。”
> —— 21 经济网/钛媒体，2026-10-13
> https://www.21jingji.com/article/20261013/herald/74acb1021d33e1ff06a9b3d5a38aac55.html

> “generating got cheap, deciding didnt. thats the whole shift and most teams never updated their process for it.”
> —— u/Popular-Cap-9013, r/FacebookAds, 2026-09-01
> https://www.reddit.com/r/FacebookAds/comments/1w3siss/

> “people use AI to spit out 50 variations but nobody's checking whether each one actually holds up before it spends.”
> —— u/Vegetable-Choice1728, r/FacebookAds, 2026-09-01

> “素材衰退速度，永远比素材生产速度快。”
> —— 人人都是产品经理，2026-09-11

**为什么难**：

1. 版本爆炸：一条母版裂变出几十上百条，人工无法逐条确认承诺、优惠、品牌调性是否被改。
2. 审核对象错位：品牌审「模板/原稿」，平台审「最终投放版本」，中间由运营/算法自由组合。
3. 工具链割裂：没有统一素材 ID 和版本链。
4. 责任边界模糊：品牌、经销商、代运营、达人、平台互相甩锅。

---

### P1-1 成本与配额失真：单条便宜，不等于总成本低

**痛点**：AI 把单条素材的边际成本打到几元甚至几角，但总成本被积分/会员/算力、废片率、返工、人工审核、封号、退款、品牌修复重新拉高。

**频次信号**：英文 3 帖直接谈钱 + 厂商定价；中文约 9 个独立来源；技术层有官方配额原文。

**关键证据**：

> “AI costs $3/video vs $420 human. Tested 134 AI concepts vs 24 human.”
> —— u/Latter-Law5336, r/FacebookAds, 2026-03-05（单一自述）

> “5 条 10 秒片烧光月额度”、“87% 失败仍扣 $4”、“失败生成不退积分”——见 `research_videogen_en.md` P0-3。
> 通用视频侧的同类证据：即梦 26 条废片换 1 条可用；剪映对口型 6 条全废、1080 积分不退（`research_videogen_cn.md` P0-1）。

**官方配额（查询日 2026-11-11，`research_videogen_tools.md` §7.1）**：

- Captions Mirage API 视频生成仅 **2 RPM/组织**：50 条变体光排队至少 25 分钟。
- TikTok `/creative/smart_video/create` 仅 **1 QPS / 30 QPM / 5,000 QPD**。
- Arcads 800 credits/条 2 分钟口播：Starter 8,000 credits ≈ 一个月 10 条。
- Creatify credits **2 个月过期**；Pencil Core/Growth 每月 50/250 generations，**不滚存**。
- Icon 人类 UGC **$1,000/6 条 ≈ $166.7/条**，12–16 天——这是「真人信任」的价格锚。

**结论**：做「一次生成 100 条变体」的产品，必须把平台配额、credits 过期、失败退款、并发上限纳入调度；否则 demo 很顺，一上量就排队/超预算。

---

### P1-2 投放前决策/审片瓶颈

**证据**：

> “To make a generated ad feel truly native, you usually need way more iterations - so many that just reviewing and picking the best ones could take longer than writing a solid script, finding 2–3 good UGC creators, and doing a couple rounds of reviews, fixes, and post-production.”
> —— u/Flesteyto_, r/PPC, 2025-08-28
> https://www.reddit.com/r/PPC/comments/1lpo9rr/

> “the 20 minutes a week is cheap, the month you lose shipping slop into a winner isn't.”
> —— u/Vegetable-Choice1728, r/FacebookAds, 2026-09-02

**含义**：AI 省下的拍摄时间，被审片时间吃回去了。判断标准是隐性的（什么算「不同论点」、什么算「产品没变」），新人无法执行——这正是可产品化的空间。

---

### P1-3 归因残缺：只知道素材死了，不知道哪个论点死了

> “arguments fatigue, not just creatives. read performance at the file level and you think the ad died so you ship another version. read it at the argument lev[el]...”
> —— u/Popular-Cap-9013, r/FacebookAds, 2026-09-01

> “tagging by argument is where it compounds... someone has to be the asshole who rejects tags.”
> —— 同上

**平台侧现状**：TikTok Smart+ 已支持按 creative material ID 出创意级报表；Google PMax 按 asset group/asset 组织素材；Meta Advantage+ 自动生成多版本。但生成工具不消费这些数据，只负责「生成更多」。用户已用 spreadsheet + 人工打标 workaround。

**局限**：依赖平台 API 权限与归因窗口；大客户可能自建。

---

### P1-4 肖像/版权/音乐/授权链

**中文证据**：

> “累计清理了4.7万余条违法违规信息，并处置了3961个相关账号。”——网信办/各平台，2026-11-09（A 级）
> “处置仿冒公众人物账号1.1万余个。”——新华报业，2025-11-15（A 级）
> 短视频使用 **16 秒背景音乐**被判侵权，赔偿 **1000 元**（湖北法治网，2026-03-13，A 级）。

**平台政策**：TikTok 明确禁止未经授权模仿他人身份、likeness、声音；禁止虚假专家背书。Meta 对政治/选举广告要求 AI 披露，并用 C2PA 自动识别第三方 AI 内容。

**英文侧**：本次广告样本中**没有**广告主讨论 AI 演员授权、UGC 创作者买断、音乐版权的一手原话——此方向在英文市场证据不足，不作为强度判断依据。

**产品含义**：素材级「权利台账」（model release、音乐/字体/品牌授权、AI 模型商用条款、地区限制），并与投放账户/地区绑定；这比「生成质量提升 10%」更能阻止下架/索赔。

---

### P1-5 本地化：翻译了字幕，翻译不了口型、俚语和文化

> “AI 翻译能解决字幕，但解决不了口型、俚语和当地场景，东南亚用户一眼看出是‘中国视频换了张皮’。”
> —— 雨果跨境卖家访谈转述，2026-04-27（C 级）

> “因未标注‘AI生成内容’，30%账号被封禁。”
> —— B站专栏，2025-06-16（C 级，案例未给原始出处）

**工具侧现状**：Pencil 支持 40+ 语言文本；TikTok Symphony 支持 2,000+ 数字人、翻译/配音/口型；Meta 有 translations/subtitles；Google PMax 文本语言跟随落地页。**工具只给「翻译」，不给「本地化合规」**——同一句「疗效/最低价/第一」在不同国家是不同监管。

**英文侧**：本次样本中没有广告主抱怨「口型/文化适配」的原话；本地化是厂商已在卷的功能点，不作强度判断。

---

### P2 级痛点（结构性/新兴风险）

| 痛点 | 证据 | 说明 |
|---|---|---|
| 高敏感行业（医疗/保健/金融/教育） | 中文约 6 个来源 | AI 会「自作主张」补功效、补权威、补案例，导致虚假宣传；投放考核与品牌合规目标冲突 |
| 矩阵号与批量发布 | 中文约 7 个来源 | 平台把「AI 批量」识别为机器行为；多账号共用 IP/设备/支付/素材容易被关联 |
| 品牌价值观与舆情 | 中文约 6 个来源 | 低俗擦边、冒犯群体；2026 上半年十余个品牌翻车，苏泊尔、自然堂、德芙最具代表性 |
| 代理商/客户接受度 | 英文 3 帖 + 中文 4–5 个来源 | 客户不买、审片反复、效果不好时背锅；缺一份可交付的「AI 素材验收标准」 |
| 平台/工具锁定 | 中文 4 个来源 | 即创→巨量、擎舵→百度；跨平台迁移和归因难 |

---

## 3. 模型能力问题 vs 工程/工作流问题

这是整份报告最重要的分类。做产品要押「工程」，不要押「模型会变好」。

| 问题 | 归类 | 广告场景判断 |
|---|---|---|
| 产品颜色/材质/logo/文字在生成中失真 | **模型能力** | 短期无解；美妆、服饰、3C、食品等「产品即卖点」品类是硬伤，不能靠工作流绕过 |
| 同一演员/场景跨镜头不换脸 | **模型能力** | 多镜头一致性仍不稳定；广告需要「同一个人讲 3 个卖点」，比单条炫技更难 |
| 多语言口型/语气/文化梗 | **模型能力 + 数据** | 翻译容易，口型与本地表达难；小语种质量差距大 |
| 手部/产品交互/使用演示 | **模型能力** | 仍容易穿模；产品演示类广告不宜全 AI |
| 「AI 感」导致信任/疲劳 | **模型能力 + 创意** | 观众能识别通用 AI 演员；不是纯技术问题，选角/脚本/真人混剪更关键 |
| 9:16 裁切/版位扩展 | **工程** | 平台有自动扩展，但会裁掉卖点/字幕；需要按版位重排，不是简单 resize |
| 批量变体/成本上限/失败重试 | **工程** | 平台配额、credits 过期、2 RPM 等都能通过调度/预算层解决 |
| 审核前置/申诉/标签 | **工程 + 规则** | 可产品化；但平台不透明，需要持续维护规则库 |
| 素材版本/A-B/归因 | **工程** | 最大空白；平台报表已具备，缺的是跨平台素材图与回流 |
| 肖像/版权/商用授权 | **工程 + 法务** | 可产品化；需要合同结构化与地区规则 |

**一句话**：不要赌「更好的生成」，要赌「更好的选择、验证、编排与交付」。模型越强，编排层的价值越大，而不是越小。

---

## 4. 现有 workaround 与竞品地图

### 4.1 广告主自创的 workaround

| Workaround | 具体做法 | 代价/局限 |
|---|---|---|
| **AI 测角度，真人拍赢家**（最主流） | 用 AI 快速测 10 个 messaging angle，找到 2–3 个能转化的，再用真人创作者重拍 | 多一轮制作；AI 只做 prototyping |
| **混剪真实素材** | AI 口播 + 真实 B-roll/产品镜头，压到 10–12 秒 | 需真人素材库；规模化难 |
| **人工「论点去重」** | swap test、one-sentence rule、按 argument 打标 | 每周 20 分钟人工；依赖老投手经验 |
| **参考图锁定 + 合成** | 锁一张产品参考静帧，镜头拉近；数字人失败时用合成而非重生成 | 只能减缓漂移 |
| **回归真人** | Icon 以「6 Human UGC ads for $1000 (no AI / 100% real)」反向定位 | 价格锚 $166/条，12–16 天 |
| **降级到静态** | 多条评论认为 AI 静态图 > AI 视频 | 牺牲视频表达力 |
| **人工二审/三审** | 品牌/运营/法务逐条看 | 跟不上日产千条 |
| **平台原生工具** | 即创/千意、擎舵/AIMax、腾讯妙思、万相、羚珑 | 单平台锁定；审核黑箱；品牌资产不沉淀 |

### 4.2 竞品地图（2026-11 官网核对）

| 类型 | 代表 | 强项 | 缺口（对本报告痛点） |
|---|---|---|---|
| **AI UGC 生成** | Creatify、Arcads、Captions、HeyGen、Synthesia | 演员库、批量、多语言 | 无内置编辑器；产品漂移；审核状态不回流 |
| **真人 UGC 市场** | Icon | 真实感、退款保证 | $166/条、12–16 天；不是 AI |
| **静态/多尺寸创意** | Pencil、AdCreative.ai、AdGen | 快速出图、A/B 变体 | 视频真实感与产品一致性弱 |
| **平台侧生成** | Meta Advantage+/Andromeda、Google PMax、TikTok Symphony/Smart+ | 一键成片、原生投放、creative-level 报表 | 广告主无法控制自动改写；跨平台不打通 |
| **通用视频模型** | Sora、Veo、Runway、Kling | 画面质感最强 | “prettiest footage... worst ad”；无投放工作流 |
| **素材分析** | 有米云/YouClaw、AppGrowing | 爆款拆解、同质化识别 | 偏事后分析；不进入生产/审核 |
| **合规检测** | ByeRisk、平台预审 | 违禁词/功效初筛 | 多查文本少查画面；无版本审计；不承担审核责任 |

一条对通用模型的精准评价：

> “veo3 made the prettiest footage by a mile and was the worst ad. gorgeous, no persuasion.”
> —— u/CosmoBloomCook, r/AI_UGC_Marketing, 2026-08-20
> https://www.reddit.com/r/AI_UGC_Marketing/comments/1vtudx0/

**结论**：市场不缺「生成工具」，也不缺「单点检测」，缺的是**把「商品真值、品牌承诺、AIGC 标识、平台规则、投放版本、效果/退款数据」串起来的中间层**。

---

## 5. 机会判断

### 机会 1（最值得做）：投放前创意质检层 + 合规/权利台账

**一句话**：在素材生成后、投放前，判断「这条素材能不能投、值不值得投、投出去会不会被拒」。

**解决的问题**：P0-1（合规/拒审）、P0-2（同质化）、P0-3（商品漂移）、P0-5（版本失控）——四个 P0 的交汇点。

**产品形态（四个模块，可按客户先做 1–2 个）**：

1. **论点去重**：用 swap test / 一句话规则，把 50 条判成 N 个真实论点；给出「还缺哪条轴」的建议。
2. **商品一致性打分**：对照商品参考图，检测颜色/比例/logo/标签位置漂移，直接拦掉「静默废片」。
3. **合规预审**：按 Meta/TikTok/Google 规则检查 AI 披露、连续单镜头口播、时长、敏感品类词、夸大效果；给出「可过审结构」改写建议（切镜头、混 B-roll、压时长）。
4. **版本/权利台账**：记录 script→shot→actor/voice→render→variant→platform ad ID；绑定肖像/音乐/字体/模型商用授权、地区限制、到期日；生成「合规证据包」用于申诉/客户交付。

**为什么是现在**：

- TikTok 已把 AI 广告免责声明列为 **mandatory**；Google 2026-07 起区域强制标签；Meta 用 C2PA 自动识别。
- 巨量 2025 年拦截百亿条违规素材、关停 400 万账户；抖音生活服务 2026Q1 处置 80 万条 AIGC 违规带货。
- 广告主已自发用 spreadsheet 做论点去重和版本管理，说明需求成立、现有工具不做。
- 94.1% 用了 AI，60.3% 觉得「一般」——价值缺口正好在这里。

**谁付费**：品牌市场部/法务、代运营/MCN、跨境卖家、多门店品牌。**投手是使用者，不是预算持有人**；产品要同时满足「投手好用」与「老板能追责」。

**壁垒**：规则库 + 拒审案例库 + 商品参考比对 + 版本链；不是模型。可与 Creatify/Arcads 等生成工具互补（它们生成，你做质检与上线）。

**风险**：平台规则不透明且会变；误杀会失去信任；需在合同上明确「辅助审核，不替代平台/法律意见」；平台可能把类似能力做成原生功能——所以要走「跨平台 + 品牌侧」。

**切入策略**：先做「抖音/千川或 TikTok/Meta + 美妆/保健/食品」的合规预审 + 版本审计，客户选代运营机构（多客户、多账户、强痛点）。

---

### 机会 2（市场最大、壁垒最高）：跨平台素材图 / 版本 / A-B / 归因层

**一句话**：一个「广告素材操作系统」，记录 script→shot→actor/voice→render→variant→platform ad ID，并回拉花费/CPA/ROAS。

**产品形态**：

- 统一 asset ID 与素材谱系；平台自动 resize/翻译/加音乐也要回写。
- 拉取 Meta/TikTok/Google 的审核状态、花费、CPA/ROAS。
- 按 creative material ID / asset 维度做 A/B 与 fatigue 预警（用户已在用「CTR 相对峰值下降 25%」阈值）。
- 按「论点」而非 ad 文件聚合效果；输出「下一批该测的论点轴」。

**为什么是现在**：TikTok Smart+ 已支持 creative-level reporting；Google 有 asset reporting；Meta 有 Advantage+ 自动变体。数据基础具备，但工具侧仍是断点。AI 广告疲劳更快，更需要快速淘汰/迭代。

**谁付费**：中大型投放团队、代理、DTC 品牌；按 ad account/素材量订阅。

**壁垒**：跨平台连接器 + 素材谱系 + 归因模型；比「再做一个生成器」更难被替代。

**风险**：依赖平台 API 权限与归因窗口；大客户可能自建；需与机会 1 捆绑才有数据入口。

---

### 机会 3（现金流好、壁垒低）：带成本上限和本地化规则的批量广告视频网关

**一句话**：面向 SMB/代理的「广告视频 API 路由器」——接 Creatify/Arcads/Captions/HeyGen/Synthesia/TikTok Symphony，统一任务、重试、配额、预算。

**产品形态**：

- 统一任务、轮询/webhook、失败重试、credits 余额/过期提醒。
- 按平台规格（9:16/1:1/4:5、时长、字幕安全区）自动出片。
- 按市场做语言/货币/禁用语/claim 替换。
- 硬预算上限，超支熔断。

**为什么是现在**：Captions 2 RPM、TikTok creative 1 QPS、Arcads 800 credits/条、Creatify credits 2 个月过期——批量投放的「配额/成本」痛点非常具体。

**风险**：容易被上游降价挤压；需要靠工作流/合规增值，不能只做转发。

---

### 机会 4（难度高、潜力大）：商品保真 + 真实感素材工厂

**一句话**：不是「让 AI 画得更像」，而是「让 AI 只能在商品真值范围内发挥」，并把「AI 编不出来的真实细节」变成可复制的素材方法论。

**产品形态**：

1. 商品数字孪生采集：多角度/多光源/尺寸标定/材质采样，形成「商品真值包」。
2. 商品锁定生成：场景/模特/光线可换，商品像素级保真；生成时校验颜色/材质/数量/结构/尺寸。
3. 真实感脚本：基于卖点生成「可验证细节」——具体时间、场景、仪器读数、真人证言、前后对比。
4. 人机混合生产：AI 负责场景/背景/多语言口播，真人负责出镜/实测/背书。
5. 本地化 QA + 效果回流（退货原因、差评关键词、退款率反哺素材评分）。

**为什么难**：产品保真仍是模型能力问题；采集流程重；中小卖家可能不愿投入。建议作为机会 1/2 的增值模块，等模型能力再进一步，或先选一个「货不对板最痛、客单较高、SKU 多」的垂直（饰品或服饰）做轻采集版本。

---

### 不建议做

- **又一个通用 AI 广告生成器**：Creatify/Arcads/Pencil/AdCreative/Captions 已拥挤，价格战且平台自带生成。
- **帮客户规避 AI 标签/去 C2PA**：平台明确自动识别、标签不可移除，违规风险高，不是可持续产品。
- **纯 AI 演员库 / 纯数字人**：观众对通用 AI 演员的信任/疲劳问题；没有选角/脚本/投放闭环很难差异化。
- **面向消费者的「检测 AI 广告」工具**：有需求，但无付费方。
- **一键爆款/躺赚**：已被大量诈骗案污染，合规与品牌风险极高。

---

## 6. 对 Opportunity Scout 的下一步建议

### 6.1 先验证哪个 wedge

三个候选 wedge，按验证成本排序：

| Wedge | 目标客户 | 最小验证 | 通过标准 |
|---|---|---|---|
| **A. 合规预审（千川/抖音）** | 代运营机构、美妆/保健/食品品牌 | 人工为 3 家代运营各审 50 条 AI 素材，记录拒审率与节省时间 | ≥2 家愿意按条/月付费；拒审率可量化下降 |
| **B. 跨平台素材台账 + 归因** | 出海投放团队、DTC 品牌 | 接 1 个 Meta/TikTok 账户，手工建素材谱系，做 2 周 fatigue 复盘 | 能复现「哪个论点/演员/脚本赢」；团队愿意每周用 |
| **C. 批量生成网关** | 出海 SMB、MCN | 用 2–3 家 API 做 100 条批量出片，记录配额/失败/成本 | 单条可用成本比客户现方案低 30%+ |

**建议先做 A**：合规是 2026 年最确定的外部推力（TikTok mandatory、Google 区域强制、Meta C2PA），且痛点强度、付费意愿、可产品化程度三项都最高。B 作为第二曲线，A 的版本台账可以自然长成 B。

### 6.2 访谈问题（10–20 人）

1. 过去 3 个月，有多少条 AI 素材被拒/停投？损失多少消耗/预算？
2. 谁负责审？审一条要多久？审的是原稿还是最终投放版本？
3. 现在怎么判断「这条素材和那条是不是同一个论点」？用什么工具？
4. 商品/品牌一致性出过几次问题？怎么发现的？退货/差评有没有回来？
5. 一个月在 AI 素材工具上花多少钱？废片率多少？credits 有没有过期/失败不退？
6. 如果有一个「投放前质检」工具，你愿意按条付还是按月付？价格锚是多少？

### 6.3 需要补的证据

- 小红书/抖音商家的一手原话（本次登录墙导致 0 直接样本）。
- Meta/TikTok/Google 广告后台的真实拒审率与申诉结果（需用户授权数据）。
- 代运营机构的真实报价与改稿成本。
- 英文市场肖像/版权/本地化的一手证据（本次不足）。

### 6.4 风险提示

- **平台规则会变**：合规产品的规则库必须持续维护，不能一次做完。
- **平台可能自己做**：即创/擎舵/PMax/Symphony 都在补原生能力；第三方必须走「跨平台 + 品牌侧 + 可审计」。
- **误杀责任**：质检工具必须可解释，合同上明确「辅助」定位。
- **模型迭代会吃掉一部分痛点**：真实感/商品保真会变好，但合规/版本/归因不会因为模型变强而消失。

---

## 7. 证据索引

### 7.1 本项目的四份源报告

- `research_ai_ads_en.md` — 英文广告市场（含 G21–G33 一手投放反馈）
- `research_ai_ads_cn.md` — 中文广告市场（含 P0/P1/P2、平台/角色分布、竞品地图）
- `research_videogen_tools.md` — 官方能力边界 + 开发者痛点 + §七 广告场景专项（O36–O72）
- `research_videogen_en.md` / `research_videogen_cn.md` — 通用 AI 生视频痛点（底层能力背景）

### 7.2 高价值一手链接（节选）

**英文投放侧**

- https://www.reddit.com/r/FacebookAds/comments/1w3siss/ — 批量同质化、论点归因（2026-08-31 / 09-01）
- https://www.reddit.com/r/FacebookAds/comments/1rlvjrg/ — AI vs 真人 UGC，$100k 测试（2026-03-08）
- https://www.reddit.com/r/AI_UGC_Marketing/comments/1wjr9h3/ — 商品保真（2026-09-18）
- https://www.reddit.com/r/PPC/comments/1pj88je/ — HeyGen B2B 信任崩塌（2025-12-10）
- https://www.reddit.com/r/FacebookAds/comments/1picn8j/ — 纯 AI 口播被拒（2025-12-09）
- https://www.reddit.com/r/AI_UGC_Marketing/comments/1smu3jr/ — 15 个 campaign 实操复盘（2026-04-16）

**中文投放侧**

- https://www.21jingji.com/article/20261013/herald/74acb1021d33e1ff06a9b3d5a38aac55.html — 版本失控、94.1%/60.3%（2026-10-13）
- https://www.youcloud.com/blog/3648/ — 200 条素材 8 小时消耗 50 元、模板台词复用（2026-08-28）
- https://finance.sina.com.cn/roll/2026-10-16/doc-inivmprk1632155.shtml — AI 带货改商品、商家投诉（2026-10-16）
- https://news.bjd.com.cn/2026/11/09/12023416.shtml — 消费者识破 AI 广告、商家报价（2026-11-09）
- https://finance.sina.cn/2026-08-09/detail-inimtpwi8690404.d.html — 苏泊尔 AI 广告翻车、审核成本（2026-08-09）
- https://www.woshipm.com/marketing/6360228.html — 素材生命周期 3 天–2 周（2026-09-11）

**平台官方政策**

- TikTok 广告免责声明（AI 合成媒体 mandatory）：https://ads.tiktok.com/resources/help/article/about-ad-disclaimers-in-tiktok-ads-manager?lang=en
- Meta AI info 标签（C2PA、地区自披露）：https://business.facebook.com/business/help/1009525374368348/
- Google AI labeling（2026-07 起）：https://support.google.com/adspolicy/answer/17257106?hl=en
- Google PMax 生成资产（不保证过审）：https://support.google.com/google-ads/answer/14150602?hl=en

**工具官方定价/API**（查询日 2026-11-11）

- Creatify：https://creatify.ai/pricing；https://docs.creatify.ai/billing
- Arcads：https://help.arcads.ai/en/articles/17595066-how-does-arcads-pricing-work；https://external-api.arcads.ai/docs
- Captions：https://captions.ai/pricing；https://captions.ai/help/docs/api/rate-limiting
- Icon：https://icon.com/pricing
- Pencil：https://trypencil.com/pricing
- AdCreative.ai：https://www.adcreative.ai/

---

## 8. 一句话给产品团队

**不要做「AI 广告生成器」，做「AI 广告的投放前质检与版本台账」。**

生成已经被商品化，合规与可追溯性才是 2026 年广告主愿意持续付费的地方。先从一个平台、一个品类、一家代运营开始，把「拒审率下降」和「审片时间下降」做成可量化的 ROI，再扩成跨平台素材图与归因层。
