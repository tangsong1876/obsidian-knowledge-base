# obsidian-knowledge-base

WorkBuddy 技能（skill）：把零散资料沉淀为可生长的个人知识库，并让库本身可被语义问答。

覆盖两条可独立使用的链路：

1. **资料 → 笔记**：把各类来源（PPTX / PDF / DOCX / HTML / 飞书 / 豆包 / 网页）转写为带 `frontmatter`、双链与 MOC 索引的 Obsidian 结构化笔记，落入带导航的 vault。
2. **笔记 → 问答**：基于本地 `20-笔记/*.md` 搭离线 RAG 问答，`bm25` 与语义向量双引擎，让 AI「问库里的任何事」。

> 本仓库即技能本体。克隆后将其内容复制到 `~/.workbuddy/skills/obsidian-knowledge-base/`（Windows 为 `C:\Users\<你>\.workbuddy\skills\obsidian-knowledge-base\`）即可在 WorkBuddy 中使用。

---

## 目录结构

```
obsidian-knowledge-base/
├── SKILL.md              # 技能说明（WorkBuddy 读取）
├── references/
│   ├── pipeline.md       # 链路一：文档→结构化笔记规范
│   └── qa_setup.md       # 链路二：本地问答搭建与避坑
├── scripts/
│   └── ask_kb.py         # 本地双引擎问答脚本
└── README.md
```

---

## 链路一：资料 → 结构化笔记

按 `references/pipeline.md` 执行，要点：

- 先确认目标 vault 结构与命名（单轨为主；双轨仅在用户要求时把原文存 `30-素材/`）。
- 按来源选解析方式：飞书 `file/wiki`、豆包需本地副本；本地 PPTX/DOCX 用 Python `zipfile`+`ElementTree` 取 `<a:t>` 文本，PDF 用 `pypdf`，HTML 用 `bs4`+`lxml` 定位正文容器后转 Markdown（不搬运远程图）。
- frontmatter 字段：`type/title/created/updated/tags/status/confidence/moc/source`；`moc` 写 YAML 列表（不要 `[[ ]]`）。
- 每篇笔记去对应 MOC 加 `[[双链]]`；单点概念拆 `概念-xxx.md` 并在 MOC「核心概念」区加链。
- 落库后跑 `[[双链]]` 校验，确保 MOC↔笔记↔概念无悬空；并据实更新 `使用说明.md`。

红线：**来源可溯、不编造、无损**。无法远程抓取的资料，明确请用户提供本地副本。

---

## 链路二：笔记 → 本地问答（第二大脑）

`scripts/ask_kb.py` 已实现，零外部服务即可离线检索。

### 基本用法

```bash
# 默认 bm25 引擎（纯离线，jieba + TF-IDF + 余弦）
python ask_kb.py "RAG 的瓶颈在哪"
python ask_kb.py "问题" --topk 5
python ask_kb.py                      # 进入交互多轮问答（exit 退出）

# 语义向量引擎（更懂同义/近义问法）
python ask_kb.py "问题" --engine embedding
python ask_kb.py "问题" --engine auto   # 有模型用 embedding，否则降级 bm25
```

`--engine` 取值：`bm25`（默认）| `embedding` | `auto`。

### 依赖

- 必装：`jieba`、`numpy`
- 可选：`sentence-transformers`（用 `embedding` 引擎时）

### 中文 embedding 模型获取（关键坑）

`HF_ENDPOINT=https://hf-mirror.com` 拉不全 `BAAI/bge-small-zh`：镜像不代理 LFS 大权重，`model.safetensors` / `sentencepiece.bpe.model` 均返回 404；HF 官方源在本环境又超时。→ **改走 ModelScope 国内 CDN**：

```bash
pip install modelscope
python -c "from modelscope import snapshot_download; \
snapshot_download('BAAI/bge-small-zh', local_dir='models/bge-small-zh')"
```

ModelScope 版是 `pytorch_model.bin`（非 safetensors），sentence-transformers 可正常 load（512 维）。脚本优先用同目录 `models/bge-small-zh`，存在即离线可用。

### 必避的三个坑

1. **不要全局设 `HF_ENDPOINT`**：会导致 sentence-transformers 加载**本地**模型时也去镜像拉 `config.json`（空响应 → `JSONDecodeError`）。直接用本地路径加载即可，无需任何镜像变量。
2. **`build_embedding_index` 必须传解析后的本地路径**，而非 HF id 字符串——否则仍去 hub 拉取而失败。
3. **Windows 下 venv 解释器路径是 `Scripts\python.exe`**（不是 `bin/python`）；缺包用该解释器 `python -m pip install`。

### 可选 LLM 生成

设置以下环境变量（OpenAI 兼容）后，检索片段会额外用于生成式回答；不设则只返回最相关原文片段：

```bash
export KB_LLM_API_KEY="sk-..."
export KB_LLM_BASE_URL="https://api.openai.com/v1"   # 或任意兼容地址
export KB_LLM_MODEL="gpt-4o-mini"                    # 默认 gpt-4o-mini
```

其他可用环境变量：`KB_ENGINE`(默认 bm25)、`KB_EMBED_MODEL`(默认 BAAI/bge-small-zh)、`KB_DIR`(笔记目录)。

> 注：`ask_kb.py` 的 `DEFAULT_KB_DIR` 指向作者本地 vault，克隆后请通过 `KB_DIR` 环境变量或 `--dir` 参数指定你自己的笔记目录。

---

## License

MIT —— 自由使用、修改与再分发。
