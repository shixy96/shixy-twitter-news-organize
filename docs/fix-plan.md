# Pipeline Fix Plan

> 基于 2026-04-03 Haiku subagent 试跑的问题分析，详见 `docs/issues-2026-04-03.md`。

---

## P0 修复

### P0-A: x-news-to-daily-post Step 2 从幽灵步骤变成真实步骤

**问题**：`SKILL.md` 的 Step 2 "Agent 组装"只有 13 行描述性文字，没有可执行 prompt、无示例、无成功标准。Haiku 面对歧义直接跳过，导致 title 英文直拷、body 机械拼接、related_links/media 全空。

**修复**：
- 在 SKILL.md Step 2 中：明确标注"Agent 任务，非脚本"；补充 MUST/MUST NOT 硬约束；提供真实的 companion → post.json item 转换示例
- 调整步骤顺序：validate_output.py 移到 Step 3（render_md 之前），validate 失败时必须修复后重新验证，不得跳过

**文件**：`skills/x-news-to-daily-post/SKILL.md`

---

### P0-B: x-news-editorial Step 4 内联内容相关性排除规则

**问题**：`editorial-rules.md` 有完整的排除规则（纯政治/社会话题 MUST NOT 入选），但 SKILL.md 只有一行"通读 editorial-rules.md"。Haiku 未能执行排除规则，导致 Trump 政治推文（31k 点赞）混入产出。

**修复**：
- 在 SKILL.md Step 4 顶部内联关键排除规则，用 MUST NOT 标记，不依赖外部文档引用

**文件**：`skills/x-news-editorial/SKILL.md`

---

## P1 修复

### P1-A: validate_output.py 与流程显式绑定

**问题**：validate_output.py 存在但从未被 subagent 调用；且当前 SKILL.md 把 validate 放在 render_md 之后（Step 4），验证一个已渲染的产物意义减半。

**修复**：
- 将 validate_output.py 提升到 Step 3（render_md 之前）
- 明确：退出码 != 0 时 post.json 无效，Agent MUST 修复错误并重新运行 Step 2，不得直接继续 render_md

**文件**：`skills/x-news-to-daily-post/SKILL.md`（与 P0-A 同文件）

---

### P1-B: fetch 重试上限 + enrich 幂等保护

**问题一**：raw.json 截断 → raw_validate 失败 → subagent 重复 fetch 5 次。SKILL.md 说"重跑 Step 1"但未规定次数上限。

**修复**：Step 1.5 明确：重跑仅限一次，若仍失败则停止并报告，不再继续。

**文件**：`skills/x-news-data-pipeline/SKILL.md`

**问题二**：enrich.py 中断后重跑时从第 1 条重新处理，浪费时间并导致竞态。

**修复**：enrich.py 启动时检查 `enrichment.json` 是否已存在且 item 数量与 companion 一致，若是则跳过（幂等保护）。

**文件**：`skills/x-news-to-daily-post/scripts/enrich.py`

---

## 不在本次修复范围内（P2/P3）

- run_id 中途丢失（A3）：需要 orchestration 层传参改进，影响较小
- companion schema 错误 strong_links/external_links 类型（C2）：schema.py 与 LLM 产出不一致，需单独处理
- editorial_review body 长度警告（C3）：QA 旁路，不阻断发布
- edge_tts Python 模块缺失（D1）：环境文档问题


## 修复情况
共修改 4 个文件：

  skills/x-news-to-daily-post/SKILL.md（P0-A + P1-A）

  - Step 2 从 13 行模糊描述变成可执行的 Agent prompt：明确"Agent 任务，非脚本"；MUST/MUST NOT 硬约束；带真实数据的 companion → post.json item 转换示例
  - 步骤顺序调整：validate_output.py 提升到 Step 3（render_md 之前），失败时 MUST 修复后重新验证
  - render_md 降为 Step 4，明确只在验证通过后运行

  skills/x-news-editorial/SKILL.md（P0-B）

  - Step 4 顶部新增"内容相关性筛查"小节，MUST NOT 规则内联（不依赖外部文档引用）：纯政治/社会话题、泛娱乐、纯自我宣传无论互动多高一律排除
  - 附"判断快捷方式"：去掉 AI 上下文后内容仍成立 → 通常不符合选题标准

  skills/x-news-data-pipeline/SKILL.md（P1-B）

  - Step 1.5 明确：重跑仅限一次，仍失败则停止不再继续

  skills/x-news-to-daily-post/scripts/enrich.py（P1-B）

  - enrich_companion() 启动时检查 enrichment.json 是否已存在且 item 数量吻合，若是则跳过（记录 step_skipped），防止中断后重跑时重复处理