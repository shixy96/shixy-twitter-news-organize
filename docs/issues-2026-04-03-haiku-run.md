# Haiku 试跑问题分析 2026-04-03

> 基于 `state.local/daily/2026-04-03/run.log.jsonl` 和 subagent 观察报告。

---

## 问题一：media 文件双写（项目根目录 + 正确目录）

**现象**：媒体文件同时出现在：
- `state.local/daily/2026-04-03/media/`（正确）
- 项目根目录 `/Users/shixy/.openclaw/x-news-skills/`（错误）

**根因**：enrich.py 被启动了三次（run.log 时间戳：20:05:30、20:07:55、20:10:00）。

- 第一次（20:05:30）：Haiku 未正确设置 `MEDIA_DIR` shell 变量，调用 enrich.py 时 `--media-dir` 未传或传了空值，argparse `default=None` → 媒体下载到 CWD（项目根目录）
- 第二次（20:07:55）：与第一次并发运行（第一次尚未结束），第二次正确传了 `--media-dir`，最先写出 enrichment.json（20:08:45）
- 第三次（20:10:00）：幂等检查命中，跳过

**直接触发原因**：Haiku agent 对 shell 环境变量的管理混乱，多次重新执行同一步骤，且部分调用遗漏了 `--media-dir` 参数。

**加重因素**：enrich.py 的 `--media-dir default=None` 在参数未传时静默降级到 CWD，而非报错退出。

---

## 问题二：post.json title/body 全是英文机械拷贝

**现象**：`post.json` 的 item.title 形如 `"模型发布: LLM Knowledge Bases\n\nSomething I'm findi"`，body 是英文推文原文的双倍复制（同一段文字重复了两次）。

**根因**：

1. **Haiku 能力不足以可靠执行 Step 2 "Agent 组装"**：SKILL.md 的 MUST 规则（中文重写 title、基于 summary + facts 生成中文 body）在文件中存在，但 Haiku 在上下文较长时直接跳过了内容生成逻辑，退化为机械复制。

2. **body 内容重复**：enrichment.json 中 `primary_content` 字段本身就含有两份重复文本（twitter CLI 输出包含 tweet + quoted tweet，被拼接为两份相同文本），enrich.py 未去重，Haiku 也未识别和清理。

3. **validate_output.py 校验时机**：根据 fix-plan.md，validate_output.py 已提升到 render_md 之前（Step 3）。但 Haiku 执行时跳过了 validate 步骤，直接进入 render_md。

**结论**：这是 Haiku 指令遵从能力的上限问题，不是 SKILL.md 规则缺失问题（规则已内联）。

---

## 问题三：Trump 政治内容漏过 editorial 筛选

**现象**：`https://x.com/factpostnews/status/2039444784083771629`（Trump 关于医保的政治观点，31k likes）进入 companion.json，最终出现在 post.json `技术洞察` 分类。

**根因**：

editorial SKILL.md 的 Step 4 已内联 MUST NOT 规则：
```
纯政治 / 社会新闻：与 AI、ML、开发者生态无直接关联的政治事件、社会议题（高 likes 不改变此规则）
```

该规则在 Haiku 试跑时已存在于 SKILL.md 中。Haiku 仍然将该推文纳入选题，分类为"技术洞察"。

**可能原因**：
- Haiku 对长文本中的 MUST NOT 规则注意力权重不足
- 31k likes 的高互动数据对 Haiku 的选题决策产生了过强的正向影响，压过了内容相关性规则
- "技术洞察"分类名称对政治内容的排斥性不够明确

---

## 其他观察

- **raw.json 三次失败后才通过**：x_list_fetch.py 前两次产生了无效 JSON（可能是 twitter CLI 输出截断）。SKILL.md 已限制"重跑仅限一次"，但 Haiku 试了三次才放弃尝试。
- **companion 验证三次才通过**：companion.json 生成后第一、二次验证失败（title 格式不符），第三次才通过。说明 Haiku 在生成结构化 JSON 时对 schema 约束的一次性遵从率较低。
- **dedup.py 被调用但结果未被充分利用**：Haiku 在 editorial Step 4 中似乎未完整处理 dedup_result.json，直接跳到生成 companion.json。

---

## 修复建议

### 短期（SKILL.md 层面）

| 问题 | 建议 |
|------|------|
| media 双写 | enrich.py `--media-dir` 改为必填参数（required=True），传空/不传直接报错退出而非静默降级 |
| 政治内容漏过 | 在 editorial Step 4 筛查阶段添加"反例验证"：要求 agent 逐条列出排除理由，而非仅列出入选理由 |
| body 英文拷贝 | Step 2 中增加"self-check"：在写出 post.json 前，要求 agent 逐条确认 body 是否为中文且不含重复段落 |

### 中期（流程层面）

- **用 Sonnet 而非 Haiku 执行 Step 2 和 editorial Step 4**：这两步是内容质量关键路径，Haiku 的指令遵从能力不足以可靠完成
- **enrich.py 并发保护**：在 DAILY_DIR 写入 `.enrich.lock`，防止多实例并发

### 长期（架构层面）

- post.json 的"Agent 组装"步骤应考虑用明确的 Claude API 调用替代 agent 自由执行，以提升可靠性和可审计性
