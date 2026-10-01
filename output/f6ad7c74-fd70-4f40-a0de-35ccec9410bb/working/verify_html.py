# -*- coding: utf-8 -*-
"""校验 md2html 产出的 HTML：结构完整性 + 内容覆盖度 + 残留标记。"""
import html as H
import re
import sys
from pathlib import Path

HTML = Path(sys.argv[1])
MD = Path(sys.argv[2])

h = HTML.read_text(encoding="utf-8")
md = MD.read_text(encoding="utf-8")

print("=== 1. 结构统计 ===")
print(
    f"table={h.count('<table')} thead={h.count('<thead')} tbody={h.count('<tbody')} "
    f"h2={h.count('<h2')} h3={h.count('<h3')} pre={h.count('<pre')} "
    f"ul={h.count('<ul>')} ol={h.count('<ol>')} li={h.count('<li>')} "
    f"quote={h.count('class=\"quote\"')} hr={h.count('<hr')}"
)

print("=== 2. 标签配平 ===")
bad = 0
for t in ["p", "li", "ul", "ol", "table", "thead", "tbody", "tr", "td", "th",
          "pre", "code", "section", "nav", "h1", "h2", "h3", "h4", "strong", "a"]:
    o = len(re.findall(r"<" + t + r"[ >]", h))
    c = h.count("</" + t + ">")
    if o != c:
        print(f"  !! {t}: open={o} close={c}")
        bad += 1
print("  配平 OK" if bad == 0 else f"  {bad} 处不配平")

# 可见文本
txt = re.sub(r"<[^>]+>", "\x00", h)
txt = H.unescape(txt).replace("\x00", " ")
flat = re.sub(r"\s+", "", txt)

print("=== 3. 残留 Markdown 标记 ===")
resid = []
for pat, name in [(r"\*\*", "**"), (r"(?<!\S)`(?!\S)", "反引号"), (r"^\|", "表格行")]:
    m = re.findall(pat, flat, re.M)
    if m:
        resid.append((name, len(m)))
print("  无残留" if not resid else f"  {resid}")


def clean(s: str) -> str:
    s = re.sub(r"^[>#\s]+", "", s)
    s = re.sub(r"^([-*]|\d+\.)\s+", "", s)
    s = s.replace("**", "").replace("`", "")
    return re.sub(r"\s+", "", s)


print("=== 4. 内容覆盖度 ===")
miss, tot = [], 0
infence = False
for ln in md.split("\n"):
    if ln.strip().startswith("```"):
        infence = not infence
        continue
    if infence or ln.strip().startswith("|") or ln.strip() == "---" or not ln.strip():
        continue
    c = clean(ln)
    if len(c) < 6:
        continue
    tot += 1
    if c not in flat:
        miss.append(c[:70])
print(f"  内容行 {tot} 行，未覆盖 {len(miss)} 行")
for m in miss[:20]:
    print("   MISS:", m)

print("=== 5. 段落切分合理性（抽查合并效果） ===")
ps = re.findall(r"<p>(.*?)</p>", h, re.S)
print(f"  普通段落数 {len(ps)}")
longest = sorted(ps, key=len, reverse=True)[:1]
for p in longest:
    print("  最长段落:", re.sub(r"<[^>]+>", "", p)[:120], "...")
