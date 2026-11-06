"""唯一的512/64切块实现；建库、检索和预览均从这里导入。"""
import re
from pathlib import Path

from config import CHUNK_SIZE, OVERLAP, PARSED

def chunk_text(text: str):
    """512/64 固定窗口切块 —— 顺序与 build_index 完全一致,块 id 才能对齐"""
    chunks, last_page, i, n = ([], 0, 0, len(text))
    while i < n:
        latter = min(i + CHUNK_SIZE, len(text))
        window = text[i:latter]
        pages = re.findall('PAGE (\\d+)', window)
        if pages:
            last_page = int(pages[-1])
        chunks.append((last_page, window))
        i += CHUNK_SIZE - OVERLAP
    return chunks


def load_corpus(parsed_dir=PARSED):
    """返回正文列表、ID列表、cid->(cid, year, page, text)，保留原编号顺序。"""
    corpus, ids, meta = [], [], {}
    for path in sorted(Path(parsed_dir).glob("*.txt")):
        match = re.search(r"20\d\d", path.stem)
        if not match:
            raise ValueError(f"年报文件名缺少年份：{path.name}")
        for index, (page, text) in enumerate(chunk_text(path.read_text(encoding="utf-8"))):
            cid = f"{path.stem}_{index}"
            corpus.append(text)
            ids.append(cid)
            meta[cid] = (cid, match.group(), page, text)
    if not corpus:
        raise FileNotFoundError(f"未找到解析文本：{parsed_dir}")
    return corpus, ids, meta


def main():
    for path in sorted(PARSED.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        print(f"{path.name}: {len(text)}字符 -> {len(chunks)}块")
        if chunks:
            page, first = chunks[0]
            print(f"  第{page}页：{first[:150].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()
