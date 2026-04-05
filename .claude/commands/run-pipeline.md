---
description: Run the full x-news 5-phase pipeline end-to-end for a given date
argument-hint: '[date YYYY-MM-DD]'
---

你是一个 AI 新闻筛选助手。你的目标是给 AI 内容创作者提供高信噪比、低重复、不漏重要事件的每日选题参考。

## 0. 最小输入

不要先去搜索“有没有现成的 eval 命令 / 包装脚本 / 一键入口”。本任务没有额外的权威入口；直接按本 prompt 和各阶段 `SKILL.md` 执行。

开始前只需要在 shell 中显式设置两个变量。

将目标日期写入 `REPORT_DATE`；如果没有指定日期，使用 Asia/Shanghai 的今天。

```bash
ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
RUN_ROOT="${ROOT_DIR}/state.local"
REPORT_DATE="${REPORT_DATE:-$(TZ=Asia/Shanghai date '+%Y-%m-%d')}"
DAILY_DIR="$RUN_ROOT/daily/$REPORT_DATE"
RUN_ID="${RUN_ID:-run-${REPORT_DATE}-$(TZ=UTC date '+%H%M%SZ')}"
RUN_LOG_PATH="$DAILY_DIR/run.log.jsonl"
mkdir -p "$DAILY_DIR"
export RUN_ROOT REPORT_DATE RUN_ID RUN_LOG_PATH
```

所有 skill 共享同一默认产物目录：`$RUN_ROOT/daily/$REPORT_DATE/`。具体文件名、脚本调用方式、参数传递规则都由对应 `SKILL.md` 负责定义，调用方不需要再额外声明内部路径变量。

## 步骤（每步前必须阅读对应 SKILL.md）

### 步骤 1：数据获取与过滤

读取 `skills/x-news-data-pipeline/SKILL.md` 并严格执行。

输入参数：
- `RUN_ROOT=$RUN_ROOT`
- `REPORT_DATE=$REPORT_DATE`

### 步骤 2：编辑分析与报告生成

读取 `skills/x-news-editorial/SKILL.md` 并严格执行。

输入参数：
- `RUN_ROOT=$RUN_ROOT`
- `REPORT_DATE=$REPORT_DATE`

### 步骤 3：生成日报

读取 `skills/x-news-to-daily-post/SKILL.md` 并严格执行。

输入参数：
- `RUN_ROOT=$RUN_ROOT`
- `REPORT_DATE=$REPORT_DATE`

### 步骤 4：TTS 朗读

读取 `skills/x-news-tts/SKILL.md` 并严格执行。

输入参数：
- `RUN_ROOT=$RUN_ROOT`
- `REPORT_DATE=$REPORT_DATE`

### 步骤 5：旁路式 QA

读取 `skills/x-news-quality-audit/SKILL.md` 并严格执行。

输入参数：
- `RUN_ROOT=$RUN_ROOT`
- `REPORT_DATE=$REPORT_DATE`

## 规则

- **QA 为旁路式，不阻止发布，即使失败也继续**
- **统一日志：所有脚本状态都写入 `$RUN_LOG_PATH`。脚本会自动追加 JSON Lines；如果 Agent 步骤或人工 shell 操作失败，也必须向同一文件追加兼容事件，避免流程黑盒**
- 兼容事件最少包含：`event`、`status`、`message`、`meta`

## 回复格式

- 先输出 `$RUN_ROOT/daily/$REPORT_DATE/post.md` 的完整 markdown 内容
- 最后一行单独追加：`MEDIA:` 后接 `$RUN_ROOT/daily/$REPORT_DATE/tts/audio.mp3` 的绝对路径
- MEDIA 行必须是最后一行
- QA 报告只落盘到 `$RUN_ROOT/daily/$REPORT_DATE/qa-report.md`，不附在回复中
- 不附加额外解释、总结、前言或结语
- 不回复 NO_REPLY
