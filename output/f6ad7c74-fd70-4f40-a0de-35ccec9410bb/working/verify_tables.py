# -*- coding: utf-8 -*-
"""逐单元格比对 HTML 表格与 docx 表格，确认表格内容零丢失。"""
import html as H
import re
import sys
from pathlib import Path

from docx import Document

DOCX = Path(sys.argv[1])
SRC_HTML = Path(sys.argv[2])

h = SRC_HTML.read_text(encoding="utf-8")
body = h.split('role="body"', 1)[1]

# 解析 HTML 顶层表格（跳过 nav 内的）
tables_html = []
for tm in re.finditer(r"<table[^>]*>(.*?)</table>", body, re.S):
    t = tm.group(1)
    rows = []
    for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        cells = [
            H.unescape(re.sub(r"<[^>]+>", "", c.group(1)))
            for c in re.finditer(r"<t[hd][^>]*>(.*?)</t[hd]>", rm.group(1), re.S)
        ]
        rows.append(cells)
    tables_html.append(rows)

d = Document(str(DOCX))
tables_docx = [
    [[c.text for c in r.cells] for r in t.rows] for t in d.tables
]


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s.replace("\u00a0", " "))


print(f"HTML 表格 {len(tables_html)} 个｜docx 表格 {len(tables_docx)} 个")
ok = True
for i, (th, td) in enumerate(zip(tables_html, tables_docx), 1):
    print(f"--- 表{i}: HTML {len(th)}行 x {len(th[0])}列 | docx {len(td)}行 x {len(td[0])}列")
    if len(th) != len(td):
        print("   !! 行数不一致")
        ok = False
        continue
    for r, (row_h, row_d) in enumerate(zip(th, td), 1):
        if len(row_h) != len(row_d):
            print(f"   !! 第{r}行列数不一致 {len(row_h)} vs {len(row_d)}")
            ok = False
            continue
        for c, (a, b) in enumerate(zip(row_h, row_d), 1):
            if norm(a) != norm(b):
                print(f"   !! r{r}c{c} 不一致\n      HTML: {a[:80]}\n      DOCX: {b[:80]}")
                ok = False
    if ok:
        print("   ✓ 全部单元格一致")
print()
print("表格比对结果:", "全部通过 ✓" if ok else "存在差异 ✗")
