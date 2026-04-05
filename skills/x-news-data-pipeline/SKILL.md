---
name: x-news-data-pipeline
description: "在共享日报目录中抓取 X List 推文，生成 raw.json、fetch-errors.jsonl 和 filtered.json。"
---

# x-news-data-pipeline

抓取 X List 原始推文 → 校验 JSON → 运行预过滤，输出分层结果供下游编辑分析使用。

## 输入参数

基础调用只需要两个输入：

| 参数 | 说明 | 示例 |
|------|------|------|
| `RUN_ROOT` | 运行时产物根目录 | `/path/to/runtime-root` |
| `REPORT_DATE` | 报告日期 | `2026-04-03` |

可选覆盖：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `BACKFILL_HOURS` | 抓取窗口小时数 | `48` |
| `FRESH_HOURS` | fresh 窗口大小 | `24` |
| `BACKFILL_WINDOW` | backfill 窗口大小 | `48` |

## 共享路径约定

所有 skill 默认共享同一产物目录，调用方不需要逐个传具体文件路径：

```bash
DAILY_DIR="$RUN_ROOT/daily/$REPORT_DATE"
SOURCE_CONFIG="$RUN_ROOT/x-list-sources.json"
RAW_PATH="$DAILY_DIR/raw.json"
FETCH_LOG_PATH="$DAILY_DIR/fetch-errors.jsonl"
FILTERED_PATH="$DAILY_DIR/filtered.json"
RUN_LOG_PATH="$DAILY_DIR/run.log.jsonl"
RUN_ID="${RUN_ID:-manual-${REPORT_DATE}-$(TZ=UTC date '+%H%M%SZ')}"
REPORT_BOUNDARY="${REPORT_DATE}T06:00:00+08:00"
mkdir -p "$DAILY_DIR"
export RUN_ROOT REPORT_DATE RUN_ID RUN_LOG_PATH
```

说明：
- `SOURCE_CONFIG` 是 `x_list_fetch.py` 的必填参数，文件不存在时应直接失败，不要猜测其他路径
- `RUN_LOG_PATH` 是统一运行日志；脚本会在开始、写文件、关键进度和失败时追加 JSONL 事件
- 常见本地约定可以是 `RUN_ROOT="state.local"`，也可以是仓库外任意目录；这只是本地选择，不是共享协议的一部分
- 除非调用方显式要求覆盖，否则默认按以上路径读写

## SOURCE_CONFIG Schema（可选）

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
- `signal_thresholds` 可选。若不提供，使用硬编码默认值（Strong: likes>=200 OR bookmarks>=80 OR ir>=1.5% 需要满足2个条件；Medium: likes>=50 AND bookmarks>=20 满足1个条件）
- `defaults` 供 x_list_fetch.py 使用

## 工作流程

### Step 1: 抓取原始数据

```bash
python3 {SKILL_DIR}/scripts/x_list_fetch.py \
  --config "$SOURCE_CONFIG" \
  --hours "$BACKFILL_HOURS" \
  --until "$REPORT_BOUNDARY" \
  --fetch-log "$FETCH_LOG_PATH" \
  --output "$RAW_PATH"
```

- **推荐**使用 `--output` 直接写入文件；脚本也支持 stdout（供调试用）
- 若省略 `--output`，则依赖调用方自行重定向 stdout
- raw 文件必须保持为合法 JSON 数组
- `--fetch-log` 可选；若提供，会把 list fetch / tweet detail 的失败记录为 JSONL，便于复查

### Step 1.5: 校验 raw JSON

```bash
python3 {SKILL_DIR}/scripts/raw_validate.py --input "$RAW_PATH"
```

- 如果校验失败：删除坏文件，严格重跑 Step 1 **一次**
- 若重跑后仍然失败：记录错误，停止当前 pipeline，不再继续（不要无限重试）
- 成功输出：`RAW_JSON_OK`

### Step 2: 运行预过滤

```bash
python3 {SKILL_DIR}/scripts/filter.py \
  "$RAW_PATH" \
  --config "$SOURCE_CONFIG" \
  --now "$REPORT_BOUNDARY" \
  --fresh-hours "$FRESH_HOURS" \
  --backfill-hours "$BACKFILL_WINDOW" \
  --output "$FILTERED_PATH"
```

- **推荐**使用 `--output` 直接写入文件；脚本也支持 stdout（供调试用），但正常流程应使用 `--output`
- filtered 文件必须保持为合法 JSON
- `--config` 可选；若提供，从 `signal_thresholds` 读取阈值；否则使用硬编码默认值

输出 JSON 包含：

| 字段 | 说明 |
|------|------|
| `stats` | 统计摘要 |
| `strong` | 0–fresh 窗口 strong 信号 items |
| `medium` | 0–fresh 窗口 medium 信号 items |
| `backfill` | 延迟发酵候选（新鲜度窗口外） |

每条 item 可能包含辅助字段：`_window`, `_source_proxy`, `_canonical_id/_canonical_url/_canonical_author/_canonical_text`, `_aggregate_likes/_bookmarks/_score/_group_size`, `_strong_links`, `_external_links`, `_related_urls`, `_canonical_id` 等。

### 错误恢复

- 如果 Step 1 或 Step 2 失败：删除坏产物，严格按原命令重跑
- 不要把"临时修补后继续"当作正常流程

## 输出

过滤结果 JSON 默认保存到 `$RUN_ROOT/daily/$REPORT_DATE/filtered.json`，包含 `stats`, `strong`, `medium`, `backfill`。

成功信号：`RAW_JSON_OK`（Step 1.5） + 过滤无异常退出。

## 脚本目录

```
{SKILL_DIR}/scripts/
├── x_list_fetch.py       # X List 抓取脚本（CLI: --config, --hours, --until）
├── raw_validate.py       # raw.json 校验脚本（CLI: --input）
└── filter.py             # 预过滤脚本（CLI: <input.json> --config, --now, --fresh-hours, --backfill-hours）
```

## 依赖工具

| 工具 | 用途 |
|------|------|
| `twitter` CLI | X API 抓取 |
