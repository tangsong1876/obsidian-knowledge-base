# 文档 → Obsidian 结构化笔记 沉淀规范

把任意资料（PPTX / PDF / DOCX / HTML / 飞书 / 豆包等）转写为可导航、可溯源、可生长的 Obsidian 笔记。本规范来自「WorkBuddy ↔ Obsidian」长期联动实践，可直接照做。

## 1. 目标库结构（推荐）
```
00-收件箱/   待整理的原始抓取/草稿
10-MOC/      MOC 地图（MOC-xxx.md），唯一总入口
20-笔记/     正式笔记（*.md），单篇一个主题
30-素材/     可选：原文副本/提取原文（双轨时用）
90-模板/     概念笔记/MOC/视频笔记模板
使用说明.md  库的使用与维护说明
```
- 笔记文件名 = 一句话主题、全库唯一（如 `RAG检索增强生成入门-让AI懂你的私有知识.md`）。
- 概念笔记以 `概念-` 开头；MOC 以 `MOC-` 开头。

## 2. frontmatter 规范
```yaml
---
type: note          # note / concept / moc / video
title: 标题
created: 2026-08-25
updated: 2026-08-25
tags: [RAG, 知识库, AI工程]
status: 已补全      # 待补充 / 已补全 / 草稿
confidence: 高      # 高 / 中 / 低
moc:                # YAML 列表！Obsidian 不解析 [[ ]] 为链接，写字符串会显示异常
  - MOC-AI入门与基础
source: https://...  # 必填，指向原文或链接，保证来源可溯
---
```
> 红线：无损、来源可溯、不确定项显式标注、不编造。缺失内容用「（原文此处为截图，未提取）」如实标注，不要编造。

## 3. 单轨 vs 双轨
- **默认单轨**：笔记独立成篇，不额外存原文副本（用户明确要"不用双轨并存"时如此）。
- **双轨（可选）**：原文档放 `30-素材/`，笔记内用 `[[...-原文]]` 双链回指。注意：双链必须是真实存在的文件名，否则是悬空链接。

## 4. 抓取与解析规则（按来源）
- **飞书 `file` / `wiki` 链接**：WebFetch 拿不到正文（SPA 空壳或跳登录）→ 请用户提供本地导出（docx/PDF/PPTX）或全文粘贴。
- **飞书 `slides` / `minutes` / `docx` 链接（bytedance.larkoffice.com）**：可直抓，但**有懒加载截断**（一次抓不全，尤其代码块/后续页）→ 多次抓取并标注「第 N 节起待补充」，拿到本地副本后补全。
- **豆包 `feishu.doubao.com/docx/...`**：远程抓不到（SPA 空壳 + larkoffice 跳登录）→ 必须本地副本。
- **本地 PPTX / DOCX**：用 Python 标准库 `zipfile` + `xml.etree.ElementTree` 解析 `ppt/slides/slideN.xml` 的 `<a:t>`（PPTX）或 `word/document.xml`（DOCX）取真实文本节点；**不要用正则在原始 XML 上匹配，会混入标签噪声**。
- **本地 PDF**：用 `pypdf` 提取文本（Read 工具直接读 PDF 有时失败，回退 Python）。
- **本地 HTML**：用 `bs4` + `lxml`（venv 已装）。先定位正文容器（`article` / `main.content` / `detail-content-left` 等），剥离 `script/style/nav/footer/header/aside` 与页眉页脚/相关文章噪声，按 `h2-h6 / p / ul / ol / blockquote` 转 Markdown；**不搬运远程图片/CDN 图**（离线失效），在笔记里透明标注「图示未提取」。

> 环境坑：本会话 shell 下 `editor_sdk` 通道曾因路径被解析成双盘符、且大体积含媒体文件加载失败而不可用 → 统一回退 Python 解析（透明告知用户）。

## 5. 导航与生长
- 每建一篇笔记，去对应 `MOC-xxx.md` 加 `[[双链]]`；主 MOC 加「按主题深入」区链到子 MOC。
- 单点概念（如 RAG、提示词工程）拆成 `概念-xxx.md`（`type: concept`），在 MOC「核心概念」区加链，形成「概念 ↔ 笔记 ↔ MOC」三层网。
- 把 `每日AI对话知识沉淀Prompt` 配成定时任务，每天自动回写 `20-笔记/`，让库"越用越长"。

## 6. 质量红线
- 落库后跑全库 `[[双链]]` 校验：MOC↔笔记↔概念 之间不能悬空（文档/模板里的语法示例 `[[]]` 不算）。
- 写完更新 `使用说明.md` 的相关章节与「最后更新」日期。
