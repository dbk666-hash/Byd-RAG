# -*- coding: utf-8 -*-
"""比亚迪年报 PDF -> 按页抽文本,保留页码信息。
输入: data/raw/*.pdf
输出: data/parsed/<文件名>.txt, 每页之间用分隔线标记页码
"""
import pymupdf
from pathlib import Path

from config import ROOT, PARSED

RAW = ROOT / "data" / "raw"
OUT = PARSED

PAGE_SEP = "=====PAGE {}=====\n"   # 页码分隔线
MIN_CHARS = 80                     # 低于此字符数的页会提示(封面/空白页)

def parse_one(pdf: Path) -> None:
    doc = pymupdf.open(pdf)
    lines = []
    total_chars = 0
    low_pages = []                  # 内容过少的页
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        total_chars += len(text)
        if len(text) < MIN_CHARS:
            low_pages.append(i + 1)
        lines.append(PAGE_SEP.format(i + 1))
        lines.append(text)
    doc.close()

    out = OUT / (pdf.stem + ".txt")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] {pdf.stem}: {total_chars} 字 -> {out.name}")
    if low_pages:
        print(f"     内容过少页(正常): {low_pages[:15]}")

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(RAW.glob("*.pdf")):
        parse_one(pdf)
    print("全部完成。")
