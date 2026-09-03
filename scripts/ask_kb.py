#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地知识库问答脚本（零外部服务，可选 LLM 增强）
================================================
基于 D:\\Obsidian\\AI学习\\20-笔记 下的 Markdown 笔记做中文检索问答。

实现：两种检索引擎，可切换 / 自动降级 ——
  • bm25     ：jieba 中文分词 + TF-IDF 向量 + 余弦相似度（纯 numpy，不依赖向量数据库，离线即用）
  • embedding：sentence-transformers + 中文模型（默认 BAAI/bge-small-zh），做语义向量检索，更懂同义/近义
     引擎由 --engine {bm25,embedding,auto} 选择；auto = 装了模型就用 embedding，否则自动降级 bm25。
     默认只做「检索」，把最相关的笔记片段返回给你自己读；
     配置了 OpenAI 兼容 API 后，可额外做「生成式回答」。

依赖：
  • 必装：jieba, numpy（隔离 venv 已具备）
  • 可选：sentence-transformers（用 embedding 引擎时需要；中文模型 BAAI/bge-small-zh 已预下载到脚本同目录 models/，离线即用）

用法：
  python ask_kb.py "你的问题"                  # 单次检索问答（默认 bm25）
  python ask_kb.py                             # 进入交互问答（连续问，输入 exit 退出）
  python ask_kb.py "问题" --topk 5             # 返回前 5 个片段
  python ask_kb.py "问题" --no-llm             # 强制只检索、不调用大模型
  python ask_kb.py "问题" --engine embedding   # 用语义向量检索（更准的近义匹配）
  python ask_kb.py "问题" --engine auto        # 有模型用 embedding，否则降级 bm25

可选环境变量：
  KB_LLM_API_KEY     OpenAI 兼容 API key（启用生成式回答）
  KB_LLM_BASE_URL    API base，如 https://api.openai.com/v1 或任意兼容地址
  KB_LLM_MODEL       模型名，默认 gpt-4o-mini
  KB_ENGINE          {bm25,embedding,auto}，默认 bm25
  KB_EMBED_MODEL     中文 embedding 模型名，默认 BAAI/bge-small-zh
  KB_DIR             笔记目录，默认 D:\\Obsidian\\AI学习\\20-笔记
  （embedding 模型已预下载到脚本同目录 models/bge-small-zh，离线即可用，无需任何镜像变量）
"""
import os
import re
import sys
import json
import argparse
import math
import urllib.request
from pathlib import Path

import numpy as np
import jieba

jieba.setLogLevel(20)  # 关闭 jieba 的构建日志

# ------------------------------------------------------------------ 配置
DEFAULT_KB_DIR = r"D:\Obsidian\AI学习\20-笔记"
SKIP_FILES = {"README.md", "index.md", "INDEX.md"}
SCRIPT_DIR = Path(__file__).resolve().parent
# embedding 模型默认放脚本同目录 models/ 下；存在则优先用本地、无需联网
DEFAULT_EMBED_MODEL_LOCAL = SCRIPT_DIR / "models" / "bge-small-zh"
DEFAULT_EMBED_MODEL_ID = "BAAI/bge-small-zh"

# 中文常见停用词（助词 / 介词 / 连词 / 代词等），减少噪声
STOPWORDS = set("""
的 了 在 是 我 你 他 她 它 们 这 那 有 和 与 或 等 也 就 都 而 及 一个 一种 可以 如何 什么 怎么
为什么 因为 所以 如果 对于 关于 通过 基于 进行 以及 我们 它们 其 该 此 这个 那个 这些 那些 但 但是
并 且 则 则 被 把 让 使 对 从 到 给 向 于 之 中 上 下 内 外 后 前 时 时候 来 去 着 过 又 还 很 更 最
已 已经 没 没有 不 不是 不要 不能 会 能 要 得 地 个 些 第 一种 这样 那样 自己 您 咱 咱们 某 各 每
例如 比如 如 即 即 包括 含 包括 其中 其它 其他 另外 此外 总之 因此 因而 从而 然后 接着 首先 其次
最后 一共 一起 一律 一概 一味 一般 一旦 一向 一点 一定 一方面 一方面 一部分 一度 一律 一些
""".split())

# ------------------------------------------------------------------ 笔记加载
def parse_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    fm, body = {}, text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"').strip("'")
        body = text[m.end():]
    return fm, body


def load_notes(kb_dir):
    notes = []
    for p in sorted(Path(kb_dir).glob("*.md")):
        if p.name in SKIP_FILES:
            continue
        text = p.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        notes.append({"file": p.stem, "path": str(p), "fm": fm, "body": body})
    return notes


def split_chunks(note):
    """按 ## / ### 分块；H1 作为整篇标题（doc_title），不单独成块。
    目录 / 相关链接 / 参考资料等「索引型」块标记 index=True，检索时降权。"""
    INDEX_KEYWORDS = ("目录", "相关链接", "参考资料", "附录", "链接", "索引", "参见", "related")
    lines = note["body"].splitlines()
    doc_title = note["fm"].get("title") or ""
    chunks, cur_heading, cur_lines = [], doc_title or "概述", []

    def flush():
        if cur_lines:
            t = "\n".join(cur_lines).strip()
            if t:
                return {"heading": cur_heading, "text": t}
        return None

    for ln in lines:
        h = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if h:
            level = len(h.group(1))
            if level == 1:
                continue  # 整篇标题（H1），不进任何块
            if 2 <= level <= 3:
                f = flush()
                if f:
                    chunks.append(f)
                cur_heading = h.group(2).strip()
                cur_lines = []
                continue
            # level 4-6 当作普通正文保留
        cur_lines.append(ln)
    f = flush()
    if f:
        chunks.append(f)

    out = []
    for c in chunks:
        out.append({
            "file": note["file"],
            "title": doc_title,
            "heading": c["heading"],
            "text": c["text"],
            "tags": note["fm"].get("tags", ""),
            "index": any(k in c["heading"] for k in INDEX_KEYWORDS),
        })
    return out


# ------------------------------------------------------------------ 分词 / 索引
def tokenize(text):
    res = []
    for w in jieba.lcut(text):
        w = w.strip().lower()
        if not w or w in STOPWORDS:
            continue
        if re.match(r"^[\u4e00-\u9fff]+$", w):           # 中文词
            res.append(w)
        elif re.match(r"^[a-z0-9][a-z0-9.+_-]*$", w):    # 英文 / 数字术语（rag, bm25, embedding…）
            if len(w) > 1:
                res.append(w)
    return res


def build_index(chunks):
    docs_tokens = [tokenize(c["text"]) for c in chunks]
    df = {}
    for toks in docs_tokens:
        for w in set(toks):
            df[w] = df.get(w, 0) + 1
    N = len(docs_tokens) or 1
    idf = {w: math.log((N + 1) / (cnt + 1)) + 1 for w, cnt in df.items()}
    vocab = sorted(df)
    w2i = {w: i for i, w in enumerate(vocab)}
    dim = len(vocab)
    mat = np.zeros((N, dim), dtype=np.float32)
    for i, toks in enumerate(docs_tokens):
        tf = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        for w, c in tf.items():
            mat[i, w2i[w]] = (1 + math.log(c)) * idf[w]
        nrm = np.linalg.norm(mat[i])
        if nrm > 0:
            mat[i] /= nrm
    return mat, w2i, idf


def search(query, mat, w2i, idf, chunks, topk=5):
    q = np.zeros(len(w2i), dtype=np.float32)
    tf = {}
    for w in tokenize(query):
        tf[w] = tf.get(w, 0) + 1
    if not tf:
        return []
    for w, c in tf.items():
        if w in w2i:
            q[w2i[w]] = (1 + math.log(c)) * idf.get(w, 1)
    nrm = np.linalg.norm(q)
    if nrm > 0:
        q /= nrm
    sims = mat @ q
    # 取更宽候选，降权索引型块后重排，避免「目录/相关链接」靠重复标题词霸榜
    K = max(topk * 3, 12)
    cands = []
    for i in np.argsort(-sims)[:K]:
        s = float(sims[i])
        if s <= 0:
            continue
        c = chunks[i]
        if c.get("index"):
            s *= 0.35
        cands.append((s, c))
    cands.sort(key=lambda x: -x[0])
    return cands[:topk]


# ------------------------------------------------------------------ embedding 引擎
def embedding_available():
    try:
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


def build_embedding_index(chunks, model_name):
    from sentence_transformers import SentenceTransformer
    print(f"⏳ 加载中文语义模型 {model_name}（首次会自动下载，约 130MB）…", file=sys.stderr)
    model = SentenceTransformer(model_name)
    texts = [(c["heading"] + "。" + c["text"]) for c in chunks]
    emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    emb = np.asarray(emb, dtype=np.float32)
    return model, emb


def embedding_search(query, model, emb, chunks, topk=5):
    q = np.asarray(model.encode([query], normalize_embeddings=True)[0], dtype=np.float32)
    sims = emb @ q
    K = max(topk * 3, 12)
    cands = []
    for i in np.argsort(-sims)[:K]:
        s = float(sims[i])
        if s <= 0:
            continue
        c = chunks[i]
        if c.get("index"):
            s *= 0.35
        cands.append((s, c))
    cands.sort(key=lambda x: -x[0])
    return cands[:topk]


# ------------------------------------------------------------------ 可选 LLM
def llm_answer(query, contexts, api_key, base_url, model):
    sys_prompt = ("你是用户的个人知识库助手。只依据【参考资料】回答，不要编造、不要使用资料外的知识。"
                  "如果资料不足以回答问题，明确说明「我的知识库里没有相关内容」。"
                  "回答尽量简洁，并标注关键结论来自哪个资料。")
    ctx = "\n\n---\n\n".join(
        f"【来源：{c['title']} › {c['heading']}】\n{c['text']}" for c in contexts)
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"参考资料：\n{ctx}\n\n用户问题：{query}"},
    ]
    data = json.dumps({"model": model, "messages": messages, "temperature": 0.2}).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=data,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read().decode())
    return resp["choices"][0]["message"]["content"]


# ------------------------------------------------------------------ 展示
def show(query, results, llm_text=None, engine="bm25"):
    print(f"\n🔍 问题：{query}  〔引擎：{engine}〕")
    if not results:
        print("  （未检索到相关内容）")
        return
    print(f"\n{'─'*60}\n检索到的最相关片段（共 {len(results)} 条）\n{'─'*60}")
    for i, (score, c) in enumerate(results, 1):
        snippet = c["text"].replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:220] + "…"
        print(f"\n[{i}] 得分 {score:.3f} | {c['title'] or c['file']}")
        print(f"    章节：{c['heading']}")
        if c["tags"]:
            print(f"    标签：{c['tags']}")
        print(f"    摘要：{snippet}")
        print(f"    文件：{c['file']}.md")
    if llm_text:
        print(f"\n{'═'*60}\n💡 AI 回答（依据以上片段生成）：\n{'═'*60}\n{llm_text}")


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser(description="本地知识库问答")
    ap.add_argument("query", nargs="*", help="要问的问题；留空进入交互模式")
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--no-llm", action="store_true", help="强制只检索不调用大模型")
    ap.add_argument("--engine", default=os.environ.get("KB_ENGINE", "bm25"),
                   choices=["bm25", "embedding", "auto"],
                   help="检索引擎：bm25=关键词(默认) / embedding=语义向量 / auto=有模型用embedding否则降级bm25")
    ap.add_argument("--model", default=os.environ.get("KB_EMBED_MODEL", DEFAULT_EMBED_MODEL_ID),
                   help="embedding 引擎用的中文模型（本地目录或 HF 模型 id）；本地 models/bge-small-zh 存在时优先")
    ap.add_argument("--dir", default=os.environ.get("KB_DIR", DEFAULT_KB_DIR))
    args = ap.parse_args()

    kb_dir = args.dir
    if not Path(kb_dir).exists():
        print(f"✗ 笔记目录不存在：{kb_dir}")
        sys.exit(1)

    # 引擎选择（auto 自动降级）
    engine = args.engine
    if engine == "auto":
        engine = "embedding" if embedding_available() else "bm25"
    if engine == "embedding" and not embedding_available():
        print("⚠ 未安装 sentence-transformers，已降级为 bm25 引擎", file=sys.stderr)
        engine = "bm25"

    # 模型名解析：默认 HF id 且本地已下载时，优先用本地目录（离线、无需镜像）
    model_name = args.model
    if model_name == DEFAULT_EMBED_MODEL_ID and DEFAULT_EMBED_MODEL_LOCAL.is_dir():
        model_name = str(DEFAULT_EMBED_MODEL_LOCAL)

    print("⏳ 正在加载并索引笔记…", file=sys.stderr)
    notes = load_notes(kb_dir)
    chunks = [c for n in notes for c in split_chunks(n)]
    if engine == "embedding":
        emb_model, emb_mat = build_embedding_index(chunks, model_name)
        print(f"✓ 已用语义向量索引 {len(notes)} 篇笔记 / {len(chunks)} 个片段", file=sys.stderr)
    else:
        mat, w2i, idf = build_index(chunks)
        print(f"✓ 已用关键词(TF-IDF)索引 {len(notes)} 篇笔记 / {len(chunks)} 个片段", file=sys.stderr)

    use_llm = (not args.no_llm) and os.environ.get("KB_LLM_API_KEY")
    if use_llm:
        api_key = os.environ["KB_LLM_API_KEY"]
        base_url = os.environ.get("KB_LLM_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("KB_LLM_MODEL", "gpt-4o-mini")
        print(f"✓ 已启用生成式回答（{model}）", file=sys.stderr)

    def ask(q):
        if engine == "embedding":
            results = embedding_search(q, emb_model, emb_mat, chunks, topk=args.topk)
        else:
            results = search(q, mat, w2i, idf, chunks, topk=args.topk)
        llm_text = None
        if use_llm and results:
            try:
                llm_text = llm_answer(q, [c for _, c in results], api_key, base_url, model)
            except Exception as e:
                print(f"⚠ LLM 调用失败，仅显示检索结果：{e}", file=sys.stderr)
        show(q, results, llm_text, engine)

    q = " ".join(args.query).strip()
    if q:
        ask(q)
    else:
        print("\n进入交互问答模式（输入 exit / quit 退出）\n")
        while True:
            try:
                q = input("你 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见。")
                break
            if not q:
                continue
            if q.lower() in ("exit", "quit", "退出"):
                print("再见。")
                break
            ask(q)


if __name__ == "__main__":
    main()
