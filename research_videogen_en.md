# AI 生视频（English-language communities）痛点调研

- 调研对象：Opportunity Scout / AI video generation
- 调研日期：2026-11-11
- 证据窗口：2025-01-01 至 2026-11-11（少量更早帖子仅用于对照，不计入频次）
- 语言范围：英文社区一手发言
- 本报告只记录可回溯的原话与链接；无来源的判断统一标注「推断」，不与证据混排。

---

## ① 调研方法与证据边界

### 1.1 渠道执行结果

| 渠道 | 状态 | 实际拿到什么 | 样本量 |
|---|---|---|---|
| Reddit（`agent-reach reddit search`，`backend: public-web`） | 成功 | 帖子正文 + 部分高赞评论 + `published_at` | 32 组关键词/子版检索，去重后 **314 个独立 thread**；其中 **299 个落在 2025-01-01 至 2026-11-11**（2025 年 113 个，2026 年 186 个） |
| YouTube（`yt-dlp --write-comments`） | 成功 | 视频元数据 + 每个视频 40 条评论 | 2 个视频，共 **80 条评论**（2025-10-15、2026-10-13 发布） |
| X / Twitter（`agent-reach twitter search`） | **失败：NEED_LOGIN** | 返回 `Not logged into x.com (no ct0 cookie)`；按只读规则停止，未尝试登录、未换账号 | 0 条站内检索结果 |
| X 单帖（Exa 搜索 + Jina 读取） | 成功 | 1 条长帖全文 | 1 条（2026-03-15） |
| Claude 内置 `WebSearch` | **失败：403** | `Access denied for web search ... Volcano Ark Console` | 0 |
| Claude 内置 `WebFetch` | **失败：域名安全校验** | `Unable to verify if domain ... is safe to fetch` | 0 |
| `agent-reach web search`（Exa 后端） | 成功（降级替代） | 官方文档、论坛帖、评测页索引 | 用于定位，不单独计入用户样本 |
| `agent-reach read`（Jina 后端） | 部分成功 | OpenAI 官网、OpenAI Community、x.com 可读 | 3 个官方页 + 2 个论坛 thread |
| Runway Help Center | **失败：Cloudflare** | 返回 `Just a moment... / Enable JavaScript and cookies` | 0；因此本报告不引用 Runway 官方定价口径，只用用户自述 |
| unrollnow（X 长帖展开服务） | **失败：Cloudflare** | 同上 | 0；改为直接读 x.com 原帖 |
| Discord（官方/社区服务器） | 未采集 | 无公开只读接口，且需邀请与登录 | 0 |
| 小红书 / B站 / V2EX 等中文社区 | 不在本报告范围 | 由另一路调研单独处理 | — |

### 1.2 样本结构

- 子版分布（Top 15）：r/SoraAi 26、r/generativeAI 25、r/StableDiffusion 23、r/VEO3 21、r/KlingAI_Videos 11、r/heygen 10、r/midjourney 10、r/aifilmmaking 7、r/davinciresolve 7、r/aivideos 7、r/OpenAI 7、r/VideoEditors 7、r/Adobe 6、r/premiere 6、r/aivideomaking 6。
- 人群标签（按发帖人自述，非精确统计）：独立创作者/YouTube 频道主、接商单的自由职业剪辑师与小型工作室、广告/品牌代理、短片与 AI 动画团队、企业培训视频制作者、纯爱好者。
- 工具覆盖：Sora / Sora 2、Runway（Gen-4 / Gen-4.5）、Kling（含 Kling 3.0）、Veo 3 / Veo 3.1 / Flow、Seedance 2.0、Hailuo、Pika、Luma Ray 3、Wan、Midjourney Video、Adobe Firefly Video、HeyGen、Synthesia（提及少）、LTX、Higgsfield、PixVerse、Grok Imagine、Freepik/KIE 等聚合器。

### 1.3 证据分级

- **A 级**：可点开的原始帖子/评论/官方文档，含作者、日期、正文；本报告绝大多数引用属此类。
- **B 级**：聚合站转述、二手评测中引用的用户原话，仅用于补充，不单独支撑 P0 结论。
- **C 级**：只能看到标题或摘要、正文被删/被折叠的帖子，只计入频次，不引用原话。
- 「推断」：由多条证据归纳出的判断，单独成段并明确标注，不作为证据。

### 1.4 证据污染与剔除

- r/generativeAI 在 2026 年存在明显的软广/水军痕迹：同一 persona（`u/Jenna_AI`）在大量帖子下以“专业口吻”回复，并在结尾自然植入产品（Morphic、OneOver、CapCut Video Studio、Visual Sandbox 等）；另有 `easyviral`、`OneOver` 等工具在评论中被反复“顺带”推荐。
- 处理：**`u/Jenna_AI` 的全部发言、以及带明确产品导流的评论，不计入独立用户证据**；只保留其中对公开定价/用量的事实性描述，并优先用其他独立帖子交叉验证。
- 厂商自述帖（如 `u/MagnificOfficial` 的 2,591 次生成复盘）按“厂商案例”标注，不作为“用户痛点”证据，只用于说明生产规模。
- 未发现跨平台复制粘贴的同一段文案；但 Reddit 上存在同一作者在多个子版重复发同一帖的情况，已按 thread ID 去重。

### 1.5 方法论限制（必须在解读时打折）

1. Reddit 是**自助取样**：抱怨者更可能发帖，满意者沉默；频次只能说明“被反复提及”，不能外推为总体比例。
2. `public-web` 返回的评论是**部分高赞评论**，不是全量；因此“某帖下有 N 人附和”只能作为下限。
3. 英文社区以北美/欧洲用户为主，价格与可用性判断不适用于所有地区。
4. 日期取帖子 `published_at`；评论日期取 Reddit 展示的相对/绝对时间，个别只精确到日。
5. 部分帖子正文含推广链接，已剔除；但无法完全排除“看起来很真诚的软广”，P0 结论均要求 ≥3 个互不相关的来源。

---

## ② 痛点清单（P0 / P1 / P2）

分级口径：
- **P0**：高频出现，且直接阻断“可用交付”或“持续付费”；不解决就无法从玩具进入生产。
- **P1**：高频但存在可绕过的 workaround；影响效率与毛利，不直接判死刑。
- **P2**：长尾、人群较窄，或已进入平台功能路线图。

频次信号写法：「N 条独立讨论」= 去重后互不相关的 thread/评论条数（同一作者跨版重复只算 1）；括号内为涉及子版数。

---

### P0-1 角色 / 风格一致性：跨镜头就“换演员”

**频次信号**：≥15 条独立讨论，跨 8 个子版（r/aivideos、r/StableDiffusion、r/aivideomaking、r/Seedance_AI、r/generativeAI、r/VEO3、r/KlingAI_Videos、r/aifilmmaking），是全部痛点中交叉验证最强的一条。

**原话**

> "Here I feel like I'm re-casting the same character every shot." — u/Pristine_Moose_4482, r/aivideos, 2026-07-13, https://www.reddit.com/r/aivideos/comments/1uv3otr/character_consistency_falls_apart_across_shots_on/

> "By clip 3 the face drifted. By clip 5 the jacket changed color and the hair looked different. Same prompt structure. same reference image. Completely different person." — u/ke1lle, r/StableDiffusion, 2026-07-13, https://www.reddit.com/r/StableDiffusion/comments/1uvamx5/same_character_5_ai_clips_5_different_faces/

> "Facial features would change, clothing would change, body proportions would drift, and occasionally entirely new features would appear." — u/the-real-neil, r/generativeAI, 2026-06-29, https://www.reddit.com/r/generativeAI/comments/1uiskc4/we_made_video_content_entirely_with_ai_for_6/

> "Kling was the fastest to a usable shot and the worst on continuity, I lost the character by the third episode both times I tried." — u/Putrid_Job6390, r/aivideomaking, 2026-09-20, https://www.reddit.com/r/aivideomaking/comments/1wlwnp4/is_there_an_ai_video_tool_that_can_keep_the_same/

> "by the third one she basically had a new nose and a different hoodie. Fine for one pretty frame, useless if you want a little sequence that reads as one person." — u/Sniper_yoha, r/Seedance_AI, 2026-08-03, https://www.reddit.com/r/Seedance_AI/comments/1ve9exo/my_ai_characters_kept_morphing_between_shots_so_i/

> "the brass knuckles jumping from one hand to both hands between shots is exactly the kind of tiny continuity slip that ruins a client job" — YouTube 评论 @dianavintagestylist1934, 2026-10-22, https://www.youtube.com/watch?v=ktEt4n9VlF4

> "Multi-character exchanges, long sequences, maintaining visual continuity across shots, keeping tone, pacing, and staging consistent… it's not impossible, but it is still a lot of work." — @henrydaubrez, X, 2026-03-15, https://x.com/henrydaubrez/status/2033237370758459892

**受影响人群**：做系列内容/短片的独立创作者、接品牌商单的自由职业者、AI 动画团队；对“同一角色多镜头”的叙事类项目是硬阻断。

**为什么难**：用户已试过参考图、三视图、提示词锁定、换模型，仍会在第 3–5 个镜头漂移（见 1uvamx5、1smtzb9）。多数 workaround 本质是“把一致性降级为剪辑问题”（先生成关键帧再逐段生成）。

---

### P0-2 可用率 / 抽卡：演示之外的真实产出比

**频次信号**：≥11 条独立讨论，跨 7 个子版；出现了多个可量化的自述数据。

**原话**

> "My actual week was 38 generations, six usable clips, and one character whose watch kept switching wrists." — u/popypep, r/aivideomaking, 2026-09-17, https://www.reddit.com/r/aivideomaking/comments/1wiwna3/ai_video_demos_are_hiding_the_part_where_you_make/

> "Seedance 2 - sometimes 5-6, especially with multi-character scenes" — u/Wazir-AI, r/grok, 2026-06-22, https://www.reddit.com/r/grok/comments/1ucqbwg/honest_question_how_many_generations_does_it/

> "tbh i usually burn 3–5 gens before one feels usable, mostly fixing the first scene." — u/avatar0027, r/ContentCreators, 2026-09-08, https://www.reddit.com/r/ContentCreators/comments/1wahwy1/how_many_ai_video_rerolls_do_you_usually_need/

> "it has so many generation bugs it needs 10 generations before you get a useable clip." — u/adrian-smith31, r/VEO3, 2026-04-11, https://www.reddit.com/r/VEO3/comments/1sikoxl/disappointed_in_veo_flow/

> "It takes hours of iterations to generate a useful 10 seconds." — u/GoliathGrouper_0417, r/OpenAI, 2025-10-14, https://www.reddit.com/r/OpenAI/comments/1o632p0/sora_2_disappointments/

> "2,591 generations"（为一个短片项目）— u/MagnificOfficial（厂商自述，仅作规模参考）, r/magnific, 2026-07-28, https://www.reddit.com/r/magnific/comments/1v8yb1w/we_made_an_ai_short_film_where_the_lead_ages_from/

> "You gotta run the same prompt sometimes a few times... You gotta roll the dice a few times" — YouTube 评论 @artvsmachine, https://www.youtube.com/watch?v=J5_8ugu8mVw

**受影响人群**：所有人；对按条报价的商单影响最大——重试成本无法转嫁给客户。

**关键细节**：用户不是不知道“多抽几次”，而是**没有预算/时间抽**。这条与 P0-3 成本、P1-4 排队强耦合，构成“越穷越抽不起，越抽不起越交不了货”的负循环。

---

### P0-3 成本 / 积分：按秒计费 + 失败不退 + 套餐缩水

**频次信号**：≥14 条独立讨论，跨 8 个子版；包含 2 条官方论坛的账单申诉与 1 条明确“失败不退”的帖子。

**原话**

> "About... FIVE SHORT (<10s) videos later, i ran out of my credits for the month. I wasn't even able to get 1 minute of video (if i stitched everything up) for this much money." — u/Extension_Virus2766, r/generativeAI, 2026-08-25, https://www.reddit.com/r/generativeAI/comments/1vxzwfk/really_bad_experience_with_runway_pro_plan_avoid/

> "I generated about 15 seconds and somehow used almost HALF my credits" — u/evina_27, r/aivideomaking, 2026-09-29, https://www.reddit.com/r/aivideomaking/comments/1wtfc2c/runway_credits_are_crazy_what_are_you_using_for/

> "1min video is barely 28$... before event getting something good." — u/Frosty-Specific4977, r/generativeAI, 2026-05-03, https://www.reddit.com/r/generativeAI/comments/1t2jrcn/runway_pricing_how_are_ppl_making_this_work/

> "I get that it's powerful, but I'm still learning and I feel like I'm paying for my mistakes." — u/jono440, r/creators, 2026-06-27, https://www.reddit.com/r/creators/comments/1ugx9ih/ive_been_using_runway_to_experiment_but_my/

> "a 8s generation failed at 87% of completion and… voiloà 4$ pulverized." — u/nickthblde, OpenAI Community, 2025-10-07, https://community.openai.com/t/sora-2-api-charges-money-on-failed-run-at-100-progress/1361332

> "I paid for $50 in credits and have already lost several credits with no actual video produced... credits are just compute requests" — u/devjordan, OpenAI Community, 2025-11-08, https://community.openai.com/t/credits-charged-for-pre-compute-moderation-blocks/1365628

> "I just burned through 10-15k of credits making vids. Videos didn't generate, and I deleted the failed generations. Looking at my remaining credits.....it's wayyyyy lower. Hence, there are no refunds." — u/WHiteMage_BLackMage, r/leonardoai, 2026-08-10, https://www.reddit.com/r/leonardoai/comments/1vkztv5/no_refunds_for_videos/

> "Google changed their pricing tiers part way through my subscription... my AI credits have been reduced to 200 a month from 1000." — u/adrian-smith31, r/VEO3, 2026-04-11, https://www.reddit.com/r/VEO3/comments/1sikoxl/disappointed_in_veo_flow/

> "When many signed up, the published Terms of Service clearly stated that Veo 3.1 Fast Generations cost 0 credits... It's essentially a bait and switch." — u/No-Aardvark-3840, r/VEO3, 2025-11-19, https://www.reddit.com/r/VEO3/comments/1p1koke/i_would_encourage_everyone_here_to_follow_up_with/

**受影响人群**：自费创作者、按项目报价的小工作室、用 API 搭自动化流程的开发者。

**结构性成因**（推断）：生成成本与“抽卡次数”线性相关，而平台把失败/审核拦截也计入算力消耗；用户无法区分“我 prompt 差”与“平台在烧我钱”，导致信任崩塌。

---

### P0-4 可控性：构图、运镜、动作、首尾帧都不听使唤

**频次信号**：≥9 条独立讨论，跨 6 个子版；与 P0-1 高度相关但可区分——一致性是“人变了”，可控性是“镜头/动作/构图不按指令走”。

**原话**

> "the model starts with my image but then generates random motion that ruins the blocking or changes the subjects identity by the end of the clip." — u/SufficientTomato916, r/aivideos, 2026-03-23, https://www.reddit.com/r/aivideos/comments/1s1g7g5/how_do_you_stop_your_ai_video_from_drifting_away/

> "character consistency / composition drifting / motion not following the prompt / camera behavior changing unexpectedly / references not being followed / shots looking good individually but not matching each other" — u/Boring-Today-8244, r/aivideomaking, 2026-09-22, https://www.reddit.com/r/aivideomaking/comments/1wn93m1/titlewhat_usually_makes_you_regenerate_an_ai/

> "it felt like too much of a gamble to get everything right in one-shot basically." — u/danielpartzsch, r/comfyui, 2026-08-17, https://www.reddit.com/r/comfyui/comments/1vqtgvk/storyboard_to_video_with_minimaxh3_how_do_you/

> "Its not nearly as controllable, doesn't have object references, and is much lower resolution (480p -- you can run it in --hd, which is 720p, but that takes a lot of fast GPU hours)" — u/amp1212, r/midjourney, 2026-06-01, https://www.reddit.com/r/midjourney/comments/1tu26nr/question_how_good_is_midjourney_video_in_2026/

> "no, I tried and didn't work, it keeps generating the video horizontally" — u/razgss, r/runwayml, 2026-01-09, https://www.reddit.com/r/runwayml/comments/1q8d15k/does_gen45_support_916_vertical_video_for/

**受影响人群**：需要精确分镜/品牌构图/竖屏投放的商单；对“图生视频”用户尤其致命——参考图只能锁第一帧，锁不住后半段。

**现状**：首尾帧（first/last frame）是用户公认最有效的控制手段，但并非所有模型/套餐都提供；提供者也常出现“尾帧对了、中间崩了”。

---

### P0-5 商用授权 / 水印 / 版权：付了钱也不一定能商用

**频次信号**：≥9 条独立讨论，跨 6 个子版；叠加官方文档 1 条、YouTube 评论 2 条。

**原话**

> "specifically, without our written persmission, you may not use or make modifications to the output for any commercial purposes" — 用户引述 Kling ToS 4.6，u/beantorres, r/KlingAI_Videos, 2025-06-10, https://www.reddit.com/r/KlingAI_Videos/comments/1l7wkpy/who_owns_the_output_is_it_copyrighted/

> "I'd like to use the ai videos for commerical use.but the watermark ruins that." — u/FurnitureRefinisher, r/SoraAi, 2025-10-18, https://www.reddit.com/r/SoraAi/comments/1oa5ecz/whats_up_with_the_strict_watermark_guidelines_can/

> "Today I used Flow with Veo quality to generate a video, and it cost 100 credits. After the video was generated, I noticed a Veo watermark in the bottom-right corner." — u/Due_Entrepreneur1546, r/GeminiAI, 2026-07-19, https://www.reddit.com/r/GeminiAI/comments/1v0t7i8/google_ai_pro_veo_watermark_can_paid_users_remove/

> "If you're delivering generated output, there are licensing implications the client genuinely needs to know about. The output isn't..." — u/Madmahi25, r/aitubers, 2026-08-25, https://www.reddit.com/r/aitubers/comments/1vxx62e/we_lost_a_pitch_to_an_agency_quoting_a_tenth_of/

> "if you use them it seems to add an 'Ai' watermark. Is there any way around this? I've got a Pro version." — u/isaacpriestley, r/CapCut, 2026-04-07, https://www.reddit.com/r/CapCut/comments/1sf3813/remove_the_ai_watermark/

> "all outputs carry a visible watermark" — OpenAI 官方, 2025-09-30（页面注明 Sora 产品已于 2026-04-26 下线）, https://openai.com/index/launching-sora-responsibly/

**受影响人群**：代理商、自由职业者、想把 AI 素材上架 stock 平台的人、需要向客户做合规披露的团队。

**关键矛盾**：平台用“水印/不可商用”规避责任，用户用“付费即商用”的直觉理解产品；两者之间的落差没有一处被清晰解释，导致退款、差评与灰色去水印产业。

---

### P0-6 审核误杀：正常创作被随机拦截，且发生在生成之后

**频次信号**：≥11 条独立讨论，跨 6 个子版；r/SoraAi 的相关帖出现 98 赞/65 评论的高互动，说明共鸣面大。

**原话**

> "content restrictions are so tight that you basically can’t generate anything anymore because 'this video may violate content policies' with no explanation behind it." — u/TheOnlyShyG, r/SoraAi, 2026-03-02（98 赞/65 评论）, https://www.reddit.com/r/SoraAi/comments/1rif15f/sora_is_officially_unusable_i_quit/

> "I’m talking normal prompts. Basic story beats. Everyday scenes. Stuff you would show your kid... You can type one thing, it blocks. You reword it slightly, it runs. Then you try the same exact prompt later and it blocks again. It feels random." — u/Suitable_Goose3637, r/SoraAi, 2025-12-24, https://www.reddit.com/r/SoraAi/comments/1pusqlb/sora_2_flags_normal_prompts_so_often_its/

> "if I use Japanese text and a character holds a sword, the AI automatically associates it with 'Demon Slayer' and flags it, even though it's my original character." — u/Agitated_Guidance992, r/SoraAi, 2026-02-05, https://www.reddit.com/r/SoraAi/comments/1qw8u3g/the_biggest_problem_with_sora_2_is_its_stupid_ai/

> "Some of the images I used were the exact same images I have used in the past (without error)." — u/RandomUserName14227, r/KLING, 2025-09-21, https://www.reddit.com/r/KLING/comments/1nmpljr/generation_failed_as_the_content_includes/

> "The reference image is unsafe (it’s not) / The prompt is considered unsafe (it’s not)" — u/Cheesy_crumpet, r/AdobeFireflyCommunity, 2026-01-02, https://www.reddit.com/r/AdobeFireflyCommunity/comments/1q1pjvr/started_off_really_good_but_suddenly_unable_to/

> "Their content moderation is too aggregious. Like it was flagging my character. My OC character that's pre pre ai. I own the IP." — YouTube 评论 @mattstaab6399, 2025-11-12, https://www.youtube.com/watch?v=J5_8ugu8mVw

> "I can't even generate anthro videos because of 'third party' content... they're too restrictive" — YouTube 评论 @ScoutChaseTV, 2026-01-12, https://www.youtube.com/watch?v=J5_8ugu8mVw

**受影响人群**：动画/同人/游戏向创作者、非英语文化题材、需要稳定批量产出的团队。

**最恶劣的细节**：拦截常发生在**生成完成之后**（1rif15f），算力已消耗、积分已扣；用户既拿不到视频，也拿不到解释，还拿不到退款——这一条同时命中 P0-3 与 P0-6。

---

### P1-1 时长 / 叙事：5–10 秒的原子镜头拼不成故事

**频次信号**：≥9 条独立讨论，跨 6 个子版；2026 年下半年出现多篇“长片复盘”，说明需求已从“玩票”转向“长内容”。

**原话**

> "I’m struggling to figure out how to make a full 10-15 min video with lip sync or uploaded audio since Kling, Veo3, and Hailuo all cap at 10 seconds... without generation 200+ prompts and piecing it together 10 seconds at a time?" — u/Rellevant1, r/Bard, 2025-06-25, https://www.reddit.com/r/Bard/comments/1ljus4t/longer_videos_than_10_sec/

> "Since Veo generates clips that are roughly 8 seconds long, anything longer requires stitching together multiple generations. That's where consistency became difficult." — u/the-real-neil, r/generativeAI, 2026-06-29, https://www.reddit.com/r/generativeAI/comments/1uiskc4/we_made_video_content_entirely_with_ai_for_6/

> "Just completed a 12 minute video. 148 shots. 7 tracks of audio in addition to dialogue." — u/AlfieSchmalfie, r/generativeAI, 2026-09-23, https://www.reddit.com/r/generativeAI/comments/1wog53q/how_are_people_making_long_ai_generated_videos/

> "Nobody is generating a long video in one shot. Scripts become a shot list, then a pile of 5–15s clips, then an edit." — u/kaboom-o, r/generativeAI, 2026-09-24, 同上

> "Each film is roughly an hour long and was assembled from thousands of individually generated short clips." — u/bdylsing, r/aivideos, 2026-09-10, https://www.reddit.com/r/aivideos/comments/1wcy62m/i_somehow_ended_up_making_seven_hourlong_ai_films/

> "Short clips are easy. Worldbuilding is not. And storytelling is still the hardest part." — @henrydaubrez, X, 2026-03-15, https://x.com/henrydaubrez/status/2033237370758459892

**受影响人群**：短片/系列剧/长视频频道；对广告与短视频影响较小。

**性质判断**：这条**不是纯模型能力问题**。即便单段能生成 30 秒，叙事仍需要分镜、连续性、节奏与声音设计；真正的缺口在“把碎片组织成片子”的生产系统，而非“更长的单次生成”。

---

### P1-2 音频 / 对白 / 口型：谁在说话、说了什么、有没有眨眼

**频次信号**：≥10 条独立讨论，跨 5 个子版（r/VEO3、r/GeminiAI、r/heygen、r/Bard、r/generativeAI）。

**原话**

> "Often a single line of dialogue will drift back and forth between two characters. Or just totally be delivered by the wrong character." — u/refriedi, r/VEO3, 2025-08-14, https://www.reddit.com/r/VEO3/comments/1mprm33/help_with_wrong_characterspeechdialogue/

> "Veo 3.1 very often swaps the dialogue lines. I tried everything - naming the character (JOHN, DOCTOR), visually identifying the character... nothing works always. It's hit or miss." — u/nanji200, r/VEO3, 2025-12-30, https://www.reddit.com/r/VEO3/comments/1pzs0wf/dialogue_challenge_in_veo_31/

> "wrong character speaking / dialogue swapping / lip sync mismatch / characters interrupting each other randomly / one character suddenly disappearing from conversational logic" — u/Optimal_Oven_3332, r/VEO3, 2026-05-28, https://www.reddit.com/r/VEO3/comments/1tptw4v/how_to_handle_multiple_characters_dialogue/

> "my avatars never blink. Never. Not a single blink in the entire video... after a few seconds the fixed stare looks unnatural and viewers notice." — u/Sea_Investment138, r/heygen, 2026-08-24, https://www.reddit.com/r/heygen/comments/1vx7sii/my_heygen_avatars_never_blink_not_once_anyone/

> "for Avatar 5... over exaggerating the lip movements and head movements. They look nice but they look AI at the same time." — u/Chance-Obligation573, r/heygen, 2026-04-28, https://www.reddit.com/r/heygen/comments/1sxrex1/avatar_v_lip_and_head_movements_gone_wrong/

> "Voice consistency was also surprisingly difficult. Even when a character looked mostly correct, accents, speech patterns, and delivery would often change between clips." — u/the-real-neil, r/generativeAI, 2026-06-29, https://www.reddit.com/r/generativeAI/comments/1uiskc4/we_made_video_content_entirely_with_ai_for_6/

> "In some videos the character speaks in some dont even why the prompt is the same. Some videos come out with no audio at all." — u/BarFickle2272, r/Bard, 2025-06-01, https://www.reddit.com/r/Bard/comments/1l0thrn/how_can_i_make_the_character_speak_on_veo_3/

**受影响人群**：口播/数字人/培训视频/多角色剧情；对纯 B-roll 用户影响小。

**可绕过性**：单角色旁白可后期配音；多角色同框对白目前几乎无稳定解法，属于 P0 级体验（但人群窄，故列 P1）。

---

### P1-3 编辑 / NLE 工作流：帧率、时长、命名、版本全对不上

**频次信号**：≥10 条独立讨论，跨 6 个子版（r/generativeAI、r/premiere、r/VideoEditors、r/davinciresolve、r/aifilmmaking、r/StableDiffusion）。

**原话**

> "as soon as you process something through the model, it comes back in 24 fps… It throws off the entire sync: audio / lipsync / editing timeline / overall timing" — u/h3rve, r/generativeAI, 2026-05-07, https://www.reddit.com/r/generativeAI/comments/1t67zac/25_fps_users_how_are_you_dealing_with/

> "the AI clip has replaced the original clip in timeline with edited parts etc, but nothing matches cause the AI clip is longer than original clip." — u/Robeloto, r/premiere, 2026-01-16, https://www.reddit.com/r/premiere/comments/1qec88n/upscaled_ai_clip_does_not_match_the_original_clip/

> "short answer: fine for the rough cut, falls apart on revisions, and you cannot hand the output straight to a client." — u/Express_Map9176, r/VideoEditors, 2026-09-04, https://www.reddit.com/r/VideoEditors/comments/1w7achv/can_you_actually_use_ai_editing_on_paid_client/

> "AI production spits out files faster than any other kind: scripts, references, prompts, raw generations, edits, versions. Without a system you lose the good take by week two." — u/MagnificOfficial（厂商案例）, r/magnific, 2026-07-28, https://www.reddit.com/r/magnific/comments/1v8yb1w/we_made_an_ai_short_film_where_the_lead_ages_from/

> "Handing off assets, assigning scenes / shots, receiving them back, marking them as complete, etc…?" — u/danoncano, r/aifilmmaking, 2026-07-23, https://www.reddit.com/r/aifilmmaking/comments/1v4gtz9/collaborating_with_a_team/

> "It automatically renames messy AI-generated files (those 'generation_img2343_heres-half-your-prompt' nightmares)" — u/Storybook_Albert, r/StableDiffusion, 2025-07-20, https://www.reddit.com/r/StableDiffusion/comments/1m4m9u5/shotbuddy_an_open_source_tool_for_managing_i2v/

**受影响人群**：所有进入后期的人；对 25fps 广播/广告交付、需要 round-trip 到 PR/AE/Resolve 的用户是硬伤。

**隐藏成本**：不是“AI 不会剪”，而是 AI 产出的素材**缺少可被 NLE 消费的元数据**（帧率、时码、镜头号、版本、色彩空间），导致每次都要手工对齐。

---

### P1-4 速度 / 排队 / 限流：付费也躲不过的等待

**频次信号**：≥8 条独立讨论，跨 6 个子版；含“无限套餐被节流”的明确指控。

**原话**

> "going from 20 minutes in the queue to 30, to 50 and now I'm at a little over an hour for every video." — u/ResponsibleFix66, r/runwayml, 2026-05-08, https://www.reddit.com/r/runwayml/comments/1t71pm3/brutal_throttling/

> "im getting queued for 10m for every video VEO 3.1 fast." — u/Stunning_Pack_4636, r/VEO3, 2026-05-14, https://www.reddit.com/r/VEO3/comments/1tctmfr/im_getting_queued_for_10m_for_every_video_veo_31/

> "Some of my video tasks stayed in the Unlimited queue for 6–10+ hours. Some tasks took 12–24 hours." — u/Ordinary_Ad1942, r/generativeAI, 2026-06-12, https://www.reddit.com/r/generativeAI/comments/1u3o9cc/my_loova_max_annual_experience_unlimited_queued/

> "every video takes at least 5 min to generate, which is very frustrating." — u/Consistent_Aspect_43, r/HiggsfieldAI, 2025-10-16, https://www.reddit.com/r/HiggsfieldAI/comments/1o82kfk/queue_time_too_long_on_models_with_unlimited/

> "48+ Hours Video Generation Que" — u/AltraVR, r/civitai, 2025-06-08（23 赞）, https://www.reddit.com/r/civitai/comments/1l6f5b1/48_hours_video_generation_que/

> "I'm frequently instantly getting 'Failed - We noticed some unusual activity' error when using the Fast [Lower Priority] mode... Seems to be google just throttling me, forcing me to either spend credits or go to the Lite mode" — u/Sephy_winz, r/VEO3, 2026-05-08, https://www.reddit.com/r/VEO3/comments/1t6zp65/constant_we_noticed_some_unusual_activity_errors/

**受影响人群**：批量产出/日更/接急单的人；“无限套餐”用户被反向节流，心理落差最大。

---

### P1-5 供应商 / 平台风险：模型下线、转售商跑路、套餐中途改规则

**频次信号**：≥7 条独立讨论 + 3 条官方文档；Sora 关停是 2026 年最强的单一事件。

**原话**

> "The Sora 2 models and Videos API were shut down on September 24, 2026... No one-to-one replacement API is available." — OpenAI 官方文档, https://developers.openai.com/api/docs/guides/video-generation

> "Sora is no longer available." — OpenAI 官方页面（并注明"As of April 26, 2026, the Sora product is no longer available."）, https://openai.com/index/launching-sora-responsibly/

> "The Sora app closed in April, and OpenAI's help page gave September 24 as the date the API goes too... 70 of them listed Sora... 31 still offer Sora as a model you can pick" — u/Tanmay_Vermaa, r/OpenAI, 2026-09-28, https://www.reddit.com/r/OpenAI/comments/1wsf2ih/the_sora_api_was_due_to_shut_down_sept_24_i/

> "Then it stops. One video fails with an error. Next one too. After three days, jobs wait forever... Now 15 days gone. I miss deadlines. Clients leave. Lost $50." — u/gobhalla, r/n8n, 2026-03-10, https://www.reddit.com/r/n8n/comments/1rpo4l7/sora_2_on_kie_ai_broke_my_work_need_a_new_tool/

> "the 'unlimited' thing is basically a lie... after you use it for a while, you hit this 'battery' system where you get throttled and then locked out entirely until you pay an extra $5" — u/Gold-Alternative9327, r/generativeAI, 2026-03-16, https://www.reddit.com/r/generativeAI/comments/1rvaj50/my_honest_experience_with_higgsfield_after_4/

> "I kind of wish Sora still around... I was working on a couple of prototype stories that I wish I could've completed." — YouTube 评论 @FallenAngel-y3o, 2026-09-12, https://www.youtube.com/watch?v=J5_8ugu8mVw

> "it is not available in my region, and when I was able to enter using a VPN it no longer let me generate anything" — YouTube 评论 @by-thalen, https://www.youtube.com/watch?v=J5_8ugu8mVw

**受影响人群**：把 AI 视频接进生产管线/自动化（n8n、API）的开发者与团队；对只做单条创意的个人影响较小。

**性质判断**：这不是“用户体验”问题，而是**采购与架构风险**。任何依赖单一闭源模型的产品，都必须假设“模型会在 18 个月内消失/涨价/改条款”。

---

### P2-1 团队协作 / 审片 / 版本管理

**频次信号**：≥6 条独立讨论，跨 5 个子版；多为“求工具/求流程”，说明品类尚未形成标准工具。

**原话**

> "I will be creating radio edits of vocal performances, animatics, and storyboards for my AI artists. Then handing off 'scene assets' to them... What apps / workflows have you guys used successfully to manage a process like this?" — u/danoncano, r/aifilmmaking, 2026-07-23, https://www.reddit.com/r/aifilmmaking/comments/1v4gtz9/collaborating_with_a_team/

> "Video review process with clients is killing my sanity. How do you guys handle feedback?" — u/CommercialMind8536, r/editors, 2026-02-16, https://www.reddit.com/r/editors/comments/1r6ens2/video_review_process_with_clients_is_killing_my/

> "a lot of people don't realise that AI will give you infinite changes because it's sole purpose is for you to be dependant on it and appear useful" — u/PackageBulky1, r/videography, 2026-09-21, https://www.reddit.com/r/videography/comments/1wmai8r/close_to_adding_an_ai_feedback_clause_to_my/

> "Version Management: Replace old generations with new ones while automatically archiving previous versions throughout the entire pipeline" — u/Storybook_Albert, r/StableDiffusion, 2025-07-20, https://www.reddit.com/r/StableDiffusion/comments/1m4m9u5/shotbuddy_an_open_source_tool_for_managing_i2v/

**受影响人群**：3 人以上的 AI 动画/短片团队、代理商的制作组。

**现状**：用 Notion/ClickUp/Frame.io/网盘硬拼；缺“镜头级”的资产、takes、审批状态与可追溯版本。

---

### P2-2 专业 vs 小白预期错位 / 客户对“AI 味”的排斥

**频次信号**：≥7 条独立讨论，跨 6 个子版；这是“卖不卖得出去”的问题，不是“做不做得出”的问题。

**原话**

> "My boss... thought the process was basically: come up with an idea, type a prompt, wait a few minutes, and the video is done. I wish it worked that way." — u/Sensitive_Signal_339, r/ArtificialInteligence, 2026-09-22, https://www.reddit.com/r/ArtificialInteligence/comments/1wn477j/my_boss_saw_an_ai_demo_and_thought_we_could_make/

> "In the 50-odd videos I've created since AI reared its head, I've used AI-generated media 3 times." — u/Xxviii_28, r/videography, 2025-06-19, https://www.reddit.com/r/videography/comments/1lf8lba/are_aigenerated_videos_reliable_enough_for_client/

> "first reaction was 'wow.' about ten seconds later: 'But why does this look fake?'... it just had that thing where every individual element is right and the whole is slightly off." — u/BrynleeCampbell, r/marketingagency, 2026-09-24, https://www.reddit.com/r/marketingagency/comments/1wop7ad/an_agency_i_know_claims_they_almost_lost_a_client/

> "AI-generated videos almost always look cheap and clunky... I haven’t seen a single piece that feels truly editorial, high-budget, or indistinguishable from real production." — u/Pale_Caregiver_3875, r/VideoProfessionals, 2025-09-10, https://www.reddit.com/r/VideoProfessionals/comments/1ndb5r4/ai_videos_look_cheap_and_unprofessional_for_any/

> "Mentioned casually that one establishing shot was AI and suddenly they wanted to 'discuss it further' even though nothing about the actual footage changed." — u/Batson_Beat, r/MotionDesign, 2026-01-28, https://www.reddit.com/r/MotionDesign/comments/1qpetha/getting_clients_comfortable_with_ai_video/

**受影响人群**：乙方/代理/自由职业者；企业内训视频负责人。

**关键洞察**：客户的抵触很多时候**与画质无关**，而与“是否披露”“版权归属”“像不像廉价货”有关——这为“合规/披露”类产品留出空间（见 §5）。

---

### P2-3 字幕 / 多语言 / 口音

**频次信号**：≥3 条独立讨论，集中在 r/VideoEditingTips、r/Bard、r/GeminiAI；样本较小，但对特定人群是每日摩擦。

**原话**

> "they regularly get words wrong when there’s an accent, non-native speaker, or even just fast talking / mumbling... I still end up having to re-listen to the whole thing and fix a bunch of words" — u/Valuable_Iron_2890, r/VideoEditingTips, 2026-08-03, https://www.reddit.com/r/VideoEditingTips/comments/1veoh9n/anyone_else_still_manually_fixing_ai_captions/

> "sometimes they just say the English translation of what I wrote" — u/rascian038, r/GeminiAI, 2025-09-29, https://www.reddit.com/r/GeminiAI/comments/1ntr6wl/characters_keep_switching_up_lines_in_veo_any_way/

---

### P2-4 格式 / 分辨率 / 平台适配

**频次信号**：≥4 条独立讨论；与 P1-3 有重叠，单列是因为它直接影响投放。

**原话**

> "Does Gen-4.5 support 9:16 vertical video... no, I tried and didn't work, it keeps generating the video horizontally" — u/razgss, r/runwayml, 2026-01-09, https://www.reddit.com/r/runwayml/comments/1q8d15k/does_gen45_support_916_vertical_video_for/

> "much lower resolution (480p -- you can run it in --hd, which is 720p, but that takes a lot of fast GPU hours)" — u/amp1212, r/midjourney, 2026-06-01, https://www.reddit.com/r/midjourney/comments/1tu26nr/question_how_good_is_midjourney_video_in_2026/

---

### 2.5 痛点优先级总表

| 级别 | 痛点 | 独立讨论数 | 子版数 | 是否可短期绕过 | 主要受害人群 |
|---|---|---|---|---|---|
| P0 | 角色/风格一致性 | ≥15 | 8 | 部分（关键帧+剪辑） | 叙事/系列/商单 |
| P0 | 可用率/抽卡 | ≥11 | 7 | 否（只能多抽） | 所有人 |
| P0 | 成本/积分/失败不退 | ≥14 | 8 | 部分（换便宜模型） | 自费者/小工作室 |
| P0 | 可控性（构图/运镜/首尾帧） | ≥9 | 6 | 部分（首尾帧） | 商单/竖屏投放 |
| P0 | 商用授权/水印/版权 | ≥9 | 6 | 否（法律风险） | 代理/自由职业 |
| P0 | 审核误杀 | ≥11 | 6 | 否（只能换词/换模型） | 动画/同人/非英语 |
| P1 | 时长/叙事 | ≥9 | 6 | 是（分镜拼装） | 长片/系列 |
| P1 | 音频/对白/口型 | ≥10 | 5 | 部分（后期配音） | 口播/数字人/剧情 |
| P1 | 编辑/NLE 工作流 | ≥10 | 6 | 是（手工对齐） | 后期/交付 |
| P1 | 速度/排队/限流 | ≥8 | 6 | 否（等或加钱） | 批量/日更/急单 |
| P1 | 供应商/平台风险 | ≥7 | 5 | 否（多模型冗余） | 开发者/团队 |
| P2 | 团队协作/审片/版本 | ≥6 | 5 | 是（通用工具硬拼） | 3 人以上团队 |
| P2 | 专业 vs 小白预期/“AI 味” | ≥7 | 6 | 部分（靠人审） | 乙方/企业 |
| P2 | 字幕/多语言/口音 | ≥3 | 3 | 是（人工校对） | 口播/访谈 |
| P2 | 格式/分辨率/竖屏 | ≥4 | 3 | 是（裁切/放大） | 社媒投放 |

---

## ③ 按工具 / 场景的痛点分布

### 3.1 按工具

| 工具 | 该工具下最集中的痛点 | 代表性证据（日期 / URL） |
|---|---|---|
| **Sora / Sora 2** | 审核误杀（最烈）；生成后拦截且不解释；积分从 30 降到 10；水印与商用限制；产品/API 关停 | 2026-03-02 https://www.reddit.com/r/SoraAi/comments/1rif15f/ ；2025-12-24 https://www.reddit.com/r/SoraAi/comments/1pusqlb/ ；2026-03-23 https://www.reddit.com/r/SoraAi/comments/1s1chwe/ ；2025-10-18 https://www.reddit.com/r/SoraAi/comments/1oa5ecz/ ；官方 https://openai.com/index/launching-sora-responsibly/ |
| **Runway（Gen-4 / 4.5）** | 积分消耗极快、Pro 套餐性价比、Unlimited 被节流、9:16 不生效、首尾帧可用但不够 | 2026-08-25 https://www.reddit.com/r/generativeAI/comments/1vxzwfk/ ；2026-05-08 https://www.reddit.com/r/runwayml/comments/1t71pm3/ ；2026-01-09 https://www.reddit.com/r/runwayml/comments/1q8d15k/ ；2026-03-23 https://www.reddit.com/r/aivideos/comments/1s1g7g5/ |
| **Kling（含 3.0）** | 跨镜头一致性最差（用户点名）、审核误杀、商用 ToS 限制、3.0 容量不足/卡住 | 2026-07-13 https://www.reddit.com/r/aivideos/comments/1uv3otr/ ；2025-09-21 https://www.reddit.com/r/KLING/comments/1nmpljr/ ；2025-06-10 https://www.reddit.com/r/KlingAI_Videos/comments/1l7wkpy/ ；2026-02-06 https://www.reddit.com/r/Freepik_AI/comments/1qxm1c6/ |
| **Veo 3 / 3.1 / Flow** | 8 秒上限、多角色对白串词、套餐中途缩水（1000→200 积分）、水印、排队 10 分钟+ | 2025-08-14 https://www.reddit.com/r/VEO3/comments/1mprm33/ ；2025-12-30 https://www.reddit.com/r/VEO3/comments/1pzs0wf/ ；2026-04-11 https://www.reddit.com/r/VEO3/comments/1sikoxl/ ；2026-07-19 https://www.reddit.com/r/GeminiAI/comments/1v0t7i8/ |
| **Seedance 2.0** | 单镜头质量高但跨镜头漂移；强制 24fps；多角色场景抽卡 5–6 次 | 2026-04-16 https://www.reddit.com/r/aivideos/comments/1smtzb9/ ；2026-08-03 https://www.reddit.com/r/Seedance_AI/comments/1ve9exo/ ；2026-05-07 https://www.reddit.com/r/generativeAI/comments/1t67zac/ |
| **HeyGen** | 数字人不眨眼、Avatar 5 口型/头部过夸张、“像 AI”；口型与音素不同步 | 2026-08-24 https://www.reddit.com/r/heygen/comments/1vx7sii/ ；2026-04-28 https://www.reddit.com/r/heygen/comments/1sxrex1/ |
| **Midjourney Video** | 可控性弱、无 object reference、480p/720p、贵在 GPU 时间；定位是“MJ 静图的衍生” | 2026-06-01 https://www.reddit.com/r/midjourney/comments/1tu26nr/ |
| **Luma Ray 3** | 运镜自然、但一致性/可控性仍不足；多作为首尾帧方案的一部分被提及 | 2026-03-23 https://www.reddit.com/r/aivideos/comments/1s1g7g5/ |
| **Adobe Firefly Video** | 初期惊艳、随后“参考图/提示词不安全”连环拦截；生成失败 | 2026-01-02 https://www.reddit.com/r/AdobeFireflyCommunity/comments/1q1pjvr/ |
| **Higgsfield** | “Unlimited”名义下电池式节流、额外收费；4 个月后流失 | 2025-10-16 https://www.reddit.com/r/HiggsfieldAI/comments/1o82kfk/ ；2026-03-16 https://www.reddit.com/r/generativeAI/comments/1rvaj50/ |
| **Pika / Hailuo / Wan / LTX** | 在“替代品”讨论中被提及；Pika/Hailuo 主要痛点是 10 秒上限与质量不稳定，Wan/LTX 的痛点转为本地部署复杂度 | 2025-06-25 https://www.reddit.com/r/Bard/comments/1ljus4t/ ；2026-09-29 https://www.reddit.com/r/aivideomaking/comments/1wtfc2c/ |
| **聚合器 / 转售商（Freepik、KIE、Loova、Leonardo 等）** | 上游模型挂了仍继续卖；容量不足；失败不退积分；“无限”排队 12–24h | 2026-09-28 https://www.reddit.com/r/OpenAI/comments/1wsf2ih/ ；2026-03-10 https://www.reddit.com/r/n8n/comments/1rpo4l7/ ；2026-06-12 https://www.reddit.com/r/generativeAI/comments/1u3o9cc/ ；2026-08-10 https://www.reddit.com/r/leonardoai/comments/1vkztv5/ |
| **本地 / 开源自建（ComfyUI + Wan/LTX/Minimax）** | 学习曲线、显存、节点编排；换来的是可控与不被限流 | 2026-09-29 https://www.reddit.com/r/aivideomaking/comments/1wtfc2c/ ；2026-08-17 https://www.reddit.com/r/comfyui/comments/1vqtgvk/ |

### 3.2 按场景

| 场景 | 第一痛点 | 第二痛点 | 第三痛点 | 备注 |
|---|---|---|---|---|
| 社媒短视频 / 日更 | 可用率（量） | 速度/排队 | 审核误杀 | 对一致性容忍度高，愿意用“换脸/换背景”规避 |
| 广告 / 电商 / UGC 投放 | 可控性（构图/产品细节） | 成本（按条报价） | 客户对“AI 味”的排斥 | 产品形状/文字/logo 极易崩，常退回实拍 |
| 叙事短片 / 系列剧 | 一致性 | 时长/叙事 | 对白/声音 | 最愿意为“连续性工具”付费的人群 |
| 企业培训 / 数字人 | 口型/眨眼/自然度 | 多语言 | 合规与品牌审批 | HeyGen/Synthesia 的主场，痛点集中在“恐怖谷” |
| 专业后期 / 交付 | 帧率/时码/round-trip | 版本管理 | 商用授权 | 愿为“能进 NLE 的元数据”付费 |
| 纯玩票 / 学习 | 成本 | 积分规则不透明 | 学习曲线 | 价格敏感，流失快 |

### 3.3 跨工具的共性结论

1. **单镜头质量已不是主要矛盾**：2026 年的抱怨几乎都集中在“第二个镜头之后”（一致性、可控性、拼接、成本），而不是“这一帧不好看”。
2. **越“专业”的用户越痛**：业余用户抽到一条能发的就满足；商单用户要为“每一条都稳定”付费，而这正是当前模型最缺的。
3. **平台把风险转嫁给用户**：审核、失败、涨价、下线，成本最终由创作者承担；用户已经形成“不要绑定单一模型”的共识。

---

## ④ 现有 workaround 与替代方案

### 4.1 一致性类

| Workaround | 具体做法 | 代价 | 证据 |
|---|---|---|---|
| 固定参考图 + 三视图 | 每个镜头都上传同一张高分辨率角色图/正侧背三视图 | 只能减缓漂移，3–5 镜头后仍失效 | 2026-07-13 https://www.reddit.com/r/StableDiffusion/comments/1uvamx5/ ；2026-04-16 https://www.reddit.com/r/aivideos/comments/1smtzb9/ |
| 先出关键帧，再逐段 i2v | 用同一角色生成 4–5 张关键帧，再分别生成视频后剪辑 | 镜头间运动不连续，转场靠剪 | 2026-07-13 评论 https://www.reddit.com/r/StableDiffusion/comments/1uvamx5/ |
| 故事板整图 reference-to-video | 把角色画进同一张多格故事板，整图喂给模型当一次任务 | 依赖模型支持多格理解；构图受限 | 2026-08-03 https://www.reddit.com/r/Seedance_AI/comments/1ve9exo/ |
| LoRA / 本地训练 | 为角色训 LoRA，锁脸锁服装 | 需显存、时间；小项目不划算 | 2026-07-13 https://www.reddit.com/r/StableDiffusion/comments/1uvamx5/ |
| 专用“主持人”产品 | 用 Argil 这类“一次设定、每集复用”的数字人 | 只能做 presenter，不能搭场景 | 2026-09-20 https://www.reddit.com/r/aivideomaking/comments/1wlwnp4/ |

### 4.2 可控性 / 时长类

- **首尾帧（first/last frame）**：用户公认唯一能稳定控制“从 A 到 B”的手段，Runway Gen-4、Luma Ray 3、PixVerse 被点名（2026-03-23，https://www.reddit.com/r/aivideos/comments/1s1g7g5/）。
- **分段生成 + NLE 拼接**：剧本→分镜→5–15 秒片段→DaVinci/Premiere 组装；12 分钟片 = 148 个镜头（2026-09-23，https://www.reddit.com/r/generativeAI/comments/1wog53q/）。
- **低分辨率草稿 → 高分辨率终稿**：Grok 480p/5s 找镜头，Gemini Omni/Seedance 出 keeper（同上）。
- **多模型切换**：同一镜头在 Runway/Kling/Veo/Seedance 之间试，谁出片用谁；代价是学习成本与素材管理混乱（2026-09-20，https://www.reddit.com/r/aivideomaking/comments/1wlwnp4/）。
- **本地 ComfyUI + Wan/LTX/Minimax**：用可控性换便利性，适合有显卡的团队（2026-09-29，https://www.reddit.com/r/aivideomaking/comments/1wtfc2c/）。

### 4.3 成本 / 失败类

- **先文本后生成**：把 shot list、风格参考、时长、运镜全部定死再烧积分（2026-06-27 评论，https://www.reddit.com/r/creators/comments/1ugx9ih/）。
- **只在草稿阶段用便宜模型**，终稿才用贵模型（2026-09-23，https://www.reddit.com/r/generativeAI/comments/1wog53q/）。
- **换聚合器/转售商**：KIE、Freepik、Loova 等按“更便宜的单价”吸引用户，但 upstream 一挂就全挂（2026-03-10，https://www.reddit.com/r/n8n/comments/1rpo4l7/）。
- **失败退款申诉**：靠客服个案处理，无制度保障；Leonardo 用户明确遇到“失败也扣积分”（2026-08-10，https://www.reddit.com/r/leonardoai/comments/1vkztv5/）。

### 4.4 后期 / 交付类

- **Topaz 超分 + 手动对齐时间线**：upscale 后时长变化，需要重新对轨（2026-01-16，https://www.reddit.com/r/premiere/comments/1qec88n/）。
- **AE 遮罩/跟踪修脸、修手、去道具**：把 AI 错误当 VFX 修，成本转嫁给后期。
- **手动口型/配音**：多角色对白拆成单角色生成，再在剪辑里对切（2025-08-14，https://www.reddit.com/r/VEO3/comments/1mprm33/）。
- **去水印（灰色）**：裁切、模糊、第三方工具；存在 ToS 与法律风险，且 C2PA/隐形水印无法去除（2025-10-18，https://www.reddit.com/r/SoraAi/comments/1oa5ecz/ ；官方说明 https://openai.com/index/launching-sora-responsibly/）。

### 4.5 团队 / 管理类

- **通用项目管理 + 网盘 + Frame.io**：Notion/ClickUp/Airtable 管镜头，Frame.io 审片；没有为 AI takes 设计。
- **自建/开源工具**：SHOTBUDDY（自动编号、缩略图、版本归档，2025-07-20，https://www.reddit.com/r/StableDiffusion/comments/1m4m9u5/）；LTX Desktop、Sonder Editor、Zapters、Prism 等在评论中被提及，但成熟度未知。
- **手工命名规范**：`shot_###_take_##_model_version`，靠人守纪律。
- **厂商一体化工作流**：Magnific 的“一个 connected workflow 管 2,591 次生成”（厂商案例，2026-07-28，https://www.reddit.com/r/magnific/comments/1v8yb1w/）。

---

## ⑤ 初步机会判断

### 5.1 最值得做的两个产品机会

#### 机会 A：AI 视频的“连续性层 / 制作 OS”（Continuity Layer）

**一句话**：不是再做一个生成器，而是做**跨模型的角色圣经 + 镜头图 + take 库 + 版本/审批 + 可回滚的局部重生成**。

**为什么是现在**
- 一致性是唯一跨 8 个子版、≥15 条独立讨论的 P0，且用户已明确说“愿意为解决方案付费/换工具”（1uv3otr、1wlwnp4）。
- 单镜头质量已经“够用”，行业瓶颈从“生成”转向“组织”；2026 年出现多篇长片复盘（148 镜头、2,591 次生成），说明生产规模已经超过手工管理极限。
- 现有工具是碎片：SHOTBUDDY 只做文件管理，Frame.io 只做审片，ComfyUI 只做生成；**没有一个东西同时理解“角色—镜头—take—版本—交付”**。
- 用户已经在用自然语言提出这个需求：“there needs to be a better standard for locking in a character along with props and wardrobe. Almost like a whole new file format specifically for AI models.”（YouTube @WinstonWilliamsofficial, 2026-10-22, https://www.youtube.com/watch?v=ktEt4n9VlF4）

**产品形态（建议）**
1. **Character Bible**：多角度参考图、锁定特征（脸/发型/服装/道具/声音）、每个模型的“一致性配方”（用哪张图、什么权重、什么提示词模板）。
2. **Shot Graph**：剧本→分镜→镜头→take 的树状结构；每个节点记录模型、seed、prompt、参考图、成本、状态。
3. **Take Library + Diff**：同一镜头的多个 take 并排对比；标记“可用/近可用/废片”；记录为什么废（脸崩/手崩/构图偏）。
4. **局部重生成**：只重跑坏掉的那 2 秒/那个区域，而不是整条重抽；与模型 API 解耦，哪家便宜用哪家。
5. **Export to NLE**：XML/EDL + sidecar metadata（帧率、时码、镜头号、版本、授权状态），直接进 PR/Resolve/AE。
6. **团队协作**：镜头级 assign、review、approve；客户只看“可批”的版本，不看到 38 条废片。

**壁垒**：不是模型，而是**数据模型 + 工作流习惯**。一旦团队的 character bible 和 shot graph 落在你这里，迁移成本极高。

**风险**：模型厂商可能自己向上做（Runway/Adobe 都在补资产管理）；应对是“跨模型、中立、可导出”。

---

#### 机会 B：商用权利与交付合规层（Rights & Delivery Compliance）

**一句话**：把“这个素材能不能商用、要不要披露、水印/ provenance 是什么、客户合同怎么写”做成可查询、可审计、可交付的产品。

**为什么是现在**
- 商用授权/水印是 P0 中**最容易被产品化、且最不依赖模型能力**的一条。
- 证据密集：Kling ToS 明确“without our written permission, you may not use... for any commercial purposes”（2025-06-10）；Veo 付费套餐仍带水印（2026-07-19）；Sora 官方“all outputs carry a visible watermark”（2025-09-30）；代理商因未披露 AI 而丢单/被质疑（2026-08-25）。
- 客户侧的真实恐惧是“被发现用了 AI”，而不是“画质差”（2026-01-28 r/MotionDesign）。
- 2026 年 Sora 关停证明：**授权状态会随供应商消失而失效**，团队需要一份独立于平台的资产台账。

**产品形态（建议）**
1. **模型/套餐授权数据库**：每个模型 × 每个套餐 × 每个地区，商用/转售/署名/水印/输出所有权/是否可训练，逐条附 ToS 原文与日期。
2. **资产 provenance 台账**：每个生成资产记录模型、版本、账号、日期、prompt、参考图授权、C2PA/隐形水印状态。
3. **交付前检查**：水印检测、分辨率/帧率/时长合规、肖像/商标/版权风险提示。
4. **客户披露报告**：一键生成“本片哪些镜头为 AI 生成、使用何模型、授权范围、不可商用项”，可作为合同附件。
5. **合同条款库**：AI 反馈条款、AI 披露条款、失败重做条款（呼应 2026-09-21 r/videography 的“AI Feedback clause”）。

**壁垒**：ToS 的持续跟踪与法律解读；一旦成为“行业事实标准”，网络效应强。

**风险**：不是纯软件问题，需要法律顾问；建议从“信息产品 + 检查工具”切入，而不是直接给法律意见。

---

### 5.2 次优机会（可做，但更适合作为功能而非公司）

| 机会 | 判断 | 理由 |
|---|---|---|
| 成本优化 / 失败退款哨兵 | 需求真实，但难独立 | 聚合器已在打价格战；退款依赖平台政策，第三方无法强制。适合作为“制作 OS”的一个计费面板 |
| AI 原生审片/批注 | 需求真实，但拥挤 | Frame.io/YouTube 都在补；差异化只能是“镜头级 + take 级”，仍可被机会 A 吸收 |
| 提示词/工作流模板库 | 不建议 | 模型一升级就失效；用户已在免费社区互换 |
| 纯聚合器/API 网关 | 不建议 | 价格战 + 上游关停风险（Sora 就是案例）；除非有独家额度或企业合规能力 |
| 去水印工具 | 不建议 | 法律/ToS 风险高，且 C2PA 无法去除；会污染品牌 |
| 一键“整片生成” | 短期不建议 | 叙事/一致性/对白都未解决；做出来就是更长的抽卡 |

### 5.3 属于“模型能力问题、短期无解”的痛点

以下不建议用产品硬解，应该用**编排/验证/人工兜底**去绕：
1. **物理与接触**：手拿道具、穿脱衣物、多人接触、液体/布料模拟；用户反复提到“watch switching wrists”“brass knuckles jumping hands”。
2. **长镜头内部连贯**：单条 30 秒以上仍会漂移；不是靠 prompt 能解决的。
3. **多角色对白归属**：Veo 3.1 仍“very often swaps the dialogue lines”；短期只能拆单角色生成。
4. **微表情/眨眼/恐怖谷**：HeyGen Avatar 5 “look nice but they look AI”。
5. **“完全不像 AI”的质感**：客户能感知“每个元素都对、整体就是不对”（2026-09-24 r/marketingagency）；这是审美/统计分布问题，不是分辨率问题。

**产品含义**：不要赌“更好的生成”，要赌“更好的选择、验证、编排与交付”。模型越强，编排层的价值越大，而不是越小。

### 5.4 机会优先级建议

| 排序 | 机会 | 目标客户 | 付费意愿 | 技术风险 | 建议 |
|---|---|---|---|---|---|
| 1 | 连续性层 / 制作 OS | 3 人以上 AI 动画/短片团队、接商单的后期 | 高（省的是重抽与返工） | 中（集成多模型 API） | **首选**，先做 character bible + shot graph + take 库 |
| 2 | 权利与交付合规层 | 代理商、自由职业者、企业品牌 | 中高（避的是法律/丢单） | 低（信息+检查） | **次选**，先做 ToS 数据库 + 披露报告 |
| 3 | 成本/退款哨兵 | 自费创作者、小工作室 | 中 | 低 | 作为机会 1 的模块 |
| 4 | AI 原生审片 | 代理/制作团队 | 中 | 中 | 作为机会 1 的模块 |

---

## ⑥ 证据索引

### 6.1 Reddit（按痛点分组；日期为帖子 `published_at`）

| # | 日期 | 子版 / 作者 | 痛点 | 关键原话（片段） | URL |
|---|---|---|---|---|---|
| 1 | 2026-07-13 | r/aivideos / u/Pristine_Moose_4482 | 一致性 | "re-casting the same character every shot" | https://www.reddit.com/r/aivideos/comments/1uv3otr/character_consistency_falls_apart_across_shots_on/ |
| 2 | 2026-07-13 | r/StableDiffusion / u/ke1lle | 一致性 | "By clip 5 the jacket changed color" | https://www.reddit.com/r/StableDiffusion/comments/1uvamx5/same_character_5_ai_clips_5_different_faces/ |
| 3 | 2026-04-16 | r/aivideos / u/siddomaxx | 一致性 | "By shot five you're watching a different person" | https://www.reddit.com/r/aivideos/comments/1smtzb9/seedance_20_character_consistency_across_shots/ |
| 4 | 2026-06-29 | r/generativeAI / u/the-real-neil | 一致性/声音 | "body proportions would drift" | https://www.reddit.com/r/generativeAI/comments/1uiskc4/we_made_video_content_entirely_with_ai_for_6/ |
| 5 | 2026-09-20 | r/aivideomaking / u/Putrid_Job6390 | 一致性（4 工具横评） | "lost the character by the third episode" | https://www.reddit.com/r/aivideomaking/comments/1wlwnp4/is_there_an_ai_video_tool_that_can_keep_the_same/ |
| 6 | 2026-08-03 | r/Seedance_AI / u/Sniper_yoha | 一致性 workaround | "a new nose and a different hoodie" | https://www.reddit.com/r/Seedance_AI/comments/1ve9exo/my_ai_characters_kept_morphing_between_shots_so_i/ |
| 7 | 2026-09-17 | r/aivideomaking / u/popypep | 可用率 | "38 generations, six usable clips" | https://www.reddit.com/r/aivideomaking/comments/1wiwna3/ai_video_demos_are_hiding_the_part_where_you_make/ |
| 8 | 2026-06-22 | r/grok / u/Wazir-AI | 可用率 | "Seedance 2 - sometimes 5-6" | https://www.reddit.com/r/grok/comments/1ucqbwg/honest_question_how_many_generations_does_it/ |
| 9 | 2026-09-08 | r/ContentCreators / u/avatar0027（评论） | 可用率 | "burn 3–5 gens before one feels usable" | https://www.reddit.com/r/ContentCreators/comments/1wahwy1/how_many_ai_video_rerolls_do_you_usually_need/ |
| 10 | 2026-04-11 | r/VEO3 / u/adrian-smith31（评论） | 可用率/涨价 | "needs 10 generations before you get a useable clip" | https://www.reddit.com/r/VEO3/comments/1sikoxl/disappointed_in_veo_flow/ |
| 11 | 2025-10-14 | r/OpenAI / u/GoliathGrouper_0417 | 可用率/编辑 | "hours of iterations to generate a useful 10 seconds" | https://www.reddit.com/r/OpenAI/comments/1o632p0/sora_2_disappointments/ |
| 12 | 2026-08-25 | r/generativeAI / u/Extension_Virus2766 | 成本 | "FIVE SHORT (<10s) videos later, i ran out of my credits" | https://www.reddit.com/r/generativeAI/comments/1vxzwfk/really_bad_experience_with_runway_pro_plan_avoid/ |
| 13 | 2026-09-29 | r/aivideomaking / u/evina_27 | 成本 | "15 seconds... almost HALF my credits" | https://www.reddit.com/r/aivideomaking/comments/1wtfc2c/runway_credits_are_crazy_what_are_you_using_for/ |
| 14 | 2026-05-03 | r/generativeAI / u/Frosty-Specific4977 | 成本 | "1min video is barely 28$" | https://www.reddit.com/r/generativeAI/comments/1t2jrcn/runway_pricing_how_are_ppl_making_this_work/ |
| 15 | 2026-06-27 | r/creators / u/jono440 | 成本 | "paying for my mistakes" | https://www.reddit.com/r/creators/comments/1ugx9ih/ive_been_using_runway_to_experiment_but_my/ |
| 16 | 2026-08-10 | r/leonardoai / u/WHiteMage_BLackMage | 失败不退 | "there are no refunds" | https://www.reddit.com/r/leonardoai/comments/1vkztv5/no_refunds_for_videos/ |
| 17 | 2025-11-19 | r/VEO3 / u/No-Aardvark-3840 | 套餐缩水 | "essentially a bait and switch" | https://www.reddit.com/r/VEO3/comments/1p1koke/i_would_encourage_everyone_here_to_follow_up_with/ |
| 18 | 2026-03-23 | r/SoraAi / u/Groundbreaking_Act44 | 积分下调 | "From 30 to 10 huh?" | https://www.reddit.com/r/SoraAi/comments/1s1chwe/from_30_to_10_huh_and_they_expect_us_to_give_them/ |
| 19 | 2026-03-23 | r/aivideos / u/SufficientTomato916 | 可控性 | "random motion that ruins the blocking" | https://www.reddit.com/r/aivideos/comments/1s1g7g5/how_do_you_stop_your_ai_video_from_drifting_away/ |
| 20 | 2026-09-22 | r/aivideomaking / u/Boring-Today-8244 | 可控性 | "camera behavior changing unexpectedly" | https://www.reddit.com/r/aivideomaking/comments/1wn93m1/titlewhat_usually_makes_you_regenerate_an_ai/ |
| 21 | 2026-08-17 | r/comfyui / u/danielpartzsch | 可控性 | "too much of a gamble to get everything right in one-shot" | https://www.reddit.com/r/comfyui/comments/1vqtgvk/storyboard_to_video_with_minimaxh3_how_do_you/ |
| 22 | 2026-06-01 | r/midjourney / u/amp1212（评论） | 可控性/分辨率 | "not nearly as controllable... 480p" | https://www.reddit.com/r/midjourney/comments/1tu26nr/question_how_good_is_midjourney_video_in_2026/ |
| 23 | 2026-01-09 | r/runwayml / u/razgss（评论） | 竖屏 | "keeps generating the video horizontally" | https://www.reddit.com/r/runwayml/comments/1q8d15k/does_gen45_support_916_vertical_video_for/ |
| 24 | 2025-06-10 | r/KlingAI_Videos / u/beantorres | 商用 ToS | "without our written persmission... commercial purposes" | https://www.reddit.com/r/KlingAI_Videos/comments/1l7wkpy/who_owns_the_output_is_it_copyrighted/ |
| 25 | 2025-10-18 | r/SoraAi / u/FurnitureRefinisher | 水印/商用 | "the watermark ruins that" | https://www.reddit.com/r/SoraAi/comments/1oa5ecz/whats_up_with_the_strict_watermark_guidelines_can/ |
| 26 | 2026-07-19 | r/GeminiAI / u/Due_Entrepreneur1546 | 水印/stock | "noticed a Veo watermark in the bottom-right corner" | https://www.reddit.com/r/GeminiAI/comments/1v0t7i8/google_ai_pro_veo_watermark_can_paid_users_remove/ |
| 27 | 2026-04-07 | r/CapCut / u/isaacpriestley | 水印 | "it seems to add an 'Ai' watermark" | https://www.reddit.com/r/CapCut/comments/1sf3813/remove_the_ai_watermark/ |
| 28 | 2026-08-25 | r/aitubers / u/Madmahi25 | 披露/授权 | "licensing implications the client genuinely needs to know about" | https://www.reddit.com/r/aitubers/comments/1vxx62e/we_lost_a_pitch_to_an_agency_quoting_a_tenth_of/ |
| 29 | 2026-03-02 | r/SoraAi / u/TheOnlyShyG | 审核误杀 | "can’t generate anything anymore"（98 赞） | https://www.reddit.com/r/SoraAi/comments/1rif15f/sora_is_officially_unusable_i_quit/ |
| 30 | 2025-12-24 | r/SoraAi / u/Suitable_Goose3637 | 审核随机 | "It feels random" | https://www.reddit.com/r/SoraAi/comments/1pusqlb/sora_2_flags_normal_prompts_so_often_its/ |
| 31 | 2026-02-05 | r/SoraAi / u/Agitated_Guidance992 | 版权误判 | "associates it with 'Demon Slayer'" | https://www.reddit.com/r/SoraAi/comments/1qw8u3g/the_biggest_problem_with_sora_2_is_its_stupid_ai/ |
| 32 | 2025-09-21 | r/KLING / u/RandomUserName14227 | 审核误杀 | "exact same images... suddenly getting flagged" | https://www.reddit.com/r/KLING/comments/1nmpljr/generation_failed_as_the_content_includes/ |
| 33 | 2026-01-02 | r/AdobeFireflyCommunity / u/Cheesy_crumpet | 审核误杀 | "The reference image is unsafe (it’s not)" | https://www.reddit.com/r/AdobeFireflyCommunity/comments/1q1pjvr/started_off_really_good_but_suddenly_unable_to/ |
| 34 | 2025-06-25 | r/Bard / u/Rellevant1 | 时长 | "all cap at 10 seconds" | https://www.reddit.com/r/Bard/comments/1ljus4t/longer_videos_than_10_sec/ |
| 35 | 2026-09-23 | r/generativeAI / u/AlfieSchmalfie（评论） | 长片 | "12 minute video. 148 shots" | https://www.reddit.com/r/generativeAI/comments/1wog53q/how_are_people_making_long_ai_generated_videos/ |
| 36 | 2026-09-10 | r/aivideos / u/bdylsing | 长片 | "seven hour-long movies... thousands of clips" | https://www.reddit.com/r/aivideos/comments/1wcy62m/i_somehow_ended_up_making_seven_hourlong_ai_films/ |
| 37 | 2025-08-14 | r/VEO3 / u/refriedi | 对白归属 | "delivered by the wrong character" | https://www.reddit.com/r/VEO3/comments/1mprm33/help_with_wrong_characterspeechdialogue/ |
| 38 | 2025-12-30 | r/VEO3 / u/nanji200 | 对白串词 | "very often swaps the dialogue lines" | https://www.reddit.com/r/VEO3/comments/1pzs0wf/dialogue_challenge_in_veo_31/ |
| 39 | 2026-05-28 | r/VEO3 / u/Optimal_Oven_3332 | 多角色对白 | "dialogue swapping / lip sync mismatch" | https://www.reddit.com/r/VEO3/comments/1tptw4v/how_to_handle_multiple_characters_dialogue/ |
| 40 | 2026-08-24 | r/heygen / u/Sea_Investment138 | 不眨眼 | "my avatars never blink" | https://www.reddit.com/r/heygen/comments/1vx7sii/my_heygen_avatars_never_blink_not_once_anyone/ |
| 41 | 2026-04-28 | r/heygen / u/Chance-Obligation573 | 恐怖谷 | "look nice but they look AI" | https://www.reddit.com/r/heygen/comments/1sxrex1/avatar_v_lip_and_head_movements_gone_wrong/ |
| 42 | 2025-06-01 | r/Bard / u/BarFickle2272 | 无音频 | "Some videos come out with no audio at all" | https://www.reddit.com/r/Bard/comments/1l0thrn/how_can_i_make_the_character_speak_on_veo_3/ |
| 43 | 2026-05-07 | r/generativeAI / u/h3rve | 24fps | "comes back in 24 fps" | https://www.reddit.com/r/generativeAI/comments/1t67zac/25_fps_users_how_are_you_dealing_with/ |
| 44 | 2026-01-16 | r/premiere / u/Robeloto | round-trip | "nothing matches cause the AI clip is longer" | https://www.reddit.com/r/premiere/comments/1qec88n/upscaled_ai_clip_does_not_match_the_original_clip/ |
| 45 | 2026-09-04 | r/VideoEditors / u/Express_Map9176 | 修订 | "falls apart on revisions" | https://www.reddit.com/r/VideoEditors/comments/1w7achv/can_you_actually_use_ai_editing_on_paid_client/ |
| 46 | 2025-07-20 | r/StableDiffusion / u/Storybook_Albert | 版本管理 | "generation_img2343_heres-half-your-prompt" | https://www.reddit.com/r/StableDiffusion/comments/1m4m9u5/shotbuddy_an_open_source_tool_for_managing_i2v/ |
| 47 | 2026-07-23 | r/aifilmmaking / u/danoncano | 团队协作 | "Handing off assets, assigning scenes / shots" | https://www.reddit.com/r/aifilmmaking/comments/1v4gtz9/collaborating_with_a_team/ |
| 48 | 2026-08-24 | r/editors / u/zyyga（评论） | 客户审片 | "train your clients to answer with specificity" | https://www.reddit.com/r/editors/comments/1r6ens2/video_review_process_with_clients_is_killing_my/ |
| 49 | 2026-09-21 | r/videography / u/PackageBulky1 | AI 反馈条款 | "infinite changes" | https://www.reddit.com/r/videography/comments/1wmai8r/close_to_adding_an_ai_feedback_clause_to_my/ |
| 50 | 2026-05-08 | r/runwayml / u/ResponsibleFix66 | 节流 | "20 minutes... to a little over an hour" | https://www.reddit.com/r/runwayml/comments/1t71pm3/brutal_throttling/ |
| 51 | 2026-05-14 | r/VEO3 / u/Stunning_Pack_4636 | 排队 | "queued for 10m for every video" | https://www.reddit.com/r/VEO3/comments/1tctmfr/im_getting_queued_for_10m_for_every_video_veo_31/ |
| 52 | 2026-06-12 | r/generativeAI / u/Ordinary_Ad1942 | 无限排队 | "Unlimited queue for 6–10+ hours" | https://www.reddit.com/r/generativeAI/comments/1u3o9cc/my_loova_max_annual_experience_unlimited_queued/ |
| 53 | 2025-10-16 | r/HiggsfieldAI / u/Consistent_Aspect_43 | 排队 | "at least 5 min to generate" | https://www.reddit.com/r/HiggsfieldAI/comments/1o82kfk/queue_time_too_long_on_models_with_unlimited/ |
| 54 | 2025-06-08 | r/civitai / u/AltraVR | 排队 | "48+ Hours Video Generation Que" | https://www.reddit.com/r/civitai/comments/1l6f5b1/48_hours_video_generation_que/ |
| 55 | 2026-05-08 | r/VEO3 / u/Sephy_winz | 限流逼氪 | "forcing me to spend credits" | https://www.reddit.com/r/VEO3/comments/1t6zp65/constant_we_noticed_some_unusual_activity_errors/ |
| 56 | 2026-02-06 | r/Freepik_AI / u/EdgarRRojas | 容量 | "All my generations... get stuck" | https://www.reddit.com/r/Freepik_AI/comments/1qxm1c6/kling_30_working/ |
| 57 | 2026-09-23 | r/SoraAi / u/Relevant_Coyote_8614 | 关停 | "the API has been officially shut down"（227 赞） | https://www.reddit.com/r/SoraAi/comments/1wojm20/goodbye_sora_2_the_api_has_been_officially_shut/ |
| 58 | 2026-03-10 | r/n8n / u/gobhalla | 转售商跑路 | "I miss deadlines. Clients leave." | https://www.reddit.com/r/n8n/comments/1rpo4l7/sora_2_on_kie_ai_broke_my_work_need_a_new_tool/ |
| 59 | 2026-09-28 | r/OpenAI / u/Tanmay_Vermaa | 虚假库存 | "31 still offer Sora as a model you can pick" | https://www.reddit.com/r/OpenAI/comments/1wsf2ih/the_sora_api_was_due_to_shut_down_sept_24_i/ |
| 60 | 2026-03-16 | r/generativeAI / u/Gold-Alternative9327 | 假无限 | "the 'unlimited' thing is basically a lie" | https://www.reddit.com/r/generativeAI/comments/1rvaj50/my_honest_experience_with_higgsfield_after_4/ |
| 61 | 2026-09-22 | r/ArtificialInteligence / u/Sensitive_Signal_339 | 预期错位 | "I wish it worked that way" | https://www.reddit.com/r/ArtificialInteligence/comments/1wn477j/my_boss_saw_an_ai_demo_and_thought_we_could_make/ |
| 62 | 2025-06-19 | r/videography / u/Xxviii_28（评论） | 采用率 | "50-odd videos... used AI-generated media 3 times" | https://www.reddit.com/r/videography/comments/1lf8lba/are_aigenerated_videos_reliable_enough_for_client/ |
| 63 | 2026-09-24 | r/marketingagency / u/BrynleeCampbell | AI 味 | "But why does this look fake?" | https://www.reddit.com/r/marketingagency/comments/1wop7ad/an_agency_i_know_claims_they_almost_lost_a_client/ |
| 64 | 2025-09-10 | r/VideoProfessionals / u/Pale_Caregiver_3875 | AI 味 | "look cheap and clunky" | https://www.reddit.com/r/VideoProfessionals/comments/1ndb5r4/ai_videos_look_cheap_and_unprofessional_for_any/ |
| 65 | 2026-01-28 | r/MotionDesign / u/Batson_Beat | 客户披露焦虑 | "suddenly they wanted to 'discuss it further'" | https://www.reddit.com/r/MotionDesign/comments/1qpetha/getting_clients_comfortable_with_ai_video/ |
| 66 | 2026-08-03 | r/VideoEditingTips / u/Valuable_Iron_2890 | 字幕口音 | "regularly get words wrong when there’s an accent" | https://www.reddit.com/r/VideoEditingTips/comments/1veoh9n/anyone_else_still_manually_fixing_ai_captions/ |
| 67 | 2025-09-29 | r/GeminiAI / u/rascian038 | 多语言 | "say the English translation of what I wrote" | https://www.reddit.com/r/GeminiAI/comments/1ntr6wl/characters_keep_switching_up_lines_in_veo_any_way/ |
| 68 | 2026-07-28 | r/magnific / u/MagnificOfficial（厂商） | 生产规模 | "2,591 generations" | https://www.reddit.com/r/magnific/comments/1v8yb1w/we_made_an_ai_short_film_where_the_lead_ages_from/ |

### 6.2 YouTube

| # | 日期 | 来源 | 关键原话 | URL |
|---|---|---|---|---|
| 69 | 2026-05-12 | @potts995 | "nobody else has a character video reference feature yet. Unfortunately it wasn't the best for serious work use" | https://www.youtube.com/watch?v=J5_8ugu8mVw |
| 70 | 2025-11-12 | @mattstaab6399 | "Their content moderation is too aggregious... My OC character that's pre pre ai. I own the IP." | https://www.youtube.com/watch?v=J5_8ugu8mVw |
| 71 | 2026-01-12 | @ScoutChaseTV | "I can't even generate anthro videos because of 'third party' content" | https://www.youtube.com/watch?v=J5_8ugu8mVw |
| 72 | 2026-09-12 | @FallenAngel-y3o | "I kind of wish Sora still around... prototype stories that I wish I could've completed." | https://www.youtube.com/watch?v=J5_8ugu8mVw |
| 73 | 2026-10-22 | @dianavintagestylist1934 | "the brass knuckles jumping from one hand to both hands between shots... ruins a client job" | https://www.youtube.com/watch?v=ktEt4n9VlF4 |
| 74 | 2026-10-22 | @MrzMirza-s6s | "the robot pulling out two swords when the sheet only had one means rendering that whole scene again, and that is where Seedance gets pricey fast." | https://www.youtube.com/watch?v=ktEt4n9VlF4 |
| 75 | 2026-10-22 | @WinstonWilliamsofficial | "there needs to be a better standard for locking in a character along with props and wardrobe. Almost like a whole new file format specifically for AI models." | https://www.youtube.com/watch?v=ktEt4n9VlF4 |
| 76 | — | @nolow_life | "So none of the methods produced a consistent character..." | https://www.youtube.com/watch?v=J5_8ugu8mVw |
| 77 | — | @artvsmachine | "You gotta run the same prompt sometimes a few times... You gotta roll the dice a few times" | https://www.youtube.com/watch?v=J5_8ugu8mVw |
| 78 | — | @by-thalen | "it is not available in my region, and when I was able to enter using a VPN it no longer let me generate anything" | https://www.youtube.com/watch?v=J5_8ugu8mVw |

### 6.3 X / 官方文档 / 论坛

| # | 日期 | 来源 | 关键原话 | URL |
|---|---|---|---|---|
| 79 | 2026-03-15 | X / @henrydaubrez | "Spent about $1000 in credits on Seedance 2.0... Short clips are easy. Worldbuilding is not." | https://x.com/henrydaubrez/status/2033237370758459892 |
| 80 | 2025-09-30（页面标注 2026-04-26 下线） | OpenAI 官方 | "all outputs carry a visible watermark" | https://openai.com/index/launching-sora-responsibly/ |
| 81 | 2026-09-24（文档） | OpenAI API 文档 | "The Sora 2 models and Videos API were shut down on September 24, 2026... No one-to-one replacement API is available." | https://developers.openai.com/api/docs/guides/video-generation |
| 82 | 2025-10-07 | OpenAI Community / u/nickthblde | "a 8s generation failed at 87% of completion and… voiloà 4$ pulverized." | https://community.openai.com/t/sora-2-api-charges-money-on-failed-run-at-100-progress/1361332 |
| 83 | 2025-11-08 | OpenAI Community / u/devjordan | "credits are just compute requests" | https://community.openai.com/t/credits-charged-for-pre-compute-moderation-blocks/1365628 |

### 6.4 未采用 / 失败的来源（可复现）

| 来源 | 错误 | 处理 |
|---|---|---|
| `agent-reach twitter search` | `NEED_LOGIN`：`Not logged into x.com (no ct0 cookie)` | 停止，不登录、不换账号；改用 Exa 搜到 1 条长帖 |
| Claude `WebSearch` | `403 Access denied... Volcano Ark Console` | 改用 `agent-reach web search`（Exa） |
| Claude `WebFetch`（community.openai.com） | 域名安全校验失败 | 改用 `agent-reach read`（Jina） |
| Runway Help Center | Cloudflare `Just a moment...` | 不引用官方定价，仅用用户自述 |
| unrollnow.com | Cloudflare challenge | 直接读 x.com 原帖 |
| Discord | 无公开只读接口 | 未采集，不用二手转述代替 |
| `timeout` 命令 | macOS 不存在 | 直接运行 `yt-dlp` |
| 1 个损坏的 `.json` 缓存 | `json.load` 失败 | try/except 跳过，不影响去重结果 |

### 6.5 复现方法（供下一轮增量调研）

```bash
# Reddit 搜索（每次间隔 ≥11s，遵守同平台 10s 限制）
agent-reach reddit search "ai video characters change between shots" --limit 10
# 读取单帖（含评论）
agent-reach reddit read "https://www.reddit.com/r/.../comments/..../"
# YouTube 评论
yt-dlp --skip-download --write-comments \
  --extractor-args "youtube:max_comments=40,all,0,0" "<video_url>"
# 非 Reddit 网页
agent-reach web search "sora 2 api failed generation charged credits"
agent-reach read "https://community.openai.com/t/..."
```

### 6.6 一句话结论

2026 年的 AI 视频痛点已经从“生成不出好看的画面”转移到“**无法稳定、可控、可商用、可协作地把画面组织成片子**”；一致性、可用率、成本、授权、审核是五个 P0，而它们共同指向同一个缺口——**缺一层跨模型的制作与合规基础设施**。
