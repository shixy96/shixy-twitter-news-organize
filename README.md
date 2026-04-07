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
├── eval/                          # Eval harness
│   ├── fixtures/                  # 历史测试数据 (fixtures/{date}/filtered.json, post.json)
│   ├── eval_lib.py                # 评估函数库
│   ├── live_runner.py             # 实时 digest 评估
│   └── cli.py                     # eval CLI
├── improve/                       # Auto-improve hill-climbing
│   ├── loop.py                    # 主循环
│   ├── judge.py                   # LLM-as-judge 评分
│   ├── proposer.py                # 规则变更提议
│   └── experiments.jsonl          # 实验记录
├── tests/                         # 单元测试
│   └── unit/                     # tests/unit/
└── docs/                          # 设计文档
    ├── 1-pipeline-redesign.md
    ├── 2-pipeline-simplify.md
    ├── 3-eval-refactor.md
    ├── 4-auto-improve.md
    └── ...
```

## 快速开始

### 环境要求

- Python 3.10+
- `twitter` CLI — X API 抓取
- `gh` CLI — GitHub 元数据（可选，失败降级）
- `edge-tts` — TTS 音频生成

### 运行特定 Phase

阅读各 skill 的 `SKILL.md`，按步骤执行。

## Eval CLI

```bash
python3 eval/cli.py live-digest --date 2026-04-06 --runs 8 --filtered /path/to/filtered.json
```

## Auto-improve CLI

```bash
python3 improve/cli.py auto-improve --max-iters 10
python3 improve/cli.py auto-improve --dates 2026-04-06 --max-iters 5 --runs-per-iter 3
```

评分：structural score (0-30) + LLM-as-judge editorial score (0-70) = composite 0-100。Pareto 改进则接受，否则丢弃。

## 单元测试

```bash
python3 -m unittest discover tests/ -v
```

## 开发规范

- **Python only** — 所有脚本 Python 3，stdlib only
- **Max 200 lines/script** — 强制单一职责
- **Subprocess** — 外部工具（twitter/gh/edge-tts）通过 subprocess 调用
- **Conventional Commits** — `feat:`, `fix:`, `docs:`, `refactor:`

## 运行时状态

共享运行时协议是 `RUN_ROOT/daily/{date}/`。

- skill 共享输入只有 `RUN_ROOT` 和 `REPORT_DATE`
- 常见本地约定 `RUN_ROOT=state.local`（已 gitignore）
