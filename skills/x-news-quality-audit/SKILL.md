---
name: x-news-quality-audit
description: "对共享日报目录中的全链路产物做旁路式 QA，输出 qa-report.md。"
---

# x-news-quality-audit

旁路式 QA，校验全链路 artifact，不阻断发布。

## 输入参数

基础调用只需要两个输入：

| 参数 | 说明 |
|------|------|
| `RUN_ROOT` | 运行时产物根目录 |
| `REPORT_DATE` | 报告日期 |

## 共享路径约定

```bash
DAILY_DIR="$RUN_ROOT/daily/$REPORT_DATE"
RAW_PATH="$DAILY_DIR/raw.json"
FILTERED_PATH="$DAILY_DIR/filtered.json"
COMPANION_JSON_PATH="$DAILY_DIR/companion.json"
ENRICHMENT_PATH="$DAILY_DIR/enrichment.json"
POST_JSON_PATH="$DAILY_DIR/post.json"
POST_MD_PATH="$DAILY_DIR/post.md"
TTS_TEXT="$DAILY_DIR/tts/script.txt"
TTS_MP3="$DAILY_DIR/tts/audio.mp3"
HTML_PATH="$DAILY_DIR/post.html"
QA_REPORT_PATH="$DAILY_DIR/qa-report.md"
RUN_LOG_PATH="$DAILY_DIR/run.log.jsonl"
RUN_ID="${RUN_ID:-manual-${REPORT_DATE}-$(TZ=UTC date '+%H%M%SZ')}"
export RUN_ROOT REPORT_DATE RUN_ID RUN_LOG_PATH
```

说明：
- 默认读取同一天目录下的全链路产物
- `HTML_PATH` 可选，不存在时按缺省处理
- 默认把 QA 结果写回同一天目录的 `qa-report.md`
- `RUN_LOG_PATH` 是统一运行日志；脚本会记录各 QA 阶段开始、完成、告警和失败
- 常见本地约定可以是 `RUN_ROOT="state.local"`，也可以是仓库外任意目录；这只是本地选择，不是共享协议的一部分

## 工作流程

### Step 1: stage_json_validate.py（脚本化）

```bash
python3 {SKILL_DIR}/scripts/stage_json_validate.py \
  --raw "$RAW_PATH" \
  --filtered "$FILTERED_PATH" \
  --companion "$COMPANION_JSON_PATH" \
  --post "$POST_JSON_PATH"
```

- 针对每个 JSON 做 schema 校验
- stats 一致性

### Step 2: stage_contract.py（脚本化）

```bash
python3 {SKILL_DIR}/scripts/stage_contract.py \
  --filtered "$FILTERED_PATH" \
  --companion "$COMPANION_JSON_PATH" \
  --post "$POST_JSON_PATH"
```

- companion.json items ↔ filtered.json candidates 映射校验
- post.json items ↔ companion.json items 映射校验
- 无信息丢失

### Step 3: editorial_review.py（脚本化）

```bash
python3 {SKILL_DIR}/scripts/editorial_review.py --post "$POST_JSON_PATH"
```

- 针对 post.json 做编辑审查
- 可读性、事实稳健性，完成度、编排感

### Step 4: generate_qa_report.py

```bash
python3 {SKILL_DIR}/scripts/generate_qa_report.py \
  --raw "$RAW_PATH" \
  --filtered "$FILTERED_PATH" \
  --companion "$COMPANION_JSON_PATH" \
  --post "$POST_JSON_PATH" \
  --output "$QA_REPORT_PATH" \
  --report-date "$REPORT_DATE"
```

- 汇总 stage_json_validate / stage_contract / editorial_review 的结果
- 输出 `qa-report.md`

## 编辑审查维度

| 维度 | 检查项 |
|------|--------|
| 可读性 | 标题格式、首段长度(>=45字)、段落密度(无>=220字段落) |
| 事实稳健性 | 断言词 vs 不确定词一致性 |
| 成稿完成度 | 无 placeholder、无缺失图片、链接完整 |
| 日报编排感 | 分类均衡、无 theme clustering |

## 定位

旁路式，不阻断。即使 QA 失败，也不阻止发布流程。

## 成功信号

- `stage_json_validate.py` 正常退出
- `stage_contract.py` 正常退出
- `editorial_review.py` 正常退出
- `generate_qa_report.py` 写出 `$RUN_ROOT/daily/$REPORT_DATE/qa-report.md`
