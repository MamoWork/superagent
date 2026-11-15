# 选定项目：短视频自动字幕工具（CaptionSnap）

> 注：本文是最初的 24 小时 MVP 选题练习。后续调研发现“CapCut 自动字幕收费”这一前提不够稳固，方向已升级为 Opportunity Scout（机会发现 → 判断 → 获取闭环），详见 `business_plan.md`。

## 1. 原帖 Reddit 链接

- 帖子：**Tell me 1 tool you need and ill go looking for either an opensource or cheap solution**
- 链接：https://www.reddit.com/r/indiehackers/comments/1g8qqqi/tell_me_1_tool_you_need_and_ill_go_looking_for/
- 需求来源：帖子下 `u/projectmind_guru` 的评论：
  > "Auto captions for short form videos. Used to be free in CapCut now it's $10/ month. Only interested in a free option"

补充佐证（同批帖子中的市场信号）：
- r/ChatGPT 帖子下最高赞评论吐槽现有 AI 工具"不免费 / 假免费 / 上传受限 / 根本不好用"，说明用户对"免费、即开即用、无套路"的工具需求明确。
- r/indiehackers 该帖 36 条评论，是这批结果中互动最集中的真实需求帖；其余多为工具导航站自荐，评论区已有"这是本周第 5 个同类网站"的疲劳信号，不适合再做导航站。

## 2. 用户的核心痛点

**目标用户**：TikTok / Instagram Reels / YouTube Shorts 的短视频创作者、口播博主、小型内容代运营团队。

**痛点**：
1. **字幕是刚需**：短视频 80% 以上是静音观看场景，没有字幕直接损失完播率和涨粉；平台算法也偏好带字幕内容。
2. **原本免费的能力被收费**：CapCut 的自动字幕从免费改为约 $10/月，用户被迫寻找替代品。
3. **现有替代品门槛高**：Submagic、Veed、Captions 等工具月费 $16–$40，强制注册、上传大小受限、导出带水印，偶尔处理一次的用户不愿意为此订阅。
4. **交付形态要"能直接发"**：创作者要的不是一段 SRT 文本，而是**已经烧录好字幕的 MP4**，能直接上传 TikTok/Reels。

**付费意愿**：短视频创作者是已被市场教育过的付费人群（CapCut Pro、Submagic 等按月付费已普遍）。该评论者个人只想要免费，但整体市场对"按次付费 + 首条免费"的接受度高。变现建议：**第一条免费，之后按次付费（如 $5/5 条）或 $9/月**，避开"必须订阅"的心理门槛。

**24 小时可交付的理由**：核心链路只有"上传视频 → Whisper 转写 → 生成时间轴 → ffmpeg 烧录字幕 → 下载"，全部是成熟 API + 成熟命令，无需训练模型、无需复杂前端。

## 3. 极简网页工具（MVP）核心功能逻辑

### 产品定位

单页 Web 工具，**无需注册即可处理第一条视频**。用户拖入一个 ≤60 秒的竖屏短视频，选择语言和字幕样式，点击生成，预览后下载带字幕的 MP4（可同时下载 SRT）。

### 核心流程

```
上传视频 → 选择语言/样式 → 点击「生成字幕」
→ 后端转写 + 生成 SRT → ffmpeg 烧录 → 预览播放 → 下载 MP4 / SRT
```

### 前端页面元素（按钮 / 输入框 / 控件）

**① 上传区**
- 拖拽上传框（Drag & Drop）
- 「选择视频」按钮（`<input type="file" accept="video/mp4,video/quicktime,video/webm">`）
- 文件限制提示：`MP4 / MOV / WebM，最长 60 秒，最大 100MB`
- 上传后显示：文件名、时长、缩略图（可选）、「移除」按钮

**② 字幕设置区**
- 语言下拉框（`Language`）：自动检测 / English / Español / Português / 日本語 / 中文 — 默认"自动检测"
- 字幕样式下拉框（`Caption Style`）：`TikTok Bold` / `Clean White` / `Classic` — 默认 `TikTok Bold`
- 位置按钮组（`Position`）：`Top` / `Middle` / `Bottom` — 默认 `Bottom`
- 字号滑块（`Font Size`）：小 / 中 / 大 — 默认"中"

**③ 生成与编辑区**
- 主按钮：**「Generate Captions」**（生成中变为 `Transcribing… 42%` 进度态，禁用重复点击）
- 转写完成后出现可编辑文本框（`Transcript`，textarea），用户可修正错别字
- 「Regenerate Video」按钮：按修改后的文本重新烧录
- 预览播放器：`<video>` 播放器 + 实时字幕叠层；提供「Play」/「Pause」控制

**④ 下载与付费区**
- 「Download MP4」按钮（主转化按钮）
- 「Download SRT」按钮（次要按钮）
- 首次使用：下载按钮下方显示 `First video free`
- 第二次点击下载时弹出付费弹窗：
  - 文案：`Unlock more videos`
  - 套餐按钮：`$5 — 5 videos`（一次性）/ `$9/month — Unlimited`
  - 「Continue to Checkout」按钮 → Stripe Payment Link / Lemon Squeezy
  - 支付成功后回到页面自动解锁下载

**⑤ 辅助元素**
- 顶部一句话价值主张：`Auto captions for short videos. No signup. Ready to post.`
- 底部信任说明：`Videos are deleted within 1 hour.`

### 后端核心逻辑（24 小时实现范围）

1. **上传**：接收视频 → 存入临时对象存储（或本地临时目录）→ 返回任务 ID。
2. **转写**：调用 OpenAI Whisper API（`whisper-1` 或 `gpt-4o-transcribe`）拿带时间戳的文本；若需更快的 word-level 时间轴，可用 Deepgram。
3. **生成 SRT**：把转写结果转为标准 SRT 文件。
4. **烧录**：服务端 ffmpeg 执行 `subtitles=` 滤镜，按所选样式/位置/字号输出新 MP4。为控制 24 小时工期，**先支持 1 套内置样式**，样式选择做 2–3 个预设即可。
5. **清理**：临时文件 1 小时后删除（cron 或定时任务）。
6. **付费**：Stripe Payment Link 或 Lemon Squeezy Checkout；用一次性兑换码/邮件收集实现解锁，v1 不做用户系统。
7. **技术栈建议**：Next.js + Tailwind；ffmpeg 跑在一台小 VPS / Railway / Fly.io 上（Vercel Serverless 不适合长时视频处理）；数据库仅需一张"任务 + 支付状态"表（Supabase/Postgres 均可）。

### 明确不做（控制 24 小时范围）

- 不做账号/登录体系
- 不做多视频批量处理
- 不做字幕动画、关键词高亮、emoji 自动插入
- 不做移动端 App
- 不做多语言界面（先英文单语，面向海外用户）

### 24 小时排期建议

| 时段 | 任务 |
|---|---|
| 0–3h | 单页 UI：上传、设置、预览、下载按钮全部静态完成 |
| 3–7h | 接入转写 API，打通"上传 → SRT" |
| 7–12h | ffmpeg 烧录链路，打通"SRT → 带字幕 MP4" |
| 12–16h | 付费墙 + Stripe Payment Link + 下载解锁 |
| 16–20h | 异常处理（超时长/超大文件/转写失败）、清理任务 |
| 20–24h | 落地页文案、部署、发 Reddit / Product Hunt / TikTok 测试首批用户 |

## 筛选理由（为什么是它，而不是其他 9 条）

| 候选 | 判断 |
|---|---|
| 各类"AI 工具导航/搜索"站（第 2、4、5、6、7、9、10 条） | 赛道严重饱和，评论区已出现"本周第 5 个"的嘲讽；用户付费意愿低，24 小时做不出差异化 |
| "Reverse Tool"：把成熟点子反向移植到新细分（第 3 条） | 需求抽象、难以验证，且需要大量数据与模型能力，24 小时不可交付 |
| Linkding + LLM 向量检索书签（第 8 条另一评论） | 面向开发者的小众自托管需求，付费意愿低，工程量大 |
| **短视频自动字幕（第 8 条）** | 痛点高频且具体、现有方案涨价留下空档、交付物"可直接发布"、API + ffmpeg 可在 24 小时内做完 MVP、创作者群体有成熟付费习惯 → **最优** |

**主要风险**：赛道竞争者多（Submagic、CapCut、Veed 等），且原评论者本人只要免费。应对：主打"无需注册 + 首条免费 + 按次付费 + 浏览器/服务端快速出片"，用低价和零门槛切"偶尔做几条视频"的长尾用户；首周在 r/indiehackers、r/NewTubers、r/TikTokCreators 收集 10 条真实反馈验证付费意愿。
