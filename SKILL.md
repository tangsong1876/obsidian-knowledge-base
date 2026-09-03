---
name: obsidian-knowledge-base
description: 当用户要把文档/网页/链接（PPTX、PDF、DOCX、HTML、飞书、豆包等）转写为带 frontmatter、双链与 MOC 索引的 Obsidian 结构化笔记并沉淀为个人知识库，或要基于本地 Markdown 笔记搭一个离线可问的"第二大脑"本地问答（RAG）时使用。This skill should be used when the user wants to (1) 把各类资料转写成可导航、可溯源的 Obsidian 笔记；(2) 搭本地知识库问答脚本（jieba BM25 + sentence-transformers 语义向量双引擎），让 AI"问库里的任何事"。
agent_created: true
---

# Obsidian 知识库联动 + 本地语义问答（第二大脑）

把零散资料沉淀为可生长的个人知识库，并让库本身可被语义问答。覆盖两条可独立使用的链路：
1. **资料 → 笔记**：任何来源的资料转写为结构化 Obsidian 笔记，落入带 MOC 导航的 vault。
2. **笔记 → 问答**：基于 `20-笔记/*.md` 搭离线 RAG 问答，bm25 与语义向量双引擎。

## 何时使用
- 用户发来一份文档/链接/网页，说"输出知识库文档""转成笔记""存进 Obsidian"。
- 用户说"我的知识库怎么用""搭个问答/第二大脑""问库里的任何事"。
- 用户想整理、归类、补全已有的 Obsidian 笔记库。

## 链路一：资料 → 结构化笔记
按 `references/pipeline.md` 执行，要点如下：
- 先确认目标 vault 结构与命名（单轨为主；双轨仅在用户要求时存 `30-素材/` 原文）。
- 按来源选解析方式：飞书 `file/wiki`、豆包需本地副本；`slides/minutes/docx` 可直抓但有懒加载截断，多次抓取并标注待补充；本地 PPTX/DOCX 用 Python `zipfile`+`ElementTree` 取 `<a:t>` 文本，PDF 用 `pypdf`，HTML 用 `bs4`+`lxml` 定位正文容器后转 Markdown（不搬运远程图）。
- frontmatter 用 `type/title/created/updated/tags/status/confidence/moc/source`，`moc` 写 YAML 列表（不要 `[[ ]]`）。
- 每篇笔记去对应 MOC 加 `[[双链]]`；单点概念拆 `概念-xxx.md` 并在 MOC「核心概念」区加链。
- 落库后跑 `[[双链]]` 校验，确保 MOC↔笔记↔概念无悬空；并据实更新 `使用说明.md`。

## 链路二：笔记 → 本地问答（第二大脑）
用 `scripts/ask_kb.py`（已验证可用），按 `references/qa_setup.md` 操作：
- 默认 `bm25` 引擎离线即用；`--engine embedding` 启用语义向量（需预下载中文模型）；`--engine auto` 自动选。
- **中文模型 `BAAI/bge-small-zh` 的获取**：HF 镜像不代理 LFS 权重（404）、官方源超时 → 用 **ModelScope** 国内 CDN 下载到 `models/bge-small-zh`（见 `references/qa_setup.md` 命令）。脚本优先用该本地目录，离线可用。
- **三必避坑**：① 不要全局设 `HF_ENDPOINT`（会让本地模型加载时去镜像拉空 `config.json` 报错）；② `build_embedding_index` 传解析后的本地路径而非 HF id；③ Windows venv 解释器路径是 `Scripts\python.exe`。
- 可选 LLM：设 `KB_LLM_API_KEY`（OpenAI 兼容）后用检索片段生成答案，不设则只返回最相关原文片段。

## 交付物
- 笔记：落入用户 vault 的 `20-笔记/`，并在 `10-MOC/` 建/补索引。
- 问答：给出可直接运行的 `ask_kb.py` 用法，必要时帮用户下载 embedding 模型。
- 始终把"来源可溯、不编造、无损"作为红线；无法远程抓取的资料，明确请用户提供本地副本。
