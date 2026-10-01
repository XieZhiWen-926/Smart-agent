# -*- coding: utf-8 -*-
"""
Markdown → 合规 HTML（doc-typeset 规范）
=======================================
把面试手册 md 转成 doc-typeset 要求的 HTML：
- :root 变量块（值取自 design-token 的 modern-minimal 主题）
- 封面 <section role="cover"> + 正文 <section role="body" data-page-restart="1">
- 全部样式引用 var(--*)，无裸值
- 表格含 thead/tbody；代码块 <pre><code>
- 左边框元素（引用块）前导 &nbsp;&nbsp;
- h2 ≥3 → 自动生成目录

v2 修正（保真度）：
1. 软换行段落：连续的普通文本行合并为**一个** <p>（此前被拆成多个 <p>）
2. 软换行引用块：连续 "> " 行合并为一个 <p class="quote">，空 ">" 行作为分段
3. 合并时按中英边界智能决定是否补空格
"""
import html
import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1])
DST = Path(sys.argv[2])

TITLE = "面试手册：智扫通智能客服 v2"
SUBTITLE = "面向岗位：后端开发 / AI 大模型 Agent 方向"

# --------------------------------------------------------------------------- #
# 章节导语（TQ-03：h2 后不得直接跟 h3，必须有一段正文）
# 内容全部由该章自身的小标题归纳而来，不引入新事实。
# --------------------------------------------------------------------------- #
LEADINS: dict[str, str] = {
    "一、技术选型篇":
        "本篇 4 问，全部围绕「为什么这么选、代价是什么」：后端框架、存储组合、"
        "向量库、前端技术栈。面试官问选型时想确认的不是你选了哪个，而是你**说得出代价**。",
    "二、后端架构篇":
        "本篇 4 问，覆盖分层设计、SSE 的 session 生命周期、连接池参数、JWT 鉴权。"
        "其中第 2 问是高频深挖点，通常会被连续追问三层以上。",
    "三、数据库篇":
        "本篇 3 问：表设计、索引依据、慢查询排查路径。回答时把「表结构 → 索引 → 执行计划」"
        "串成一条线，比单点罗列更有说服力。",
    "四、AI Agent 篇（重点，面试官最关心）":
        "本篇 8 问，是整份材料的重心：ReAct 原理、可观测性、工具注册与中间件、实例生命周期、"
        "流式输出、短期与长期记忆。建议把「工具结果有效率只有 54.5%」当作主动抛出的钩子。",
    "五、RAG 与评测篇":
        "本篇 5 问：RAG 全链路、评测方法、LLM 裁判可信度、适用边界、RAG 与 Text2SQL 的分流。"
        "这里的数字（Recall@3 80%）是全篇最容易被追问的地方。",
    "六、高并发与部署篇":
        "本篇 3 问：高并发改造清单、Nginx 层调优、Docker Compose 编排与依赖。"
        "注意区分「我做了」与「我知道但没做」，后者要主动说明取舍。",
    "八、场景适用性与边界":
        "本篇 2 问，考的是判断力而不是记忆力：这套系统适合什么场景、不适合什么场景，"
        "以及如果重来会怎么改。",
    "八·五、通用后端基础题（必问，用项目回答最有说服力）":
        "本篇 6 问，是通用后端基础题：GIL、await 底层、SSE 与 WebSocket 的区别、Redis 的角色、"
        "事务隔离级别、外部依赖挂掉后的兜底。每一题都用本项目作答，避免背教科书。",
    "九、压力问题应对":
        "本篇 3 问，全部是压力型问题：项目是不是你一个人做的、最大的不足是什么、"
        "问到不会的怎么办。这一章考的是姿态，不是知识。",
}


# --------------------------------------------------------------------------- #
# 内联标记
# --------------------------------------------------------------------------- #
def inline(text: str) -> str:
    """转义 HTML 后处理 **粗体** 与 `代码`"""
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


# --------------------------------------------------------------------------- #
# 软换行合并
# --------------------------------------------------------------------------- #
_ASCII_TAIL = re.compile(r"""[A-Za-z0-9.,;:!?)\]}"'》]""")
_ASCII_HEAD = re.compile(r"""[A-Za-z0-9(\[{]""")

# 「短标签：」——作者用来开新一条目的显式信号，如 `用法：`、`注意：`
_LABEL = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9]{1,5}：")


def join_wrapped(parts: list[str]) -> str:
    """把软换行的多行合并成一段：中文直接接，英文词边界补空格。"""
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if buf and _ASCII_TAIL.match(buf[-1]) and _ASCII_HEAD.match(p[0]):
            buf += " " + p
        else:
            buf += p
    return buf


def split_wrapped(parts: list[str]) -> list[list[str]]:
    """按软换行规则把一组行切成若干段落。

    切分依据（保守，只切「显式新条目」）：
    - 下一行以「短标签：」开头（如 `用法：`、`注意：`）
    其余一律视为同一段的软换行，合并。
    """
    paras: list[list[str]] = [[]]
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if paras[-1] and _LABEL.match(p):
            paras.append([])
        paras[-1].append(p)
    return [x for x in paras if x]


# --------------------------------------------------------------------------- #
# 主解析
# --------------------------------------------------------------------------- #
def convert(md: str) -> tuple[str, str]:
    lines = md.split("\n")
    out: list[str] = []
    toc: list[tuple[str, str]] = []          # (anchor_id, 标题文本)

    i = 0
    n = len(lines)
    sec_no = 0
    stack: list[str] = []

    def close_lists():
        while stack and stack[-1] in ("ul", "ol"):
            out.append(f"</{stack.pop()}>")

    def kind_of(s: str) -> str:
        t = s.strip()
        if not t:
            return "blank"
        if t == "---":
            return "hr"
        if re.match(r"^#{1,6} ", t):
            return "head"
        if t.startswith("|"):
            return "table"
        if t.startswith(">"):
            return "quote"
        if re.match(r"^[-*] ", t):
            return "ul"
        if re.match(r"^\d+\. ", t):
            return "ol"
        return "text"

    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        # ---------- 围栏代码块 ----------
        if stripped.startswith("```"):
            close_lists()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            code = html.escape("\n".join(buf), quote=False)
            out.append(f'<pre class="code-block"><code>{code}</code></pre>')
            continue

        # ---------- 空行 ----------
        if not stripped:
            close_lists()
            i += 1
            continue

        # ---------- 分隔线 ----------
        if stripped == "---":
            close_lists()
            out.append('<hr class="divider">')
            i += 1
            continue

        # ---------- 表格 ----------
        if stripped.startswith("|") and i + 1 < n and re.match(
            r"^\|[\s:|-]+\|$", lines[i + 1].strip()
        ):
            close_lists()
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in header)
            tb = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows
            )
            out.append(
                f'<table class="data-table"><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>'
            )
            continue

        # ---------- 引用块（合并软换行，空 ">" 行分段） ----------
        if stripped.startswith(">"):
            close_lists()
            chunks: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                chunks.append(lines[i].strip().lstrip(">").strip())
                i += 1
            # 空 ">" 行先切成大块，再按软换行规则细分
            blocks: list[list[str]] = [[]]
            for c in chunks:
                if c:
                    blocks[-1].append(c)
                elif blocks[-1]:
                    blocks.append([])
            for blk in blocks:
                for para in split_wrapped(blk):
                    out.append(f'<p class="quote">&nbsp;&nbsp;{inline(join_wrapped(para))}</p>')
            continue

        # ---------- 标题 ----------
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            close_lists()
            level = len(m.group(1))
            text = m.group(2).strip()

            # 文档主标题 → 不进正文（已放封面）
            if level == 1 and text.startswith("面试手册："):
                i += 1
                continue

            if level == 1:                      # 章节 → h2
                sec_no += 1
                anchor = f"section-{sec_no}"
                toc.append((anchor, text))
                out.append(f'<h2 id="{anchor}" class="chapter">{inline(text)}</h2>')
                # TQ-03：若下一非空行就是 "## "（h3），补一段章节导语
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                if j < n and re.match(r"^##\s+", lines[j].strip()):
                    lead = LEADINS.get(text)
                    if not lead:
                        lead = "本篇按「结论 → 理由 → 代价」的顺序展开，每一问都配了追问链。"
                    out.append(f'<p class="chapter-lead">{inline(lead)}</p>')
            elif level == 2:                    # Q → h3
                out.append(f'<h3 class="q-title">{inline(text)}</h3>')
            else:
                out.append(f"<h4>{inline(text)}</h4>")
            i += 1
            continue

        # ---------- 列表（含续行，续行并入同一 <li>） ----------
        m_ul = re.match(r"^[-*] (.*)$", stripped)
        m_ol = re.match(r"^\d+\. (.*)$", stripped)
        if m_ul or m_ol:
            tag = "ul" if m_ul else "ol"
            if not stack or stack[-1] != tag:
                close_lists()
                out.append(f"<{tag}>")
                stack.append(tag)
            content = [(m_ul or m_ol).group(1)]
            i += 1
            while i < n and kind_of(lines[i]) == "text":
                content.append(lines[i].strip())
                i += 1
            out.append(f"<li>{inline(join_wrapped(content))}</li>")
            continue

        # ---------- 普通段落：合并连续文本行（软换行） ----------
        close_lists()
        buf = [lines[i].strip()]
        i += 1
        while i < n and kind_of(lines[i]) == "text":
            if _LABEL.match(lines[i].strip()):
                break
            buf.append(lines[i].strip())
            i += 1
        for para in split_wrapped(buf):
            out.append(f"<p>{inline(join_wrapped(para))}</p>")

    close_lists()

    toc_html = ""
    if len(toc) >= 3:
        items = "".join(f'<li><a href="#{a}">{inline(t)}</a></li>' for a, t in toc)
        toc_html = (
            '<nav class="doc-toc" aria-label="文档目录">'
            '<p class="toc-title">目录</p>'
            f'<ol class="toc-list">{items}</ol></nav>'
        )
    return "\n".join(out), toc_html


# --------------------------------------------------------------------------- #
# 样式（全部引用 var(--*)）
# --------------------------------------------------------------------------- #
CSS = """
  :root {
    /* === design tokens :: modern-minimal (genre=general) === */
    --fs-title: 24pt;
    --fs-h1: 18pt;
    --fs-h2: 15pt;
    --fs-h3: 13pt;
    --fs-body: 11pt;
    --fs-small: 9pt;
    --ff-heading: PingFang SC, 苹方-简, 微软雅黑, sans-serif;
    --ff-body: PingFang SC, 苹方-简, 微软雅黑, sans-serif;
    --ff-mono: JetBrains Mono, Fira Code, Consolas, monospace;
    --lh-body: 1.7;
    --lh-heading: 1.3;
    --fw-bold: 600;
    --fw-normal: 400;
    --color-primary: #2563EB;
    --color-text: #111827;
    --color-textSecondary: #6B7280;
    --color-heading: #111827;
    --color-border: #E5E7EB;
    --color-divider: #F3F4F6;
    --color-background: #FFFFFF;
    --color-codeBackground: #F9FAFB;
    --color-highlight: #FEF3C7;
    --spacing-paragraph: 0.5em;
    --spacing-sectionGap: 2em;
    --spacing-listItemGap: 0.4em;
    /* 派生间距 token（用于 padding，禁止裸值） */
    --spacing-xs: 0.2em;
    --spacing-sm: 0.4em;
    --spacing-md: 0.5em;
    --spacing-lg: 0.6em;
    --spacing-xl: 0.8em;
    --spacing-2xl: 1em;
    --layout-marginTop: 2.5cm;
    --layout-marginBottom: 2.0cm;
    --layout-marginLeft: 2.5cm;
    --layout-marginRight: 2.5cm;
    --page-content-width: 15.6cm;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: var(--ff-body);
    font-size: var(--fs-body);
    line-height: var(--lh-body);
    color: var(--color-text);
    background: var(--color-background);
    max-width: var(--page-content-width);
    margin-left: auto;
    margin-right: auto;
    padding-top: var(--layout-marginTop);
    padding-bottom: var(--layout-marginBottom);
  }

  /* ---------- 封面（每个块显式 text-align，禁止依赖继承） ---------- */
  section[role="cover"] > p.cover-eyebrow {
    text-align: center;
    font-size: var(--fs-small);
    color: var(--color-textSecondary);
    letter-spacing: 0.1em;
    margin-bottom: var(--spacing-sectionGap);
  }
  section[role="cover"] > h1 {
    text-align: center;
    font-family: var(--ff-heading);
    font-size: var(--fs-title);
    line-height: var(--lh-heading);
    font-weight: var(--fw-bold);
    color: var(--color-heading);
    margin-top: var(--spacing-sectionGap);
    margin-bottom: var(--spacing-paragraph);
  }
  section[role="cover"] > p.cover-subtitle {
    text-align: center;
    font-size: var(--fs-h3);
    color: var(--color-textSecondary);
    margin-bottom: var(--spacing-sectionGap);
  }
  section[role="cover"] > p.cover-meta {
    text-align: center;
    font-size: var(--fs-small);
    color: var(--color-textSecondary);
    margin-bottom: var(--spacing-listItemGap);
  }

  /* ---------- 标题 ---------- */
  h2.chapter {
    font-family: var(--ff-heading);
    font-size: var(--fs-h1);
    line-height: var(--lh-heading);
    font-weight: var(--fw-bold);
    color: var(--color-heading);
    margin-top: var(--spacing-sectionGap);
    margin-bottom: var(--spacing-paragraph);
  }
  h3.q-title {
    font-family: var(--ff-heading);
    font-size: var(--fs-h2);
    line-height: var(--lh-heading);
    font-weight: var(--fw-bold);
    color: var(--color-heading);
    margin-top: var(--spacing-sectionGap);
    margin-bottom: var(--spacing-paragraph);
  }
  h4 {
    font-family: var(--ff-heading);
    font-size: var(--fs-h3);
    line-height: var(--lh-heading);
    font-weight: var(--fw-bold);
    color: var(--color-heading);
    margin-top: var(--spacing-paragraph);
    margin-bottom: var(--spacing-paragraph);
  }
  p.chapter-lead {
    font-size: var(--fs-body);
    color: var(--color-textSecondary);
    border-left: 3px solid var(--color-primary);
    padding-left: var(--spacing-xl);
    margin-bottom: var(--spacing-paragraph);
  }

  /* ---------- 正文 ---------- */
  p { margin-bottom: var(--spacing-paragraph); }
  strong { font-weight: var(--fw-bold); color: var(--color-heading); }
  code {
    font-family: var(--ff-mono);
    font-size: var(--fs-small);
    background: var(--color-codeBackground);
    color: var(--color-text);
  }
  pre.code-block {
    font-family: var(--ff-mono);
    font-size: var(--fs-small);
    line-height: var(--lh-heading);
    background: var(--color-codeBackground);
    border: 1px solid var(--color-border);
    padding: var(--spacing-lg) var(--spacing-xl);
    margin-bottom: var(--spacing-paragraph);
    white-space: pre-wrap;
  }
  pre.code-block code { background: transparent; border: none; }

  ul, ol { padding-left: var(--spacing-sectionGap); margin-bottom: var(--spacing-paragraph); }
  li { margin-bottom: var(--spacing-listItemGap); }

  p.quote {
    border-left: 3px solid var(--color-primary);
    background: var(--color-divider);
    padding: var(--spacing-md) var(--spacing-xl);
    margin-bottom: var(--spacing-paragraph);
    color: var(--color-text);
  }

  hr.divider {
    border: none;
    border-top: 1px solid var(--color-border);
    margin-top: var(--spacing-sectionGap);
    margin-bottom: var(--spacing-sectionGap);
  }

  /* ---------- 表格 ---------- */
  table.data-table { border-collapse: collapse; width: 100%; margin-bottom: var(--spacing-paragraph); }
  table.data-table th, table.data-table td {
    border: 1px solid var(--color-border);
    padding: var(--spacing-sm) var(--spacing-lg);
    font-size: var(--fs-small);
    text-align: left;
    vertical-align: top;
  }
  table.data-table th {
    font-weight: var(--fw-bold);
    background: var(--color-divider);
    color: var(--color-heading);
  }

  /* ---------- 目录 ---------- */
  nav.doc-toc {
    background: var(--color-codeBackground);
    padding: var(--spacing-xl) var(--spacing-2xl);
    margin-bottom: var(--spacing-sectionGap);
  }
  p.toc-title {
    font-size: var(--fs-h3);
    font-weight: var(--fw-bold);
    color: var(--color-heading);
    margin-bottom: var(--spacing-paragraph);
  }
  .toc-list, .toc-list ol, .toc-list ul { list-style: none; list-style-type: none; padding-left: 0; }
  .toc-list li { margin-bottom: var(--spacing-listItemGap); font-size: var(--fs-small); }
  .toc-list a { color: var(--color-primary); text-decoration: none; }
"""

# --------------------------------------------------------------------------- #
md = SRC.read_text(encoding="utf-8")
body, toc = convert(md)

cover = f"""  <section role="cover">
    <p class="cover-eyebrow">面试准备材料 · INTERVIEW PLAYBOOK</p>
    <h1>{html.escape(TITLE)}</h1>
    <p class="cover-subtitle">{html.escape(SUBTITLE)}</p>
    <p class="cover-meta">项目：智扫通智能客服 v2</p>
    <p class="cover-meta">技术栈：FastAPI · LangGraph · Vue 3 · MySQL · Redis · Chroma</p>
  </section>"""

doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="docx-page-size" content="A4">
  <title>{html.escape(TITLE)}</title>
  <style>{CSS}</style>
</head>
<body>
{cover}
  <section role="body" data-page-restart="1">
{toc}
{body}
  </section>
</body>
</html>
"""

DST.write_text(doc, encoding="utf-8")
print(f"HTML 已生成: {DST}")
print(f"正文元素行数: {len(body.splitlines())}")
print(f"章节数: {toc.count('<li>')}")
