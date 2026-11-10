"""唯一的页内 512/64 切块实现，供建库、检索和预览共用。"""
import re
from pathlib import Path

from config import CHUNK_SIZE, OVERLAP, PARSED
from extract_unit import PAGE_MARKER


def page_ranges(text):
    """返回页码和正文在原始文本中的起止位置。"""
    markers = list(PAGE_MARKER.finditer(text))
    if not markers:
        yield 0, 0, len(text)
        return

    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        yield int(marker[1]), marker.end(), end


def chunk_spans(text):
    """页内滑窗，返回 (页码, 原文起点, 原文终点)。"""
    for page, start, end in page_ranges(text):
        body = text[start:end]
        start += len(body) - len(body.lstrip())
        end -= len(body) - len(body.rstrip())
        while start < end:
            stop = min(start + CHUNK_SIZE, end)
            yield page, start, stop
            if stop == end:
                break
            start += CHUNK_SIZE - OVERLAP


def chunk_text(text: str):
    return [(page, text[start:end]) for page, start, end in chunk_spans(text)]


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
