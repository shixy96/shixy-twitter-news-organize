# x-news Pipeline 整理计划

> original prompt: 这个项目是一个 skill-native 的项目，需要把 @../skills/skills/x-news-data-pipeline/ @../skills/skills/x-news-editorial/ @../skills/skills/x-news-to-daily-post/ @../skills/skills/x-news-tts/ 整合起来(不是做成一个 skill，还是要按照职责分，避免一个 skill 包揽好几件完全不同的事)，整体流程见 @../cron/jobs.json "X List AI-NEWS 每日分析" job。目标是做成可分发的、效果稳定的 skill 仓库。需要整理整个流程，去掉冗余的、不确定的部分，要做 skill evaluation harness，提高 skill 的可评测性
> 本文档是 x-news 日更 AI 新闻 pipeline 的重构设计文档。作为 handoff 文档，包含完整的背景、已知问题、设计决策和实施指南

## Context

x-news pipeline 当前是"全 agent 驱动"的 prompt-native 设计，技能通过读 SKILL.md 执行，存在结果不稳定、难以量化评测的问题。pipeline-redesign.md 定义了重构目标：将固定 I/O 步骤沉淀成脚本，用 JSON 契约串联各阶段，使 pipeline 可评测、可分发。

x-news-job 是在 general skills monorepo 中已经实现的同 pipeline，它有完整的 repo-native eval harness（`eval_lib.py` ~1585 行）和 Python 编排层。本项目（x-news-skills）是**可分发的 skill 仓库**，但 eval 基础设施应借鉴 x-news-job 的成熟实践。

---

## 背景与动机

### 为什么需要重构

当前 pipeline 存在以下问题，促成本次重构：

| 问题 | 影响 | 优先级 |
|------|------|--------|
| 中间产物 report.md 需要 agent 解析 | markdown 解析歧义导致 downstream 校验不稳定 | 高 |
| 信息补充依赖 agent 内存 | 可能遗漏、结果不一致 | 高 |
| 各阶段输出无 schema 校验 | 问题层层传递，到 QA 才发现 | 中 |
| 去重逻辑由 agent 实现 | 每次运行结果可能有差异 | 中 |
| strong 信号占比过高 | 入选条目标准偏宽 | 低 |

### 当前数据流（重构前）

```
data-pipeline: raw.json → filtered.json
     ↓
editorial: filtered.json + agent → report.md + companion.json
     ↓
daily-post: report.md + companion.json + agent → post.md + media/
     ↓
tts: post.md → script.txt + audio.mp3
     ↓
html → wechat
     ↓
quality-audit: qa-report.md
```

### 目标数据流（重构后）

```
data-pipeline: raw.json + filtered.json
     ↓
editorial: filtered.json + dedup.py → companion.json
     ↓
daily-post: companion.json + enrich.py + Agent assemble step → post.json + post.md + media/
     ↓
tts: post.json → script.txt + audio.mp3
     ↓
html → wechat
     ↓
quality-audit: 全链路 JSON 校验 + qa-report.md
```

---

## 核心设计原则

1. **去掉中间 markdown** — 阶段间传递改用 JSON，避免 markdown 解析歧义
2. **固定 I/O 的步骤沉淀成脚本** — 减少 agent 不稳定性
3. **数据流可验证** — 每步输入输出有 schema 可循
4. **信息筛选在 editorial 完成，daily-post 只做转化** — 单一职责
5. **旁路式 QA** — 不阻断发布，但校验结果结构化

### 复杂度控制原则

所有实现必须遵循以下约束：

1. **每个脚本单一职责**：一个脚本只做一件事（raw_validate.py 只校验 JSON，render_md.py 只做模板渲染），禁止大而全的脚本
2. **无新增外部依赖**：只用 Python 标准库，禁止引入 requests、pyyaml 等第三方库（subprocess 调用外部工具除外）
3. **脚本行数上限**：每个脚本不超过 200 行，超出则拆分成多个脚本
4. **无复杂状态管理**：脚本之间通过 JSON 文件传递状态，不共享内存或全局变量
5. **错误处理明确**：工具调用失败时显式降级，不静默忽略

---

## 可行性审查

### 设计分析

**1. 架构是否 sound？阶段边界是否清晰？**

五阶段 + JSON 边界契约是成熟模式，阶段边界逻辑清晰。有一个边界模糊之处：enrich.py 标注为"脚本化"，但它需要网络调用（twitter CLI、gh CLI、WebFetch），这实际上是 I/O 密集型获取步骤，不是纯转换。设计原则 4 说"daily-post 只做转化"与此存在矛盾——已明确：enrich.py 负责信息获取，assemble 是 Agent 组装步骤。

**2. 去掉 report.md 是否正确？**

正确。当前 agent 生成 markdown，validate_report.py 解析回结构化数据再校验，这个 roundtrip 是不稳定性的根源。companion.json schema 覆盖了 report.md 的所有字段。

**3. companion.json schema 是否完整？**

基本完整。缺失一点：没有记录 Agent 对 require_decision 条目的决策理由（当前隐含在 report.md 中）。另外 categories[] 和 items[] 有冗余——items[] 是 source of truth，categories[] 是派生视图，需在文档中明确。

**4. Agent 步骤 vs 脚本步骤的划分是否合理？**

合理，但 `assemble` 命名存在歧义：它在文档中容易被误读为脚本化步骤，但 body 生成本质上是 Agent 工作（"高价值 3-4 段"、"metrics 口语化"）。已明确：assemble 是 Agent 组装步骤，不是仓库里的脚本文件；脚本只负责收集/校验/格式化。

### 实现分析

**1. 迁移 vs 新实现**

本项目是**在新仓库中重新实现**，不是迁移。Phase 1-3 可独立开发和验证，Phase 4 为集成节点，Phase 5 QA 依赖 Phase 4 完整 artifact。

**2. validate_report.py（1046 行）的去留**

validate_report.py 有三部分逻辑：
- Report markdown 解析 → report.md 删除后成为死代码
- Companion JSON 校验 → 提取到 validate_companion.py，需重写跨引用逻辑
- 历史 dedup 逻辑 → 提取到 dedup.py

建议：不修改原文件，新建 dedup.py 和 validate_companion.py，原文件归档供参考。

**3. generate_qa_report.py（1014 行）的去留**

需拆分：
- stage_editorial() → 调用 validate_report.py，该路径在 report.md 删除后 break，需重写
- stage_daily_post() → 依赖 post.md 特定格式，改为针对 post.json 校验
- 4 个 review_* 函数 → 提取到 editorial_review.py，适配 post.json

### 风险评估

| 风险 | 等级 | 说明 |
|------|------|------|
| Phase 4 集中切换 | 高 | editorial/daily-post/quality-audit 需同步切换，否则 pipeline break |
| enrich.py 工具调用 | 高 | standalone 脚本如何调用 twitter/gh/WebFetch 工具，需明确 subprocess 方案 |
| assemble 范围歧义 | 中 | 若期望生成 prose 文本则必须是 Agent 步骤，不能是纯脚本 |
| QA 断言重写 | 中 | generate_qa_report.py ~1014 行需全面适配新 artifact 格式 |
| history dedup 回归 | 中 | 新 dedup.py 需同时支持读取旧 report.md 和新 companion.json 历史格式 |

### 设计缺口

1. **PRIOR_COMPANIONS[]**：脚本取今天-2 天日期，构造 `$DAILY_DIR/{DATE}/companion.json` 路径数组，较新日期在前
2. **TTS 接口变更被夸大**：tts.py 代码不变，仅 SKILL.md 变更读取源指定
3. **下游 HTML/WeChat 阶段**：文档只顺带提及，QA audit 依赖之但未详细说明

---

## 各阶段详解

### 1. x-news-data-pipeline

**职责**：抓取 X List 推文，按 engagement 信号分层。

#### 输入参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `SOURCE_CONFIG` | x-list-sources.json 路径 | `~/.openclaw/.../x-list-sources.json` |
| `OUTPUT_DIR` | 输出目录 | `~/.openclaw/.../daily/2026-04-01/` |
| `REPORT_BOUNDARY` | 截止时间 ISO 8601 | `2026-04-01T06:00:00+08:00` |
| `FRESH_HOURS` | fresh 窗口（默认 24） | `24` |
| `BACKFILL_HOURS` | backfill 窗口（默认 48） | `48` |

#### SOURCE_CONFIG Schema

```json
{
  "signal_thresholds": {
    "strong": {
      "conditions": 2,
      "likes": 200,
      "bookmarks": 80,
      "interaction_rate": 0.015
    },
    "medium": {
      "conditions": 1,
      "likes": 50,
      "bookmarks": 20
    }
  },
  "defaults": {
    "max": 50,
    "detail_max": 3
  },
  "sources": [
    { "id": "<list_id>", "name": "AI Leaders", "max": 240, "detail_max": 5 }
  ]
}
```

**说明**：
- `conditions`: strong 需要满足几个条件（默认 2 个：likes OR bookmarks OR ir）
- medium 满足 1 个条件即可
- 阈值可按 source 单独配置，也可走 defaults

#### 处理流程

```
Step 1: x_list_fetch.py
  └── twitter CLI 抓取 X List 推文
  └── 原始 JSON 稳定写入 OUTPUT_DIR/raw.json（先写 .tmp，校验通过后 rename）
  └── 关键：不用 stdout 重定向，避免 stderr 混入

Step 2: raw_validate.py（新增）
  └── json.load() 校验
  └── 失败：删除坏文件，严格重跑 Step 1
  └── 成功：输出 "RAW_JSON_OK"

Step 3: filter.py
  └── 从 SOURCE_CONFIG 读取信号阈值
  └── 分组、去重、author cap（每作者最多 2 条）
  └── 输出到 OUTPUT_DIR/filtered.json
```

#### 输出

**raw.json** — 原始推文数组：
```json
[
  {
    "id": "123456",
    "url": "https://x.com/user/status/123456",
    "author": "@username (Display Name)",
    "text": "推文内容",
    "time": "2026-04-01T10:00:00+00:00",
    "likes": 500,
    "views": 100000,
    "bookmarks": 100,
    "links": ["https://github.com/..."],
    "media": [...],
    ...
  }
]
```

**filtered.json**：
```json
{
  "stats": {
    "total_raw": 150,
    "unique": 120,
    "within_window": 80,
    "grouped_candidates": 45,
    "strong": 10,
    "medium": 5,
    "backfill": 3,
    "skipped": 35
  },
  "strong": [ /* items with _signal: "strong" */ ],
  "medium": [ /* items with _signal: "medium" */ ],
  "backfill": [ /* items with _window: "backfill" */ ]
}
```

每条 item 附加字段：`_canonical_id/_url/_author/_text`、`_signal/_score/_window`、`_aggregate_likes/_bookmarks/_score/_interaction_rate`、`_strong_links/_external_links/_related_urls`、`_source_proxy`（是否代理源推文）。

#### 成功信号

`RAW_JSON_OK` + filter.py 退出码 0

---

### 2. x-news-editorial

**职责**：去重、选题、生成 companion.json。

#### 输入参数

| 参数 | 说明 |
|------|------|
| `FILTERED_PATH` | filtered.json 路径 |
| `PRIOR_COMPANIONS[]` | 历史 companion JSON 路径数组 |
| `REPORT_BOUNDARY` | 时间基准 ISO 8601 |
| `REPORT_TIME` | 报告显示时间 |
| `OUTPUT_PATH` | companion.json 输出路径 |

**注意**：`PRIOR_COMPANIONS` 由编排层（cron/orchestrator）计算并传入。编排层取今天-2 天的日期，构造 `$DAILY_DIR/{DATE}/companion.json` 路径数组，较新日期在前。dedup.py 不做日期计算，只接收不可变的历史 artifact 路径——这是为了保证 dedup 结果可复现、eval case 可精确重放。

#### 处理流程

```
Step 1: dedup.py（脚本化）
  └── 输入：filtered.json, PRIOR_COMPANIONS[]（编排层传入的显式路径）
  └── 输出一：dedup_result.json
    {
      "auto_resolved": [
        { "canonical_id": "...", "dedup_type": "history_exact_match", "reason": "上一期已选" }
      ],
      "history_prior_match": [
        {
          "canonical_id": "...",
          "prior_item": { /* 历史中那条 item */ },
          "has_new_content_delta": true/false,
          "delta_summary": "新链接 / 新时间戳 / 新正文",
          "reason": "历史已有相同 canonical_id，需判断是否为有效跟进"
        }
      ],
      "require_decision": [
        {
          "canonical_id": "...",
          "candidates": [ /* 同事件的不同 candidate */ ],
          "reason": "需要判断哪条更相关"
        }
      ],
      "by_author": { "author_name": [candidates...] }
    }
  └── 输出二：historical_signatures.json（供校验用）

Step 2: Agent 决策
  └── 读取 dedup_result.json
  └── 对 history_prior_match 逐个判断（有 new_content_delta 时决定是否标记为跟进）
  └── 对 require_decision 逐个判断（选哪条、是否跟进等）
  └── 决定最终入选 items（目标 8-12 条）
  └── 直接生成 companion.json

Step 3: validate_companion.py（脚本化）
  └── 校验 schema
  └── 校验 items 可追溯到 filtered candidates
  └── 校验 stats 一致性
  └── 校验 dynamic title 格式
```

#### 输出 schema

**companion.json**（替代 report.md）：

```json
{
  "generated_at": "2026-04-01T06:00:00+08:00",
  "report_date": "2026-04-01",
  "title": "Claude Code 源码意外泄漏【AI 资讯日报 2026-04-01】",
  "description": "每日 AI 领域精选资讯",
  "stats": {
    "strong": 12,
    "medium": 3,
    "backfill": 2,
    "total": 17,
    "selected": 9
  },
  "categories": [
    {
      "name": "开发生态",
      "items": [ /* items in this category */ ]
    }
  ],
  "items": [
    {
      "index": 1,
      "canonical_id": "2038894956459290963",
      "title": "条目标题",
      "author": "作者名",
      "author_screen_name": "screen_name",
      "category": "开发生态",
      "is_highlight": true,
      "summary": "要点内容",
      "metrics": { "likes": 41188, "views": 28480533, "bookmarks": 36888 },
      "primary_url": "https://x.com/.../status/...",
      "strong_links": ["https://github.com/..."],
      "external_links": ["https://..."],
      "related_urls": ["https://x.com/.../status/..."],
      "is_backfill": false,
      "is_followup": false
    }
  ]
}
```

**字段说明**：
- `title`: dynamic，从当日内容生成，格式 `{核心要点}【AI 资讯日报 {DATE}】`
- `categories[]`: 按 6 个允许分类分组（模型发布、开发生态、技术洞察、产品动态、安全事件、行业观点）
- `items[]`: 打平的全局编号，与 categories 里的引用一一对应；**source of truth**，categories[] 为派生视图
- `is_highlight`: 是否标记为 `> **[重点关注]**`

#### 成功信号

`validate_companion.py` 退出码 0

---

### 3. x-news-to-daily-post

**职责**：信息补充 + 组装输出。

**核心约束**：**Phase 2 editorial 输出的条目，Phase 3 必须全部处理，不允许删减**。只能做信息补充（enrich）、格式转换（assemble → render_md）、输出校验，不做二次筛选。

#### 输入参数

| 参数 | 说明 |
|------|------|
| `COMPANION_PATH` | companion.json 路径 |
| `REPORT_DATE` | 日期 |
| `OUTPUT_DIR` | 输出目录 |

#### 处理流程

```
Step 1: enrich.py（信息补充，脚本化）
  └── 输入：companion.json
  └── 工具调用方式：通过 subprocess 调用 twitter CLI、gh CLI；WebFetch 通过 HTTP 请求。工具失败时降级使用 companion.json 的 summary，打印警告，记录 fetch_status。
  └── 输出：enrichment.json
    {
      "items": [
        {
          "index": 1,
          "fetch_status": {
            "primary_url": "success" | "failed" | "degraded",
            "related_urls": "success" | "partial" | "failed",
            "link_fetches": "success" | "partial" | "failed",
            "media": "success" | "degraded" | "skipped"
          },
          "primary_url_fetch": { /* twitter tweet YAML */ },
          "related_url_fetches": [ /* 1-2 个补充 X URL YAML */ ],
          "link_fetches": [
            { "url": "https://github.com/...", "type": "github", "data": { "description": "...", "stars": N }, "fetch_status": "success" | "failed" },
            { "url": "...", "type": "webfetch", "data": { "title": "...", "summary": "..." }, "fetch_status": "success" | "failed" }
          ],
          "selected_context_facts": [
            { "text": "...", "source_url": "...", "source_type": "github|web|x" }
          ],
          "media_files": ["media/2026-04-01/123456_0.jpg"],
          "warnings": ["twitter rate limited, used summary fallback", ...]
        }
      ]
    }
  └── 高价值条目（is_highlight:true）下载媒体到 media/{DATE}/
  └── 最低覆盖率约束：highlight 条目若 primary_url_fetch 失败，标记为 degraded，validate_output.py 将其作为 blocking warning
  └── 工具失败：打印警告到 stderr，降级使用 companion.json 的 summary，fetch_status 记录为 degraded

Step 2: assemble（Agent 组装步骤，结构化输入输出）
  └── 输入：companion.json + enrichment.json
  └── 输出：post.json（item title 与 body 由 Agent 生成，非模板拼接）
  └── 脚本负责：收集结构化数据、校验字段完整性、格式化 post.json 结构、注入 frontmatter 元数据
    {
      "title": "动态标题【AI 资讯日报 2026-04-01】",
      "description": "...",
      "pubDate": "2026-04-01",
      "tags": ["AI", "资讯"],
      "slug": "ai-news-2026-04-01",
      "categories": [
        {
          "name": "开发生态",
          "items": [
            {
              "index": 1,
              "title": "H2 标题",
              "link": "https://x.com/...",
              "body": "正文内容，整合 summary + enrichment + media",
              "media": ["media/2026-04-01/xxx.jpg"],
              "related_links": [
                { "text": "GitHub", "url": "https://github.com/..." }
              ]
            }
          ]
        }
      ]
    }
  └── item title: 基于 companion + enrichment 重新组织语言，不能直接复用 companion 原题
  └── body: 高价值 3-4 段，普通 3+ 句
  └── body 整合所有信息
  └── metrics 口语化: "收到广泛关注" 而非 41188 likes

Step 3: render_md.py（脚本化）
  └── 输入：post.json
  └── 输出：post.md
  └── 按 category 分 section
  └── 无概览区

Step 4: validate_output.py（确定性校验）
  └── frontmatter 字段完整性
  └── category 分组正确
  └── item 数与 companion.json 一致
  └── item title 不为空、非占位符，且不能与 companion 原题完全相同
  └── 无 markdown 残留
  └── highlight 条目 enrichment 覆盖率检查：primary_url_fetch 失败时 emit blocking warning
```

#### 输出 schema

**post.json**：
```json
{
  "title": "动态标题【AI 资讯日报 2026-04-01】",
  "description": "每日 AI 领域精选资讯",
  "pubDate": "2026-04-01",
  "tags": ["AI", "资讯"],
  "slug": "ai-news-2026-04-01",
  "categories": [
    {
      "name": "开发生态",
      "items": [
        {
          "index": 1,
          "title": "条目标题",
          "link": "https://x.com/...",
          "body": "正文内容...",
          "media": ["media/2026-04-01/xxx.jpg"],
          "related_links": [...]
        }
      ]
    }
  ]
}
```

**post.md**：
```markdown
---
title: "{动态标题}【AI 资讯日报 2026-04-01】"
description: "每日 AI 领域精选资讯"
pubDate: 2026-04-01
tags: ["AI", "资讯"]
slug: "ai-news-2026-04-01"
---

# {动态标题}

## 开发生态

### 条目标题

正文内容...

![图片](media/2026-04-01/xxx.jpg)

相关链接：
- [GitHub](https://github.com/...)

---

## 模型发布

...
```

#### TTS 相关

**接口变更说明**：`tts.py` 代码本身不变（接收 `--input script.txt`），变更仅在 SKILL.md：指定 Agent 从 post.json 而非 post.md 读取源数据生成 script.txt。

post.json.categories[].items[].body 已整合所有信息（summary + enrichment + media），metrics 已口语化，Agent 将其展开为 TTS 脚本。

#### 成功信号

`validate_output.py` 退出码 0

---

### 4. x-news-tts

**职责**：将日报转为 TTS 朗读脚本 + 音频。

#### 输入参数

| 参数 | 说明 |
|------|------|
| `POST_JSON_PATH` | post.json 路径 |
| `OUTPUT_DIR` | tts/ 目录 |

#### 处理流程

```
Step 1: Agent 生成 TTS 脚本
  └── 输入：post.json
  └── 消费：post.json.categories[].items[].title + body
  └── 规则：
      - metrics 口语化："收到广泛关注" 而非 41188 likes
      - 保留 title，body 展开
      - 无概览区
      - 开场白/结束语

Step 2: tts.py
  └── edge-tts 生成 MP3
```

**TTS 脚本格式**：
```
大家好，今天是2026年4月1日，欢迎收听今日 AI 资讯速递。

[title]: body 内容...

[title]: body 内容...

以上就是今天的 AI 资讯精选。感谢收听，我们明天再见。
```

#### 输出

- `tts/script.txt`
- `tts/audio.mp3`

---

### 5. x-news-quality-audit

**职责**：旁路式 QA，校验全链路 artifact，不阻断发布。

#### 输入

各阶段产出的 JSON/文件路径：
- `raw.json`
- `filtered.json`
- `companion.json`
- `post.json`
- `enrichment.json`（highlight 条目覆盖率低于阈值时 emit blocking warning）
- `post.md`
- `tts/script.txt`
- `tts/audio.mp3`
- `html/`（可选）

#### 处理流程

```
Step 1: stage_json_validate.py（脚本化）
  └── 针对每个 JSON 做 schema 校验
  └── filtered.json、companion.json、post.json required fields
  └── stats 一致性

Step 2: stage_contract.py（脚本化）
  └── companion.json items ↔ filtered.json candidates 映射校验
  └── post.json items ↔ companion.json items 映射校验
  └── 无信息丢失

Step 3: editorial_review.py（脚本化）
  └── 针对 post.json 做编辑审查
  └── 可读性、事实稳健性，完成度、编排感

Step 4: generate_qa_report.py
  └── 汇总所有 stage 结果
  └── 输出 qa-report.md
```

#### 编辑审查维度

| 维度 | 检查项 |
|------|--------|
| 可读性 | 标题格式、首段长度(>=45字)、段落密度(无>=220字段落) |
| 事实稳健性 | 断言词 vs 不确定词一致性 |
| 成稿完成度 | 无 placeholder、无缺失图片、链接完整 |
| 日报编排感 | 分类均衡、无 theme clustering |

#### 定位

旁路式，不阻断。

---

## 跨阶段共享模块

### src/x_news_shared/

```
src/x_news_shared/
├── __init__.py
├── schema.py           # JSON Schema 定义
├── normalize.py        # URL 规范化（从 x_news_common.py 提取）
└── validate.py         # 通用 JSON 校验函数
```

所有 skill 共享 schema 定义，保证阶段间数据契约一致。

**schema.py 要定义的 Schema**：
- `RAW_SCHEMA` — raw.json 数组元素
- `FILTERED_SCHEMA` — filtered.json（stats + strong/medium/backfill 数组）
- `COMPANION_SCHEMA` — companion.json（包含新增字段：title, description, report_date, categories[]）
- `POST_SCHEMA` — post.json
- `DEDUP_RESULT_SCHEMA` — dedup_result.json
- `ENRICHMENT_SCHEMA` — enrichment.json

---

## 实施计划

### Phase 1 — Foundation（无 pipeline 影响）

1. 创建 `src/x_news_shared/` 共享模块（normalize.py, schema.py, validate.py）
2. 创建 `raw_validate.py`（skills/x-news-data-pipeline/scripts/）
3. 改造 `filter.py` 读 SOURCE_CONFIG 阈值（向后兼容，无配置时用硬编码默认值）
4. 更新 skills/x-news-data-pipeline/SKILL.md

### Phase 2 — Editorial 脚本化

1. 创建 `dedup.py`（PRIOR_COMPANIONS 由编排层计算并传入，脚本只接收显式路径）
2. 创建 `validate_companion.py`（从 validate_report.py 提取 companion 校验逻辑并重写）
3. 扩大 companion.json schema（新增 title, description, report_date, categories[]）
4. 更新 skills/x-news-editorial/SKILL.md（去 report.md）
5. 用真实历史数据测试 dedup.py 和 validate_companion.py

### Phase 3 — Daily-Post 脚本化

1. 创建 `render_md.py`（纯模板渲染）
2. 创建 `validate_output.py`（校验 post.json 完整性）
3. 创建 `enrich.py`（subprocess 调用 twitter/gh/WebFetch，降级处理）
4. Agent 步骤：assemble（body 由 Agent 生成，不对应仓库脚本文件）
5. 更新 skills/x-news-to-daily-post/SKILL.md（去 REPORT_PATH）

### Phase 4 — 集成

1. 串联各阶段，端到端测试
2. 更新 skills/x-news-tts/SKILL.md（读取源改为 post.json）
3. 更新 cron job / 编排层参数
4. 验证无信息丢失、TTS 脚本正常生成

### Phase 5 — QA 体系重建

1. 创建 `stage_json_validate.py`
2. 创建 `stage_contract.py`
3. 创建 `editorial_review.py`（适配 post.json）
4. 重写 `generate_qa_report.py` 为聚合脚本

---

## Eval 基础设施

借鉴 x-news-job eval harness 设计模式：

### CLI 入口

```
x-news eval <command> [options]
```

**命令分类**：

#### 诊断类（出了问题想知道原因）

| 命令 | 说明 |
|------|------|
| `eval diagnose --date 2026-04-01` | 诊断当天各阶段产物质量问题（JSON 校验失败、enrichment 降级、coverage 低） |
| `eval diagnose --phase editorial --date 2026-04-01` | 针对单个阶段诊断 |
| `eval compare <run-a> <run-b>` | 对比两次运行的产物差异 |

#### 重跑类（修复问题后想验证）

| 命令 | 说明 |
|------|------|
| `eval run --date 2026-04-01` | 全流程 eval，runs=8（默认），测稳定性 |
| `eval run --phase editorial --date 2026-04-01` | 单阶段重跑（绕过其他阶段，快速验证修复） |
| `eval run --with-fixtures --date 2026-04-01` | 用 fixture 数据重跑，绕过真实 API，测脚本逻辑 |

#### 统计分析类（长期观察质量趋势）

| 命令 | 说明 |
|------|------|
| `eval history` | 查看历史所有 eval run 的通过率、失败模式、高方差案例 |
| `eval benchmark --date 2026-04-01` | 多次运行聚合报告（pass rate、方差、质量维度） |

#### Case 管理类（维护 eval 基础设施）

| 命令 | 说明 |
|------|------|
| `eval cases list` | 列出所有 case 和 fixture |
| `eval cases add --date 2026-04-01` | 用历史某天数据新增一个 case |
| `eval cases validate` | 验证 case 定义（schema 合法、expected 与 fixture 一致） |

---

### 结构化 Eval Case

```
eval/cases/
├── suites/
│   ├── suite-2026-04-01.json
│   └── suite-2026-04-02.json
└── fixtures/
    ├── 2026-04-01/
    └── 2026-04-02/
```

**Case schema**：
```json
{
  "id": "suite-2026-04-01",
  "report_date": "2026-04-01",
  "runs": 8,
  "inputs": {
    "source_config": "config/x-list-sources.json",
    "report_boundary": "2026-04-01T06:00:00+08:00"
  },
  "expected": {
    "selected_canonical_ids": ["id1", "id2", ...],
    "allowed_followups": ["id3"],
    "categories": ["开发生态", "模型发布", ...],
    "min_enrichment_coverage": {
      "highlight_items": { "primary_url_fetch": "success", "media": "success" }
    }
  }
}
```

---

### 断言体系

**可 programmatic 检查的**：
- companion.json stats 一致性：`stats.selected == len(items)`
- 端到端 item 数量：`post.json item count == companion.json item count`
- JSON schema 校验通过
- 无信息丢失
- 选中 item 的 canonical_id 出现在 expected.selected_canonical_ids 中
- follow-up item 的 canonical_id 出现在 expected.allowed_followups 中
- highlight 条目 enrichment coverage 达标

**多次运行方差检查**：
- 多次运行（runs>=8）的 companion.json 条目 Jaccard 相似度 >= 0.75
- 低于阈值则 FAIL，记录不稳定案例

**Human review**：
- 4 个 editorial review 维度的评分
- 参照 x-news-job 的 `eval_lib.py` 断言函数模式

---

### Eval 工作空间

```
eval/
├── README.md
├── cases/          # case 定义（带 expected outputs）
├── fixtures/       # 静态输入（真实历史数据）
│   ├── 2026-04-01/
│   └── 2026-04-02/
└── runs/           # eval 输出
    └── <date>/
        └── <timestamp>-<mode>-<id>/
            ├── metrics.json    # PASS/WARN/FAIL + failure_codes + 方差指标
            ├── judge.json      # rule-based quality summary
            └── artifacts/      # 各阶段 artifact 拷贝
```

---

## 已知问题与限制

| 问题 | 说明 | 解决方案 |
|------|------|---------|
| strong 信号占比高 | 当前阈值偏宽 | 通过 SOURCE_CONFIG 调整 signal_thresholds |
| backfill 界定模糊 | 24-48h 窗口外的不处理 | 当前设计仅处理窗口内 |
| TTS metrics 口语化标准 | 无明确规则 | 依赖 agent 判断，积累案例 |
| history dedup 过渡期 | 历史目录含旧 report.md 和新 companion.json | dedup.py 需同时支持两种格式 |
| highlight enrichment 降级静默 | 工具全挂时 post.json 仍"合法" | fetch_status 字段 + validate_output.py blocking warning |

---

## 文件变更汇总

### 新建文件

**共享模块（Phase 1）**：
- `src/x_news_shared/{__init__.py, normalize.py, schema.py, validate.py}`

**data-pipeline（Phase 1）**：
- `skills/x-news-data-pipeline/scripts/raw_validate.py`

**editorial（Phase 2）**：
- `skills/x-news-editorial/scripts/dedup.py`
- `skills/x-news-editorial/scripts/validate_companion.py`

**daily-post（Phase 3）**：
- `skills/x-news-to-daily-post/scripts/render_md.py`
- `skills/x-news-to-daily-post/scripts/validate_output.py`
- `skills/x-news-to-daily-post/scripts/enrich.py`

**quality-audit（Phase 5）**：
- `skills/x-news-quality-audit/scripts/stage_json_validate.py`
- `skills/x-news-quality-audit/scripts/stage_contract.py`
- `skills/x-news-quality-audit/scripts/editorial_review.py`

**eval**：
- `eval/README.md`
- `eval/cases/`（各 case JSON）
- `eval/fixtures/`（历史数据 fixtures）

### 修改文件

| Skill | 变更 |
|-------|------|
| x-news-data-pipeline | SKILL.md（+raw_validate, +SOURCE_CONFIG schema）、filter.py（读阈值配置） |
| x-news-editorial | SKILL.md（去 report.md，+dedup.py, +validate_companion.py）、validate_report.py 归档 |
| x-news-to-daily-post | SKILL.md（去 REPORT_PATH，+4 脚本流程） |
| x-news-tts | SKILL.md（读取源改为 post.json），tts.py 代码不变 |
| x-news-quality-audit | SKILL.md 重写、generate_qa_report.py 改为聚合脚本 |

### 关键依赖文件（参考实现）

- `x-news-job/src/x_news/eval_lib.py` — eval harness 参考（fixture_copy/agent_turn 模式，metrics.json/judge.json 结构）
- `x-news-job/src/x_news/stages/editorial/validate_report.py` — 历史 dedup 逻辑和 companion 校验逻辑的提取来源
- `x-news-job/src/x_news/stages/qa/generate_qa_report.py` — QA 断言逻辑参考
- `x-news-job/eval/cases/` — eval case 结构参考

---

## 验证方式

```bash
# Phase 1-2 独立验证
python3 skills/x-news-data-pipeline/scripts/raw_validate.py --input eval/fixtures/2026-04-01/raw.json
python3 skills/x-news-data-pipeline/scripts/filter.py --config config/x-list-sources.json eval/fixtures/2026-04-01/raw.json

python3 skills/x-news-editorial/scripts/dedup.py --filtered eval/fixtures/2026-04-01/filtered.json --prior-companions $DAILY_DIR/2026-03-30/companion.json $DAILY_DIR/2026-03-31/companion.json
python3 skills/x-news-editorial/scripts/validate_companion.py --companion eval/fixtures/2026-04-01/companion.json --filtered eval/fixtures/2026-04-01/filtered.json

# Phase 3 独立验证
python3 skills/x-news-to-daily-post/scripts/render_md.py --input post.json --output post.md
python3 skills/x-news-to-daily-post/scripts/validate_output.py --post-json post.json --companion companion.json

# Phase 4 端到端
uv run x-news run daily --date 2026-04-02 --json

# Phase 5 QA
python3 skills/x-news-quality-audit/scripts/stage_json_validate.py --filtered filtered.json --companion companion.json --post post.json
python3 skills/x-news-quality-audit/scripts/stage_contract.py --filtered filtered.json --companion companion.json --post post.json
```

---

## 依赖工具

| 工具 | 用途 |
|------|------|
| `twitter` CLI | X API 抓取（x_list_fetch.py），另 enrich.py 通过 subprocess 调用 `twitter tweet` 获取详情 |
| `gh` CLI | GitHub 元数据（enrich.py 通过 subprocess 调用 `gh repo view`）|
| `edge-tts` | TTS 音频生成 |
