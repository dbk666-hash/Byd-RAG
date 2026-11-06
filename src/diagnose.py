"""关键词原文定位与年份过滤后的向量诊断。"""
import re
from config import PARSED
from retrieval import extract_years, get_retriever

def kw_locate(kw: str):
    """扫描全部年报,报告每个词出现在哪些年份的哪些页"""
    print(f'\n=== 关键词「{kw}」在原文中出现的位置 ===')
    for txt in sorted(PARSED.glob('*.txt')):
        year = re.search('(20\\d\\d)', txt.stem).group(1)
        hits, cur_page, page_text = ([], 0, '')
        for line in txt.read_text(encoding='utf-8').splitlines():
            m = re.match('=====PAGE (\\d+)=====', line)
            if m:
                if kw in page_text:
                    hits.append(cur_page)
                cur_page, page_text = (int(m.group(1)), '')
            else:
                page_text += line
        if kw in page_text:
            hits.append(cur_page)
        print(f'  {year}年报: 出现「{kw}」的页 = {hits[:25]}')


def main():
    query = input("要诊断的问题> ").strip()
    print("目标年份：", extract_years(query) or "全部年份")
    result = get_retriever().vector_results(query, 5)
    for doc, meta in zip(result["documents"][0], result["metadatas"][0]):
        print(f"[{meta['year']}年报·第{meta['page']}页] {doc.replace(chr(10), ' ')[:160]}")
    keyword = input("关键词反查（回车跳过）> ").strip()
    if keyword:
        kw_locate(keyword)


if __name__ == "__main__":
    main()
