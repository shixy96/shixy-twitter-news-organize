---
name: x-news-to-daily-post
description: "基于共享日报目录中的 companion.json 生成 enrichment.json、post.json、post.md 和 media/。"
---

# x-news-to-daily-post

将 `x-news-editorial` 输出的 companion.json 转化为 post.json/post.md，补充信息并由 Agent 完成组装。

**核心约束**：**Phase 2 editorial 输出的条目，Phase 3 必须全部处理，不允许删减**。只能做信息补充（enrich）、Agent 组装（assemble）、格式渲染（render_md）、输出校验，不做二次筛选。

## 输入参数

基础调用只需要两个输入：

| 参数 | 说明 |
|------|------|
| `RUN_ROOT` | 运行时产物根目录 |
| `REPORT_DATE` | 报告日期 |

## 共享路径约定

```bash
DAILY_DIR="$RUN_ROOT/daily/$REPORT_DATE"
COMPANION_PATH="$DAILY_DIR/companion.json"
OUTPUT_DIR="$DAILY_DIR"
ENRICHMENT_PATH="$OUTPUT_DIR/enrichment.json"
POST_JSON_PATH="$OUTPUT_DIR/post.json"
POST_MD_PATH="$OUTPUT_DIR/post.md"
MEDIA_DIR="$OUTPUT_DIR/media"
RUN_LOG_PATH="$DAILY_DIR/run.log.jsonl"
RUN_ID="${RUN_ID:-manual-${REPORT_DATE}-$(TZ=UTC date '+%H%M%SZ')}"
mkdir -p "$OUTPUT_DIR" "$MEDIA_DIR"
export RUN_ROOT REPORT_DATE RUN_ID RUN_LOG_PATH
```

说明：
- 默认输入是上一阶段生成的 `$RUN_ROOT/daily/$REPORT_DATE/companion.json`
- 默认输出全部写回同一天目录
- `RUN_LOG_PATH` 是统一运行日志；脚本会记录 enrich 进度、渲染写出和校验失败
- 常见本地约定可以是 `RUN_ROOT="state.local"`，也可以是仓库外任意目录；这只是本地选择，不是共享协议的一部分
- 除非调用方显式要求覆盖，否则默认按以上路径读写

## 工作流程

### Step 1: enrich.py（信息补充，脚本化）

```bash
python3 {SKILL_DIR}/scripts/enrich.py \
  --companion "$COMPANION_PATH" \
  --output "$ENRICHMENT_PATH" \
  --media-dir "$MEDIA_DIR"
```

- 工具调用方式：通过 subprocess 调用 twitter CLI、gh CLI；WebFetch 通过 HTTP 请求
- 工具失败时降级使用 companion.json 的 summary，打印警告，记录 fetch_status
- 高价值条目（is_highlight:true）下载媒体到 media/{DATE}/

### Step 2: Agent 组装（**Agent 任务，非脚本**）

读取 `$COMPANION_PATH` 和 `$ENRICHMENT_PATH`，为每条入选内容编写中文标题和正文，填充 related_links 和 media，然后写出 `$POST_JSON_PATH`。

**输入文件：**
- `$COMPANION_PATH`：editorial 产出，包含 items 列表（含 summary、category、strong_links、metrics 等）和 categories 分组
- `$ENRICHMENT_PATH`：enrich.py 产出，每条 item 对应 link_fetches、selected_context_facts、media_files

**输出文件：** `$POST_JSON_PATH`，格式见本文件"post.json Schema"章节。

#### 每条 item 的生成规则

**MUST（强制执行）：**
- `title`：**必须用中文重写**，不得与 `companion.title` 完全相同（validate_output.py 会检测并报错）。简短有力，30 字以内，突出核心价值点。
- `body`：**必须基于** companion.summary + enrichment.selected_context_facts **生成中文正文**，不得原样复制英文推文内容。
  - `is_highlight: true` 的条目：3-4 段，每段 2-3 句，充分展开背景、技术细节和意义
  - 普通条目：1-2 段，至少 3 句，说清"是什么、为什么值得关注"
  - 互动数据必须口语化：不写"likes 22561"，写"引发广泛关注"或"获得大量传播"
- `related_links`：从 `enrichment.link_fetches` 中取 `fetch_status="success"` 的条目，转为 `{"text": "<来源>: <描述>", "url": "<url>"}` 格式。优先级：GitHub > arXiv > HuggingFace > 官方 docs/blog > 其他。每条最多 3 个链接。若 link_fetches 为空则设为 `[]`。
- `media`：从 `enrichment.media_files` 中取，格式为字符串路径数组。若无则设为 `[]`。
- `link`：直接复制 companion.primary_url。
- `index`：直接复制 companion.index。

**MUST NOT：**
- **不得**将 companion.title 原样复制到 post.json.title
- **不得**写英文 body（代码片段除外）
- **不得**在 body 中写"该内容获得 XX 点赞，XX 收藏"之类的生硬数字指标
- **不得**捏造或猜测 related_links URL，只能使用 enrichment.link_fetches 中已有的链接

**写出 post.json 前必须自检（逐条过）：**
1. title 是否为中文，且不是 companion.title 的原样复制？
2. body 是否为中文正文，且不包含重复的段落或句子？
3. body 是否基于 companion.summary 或 enrichment.selected_context_facts，而非原始英文推文？
4. 如有疑问，重新生成该条目，直到三项均满足。

#### 示例转换（companion + enrichment → post.json item）

**companion item 输入：**
```json
{
  "index": 4,
  "title": "🚨 We can download models, but not see how they were built.",
  "category": "开发生态",
  "is_highlight": true,
  "summary": "Stanford/MIT paper shows harnesses can create 6x performance gap for fixed LLMs. The harness—not the model—is the real source of benchmark variance.",
  "primary_url": "https://x.com/QinYi88814/status/2038971910835560921",
  "strong_links": ["https://huggingface.co/papers/2603.27164"],
  "metrics": {"likes": 251, "bookmarks": 135}
}
```

**enrichment item 输入（link_fetches 片段）：**
```json
{
  "link_fetches": [
    {
      "url": "https://huggingface.co/papers/2603.27164",
      "type": "webfetch",
      "fetch_status": "success",
      "data": {"title": "Model Harnesses Can Create a 6x LLM Performance Gap"}
    }
  ],
  "media_files": []
}
```

**post.json item 输出：**
```json
{
  "index": 4,
  "title": "Stanford/MIT：模型 harness 的选择可造成 6 倍性能差距",
  "link": "https://x.com/QinYi88814/status/2038971910835560921",
  "body": "Stanford 和 MIT 联合研究揭示了一个关键盲区：同一个 LLM，搭配不同的评测框架（harness），benchmark 得分差距可达 6 倍。这意味着当前的模型排行榜，实际上更多反映的是 harness 工程能力，而非模型本身的推理上限。\n\n研究进一步指出，如果 harness 本身可以被自动化优化，AI 评测将进入全新范式。对模型开发者而言，在关注刷榜分数之前，更值得先审视评测工具本身的合理性。harness 设计正在成为 AI 工程的核心竞争力之一。",
  "media": [],
  "related_links": [
    {"text": "HuggingFace: Model Harnesses Can Create a 6x LLM Performance Gap", "url": "https://huggingface.co/papers/2603.27164"}
  ]
}
```

#### frontmatter 字段

post.json 的顶层 frontmatter 字段从 companion.json 中派生：
- `title`：`companion.title`（companion 的整体标题，不是 item title）
- `description`：`companion.description`
- `pubDate`：`$REPORT_DATE`
- `tags`：`["AI", "资讯", "日报"]`
- `slug`：`"ai-news-$REPORT_DATE"`
- `categories`：按 companion.categories 分组，items 为该分类下的完整 post.json item 对象

### Step 3: validate_output.py（确定性校验，**在 render_md 之前运行**）

```bash
python3 {SKILL_DIR}/scripts/validate_output.py \
  --post-json "$POST_JSON_PATH" \
  --companion "$COMPANION_PATH" \
  --enrichment "$ENRICHMENT_PATH"
```

校验项：
- frontmatter 字段完整性
- category 分组正确
- item 数与 companion.json 一致
- item title 不是空值、占位符或 companion 原题直拷
- 无 markdown 残留
- highlight 条目 enrichment 覆盖率检查

**如果退出码 != 0：MUST 修复 post.json 中的错误后重新运行本步骤，不得跳过直接继续 render_md。**

成功信号：`POST_VALIDATION_OK`

### Step 4: render_md.py（脚本化，**仅在 Step 3 通过后运行**）

```bash
python3 {SKILL_DIR}/scripts/render_md.py \
  --input "$POST_JSON_PATH" \
  --output "$POST_MD_PATH"
```

## post.json Schema

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
          "title": "H2 标题",
          "link": "https://x.com/...",
          "body": "正文内容...",
          "media": ["media/2026-04-01/xxx.jpg"],
          "related_links": [
            { "text": "GitHub", "url": "https://github.com/..." }
          ]
        }
      ]
    }
  ]
}
```

## 脚本目录

```
{SKILL_DIR}/scripts/
├── enrich.py           # CLI: --companion, --output, --media-dir
├── render_md.py        # CLI: --input, --output
└── validate_output.py  # CLI: --post-json, --companion, --enrichment
```

## 依赖工具

| 工具 | 用途 |
|------|------|
| `twitter` CLI | X tweet 详情获取 |
| `gh` CLI | GitHub 元数据 |
