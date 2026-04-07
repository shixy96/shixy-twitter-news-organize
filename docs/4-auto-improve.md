# Auto-Improve: 借鉴 autoresearch 的 hill-climbing 优化 editorial-rules

## Context

当前 eval-digest 只做结构性验证（JSON 合法、中文标题、分类正确、条目数 8-12），**没有内容质量评分，也没有反馈闭环**。autoresearch 用简单的 hill-climbing（propose → run → measure → keep/discard）自动优化 `train.py`，我们要把同样的思路用于优化 `editorial-rules.md`。

**核心类比**：

| autoresearch | auto-improve |
|---|---|
| `train.py`（被优化的程序） | `editorial-rules.md`（被优化的 prompt） |
| `val_bpb`（单一标量指标） | composite score 0-100（structural 30 + LLM judge 70） |
| `prepare.py`（固定 eval） | `judge.py` + `eval_lib.py`（固定评分） |
| `program.md`（meta 指令） | `meta.md`（指导 improver agent） |
| `results.tsv` | `experiments.jsonl` |

## 方案设计

### 1. 质量指标（0-100 composite score）

**Layer 1 — 结构分 (0-30)**：复用 `eval_lib.evaluate_digest()` 的结果
- PASS = 30, WARN = 20, FAIL = 0

**Layer 2 — 编辑质量分 (0-70)**：LLM-as-judge，7 个维度各 0-10 分
- `selection_relevance`：选题是否覆盖重要新闻
- `selection_dedup`：同一事件是否正确合并
- `title_quality`：中文标题简洁准确
- `body_quality`：中文正文质量与深度
- `link_quality`：链接使用规范
- `editorial_judgment`：排除/纳入判断合理性
- `overall_coherence`：分类分布、highlight、整体协调

**可靠性策略**：
- 每次实验 **每个 fixture 跑 3 次** digest，取 **中位数** composite score
- Judge 用 **opus**，digest 跑 sonnet
- Judge rubric 固定不变，不被优化器修改
- **多 fixture 交叉验证**：修改必须在所有 fixture 上都不退步才 accept（防 overfitting）

### 2. 优化目标

只修改 `skills/x-news-digest/reference/editorial-rules.md`。不动 SKILL.md（避免破坏 JSON 格式）。

### 3. Hill-climbing 循环

```
fixtures = [2026-04-06, ...]  # 所有可用 fixture dates
baseline: 对每个 fixture 跑 3 次 → 取中位数 → best_scores = {date: score}

loop (max N 次):
  1. PROPOSE: claude -p + meta.md → 输出完整新 editorial-rules.md
     (输入: 当前 rules + 历史实验结果 + judge 反馈)
  2. APPLY: 写入磁盘
  3. EVALUATE: 对每个 fixture 跑 3 次 digest + 3 次 judge → 中位数
     new_scores = {date: median_score}
  4. COMPARE (多 fixture 交叉验证):
     所有 fixture 的 new_score >= best_score 且至少一个 strictly better
       → ACCEPT: git commit, 更新 best_scores, 记录 accepted
     任一 fixture 退步
       → REJECT: git checkout 回退, 记录 rejected
  5. LOG: 追加到 experiments.jsonl
```

**多 fixture 判定逻辑**：改动必须 Pareto-improve（没有任何 fixture 退步，至少一个进步）。这防止针对单日数据 overfitting。

### 4. 安全护栏

- 任何 run 返回 FAIL → 自动 discard（结构性底线）
- editorial-rules.md 超过原始大小 2x → 指示 proposer 精简
- Git 记录每次 accepted change，可随时回滚

### 5. 文件结构

```
improve/
├── cli.py              # CLI 入口 (~120 行)
├── loop.py             # Hill-climbing 循环 (~180 行)
├── judge.py            # LLM-as-judge 评分 (~100 行)
├── proposer.py         # 提议 rules 修改 (~80 行)
├── meta.md             # 给 improver agent 的 meta 指令
├── judge_rubric.md     # 固定评分 rubric（不被修改）
└── experiments.jsonl   # 实验日志（gitignored）

.claude/commands/auto-improve.md  # slash command
```

### 6. 复用现有代码

| 现有代码 | 复用方式 |
|---|---|
| `eval/live_runner.py::run_single()` | 直接调用跑 digest |
| `eval/eval_lib.py::evaluate_digest()` | 结构性验证 |
| `eval/eval_lib.py::load_json, write_json, ensure_dir` | 工具函数 |
| `eval/fixtures/2026-04-06/filtered.json` | 固定输入 |

注意：`run_single()` 从磁盘读 `EDITORIAL_RULES`（line 105），所以直接改文件即可生效。

### 7. 实现顺序

1. `improve/judge_rubric.md` — 写固定评分 rubric
2. `improve/judge.py` — 实现 judge（调 `claude -p`）
3. `improve/meta.md` — 写 meta 指令
4. `improve/proposer.py` — 实现提议器
5. `improve/loop.py` — 实现 hill-climbing 循环
6. `improve/cli.py` — CLI 入口
7. `.claude/commands/auto-improve.md` — slash command

### 8. CLI 接口

```bash
# 完整运行（所有 fixture, 10 轮, 每 fixture 3 次 run）
python3 improve/cli.py auto-improve --max-iters 10

# 指定 fixture dates
python3 improve/cli.py auto-improve --dates 2026-04-06 --max-iters 5

# 调整 runs-per-iter
python3 improve/cli.py auto-improve --max-iters 5 --runs-per-iter 2

# 默认: --judge-model opus --digest-model sonnet
```

自动发现 `eval/fixtures/*/filtered.json` 作为可用 fixture。

### 9. 验证方式

```bash
# smoke test: 1 个 fixture, 2 轮, 每轮 2 次
python3 improve/cli.py auto-improve --dates 2026-04-06 --max-iters 2 --runs-per-iter 2

# 检查: experiments.jsonl 有记录, git log 有 accepted commits
```

## 关键文件

- `eval/live_runner.py` — 复用 `run_single()`、`build_prompt()`
- `eval/eval_lib.py` — 复用 `evaluate_digest()` 及工具函数
- `skills/x-news-digest/reference/editorial-rules.md` — 优化目标（262 行）
- `eval/fixtures/2026-04-06/filtered.json` — 固定测试输入
