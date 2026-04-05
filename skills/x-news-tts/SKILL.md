---
name: x-news-tts
description: "将 AI 资讯日报转换为 TTS 朗读脚本并生成音频。"
---

# TTS 朗读脚本生成

将 `x-news-to-daily-post` 输出的 post.md 转换为 TTS 朗读脚本和音频。

## 输入

news-to-daily-post 生成的日报 markdown 文件，或直接的日报内容。

## 输出路径

保存 TTS 脚本到与日报相同目录的 `tts/` 子目录：
```
{日报所在目录}/tts/{日期}.txt
```
例如：`~/daily/ai-news-2026-03-28.md` → `~/daily/tts/2026-03-28.txt`

## 核心约束

**输出必须为中文。** 即使 markdown 包含英文术语，脚本也应以中文为主。常见英文技术术语保持原样（如 "GPU"、"API"、"Claude Code"）。

## 输出结构

纯文本，无 markdown。分三部分：

### 1. 开场白

```
大家好，今天是2026年3月28日，欢迎收听今日 AI 资讯速递。
```

### 2. 结束语

```
以上就是今天的 AI 资讯精选。感谢收听，我们明天再见。
```

## 转换规则

1. **Strip all markdown** — 删除所有 markdown 标记（`#` 标题、`**bold**`、`> 引用`、`---` 分隔线）
2. **Strip all URLs** — 完全删除 `[链接文字](url)`
3. **Strip link reference markers** — 删除 `相关链接：`区块
4. **Skip 概览区** — 只处理各条目的展开正文，不写概览区
5. **术语转中文优先**：`fps`→`帧每秒`、`MW`→`兆瓦`、`E2E RL`→`端到端强化学习`、`MFU`→`模型浮点利用率`、`RL`→`强化学习`、`SFT`→`监督微调`
6. **数字+单位加空格**：`100K`→`100 K`、`2B`→`2 B`、`8xH100`→`8x H100`、`32+`→`32加`
7. **英文缩写/名称加空格**：LLM、API、GPU、CPU；Claude Code、GitHub Copilot；OpenClaw、Anthropic 等前后加空格
8. **One paragraph per item** — 条目之间空行，每个条目自包含一段完整内容
9. **Natural sentences** — 每条目 1-3 个完整句子，像人在说话般自然
10. **Skip media descriptions** — 忽略 `![图片](path)` 或 `<video>` 媒体引用
11. **Skip embedded quotes unless essential** — 引述内容已被正文转述时跳过；独家原话且未被转述时保留关键句

## 语言风格

- **播报节奏**：单句超过 25 字建议拆分
- **句式多样**：避免连续"XX 是 XX"判断句，穿插动作句、过渡句
- **过渡词**：条目之间使用"首先"、"此外"、"最后"等自然过渡词
- **人名处理**：首次出现可加简短身份标签，如"AI 研究者 Chollet"
- **数字播报**："36.5 万美元"而非"36.5万美元"，"10万 token"而非"100K token"
- **信息密度**：保留核心数据（模型参数量、精度提升、费用节省等）

## 生成音频

```bash
uv run --with edge-tts {SKILL_DIR}/scripts/tts.py --input {脚本路径} --output {输出mp3路径}
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | 必填 | TTS 脚本文件路径 |
| `--output` | auto | 输出 MP3 路径（默认与输入同目录同文件名） |
| `--voice` | `zh-CN-YunyangNeural` | TTS 音色 |
| `--rate` | `+0%` | 语速调整 |

## 输出

纯文本脚本 + MP3 音频文件
