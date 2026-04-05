---
title: "AI 资讯日报 2026-04-01"
description: "每日 AI 领域精选资讯：开发生态、技术洞察、模型发布、产品动态"
pubDate: "2026-04-01"
tags: ["AI", "资讯"]
slug: "x-news-daily-2026-04-01"
---

# AI 资讯日报 2026-04-01

## 概览

### 开发生态

Claude Code 源码遭意外泄露事件持续发酵——Fried_rice 率先通过 npm registry map 文件扒出完整代码（含所有 prompt），GitHub fork 已在数小时内积累 32.6k stars，随后社区用 Python 重写以规避 DMCA 下架风险；与此同时 OpenAI Codex 被指其实一直开源但鲜为人知，AI coding tool 的安全与版权边界成焦点。npm axios 供应链攻击确认仍在活跃，3 亿周下载量使影响面极大，Ferross 呼吁开发者立即锁定版本。

- Claude Code 源码惊现 npm registry [↗](https://x.com/Fried_rice/status/2038894956459290963) `#1`
- Codex 完整代码曝光 [↗](https://x.com/reach_vb/status/2038971515572523502) `#2`
- npm axios 供应链攻击仍在活跃 [↗](https://x.com/ferross/status/2038807290422370479) `#3`
- Claude Code 挫败感检测代码 [↗](https://x.com/byteHumi/status/2038960489154380261) `#4`

### 技术洞察

Claude Code 源码曝光后，Sebastian Raschka 公开分析其"真正秘密"：harness 设计而非模型本身才是性能差距来源，live repo context、prompt cache 复用、专用 Grep/Glob 工具链等工程细节首次披露。Yuchen Jin 进一步指出，50 万行 Claude Code 源码流出后，所有模型厂商和 AI coding 创业公司都将加速研究这一 harness 差距。

- Sebastian Raschka 谈 Claude Code 源码 [↗](https://x.com/rasbt/status/2038980345316413862) `#5`
- Stanford/MIT：harness 对固定模型可产生 6 倍性能差距 [↗](https://x.com/omarsar0/status/2038967842075500870) `#6`

### 模型发布

本周模型发布密集：Qwen3.5-27B 成功蒸馏 Claude 4.6 Opus 推理能力，16GB 显存即可运行，刷新本地部署性价比；Holo3 的 computer-use 模型以十分之一成本超越 GPT-5.4 和 Opus 4.6；Google Veo 3.1 Lite 继续压低视频生成成本。

- Qwen3.5-27B 蒸馏版发布 [↗](https://x.com/outsource_/status/2038999111039357302) `#7`
- Holo3 computer-use 模型 [↗](https://x.com/hcompany_ai/status/2039021096649805937) `#8`
- Google Veo 3.1 Lite [↗](https://x.com/OfficialLoganK/status/2039015034286694618) `#9`

---

## [Claude Code 完整源码惊现 npm registry：地图文件意外暴露 Anthropic 核心代码](https://x.com/Fried_rice/status/2038894956459290963) `#1`

> Claude Code 源码通过 npm registry 的 map 文件被意外泄露，完整代码和盘托出，含所有 prompt——GitHub fork 数小时内突破 32.6k stars。

Chaofan Shou（@Fried_rice）在 npm registry 的 map 文件中发现了 Claude Code 的完整 TypeScript 源码，随即被社区广泛传播。这份代码包含了 Claude Code 的所有 system prompt、工具调用逻辑和上下文管理实现，是至今最完整的顶级 AI coding agent 内部机制曝光。

社区反应迅速：fork 版本在 GitHub 上迅速积累了 32.6k stars 和 44.3k forks。随后有开发者将 TypeScript 代码用 Codex 转译为 Python，借此规避了版权风险——Gergely Orosz 指出，这是"聪明还是可怕"的边界操作：用纯 Python 重写后不再受 DMCA 管辖，无法被强制下架。

Anthropic 尚未就此公开发表声明，但据报道已对部分直接分发源码的仓库发出 DMCA 删除通知。Yuchen Jin 评论道："AI 正在悄然侵蚀版权"，暗示这场泄露将引发对 AI coding tool 版权框架的深层讨论。

![Claude Code 源码截图](media/2038894956459290963_0.jpg)

> "Anthropic 意外泄露了 Claude Code 的 TypeScript 源码。直接分发的仓库被 DMCA 下架。但这个仓库用 Python 重写了代码，因此不侵犯版权，无法被下架！" ——Gergely Orosz 在分析中写道。

相关链接：
- Fried_rice: Claude Code 源码泄露详情：https://x.com/Fried_rice/status/2038894956459290963
- GergelyOrosz: DMCA 与 Python 重写分析：https://x.com/GergelyOrosz/status/2038985760175505491
- Yuchenj_UW: Anthropic Claude Code 泄露始末：https://x.com/Yuchenj_UW/status/2038996920845430815
- GitHub: openai/codex：https://github.com/openai/codex

---

## [OpenAI Codex 代码库曝光：官方确认一直开源但鲜为人知](https://x.com/reach_vb/status/2038971515572523502) `#2`

> OpenAI Codex 完整代码库被分享至 GitHub 后，OpenAI 内部员工随即澄清：Codex 自推出起即为开源项目，此次并非"泄露"，而是引发了一次关于开源边界的讨论。

OpenAI 开发者关系工程师 Vaibhav Srivastav（@reach_vb）在分享 Codex GitHub 仓库时引发广泛关注。随后他本人在同一 thread 中补充说明："为避免疑惑，Codex 自成立起就是开源的！这次分享本质上只是提高了人们对这个事实的认知。"

不过社区反应热烈：许多开发者此前并不知道 Codex 已开源，相关 repo 迅速传播。这与同一天的 Claude Code 源码泄露事件形成对照——同样是代码曝光，OpenAI 选择公开透明，而 Anthropic 则以 DMCA 应对。两者做法差异引发关于 AI coding tool 商业策略的讨论。

相关链接：
- reach_vb: Codex 开源说明：https://x.com/reach_vb/status/2038971515572523502
- GitHub: openai/codex：https://github.com/openai/codex

---

## [npm axios 3 亿周下载量 HTTP 库确认遭遇活跃供应链攻击](https://x.com/ferross/status/2038807290422370479) `#3`

> npm 生态最流行的 HTTP 客户端库 axios 确认遭供应链攻击，最新版本 1.14.1 引入了来历不明的 plain-crypto-js 依赖包，Socket AI 分析确认其为恶意加载程序。

npm 生态核心依赖 axios（周下载量 3 亿次）遭遇新型供应链攻击。安全研究员 Feross（@ferross）披露：axios 1.14.1 版本新增了 plain-crypto-js@4.2.1 依赖，而该包此前并不存在——这是典型的供应链劫持标志。

Socket AI 的分析揭示了 plain-crypto-js 的恶意行为模式：运行时解密并执行有效载荷；动态加载 fs、os、execSync 等系统模块以规避静态分析；将 payload 文件写入系统 temp 和 Windows ProgramData 目录；执行后删除和重命名 artifact 以销毁取证痕迹。

目前 axios 团队尚未发布安全更新。Feross 建议开发者立即锁定 axios 版本并审查 lockfile，切勿升级到最新版本。

相关链接：
- Feross: npm axios 供应链攻击详解：https://x.com/ferross/status/2038807290422370479
- Yuchenj_UW: 相关技术分析：https://x.com/Yuchenj_UW/status/2038831443271704964

---

## [Claude Code 内置「用户挫败感检测」：一行 regex 触发情绪响应](https://x.com/byteHumi/status/2038960489154380261) `#4`

> Claude Code 内置了检测用户愤怒情绪的 regex，完全硬编码，触发时会改变 Claude 的行为和 UI——相关讨论引发大量开发者共鸣。

Claude Code 的代码库中有一项鲜为人知的功能：内置的"用户挫败感检测"。开发者 Humi（@byteHumi）分享了一张截图，展示了这段完全硬编码的 regex 模式，用于检测用户是否在咒骂 AI——当检测到用户愤怒时，Claude 会改变其行为和界面状态。

该 regex 覆盖了从"wtf"到"fuck you"再到"this sucks"等常见表达式的组合，显示出 Claude Code 在用户体验层面的精细设计。这一发现引发了大量开发者的共鸣和幽默回应，相关浏览量超过 44 万。

![Claude Code 挫败感检测 regex](media/2038960489154380261_0.jpg)

相关链接：
- byteHumi: Claude Code 挫败感检测代码：https://x.com/byteHumi/status/2038960489154380261

---

## [Sebastian Raschka 谈 Claude Code 源码：真正秘密是 harness 而非模型本身](https://x.com/rasbt/status/2038980345316413862) `#5`

> Claude Code 源码曝光后，Sebastian Raschka 撰文分析：Claude Code 比普通 Chat UI 代码能力强，关键不在于模型，而在于精心设计的 software harness——专用工具链、prompt cache 复用和 live repo context。

Claude Code 源码曝光后，Sebastian Raschka（@rasbt）发布了备受关注的分析文章。Raschka 指出：Claude Code 之所以比普通 Chat UI 代码能力强，关键不在于底层的 Claude 模型，而在于其精心设计的 software harness。

他总结了三个核心工程细节：第一，Claude Code 在启动时会主动加载当前 git 分支、最近 commit、CLAUDE.md 等 live repo context，而非将代码视为静态文本；第二，存在类似边界标记的机制分隔静态和动态内容，静态部分全局缓存以避免每次重建；第三，Claude Code 放弃了通过 Bash 调用 grep/rg 的传统方式，转而使用专用的 Grep 工具和 Glob 工具，并集成了 LSP（Language Server Protocol）获取调用层级和引用关系——这相比普通 Chat UI 是显著的性能提升。

Raschka 的判断是：如果把其他模型（如 DeepSeek、MiniMax 或 Kimi）接入同一 harness 并做相应优化，也能达到很强的代码能力。harness 设计才是真正的护城河。

相关链接：
- rasbt: Claude Code 源码分析：https://x.com/rasbt/status/2038980345316413862

---

## [Stanford 与 MIT 联合研究：固定 LLM 换 harness 可产生 6 倍性能差距](https://x.com/omarsar0/status/2038967842075500870) `#6`

> Stanford 和 MIT 联合研究表明，围绕同一 LLM 更换 harness（测试框架），同一 benchmark 可产生 6 倍性能差距——评测体系本身对结果的影响远超模型本身。

AI 领域广泛默认"模型性能 = 基准分数"，但 Stanford 和 MIT 的联合研究揭示了一个更复杂的现实：同一 LLM，搭配不同的 harness（评测框架/工具链），性能差距可达 6 倍。这意味着当前的 benchmark 排名可能更多反映的是 harness 设计能力，而非模型本身的推理能力。

研究进一步提出了一个更激进的问题：如果 harness 本身也能被自动化优化，模型评估将进入新范式。这对研究者和模型开发者均有重要启示：在关注刷榜分数之前，或许应该先审视评测工具本身的合理性。

相关链接：
- elvis: Stanford/MIT harness 研究解读：https://x.com/omarsar0/status/2038967842075500870

---

## [Qwen3.5-27B 蒸馏版：从 Claude 4.6 Opus 推理链中提取，16GB VRAM 可跑](https://x.com/outsource_/status/2038999111039357302) `#7`

> 基于 Qwen3.5 微调的 27B 变体，通过蒸馏 Claude 4.6 Opus 的推理轨迹，在消费级 GPU（仅 16GB 显存）上实现了接近 Opus 级别的前沿代码推理能力。

开发者 Eric（@outsource_）发布了 Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled 模型：基于 Qwen3.5 微调，用 Claude 4.6 Opus 的推理轨迹做知识蒸馏，27B 参数在消费级 GPU（16GB 显存）上即可运行，提供了接近 Opus 级别的前沿代码推理能力。

模型已在 HuggingFace 发布，包含 v1 和 v2 GGUF 量化版本，降低了本地部署门槛。这是知识蒸馏技术在 2026 年的又一次成功应用，展示了用顶级模型监督信号训练小参数模型的可行性。

相关链接：
- outsource_: Qwen3.5-27B 推理模型发布：https://x.com/outsource_/status/2038999111039357302
- HuggingFace: Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled：https://huggingface.co/Jackrong/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled

---

## [Holo3 发布前沿 computer-use 模型：78.9% OSWorld 得分，成本仅十分之一](https://x.com/hcompany_ai/status/2039021096649805937) `#8`

> Holo3 发布新一代 computer-use 系列模型，在 OSWorld-Verified 基准上达到 78.9%，超越 GPT-5.4 和 Opus 4.6，且 weight-only inference 使成本仅为十分之一。

Holo3 推出其 computer-use 系列模型，在 OSWorld-Verified 基准上达到 78.9% 准确率，在该测试维度上超越了 GPT-5.4 和 Opus 4.6。更值得关注的是其成本结构：支持 weight-only inference，使服务成本仅为主流方案的十分之一。

computer-use 能力——让 AI 直接操控计算机完成复杂任务——正在成为 2026 年模型竞争的新高地。Holo3 以如此低的成本达到前沿水平，对需要自动化操作能力的开发者和企业用户有很强吸引力。

相关链接：
- hcompany_ai: Holo3 发布公告：https://x.com/hcompany_ai/status/2039021096649805937

---

## [Google Veo 3.1 Lite：视频生成成本再降，4 月 7 日进一步调价](https://x.com/OfficialLoganK/status/2039015034286694618) `#9`

> Google 推出 Veo 3.1 Lite，是目前成本效率最高的视频生成模型，同时宣布 4 月 7 日下调 Veo 3.1 Fast 价格，持续压低 AI 视频生成门槛。

Google 在 AI 视频生成领域继续推进价格战。Logan Kilpatrick（@OfficialLoganK）宣布推出 Veo 3.1 Lite，定位为"迄今成本效率最高的视频生成模型"。同时 Google 预告 4 月 7 日将进一步下调 Veo 3.1 Fast 的价格。

AI 视频生成在 2026 年的竞争正在从能力比拼转向成本比拼，门槛持续下降对独立开发者和小型团队是直接利好。

相关链接：
- Logan Kilpatrick: Veo 3.1 Lite 发布：https://x.com/OfficialLoganK/status/2039015034286694618
