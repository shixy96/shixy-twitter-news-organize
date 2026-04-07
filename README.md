# shixy-twitter-news-organize

3 个可分发 pipeline skill，生产每日 AI 新闻日报。

## Pipeline 概览

| Skill | Phase | 输出 |
|-------|-------|------|
| `skills/x-news-fetch` | 1 | `filtered.json` — engagement 预过滤候选 |
| `skills/x-news-digest` | 2 | `post.json` + `post.md` — 选题、补充信息、写作 |
| `skills/x-news-tts` | 3 | `audio.mp3` — TTS 朗读 |

## 项目结构

```
shixy-twitter-news-organize/
├── skills/
│   ├── x-news-fetch/
│   │   └── scripts/
│   │       ├── fetch.py           # X List 抓取
│   │       └── filter.py          # engagement 预过滤
│   ├── x-news-digest/
│   │   ├── scripts/
│   │   │   └── render_md.py       # JSON → Markdown
│   │   └── reference/
│   │       ├── editorial-rules.md # 编辑规则
│   │       └── example-output.md  # 输出示例
│   └── x-news-tts/
│       └── scripts/
│           └── tts.py             # edge-tts 音频生成
├── src/x_news_shared/             # 跨 skill 共享模块
│   ├── schema.py                  # JSON Schema + 校验
│   └── normalize.py               # URL 规范化
├── eval/                          # Eval harness
│   ├── cases/                     # eval case 定义
│   ├── fixtures/                  # 历史测试数据
│   └── cli.py                     # eval CLI
└── docs/
    └── pipeline-redesign.md       # 设计文档
```

## 快速开始

### 环境要求

- Python 3.10+
- `twitter` CLI — X API 抓取
- `gh` CLI — GitHub 元数据（可选，失败降级）
- `edge-tts` — TTS 音频生成

### 运行全量 Pipeline

```bash
/run-pipeline
```

### 运行特定 Phase

阅读各 skill 的 `SKILL.md`，按步骤执行。

## Eval CLI

```bash
python3 eval/cli.py <command>

eval diagnose --date 2026-04-01     # 诊断质量问题
eval run --date 2026-04-01 --runs 8 # 8 次迭代
eval benchmark --date 2026-04-01    # 多 run 聚合
eval cases list                     # 列出所有 case
```

## 共享模块

`src/x_news_shared/` 提供跨 skill 复用：

```python
from x_news_shared import normalize_domain, ALLOWED_CATEGORIES, validate_json_schema
```

| 模块 | 用途 |
|------|------|
| `schema.py` | FILTERED_SCHEMA, POST_SCHEMA, ALLOWED_CATEGORIES, validate_json_schema() |
| `normalize.py` | URL 规范化 |

## 开发规范

- **Python only** — 所有脚本 Python 3，stdlib only
- **Max 200 lines/script** — 强制单一职责
- **Subprocess** — 外部工具（twitter/gh/edge-tts）通过 subprocess 调用
- **Conventional Commits** — `feat:`, `fix:`, `docs:`, `refactor:`

## 运行时状态

共享运行时协议是 `RUN_ROOT/daily/{date}/`。

- skill 共享输入只有 `RUN_ROOT` 和 `REPORT_DATE`
- 常见本地约定 `RUN_ROOT=state.local`（已 gitignore）
