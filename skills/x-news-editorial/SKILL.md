---
name: x-news-editorial
description: "基于共享日报目录中的 filtered.json 做去重与选题，生成 companion.json。"
---

# x-news-editorial

基于 `x-news-data-pipeline` 的过滤结果，完成编辑分析、报告生成和 companion JSON 输出。

**前置依赖**：必须先完成 `x-news-data-pipeline`，拿到过滤后的 JSON。

## 输入参数

基础调用只需要两个输入：

| 参数 | 说明 | 示例 |
|------|------|------|
| `RUN_ROOT` | 运行时产物根目录 | `/path/to/runtime-root` |
| `REPORT_DATE` | 报告日期 | `2026-04-03` |

## 共享路径约定

```bash
DAILY_DIR="$RUN_ROOT/daily/$REPORT_DATE"
FILTERED_PATH="$DAILY_DIR/filtered.json"
OUTPUT_PATH="$DAILY_DIR/companion.json"
DEDUP_RESULT_PATH="$DAILY_DIR/dedup_result.json"
RUN_LOG_PATH="$DAILY_DIR/run.log.jsonl"
RUN_ID="${RUN_ID:-manual-${REPORT_DATE}-$(TZ=UTC date '+%H%M%SZ')}"
REPORT_BOUNDARY="${REPORT_DATE}T06:00:00+08:00"
REPORT_TIME="$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M')"
export RUN_ROOT REPORT_DATE RUN_ID RUN_LOG_PATH
PRIOR_COMPANIONS=()
for offset in 1 2; do
  prior_date="$(python3 - <<'PY' "$REPORT_DATE" "$offset"
from datetime import datetime, timedelta
import sys
report_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
offset = int(sys.argv[2])
print((report_date - timedelta(days=offset)).isoformat())
PY
)"
  prior_path="$RUN_ROOT/daily/${prior_date}/companion.json"
  if [ -f "$prior_path" ]; then
    PRIOR_COMPANIONS+=("$prior_path")
  fi
done
```

说明：
- 默认从最近 2 天的 `companion.json` 读取历史；只传入实际存在的文件
- 若没有任何历史 companion，传空数组即可；`dedup.py` 必须能在零历史输入下继续运行
- `RUN_LOG_PATH` 是统一运行日志；脚本会记录去重、校验和失败状态
- 常见本地约定可以是 `RUN_ROOT="state.local"`，也可以是仓库外任意目录；这只是本地选择，不是共享协议的一部分
- 除非调用方显式要求覆盖，否则默认按以上路径读写

## 工作流程

### Step 1: 读取过滤结果

解析 `filtered.json`（strong / medium / backfill）；立即统计各 bucket 条数，作为 companion `stats` 的唯一来源。

### Step 2: 读取编辑规则

通读 `references/editorial-rules.md`

### Step 3: 去重分析

```bash
DEDUP_CMD=(python3 {SKILL_DIR}/scripts/dedup.py --filtered "$FILTERED_PATH")
if ((${#PRIOR_COMPANIONS[@]} > 0)); then
  DEDUP_CMD+=(--prior-companions "${PRIOR_COMPANIONS[@]}")
fi
"${DEDUP_CMD[@]}" > "$DEDUP_RESULT_PATH"
```

输出 `$DEDUP_RESULT_PATH`：
```json
{
  "auto_resolved": [...],
  "history_prior_match": [...],
  "require_decision": [...],
  "by_author": {...}
}
```

### Step 4: Agent 决策

**第一步：内容相关性筛查（在处理任何 dedup 结果之前，逐条执行）**

**MUST NOT 纳入以下内容，无论互动数据多高：**
- 纯政治 / 社会新闻：与 AI、ML、开发者生态无直接关联的政治事件、社会议题（高 likes 不改变此规则）
- 泛娱乐 / 生活方式 / 名人动态：无实质技术价值的内容
- 纯自我宣传：招聘公告、活动预告、播客推广（全新能力/API/工具发布不受此限制）
- 与 AI / 开发者生态弱相关：纯 CLI 运维技巧、系统维护、SSH 配置等，除非有明确的 AI 工具链影响

**判断快捷方式**：去掉"AI / ML / 开发者生态"这一上下文后，内容若仍然成立，通常不符合选题标准。

**反例验证（强制）**：筛查结束后，必须逐条列出被排除的 item 及其排除理由，格式如下（内部思考，不写入 companion.json）：

```
排除: [index] <title片段> — 原因: <排除规则名称>
例: 排除: [12] "Trump: We can't take care..." — 原因: 纯政治/社会新闻，与 AI 无关
```

若某条 item 不确定是否应排除，默认排除（宁可少选，不可混入无关内容）。

详细规则见 `references/editorial-rules.md`。

---

**第二步：处理 dedup 结果，决定最终入选**

- 对 `history_prior_match` 逐个判断（有 `new_content_delta` 时决定是否标记为跟进）
- 对 `require_decision` 逐个判断（选哪条、是否跟进等）
- 决定最终入选 items（目标 8-12 条）
- 直接生成 `companion.json`

**硬约束**：
- `companion.json.items[]` 必须是 editorial 精选后的最终结果，不能把 `filtered.json` 的全部候选原样带下游
- 当日候选数 `>= 8` 时，必须精选到 8-12 条
- 当日候选数 `< 8` 时，可以少于 8 条，但不能超过候选总数
- `stats.selected` 必须等于精选后条数，不能等于 `stats.total` 除非当日候选总数本身 `<= 12`
- daily-post 不负责二次筛选，所以 editorial 阶段必须完成取舍

### Step 5: 校验 companion.json

```bash
python3 {SKILL_DIR}/scripts/validate_companion.py \
  --companion "$OUTPUT_PATH" \
  --filtered "$FILTERED_PATH"
```

成功信号：`REPORT_VALIDATION_OK`

## Companion JSON Schema

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

## 允许分类

| 分类 | 说明 |
|------|------|
| 模型发布 | 新模型推出、版本更新 |
| 开发生态 | 工具、框架、库更新 |
| 技术洞察 | 深度分析、技术原理 |
| 产品动态 | 产品发布、功能更新 |
| 安全事件 | 安全漏洞、数据泄露 |
| 行业观点 | 行业趋势、观点评论 |

## 脚本目录

```
{SKILL_DIR}/scripts/
├── dedup.py              # CLI: --filtered, --prior-companions
└── validate_companion.py  # CLI: --companion, --filtered
```

## 输出

校验通过的 `$RUN_ROOT/daily/$REPORT_DATE/companion.json`

成功信号：`validate_companion.py` 退出码 0
