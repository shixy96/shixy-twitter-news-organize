---
name: x-news-fetch
description: "抓取 X List 推文，按 engagement 信号分层过滤，输出 filtered.json。"
---

# x-news-fetch

抓取 X List 原始推文 → 过滤分层，输出供下游编辑使用的 filtered.json。

## 输入参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `RUN_ROOT` | 运行时产物根目录 | `/path/to/runtime-root` |
| `REPORT_DATE` | 报告日期 | `2026-04-05` |

可选覆盖：`FRESH_HOURS`(默认 24)、`BACKFILL_HOURS`(默认 48)。

## 路径约定

```bash
DAILY_DIR="$RUN_ROOT/daily/$REPORT_DATE"
SOURCE_CONFIG="$RUN_ROOT/x-list-sources.json"
RAW_PATH="$DAILY_DIR/raw.json"
FILTERED_PATH="$DAILY_DIR/filtered.json"
REPORT_BOUNDARY="${REPORT_DATE}T06:00:00+08:00"
mkdir -p "$DAILY_DIR"
```

## 工作流程

### Step 1: 抓取

```bash
python3 {SKILL_DIR}/scripts/fetch.py \
  --config "$SOURCE_CONFIG" \
  --hours "${BACKFILL_HOURS:-48}" \
  --until "$REPORT_BOUNDARY" \
  --output "$RAW_PATH"
```

成功输出 `RAW_JSON_OK`。若失败，删除坏文件重跑一次。

### Step 2: 过滤

```bash
python3 {SKILL_DIR}/scripts/filter.py \
  "$RAW_PATH" \
  --config "$SOURCE_CONFIG" \
  --now "$REPORT_BOUNDARY" \
  --fresh-hours "${FRESH_HOURS:-24}" \
  --backfill-hours "${BACKFILL_HOURS:-48}" \
  --output "$FILTERED_PATH"
```

## 输出

`filtered.json`：`{stats, strong[], medium[], backfill[]}`

每条 item 附带：`_canonical_id/_url/_author/_text`、`_signal/_score/_window`、`_aggregate_*`、`_strong_links`、`_external_links`、`_related_urls`。

## 脚本

```
{SKILL_DIR}/scripts/
├── fetch.py    # --config, --hours, --until, --output
└── filter.py   # <input> --config, --now, --fresh-hours, --backfill-hours, --output
```

## 依赖

| 工具 | 用途 |
|------|------|
| `twitter` CLI | X API 抓取 |
