# x-news-skills

5 个可分发 pipeline skill，生产每日 AI 新闻日报。

## Pipeline 概览

| Skill | Phase | 输出 |
|-------|-------|------|
| `skills/x-news-data-pipeline` | 1 | `filtered.json` — engagement 预过滤候选 |
| `skills/x-news-editorial` | 2 | `companion.json` — 编辑选题、去重 |
| `skills/x-news-to-daily-post` | 3 | `post.md` — 渲染日报 |
| `skills/x-news-tts` | 4 | `audio.mp3` — TTS 朗读 |
| `skills/x-news-quality-audit` | 5 | `qa-report.md` — 旁路式 QA |

## 项目结构

```
x-news-skills/
├── skills/                      # 5 个可分发 skill
│   ├── x-news-data-pipeline/
│   │   └── scripts/
│   │       ├── filter.py        # engagement 预过滤
│   │       └── raw_validate.py  # raw.json 校验
│   ├── x-news-editorial/
│   │   └── scripts/
│   │       ├── dedup.py              # 去重分析
│   │       └── validate_companion.py  # companion.json 校验
│   ├── x-news-to-daily-post/
│   │   └── scripts/
│   │       ├── enrich.py          # 信息补充
│   │       ├── render_md.py       # JSON → Markdown
│   │       └── validate_output.py # 输出校验
│   ├── x-news-tts/
│   │   └── scripts/
│   │       └── tts.py             # edge-tts 音频生成
│   └── x-news-quality-audit/
│       └── scripts/
│           ├── stage_json_validate.py
│           ├── stage_contract.py
│           └── editorial_review.py
├── src/x_news_shared/            # 跨 skill 共享模块
│   ├── schema.py               # JSON Schema 定义
│   ├── normalize.py            # URL 规范化
│   └── validate.py              # 通用校验
├── eval/                        # Eval harness
│   ├── cases/                  # eval case 定义
│   ├── fixtures/               # 历史测试数据
│   └── cli.py                  # eval CLI
└── docs/
    └── pipeline-redesign.md    # 重构设计文档
```

## 快速开始

### 环境要求

- Python 3.10+
- `twitter` CLI — X API 抓取
- `gh` CLI — GitHub 元数据
- `edge-tts` — TTS 音频生成

### 安装依赖

```bash
pip install -e .
```

### 运行全量 Pipeline

```bash
/run-pipeline
```

### 运行特定 Phase

阅读各 skill 的 `SKILL.md`，按步骤执行脚本。

## Eval CLI

```bash
python3 eval/cli.py <command>

# 诊断
eval diagnose --date 2026-04-01     # 诊断质量问题
eval compare <run-a> <run-b>        # 对比两次运行

# 重跑
eval run --date 2026-04-01 --with-fixtures   # fixture 模式
eval run --date 2026-04-01 --runs 8          # 8 次迭代

# 统计分析
eval benchmark --date 2026-04-01   # 多 run 聚合
eval history                       # 历史通过率

# Case 管理
eval cases list                    # 列出所有 case
```

## 共享模块

`src/x_news_shared/` 提供跨 skill 复用：

```python
from x_news_shared import append_run_log, normalize, schema, validate
```

| 模块 | 用途 |
|------|------|
| `schema.py` | RAW_SCHEMA, FILTERED_SCHEMA, COMPANION_SCHEMA, POST_SCHEMA |
| `normalize.py` | URL 规范化 |
| `runlog.py` | 统一 `run.log.jsonl` 运行状态日志 |
| `validate.py` | `validate_json_schema()` 通用校验 |

## 开发规范

- **Python only** — 所有脚本 Python 3，stdlib only
- **Max 200 lines/script** — 强制单一职责
- **Stdlib only** — 禁止引入 requests/pyyaml 等第三方库
- **Subprocess** — 外部工具（twitter/gh/edge-tts）通过 subprocess 调用
- **Conventional Commits** — `feat:`, `fix:`, `docs:`, `refactor:`
- **分支命名** — `feat/`, `fix/`, `docs/` 前缀

## 运行时状态

共享运行时协议是 `RUN_ROOT/daily/{date}/`。

- skill 共享输入只有 `RUN_ROOT` 和 `REPORT_DATE`
- `RUN_LOG_PATH` 默认是 `RUN_ROOT/daily/{date}/run.log.jsonl`
- `RUN_ID` 可选；设置后会写进统一日志，便于追踪一次完整运行

常见本地约定可以是 `RUN_ROOT=state.local`，该目录已加入 `.gitignore`，但这只是本地选择，不是 skill 协议的一部分。

## 相关文档

- `@docs/pipeline-redesign.md` — 重构设计文档
- `@eval/README.md` — Eval 基础设施详解
- 各 skill 的 `SKILL.md` — 接口规范
