# -*- coding: utf-8 -*-
"""Step 4 切块: 把解析好的全文切成固定大小的小块(带页码)。
策略(v0): 固定 512 字符 + 相邻块重叠 64 字符。
块对应的页码 = 块内最后出现的页码标记(近似但够用)。
"""
import re
from pathlib import Path

PARSED = Path(__file__).resolve().parent.parent / "data" / "parsed"

CHUNK_SIZE = 512     # 每块约 512 字符(约合一个"段落"量级)
OVERLAP = 64         # 相邻块重叠 64 字符,防止信息被切在边界丢失

def chunk_text(text: str):
    """按字符窗口切块,返回 [(页码, 块文本), ...]"""
    chunks = []
    last_page = 0
    i = 0
    n = len(text)
    while i < n:
        window = text[i:i + CHUNK_SIZE]              # 取一个窗口
        pages = re.findall(r"PAGE (\d+)", window)    # 找窗口内页码标记
        if pages:
            last_page = int(pages[-1])               # 用最近一个页码
        chunks.append((last_page, window))
        i += CHUNK_SIZE - OVERLAP                    # 前进 = 块长 - 重叠
    return chunks

for txt in sorted(PARSED.glob("*.txt")):
    text = txt.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    print(f"{txt.name}: 全文 {len(text)} 字符 -> 切成 {len(chunks)} 块")
    # 抽查第一块前 150 字,看文本质量与页码是否正确
    p, first = chunks[0]
    print(f"   抽样[第{p}页]: {first[:150].replace(chr(10),' ')}")

print("切块完成。")