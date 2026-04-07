# x-news-skills 简化重构计划

## Context

项目初衷：每天从 X 抓取 AI 领域最重要的新闻，筛选整理成中文日报。但当前实现方向偏离——7157 行代码、21 个 Python 文件、5 个 skill、5 层验证脚本，大量精力花在工具和流程约束上，而非信息整理质量本身。每次运行仍然不是过滤出问题就是整合出问题。

核心问题：**pipeline 过度工程化，Agent 跨 skill 边界丢失上下文，中间产物过多导致信息在传递中损耗。**

## 问题分析

### 1. 架构过度拆分

当前 5 个 skill 意味着 Agent 要跨 5 次 SKILL.md 边界。editorial 和 daily-post 分成两个 skill，Agent 在 editorial 做完选题后，上下文被切断，到 daily-post 又要重新理解 companion.json。这个 context 断裂是写作质量不稳定的根源。

### 2. 中间产物过多

`raw.json → filtered.json → dedup_result.json → companion.json → enrichment.json → post.json → post.md`——7 个中间文件，每个都有 schema 定义和验证脚本。信息在每次序列化/反序列化中都会损耗。

### 3. 脚本替代不了 Agent 判断

`dedup.py`（379 行）做的事情——判断两条新闻是否同一事件——Agent 看一眼就知道。`enrich.py`（627 行）用 subprocess 调 twitter/gh CLI 抓详情，但 Agent 本身就能调这些工具，而且只需要对选中的 8-12 条抓取，不需要全量抓取。

### 4. 验证脚本不解决质量问题

5 个 validate 脚本（1408 行）检查的是 schema 合规性，而非"这条新闻选得对不对""这段中文写得好不好"。真正的质量问题（选题偏差、信息遗漏、翻译生硬）这些脚本一个都抓不到。

### 5. 历史去重价值有限

只抓 24h 内容，重叠率本身就低。379 行的 dedup.py 解决的是一个低频问题。

## 简化方案：3 Skills

### 新数据流

```
x-news-fetch (脚本)     x-news-digest (Agent 核心)     x-news-tts (脚本)
==================      =======================       ===============
twitter CLI              filtered.json                 post.md / post.json
    ↓                        ↓                             ↓
fetch.py → raw.json     Agent 一次性完成:              tts.py → audio.mp3
    ↓                   1. 阅读编辑规则
filter.py →             2. 筛选 8-12 条
  filtered.json         3. 对选中条目用工具补充信息
                        4. 写中文标题和正文
                        5. 输出 post.json
                            ↓
                        render_md.py → post.md
```

产物：`raw.json` → `filtered.json` → `post.json` → `post.md` → `audio.mp3`（5 个，从 7 个减少）

去掉：`dedup_result.json`、`companion.json`、`enrichment.json`、`qa-report.md`

### Skill 1: x-news-fetch（替代 x-news-data-pipeline）

**职责**：抓取 + 过滤，纯脚本，无 Agent 参与。

| 脚本 | 来源 | 变更 |
|------|------|------|
| `fetch.py` (~200行) | 从 `x_list_fetch.py`(705行) 精简 | 去掉 run log 基础设施(~200行)、elaborate error metadata(~150行)、inline raw validation |
| `filter.py` (~200行) | 从 `filter.py`(698行) 精简 | 去掉 run log、简化 link 优先级打分、去掉 SOURCE_CONFIG 动态加载（用硬编码默认值） |

**删除**：`raw_validate.py`（吸收为 fetch.py 末尾 10 行检查）

**输出不变**：`filtered.json`，schema 与当前一致。

### Skill 2: x-news-digest（替代 editorial + daily-post + quality-audit）

**职责**：Agent 在一个连续 session 中完成选题 → 补充信息 → 写作 → 输出。

**这是最关键的改变**：把 editorial 和 daily-post 合并，Agent 不再在两个 skill 之间断开上下文。

**脚本（仅 1 个）**：
- `render_md.py`（~150行）：从当前 `render_md.py`(260行) 精简，去掉 run log

**SKILL.md 结构**：
1. 输入：`RUN_ROOT`、`REPORT_DATE`、`filtered.json` 路径
2. 编辑规则：当前 `editorial-rules.md` 的核心内容（内容判断、分类、取舍优先级、链接规则、重点标注）——保留为 reference 文件供 Agent 读取
3. 写作规则：当前 `x-news-to-daily-post/SKILL.md` 的 Agent 组装规则（中文标题重写、body 生成、metrics 口语化）
4. 工具使用指南：如何用 `twitter tweet <id> --json`、`gh repo view`、WebFetch 补充信息（简短说明，Agent 知道怎么用这些工具）
5. 输出：`post.json` schema + 调用 `render_md.py` 生成 `post.md`
6. 自检清单（替代 5 个 validate 脚本）：5-8 条核心检查项

**Agent 工作流**：
1. 读 `filtered.json`，读编辑规则
2. 从 strong/medium/backfill 中选 8-12 条（直接做，不需要 dedup.py）
3. 对选中的每条，用 `twitter tweet <id> --json` 获取详情，用 `gh repo view` 获取 GitHub 信息（仅选中的条目，不是全量）
4. 为每条写中文标题和正文，组装 `post.json`
5. 自检：item 数量、中文、title 非直拷、category 合法、无 placeholder
6. 运行 `render_md.py` 输出 `post.md`

**去掉 companion.json 中间层**：Agent 直接从 filtered → post.json。如果需要可追溯性，post.json 的每个 item 保留 `canonical_id` 和 `source_url` 字段即可。

### Skill 3: x-news-tts（不变）

保持 `tts.py`(201行) 不变。输入改为读 `post.json`（Agent 生成 TTS 脚本后调 tts.py）。

### 共享模块精简

```
src/x_news_shared/
├── __init__.py
├── normalize.py    (~50行，不变)
└── schema.py       (~100行，只保留 FILTERED_SCHEMA + POST_SCHEMA + ALLOWED_CATEGORIES + validate 函数)
```

**删除**：`runlog.py`、`validate.py`（合入 schema.py）
**删除 schema**：`RAW_SCHEMA`、`COMPANION_SCHEMA`、`DEDUP_RESULT_SCHEMA`、`ENRICHMENT_SCHEMA`

### 删除清单

| 文件/目录 | 行数 | 删除原因 |
|-----------|------|---------|
| `skills/x-news-data-pipeline/` | - | 被 `x-news-fetch` 替代 |
| `skills/x-news-editorial/` | - | 合入 `x-news-digest` |
| `skills/x-news-to-daily-post/` | - | 合入 `x-news-digest` |
| `skills/x-news-quality-audit/` (整个) | 1158 | QA 旁路式审计，不解决实际质量问题 |
| `dedup.py` | 379 | Agent 直接做，24h 窗口不需要复杂去重 |
| `enrich.py` | 627 | Agent 用工具直接获取，更精准 |
| `validate_companion.py` | 416 | companion.json 不再存在 |
| `validate_output.py` | 338 | 替换为 SKILL.md 自检清单 |
| `src/x_news_shared/runlog.py` | 104 | 过度工程 |
| `src/x_news_shared/validate.py` | 157 | 合入 schema.py |

### 新文件结构

```
skills/
  x-news-fetch/
    SKILL.md
    scripts/
      fetch.py        (~200 LOC)
      filter.py       (~200 LOC)
  x-news-digest/
    SKILL.md          (编辑规则 + 写作规则 + 自检)
    scripts/
      render_md.py    (~150 LOC)
    reference/
      editorial-rules.md  (保留，供 Agent 读取)
      example-output.md   (保留)
  x-news-tts/
    SKILL.md          (微调：输入改为 post.json)
    scripts/
      tts.py          (~200 LOC, 不变)
src/x_news_shared/
  __init__.py
  normalize.py        (~50 LOC)
  schema.py           (~100 LOC)
```

**预估代码量**：~900 行脚本 + shared（从 ~5960 行降至 ~900 行，减少 85%）

## Eval 简化

当前 eval（1557 行）主要测 schema 合规性。简化方向：

1. **保留**：fixture-based 测试框架、`cli.py` 入口、多次运行 Jaccard 稳定性
2. **简化**：去掉按阶段分别 eval（不再有 editorial/daily-post 分阶段），改为端到端 eval：给定 filtered.json → 看 post.json 质量
3. **核心指标**：
   - 选题稳定性：多次运行 canonical_id Jaccard >= 0.75
   - item 数量在 8-12 范围
   - 中文标题非直拷
   - body 长度达标（highlight >= 150字，普通 >= 80字）
   - category 合法

**目标**：eval 总量从 1557 行降至 ~500 行。

## 实施步骤

### Phase 1: 创建 x-news-fetch
1. 新建 `skills/x-news-fetch/SKILL.md`
2. 从 `x_list_fetch.py` 精简为 `fetch.py`（去 run log、简化 error handling）
3. 从 `filter.py` 精简（去 run log、去 SOURCE_CONFIG 动态加载）
4. 用现有 fixture 验证 filtered.json 输出一致

### Phase 2: 创建 x-news-digest
1. 合并 editorial + daily-post SKILL.md 为单一 SKILL.md
2. 移入 `editorial-rules.md` 和 `example-output.md` 作为 reference
3. 精简 `render_md.py`
4. 用 fixture 的 filtered.json 端到端测试

### Phase 3: 精简 shared 模块 + 清理
1. 精简 `schema.py`（只保留 FILTERED_SCHEMA + POST_SCHEMA）
2. 删除 `runlog.py`、`validate.py`
3. 删除旧 skill 目录
4. 更新 `CLAUDE.md`、`README.md`

### Phase 4: 简化 eval
1. 重写 eval 为端到端模式
2. 更新 fixture cases
3. 更新 slash commands

## 验证方式

```bash
# Phase 1 验证：filtered.json 输出一致性
python3 skills/x-news-fetch/scripts/filter.py --input eval/fixtures/2026-04-01/raw.json --output /tmp/filtered.json
diff <(python3 -m json.tool eval/fixtures/2026-04-01/filtered.json) <(python3 -m json.tool /tmp/filtered.json)

# Phase 2 验证：端到端运行
# 在 Agent 中执行 x-news-digest skill，输入 eval/fixtures/2026-04-01/filtered.json
# 对比 post.json/post.md 输出质量

# Phase 4 验证：eval 运行
python3 eval/cli.py run --date 2026-04-01
```

## 风险

| 风险 | 缓解 |
|------|------|
| Agent 直接 enrich 比脚本慢 | 只对选中的 8-12 条 enrich，比脚本全量 enrich 更快 |
| 合并后 SKILL.md 过长 | 编辑规则放 reference 文件，SKILL.md 只放工作流和写作规则 |
| 去掉 validate 脚本后质量下降 | render_md.py 输入非法时会报错；SKILL.md 自检清单替代；eval 做端到端质量检测 |
| 去掉 companion.json 丢失可追溯性 | post.json 每个 item 保留 canonical_id + source metrics |
