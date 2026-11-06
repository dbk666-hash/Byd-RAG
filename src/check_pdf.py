"""检查本地PDF文本质量，不调用模型。"""
import pymupdf
from config import ROOT

RAW = ROOT / "data/raw"

def main():
    for pdf in sorted(RAW.glob('*.pdf')):
        doc = pymupdf.open(pdf)
        pages = doc.page_count
        total_chars = 0
        blank_pages = []
        for i in range(pages):
            text = doc[i].get_text('text')
            total_chars += len(text)
            if len(text.strip()) < 20:
                blank_pages.append(i + 1)
        doc.close()
        mb = pdf.stat().st_size / 1024 / 1024
        print(f'{pdf.name}: {pages} 页, 可抽文本 {total_chars} 字, 文件 {mb:.1f} MB')
        if blank_pages:
            print(f"   空白/纯图页(正常): {blank_pages[:10]}{('...' if len(blank_pages) > 10 else '')}")
        if total_chars < 5000:
            print('   ⚠️ 文本极少 —— 可能是扫描件或下载错了,这份要换!')

if __name__ == "__main__":
    main()
