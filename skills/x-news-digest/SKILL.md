---
name: x-news-digest
description: "从 filtered.json 筛选最重要的 AI 新闻，补充信息，生成中文日报 post.json + post.md。"
---

# x-news-digest

从 `x-news-fetch` 的过滤结果中选出当日最重要的 AI 新闻，补充完整信息，生成中文日报。

**这是 pipeline 的核心 skill**：选题质量和写作质量在这一步决定。

## 输入参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `RUN_ROOT` | 运行时产物根目录 | `/path/to/runtime-root` |
| `REPORT_DATE` | 报告日期 | `2026-04-05` |

## 路径约定

```bash
DAILY_DIR="$RUN_ROOT/daily/$REPORT_DATE"
FILTERED_PATH="$DAILY_DIR/filtered.json"
POST_JSON_PATH="$DAILY_DIR/post.json"
POST_MD_PATH="$DAILY_DIR/post.md"
MEDIA_DIR="$DAILY_DIR/media"
mkdir -p "$DAILY_DIR" "$MEDIA_DIR"
```

## 工作流程

### Step 1: 读取输入和规则

1. 读取 `$FILTERED_PATH`（strong / medium / backfill 三个 bucket）
2. 通读 `{SKILL_DIR}/reference/editorial-rules.md`——这是选题的核心规则

### Step 2: 选题（8-12 条）

从 filtered.json 的候选中选出 8-12 条最值得报道的 AI 新闻。

**选题流程**：

1. **内容相关性筛查**（先排除再选入）：
   - 排除：纯政治/社会、泛娱乐/生活方式、纯自我宣传（招聘/播客/预告）、与 AI/开发者弱相关的内容
   - 判断快捷方式：去掉"AI/ML/开发者生态"上下文后内容仍成立 → 不选
   - 不确定时默认排除

2. **同一事件合并**：
   - 以 `_canonical_id` / `_canonical_url` 判断是否同一事件
   - 同一事件只保留 1 条，优先源帖
   - 源帖 + 讨论帖 + 分析帖 = 合并为 1 条

3. **优先级排序**（从高到低）：
   - 首发论文/基准 > 官方 release > 开源 release/GitHub > 工程实证 > 高信息密度 thread > 纯观点
   - likes > 5000 为强信号
   - 纯观点类最多 2 条，且必须来自关键人物或附原始资料链接

4. **分类**（6 个固定分类）：
   - 模型发布、开发生态、技术洞察、产品动态、安全事件、行业观点
   - 冲突优先级：安全事件 > 模型发布 > 开发生态 > 技术洞察 > 产品动态

5. **重点标注** `is_highlight`（满足任一）：
   - likes > 5000 或 bookmarks > 3000
   - 突破性技术/benchmark
   - 关键人物重要内容
   - 每天 1-5 条

详细规则见 `{SKILL_DIR}/reference/editorial-rules.md`。

**硬约束**：
- 候选数 >= 8 时，必须精选到 8-12 条
- 候选数 < 8 时，可少于 8 条
- 每类 2-5 条，宁缺毋滥

### Step 3: 信息补充（仅对选中条目）

对每条选中的 item，用工具补充信息：

1. **X 推文详情**：`twitter tweet <tweet_id> --json` 获取完整推文内容
   - 仅在 item 的 summary 不够充分时使用
   - 失败时用 filtered.json 中已有的 text/summary

2. **GitHub 信息**：对 `_strong_links` 中的 GitHub URL，运行 `gh repo view <owner/repo> --json description,stargazersCount`
   - 失败时跳过，不影响整体流程

3. **网页内容**：对重要的外部链接（论文、官方博客），用 WebFetch 获取摘要
   - 仅对 is_highlight 条目的关键链接使用
   - 失败时跳过

4. **媒体下载**（仅 is_highlight 条目）：
   a. 来源：filtered.json 中该 item 的 `media` 字段包含图片/视频 URL 列表
   b. 下载：对每个 URL 执行 `curl -sL -o "$MEDIA_DIR/{tweet_id}_{index}.{ext}" "{url}"`
      - `{tweet_id}` = item 的 id 字段
      - `{index}` = 该 item 内媒体序号（0, 1, 2...）
      - `{ext}` = 从 URL 推断（jpg/png/mp4），默认 jpg
   c. 填入 post.json：将下载后的**相对路径** `media/{tweet_id}_{index}.{ext}` 写入该 item 的 `media` 数组
   d. 失败则跳过该媒体，`media` 保持 `[]`

**原则**：工具调用是补充手段，不是必需步骤。任何工具失败都不应阻断流程，用已有信息继续。

### Step 4: 写作——生成 post.json

为每条选中内容编写中文标题和正文，输出 `$POST_JSON_PATH`。

#### post.json 结构

```json
{
  "title": "{当日核心要点}【AI 资讯日报 {REPORT_DATE}】",
  "description": "每日 AI 领域精选资讯：{实际使用的分类列表}",
  "pubDate": "{REPORT_DATE}",
  "tags": ["AI", "资讯", "日报"],
  "slug": "ai-news-{REPORT_DATE}",
  "categories": [
    {
      "name": "开发生态",
      "items": [
        {
          "index": 1,
          "canonical_id": "原始 _canonical_id",
          "title": "中文标题（30 字以内）",
          "link": "https://x.com/.../status/...",
          "body": "中文正文...",
          "media": ["media/xxx.jpg"],
          "related_links": [
            {"text": "GitHub: repo-name", "url": "https://github.com/..."}
          ]
        }
      ]
    }
  ]
}
```

#### 每条 item 写作规则

**title**：
- 必须中文，30 字以内，突出核心价值点
- 不得与原始推文标题相同

**body**：
- 必须中文正文，基于推文内容 + 补充信息生成
- `is_highlight` 条目：3-4 段，充分展开背景、技术细节和意义
- 普通条目：1-2 段，说清"是什么、为什么值得关注"
- 互动数据口语化：不写"likes 22561"，写"引发广泛关注"
- 不得原样复制英文推文内容

**related_links**：
- 从 `_strong_links` + 补充信息中的有效链接取
- 优先级：GitHub > arXiv > HuggingFace > 官方 docs > 其他
- 每条最多 3 个链接
- 只能使用实际存在的 URL，不得捏造

**link**：item 的 X 主链接，直接用 `_canonical_url` 或 item 的 `url`

**media**：is_highlight 条目从 Step 3 下载的图片相对路径数组（如 `media/12345_0.jpg`）；非 highlight 或下载失败则 `[]`

#### frontmatter

- `title`：从当日最重要的内容动态生成，格式 `{核心要点}【AI 资讯日报 {DATE}】`
- `description`：`"每日 AI 领域精选资讯：{实际使用的分类列表}"`，如 `"每日 AI 领域精选资讯：开发生态、技术洞察"`
- `pubDate`：`REPORT_DATE`
- `tags`：`["AI", "资讯", "日报"]`
- `slug`：`"ai-news-{REPORT_DATE}"`

### Step 5: 自检

写出 post.json 前逐条检查：

1. ✅ item 总数在 8-12 范围（候选充足时）
2. ✅ 每条 title 是中文，且不是原始推文标题的直拷
3. ✅ 每条 body 是中文正文，不含重复段落
4. ✅ category 来自允许列表（模型发布、开发生态、技术洞察、产品动态、安全事件、行业观点）
5. ✅ 无 placeholder 文本（TODO、TBD、xxx、待补充）
6. ✅ related_links 中的 URL 不是捏造的
7. ✅ canonical_id 字段已填写（用于可追溯性）

不通过则修复后重新写出。

### Step 6: 渲染 Markdown

```bash
python3 {SKILL_DIR}/scripts/render_md.py --input "$POST_JSON_PATH" --output "$POST_MD_PATH"
```

## 示例转换

**filtered.json 中的候选**：
```json
{
  "_canonical_id": "2038894956459290963",
  "_canonical_url": "https://x.com/user/status/2038894956459290963",
  "text": "Stanford/MIT paper shows harnesses can create 6x performance gap...",
  "_strong_links": [{"url": "https://huggingface.co/papers/2603.27164", ...}],
  "_aggregate_likes": 251, "_aggregate_bookmarks": 135
}
```

**post.json 中的 item**：
```json
{
  "index": 4,
  "canonical_id": "2038894956459290963",
  "title": "Stanford/MIT：模型 harness 的选择可造成 6 倍性能差距",
  "link": "https://x.com/user/status/2038894956459290963",
  "body": "Stanford 和 MIT 联合研究揭示了一个关键盲区：同一个 LLM，搭配不同的评测框架（harness），benchmark 得分差距可达 6 倍。...",
  "media": [],
  "related_links": [
    {"text": "HuggingFace: Model Harnesses Performance Gap", "url": "https://huggingface.co/papers/2603.27164"}
  ]
}
```

## 脚本

```
{SKILL_DIR}/scripts/
└── render_md.py   # --input post.json --output post.md
```

## 依赖工具

| 工具 | 用途 | 必须 |
|------|------|------|
| `twitter` CLI | 推文详情补充 | 否（失败降级） |
| `gh` CLI | GitHub 元数据 | 否（失败跳过） |
