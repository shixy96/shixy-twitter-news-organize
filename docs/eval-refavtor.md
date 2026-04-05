# Plan: 将 eval 基础设施从 x-news-job 迁移到 x-news-skills

## Context

x-news-skills 是一个可分发的 skill 仓库，需要 eval 基础设施来评测 skill 质量。x-news-job 有完整的 eval harness（eval_lib.py ~1585 行）和 fixture 数据。需要将这些迁移过来，但要做适配因为两个项目的架构不同：
- x-news-job: 完整的 pipeline runner，有 Python 编排层
- x-news-skills: 可分发的 skill 仓库，skill 通过 SKILL.md 执行

## 待迁移内容

### 1. Fixture 数据 (eval/fixtures/)

从 x-news-job 复制实际 fixture 文件：
- `eval/fixtures/2026-04-01/{filtered.json, companion.json, post.md}`
- `eval/fixtures/2026-04-02/{filtered.json, companion.json, post.md}`

### 2. Case 定义 (eval/cases/)

从 x-news-job 复制并适配 case 定义：
- `eval/cases/suites/fixture-YYYY-MM-DD.json` → `eval/cases/suites/suite-YYYY-MM-DD.json`
- `eval/cases/x-news-editorial/fixture-YYYY-MM-DD.json` → 对应 skill 目录
- `eval/cases/x-news-data-pipeline/fixture-YYYY-MM-DD.json`
- `eval/cases/x-news-to-daily-post/fixture-YYYY-MM-DD.json`

### 3. Eval Harness 实现

x-news-job 的 eval_lib.py 紧密耦合其 pipeline 结构。x-news-skills 需要一个更轻量的 eval harness。

**方案**：参考 x-news-job 的设计模式，创建简化版 eval_lib.py：

```
eval/
├── eval_lib.py          # 核心库（从 x-news-job eval_lib.py 简化适配）
├── eval_ops.py          # 高层操作（从 x-news-job eval_ops.py 简化）
└── cli.py               # CLI 入口（实现 eval/ README.md 定义的接口）
```

**eval_lib.py 核心功能**：
- `InvocationPaths` - 管理 eval 运行目录结构
- `load_case() / load_suite()` - 加载 case 定义
- `run_evaluation()` - 运行单个 skill 的 eval
- `evaluate_run()` - 验证 artifact 产生 metrics.json + judge.json
- `build_benchmark()` - 聚合多次运行结果
- `compare_invocations()` - 对比两次运行

**eval_ops.py**：
- `analyze_stage()` - 分析单个 stage
- `diagnose_daily()` - 诊断某日期的全链路问题
- `rerun_stage()` - 重跑并验证

**CLI 入口**（实现 eval/README.md）：
```
x-news eval run --date 2026-04-01
x-news eval diagnose --date 2026-04-01
x-news eval compare <run-a> <run-b>
x-news eval history
x-news eval benchmark --date 2026-04-01
x-news eval cases list
```

## 关键文件修改

| 文件 | 操作 |
|------|------|
| `eval/fixtures/2026-04-01/filtered.json` | 复制 |
| `eval/fixtures/2026-04-01/companion.json` | 复制 |
| `eval/fixtures/2026-04-01/post.md` | 复制 |
| `eval/fixtures/2026-04-02/*` | 复制 |
| `eval/cases/suites/suite-2026-04-01.json` | 创建 |
| `eval/cases/suites/suite-2026-04-02.json` | 创建 |
| `eval/cases/x-news-data-pipeline/case-2026-04-01.json` | 创建 |
| `eval/cases/x-news-editorial/case-2026-04-01.json` | 创建 |
| `eval/cases/x-news-to-daily-post/case-2026-04-01.json` | 创建 |
| `eval/eval_lib.py` | 创建（简化自 x-news-job） |
| `eval/eval_ops.py` | 创建（简化自 x-news-job） |
| `eval/cli.py` | 创建 |
| `eval/README.md` | 更新 |

## 执行步骤

### Step 1: 迁移 Fixture 数据
从 x-news-job/eval/fixtures/ 复制历史 fixture 到 x-news-skills/eval/fixtures/

### Step 2: 创建 Case 定义
为各 skill 创建 case JSON 文件，引用 fixture 数据

### Step 3: 实现 eval_lib.py (简化版 ~400-500 行)
核心模块：
- `InvocationPaths` - 目录结构管理
- `load_case() / load_suite()` - case 加载
- `stage_fixtures()` - fixture 准备
- `run_evaluation()` - 执行评估
- `evaluate_*()` - 各阶段评估函数
- `build_benchmark()` - 聚合结果
- `compare_invocations()` - 对比运行

### Step 4: 实现 eval_ops.py
高层操作封装

### Step 5: 实现 CLI 入口
实现 eval/README.md 定义的命令

## 验证方式

1. `python3 eval/cli.py cases list` - 列出所有 case
2. `python3 eval/cli.py run --date 2026-04-01 --with-fixtures` - 用 fixture 数据运行 eval
3. 检查 `eval/runs/<date>/<timestamp>*/metrics.json` 产生正确结果
