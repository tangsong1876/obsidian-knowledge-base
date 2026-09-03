# 本地知识库问答（第二大脑）搭建与坑

基于 `20-笔记/*.md` 搭一个离线可问的 RAG 问答脚本，对应 `概念-RAG检索增强生成` 的流水线：加载 → 剥离 frontmatter → 按 `##/###` 分块 → 检索 → 可选 LLM 生成。`scripts/ask_kb.py` 已实现，含双引擎。

## 1. 双检索引擎
| 引擎 | 原理 | 联网 | 适用 |
|---|---|---|---|
| `bm25`（默认） | jieba 中文分词 + TF-IDF + 余弦 | 完全离线 | 术语明确的问法，最快 |
| `embedding` | sentence-transformers + `BAAI/bge-small-zh` 语义向量 | 模型需预下载 | 口语化/近义问法更准 |
| `auto` | 有本地模型用 embedding，否则降级 bm25 | — | 省心默认 |

用法：
```bash
python ask_kb.py "问题"                  # bm25（默认）
python ask_kb.py "问题" --engine embedding
python ask_kb.py "问题" --engine auto
python ask_kb.py                         # 交互多轮
```
- 可选 LLM 生成：设 `KB_LLM_API_KEY`（+ `KB_LLM_BASE_URL`/`KB_LLM_MODEL`，OpenAI 兼容）后，用检索片段生成答案；不设则只返回最相关原文片段。
- 索引实时构建、不写缓存、不污染 vault。

## 2. 中文 embedding 模型获取（关键坑）
**`HF_ENDPOINT=https://hf-mirror.com` 拉不全 bge 模型**：镜像不代理 LFS 大权重，`model.safetensors` / `sentencepiece.bpe.model` 均返回 **404**；HF 官方源在本环境又超时。→ **改走 ModelScope 国内 CDN**：
```bash
pip install modelscope
python -c "from modelscope import snapshot_download; \
snapshot_download('BAAI/bge-small-zh', local_dir='models/bge-small-zh')"
```
- ModelScope 版是 `pytorch_model.bin`（非 safetensors），sentence-transformers 可正常 load（512 维）。
- `ask_kb.py` 优先用脚本同目录 `models/bge-small-zh`，存在即离线可用；`--model` 可改本地路径或 HF id。

## 3. 必避的三个坑
1. **不要全局设 `HF_ENDPOINT`**：会导致 sentence-transformers 加载**本地**模型时也去镜像拉 `config.json`（空响应 → `JSONDecodeError`）。直接用本地路径加载即可，无需任何镜像变量。
2. **`build_embedding_index` 必须传解析后的本地路径**，而非 HF id 字符串（如 `args.model`）——否则仍去 hub 拉取而失败。
3. **Windows 下 venv 解释器路径是 `Scripts\python.exe`**（不是 `bin/python`）；缺包用该解释器 `python -m pip install`。

## 4. 分块与召回质量
- 按 `##/###` 分块；H1 作为整篇标题，**不单独成块**（否则块正文混入 H1 行）。
- 「目录 / 相关链接 / 参考资料」等索引型块靠重复标题词霸榜 → 检索时对其降权（如 ×0.35）后再重排。
- 列表项之间不要插空行，否则 Obsidian/Markdown 列表渲染断裂。
