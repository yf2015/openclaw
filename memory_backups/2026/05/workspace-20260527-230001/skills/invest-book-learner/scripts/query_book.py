#!/usr/bin/env python3
"""
投资书籍知识库查询脚本
用法:
  python3 query_book.py "<关键词>"           # 搜索两本书
  python3 query_book.py --rerun-ocr         # 重新OCR（200DPI高质量）
  python3 query_book.py --status             # 查看知识库状态
"""

import sys, re, os, subprocess
from pathlib import Path

KB_DIR = Path("/home/www/toolbox-api/data/_learned")
CANDLESTICK_TXT = KB_DIR / "japan_candlestick.txt"
LI_DAXIAO_TXT = KB_DIR / "li_daxiao_ocr.txt"
PDF_LIDAXIAO = Path("/home/www/toolbox-api/data/李大霄投资战略 精装版(1).pdf")
TMP_DIR = Path("/tmp/pdf_ocr_hq")
OUT_TXT = KB_DIR / "li_daxiao_ocr.txt"


def get_status():
    cs_exists = CANDLESTICK_TXT.exists()
    lx_exists = LI_DAXIAO_TXT.exists() and LI_DAXIAO_TXT.stat().st_size > 1000

    cs_size = CANDLESTICK_TXT.stat().st_size if cs_exists else 0
    lx_size = LI_DAXIAO_TXT.stat().st_size if lx_exists else 0

    print("📚 投资书籍知识库状态")
    print(f"   日本蜡烛图技术: {'✅' if cs_exists else '❌'} {cs_size//1024}KB")
    print(f"   李大霄投资战略: {'✅' if lx_exists else '❌'} {lx_size//1024}KB（扫描版，低分辨率OCR质量差）")
    print()

    if lx_exists and lx_size < 10000:
        print("⚠️  李大霄PDF为扫描版，OCR质量较差（仅~6KB）")
        print("   运行 --rerun-ocr 可重新提取（200DPI，需75分钟）")
        print()


def search_file(filepath, keyword, context_lines=5, max_chars=2500):
    if not filepath.exists() or filepath.stat().st_size < 100:
        return None
    content = filepath.read_text(encoding="utf-8", errors="ignore")
    lines = content.split('\n')
    results = []
    kw_lower = keyword.lower()
    for i, line in enumerate(lines):
        if kw_lower in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            snippet = '\n'.join(lines[start:end])
            results.append(snippet)
            if sum(len(r) for r in results) > max_chars:
                break
    return '\n---\n'.join(results) if results else None


def search_both(keyword):
    results = {}
    cs = search_file(CANDLESTICK_TXT, keyword)
    if cs:
        results['日本蜡烛图技术'] = cs

    lx = search_file(LI_DAXIAO_TXT, keyword)
    if lx:
        results['李大霄投资战略'] = lx

    return results


def rerun_ocr():
    """重新OCR（200DPI高质量模式）"""
    if not PDF_LIDAXIAO.exists():
        print(f"❌ PDF文件不存在: {PDF_LIDAXIAO}")
        return

    from pypdf import PdfReader
    r = PdfReader(str(PDF_LIDAXIAO))
    total_pages = len(r.pages)
    print(f"开始OCR《李大霄投资战略》（200DPI高清版，共{total_pages}页）...")
    print("⚠️  需要约75分钟，请耐心等待，进度每20页报告一次")

    TMP_DIR.mkdir(exist_ok=True)
    all_text = []

    for pn in range(1, total_pages + 1):
        png = TMP_DIR / f"p{pn:04d}.png"
        try:
            subprocess.run(['pdftoppm', '-r', '200', '-f', str(pn), '-l', str(pn),
                           '-png', str(PDF_LIDAXIAO), str(TMP_DIR / f"p{pn:04d}")],
                          capture_output=True, timeout=30)
            r2 = subprocess.run(['tesseract', str(png), 'stdout', '-l', 'chi_sim',
                                 '--psm', '6'],
                                capture_output=True, text=True, timeout=60)
            txt = r2.stdout.strip()
        except Exception as e:
            txt = f"[失败: {e}]"
        all_text.append(f"\n=== 第{pn}页 ===\n{txt}")
        if pn % 20 == 0:
            print(f"  进度: {pn}/{total_pages} ({pn*100//total_pages}%)")

    full = '\n'.join(all_text)
    OUT_TXT.write_text(full, encoding='utf-8')
    char_count = len(re.sub(r'\s+', '', full))
    print(f"✅ OCR完成！输出: {OUT_TXT}（约{char_count}字）")


def main():
    if len(sys.argv) < 2:
        get_status()
        return

    cmd = sys.argv[1]

    if cmd == '--status':
        get_status()
    elif cmd == '--rerun-ocr':
        rerun_ocr()
    else:
        keyword = cmd
        get_status()
        print(f"🔍 搜索关键词: {keyword}\n")
        results = search_both(keyword)
        if not results:
            print(f"未找到「{keyword}」相关内容")
            return
        for book, snippet in results.items():
            print(f"📖 [{book}]")
            print("=" * 60)
            print(snippet)
            print()


if __name__ == "__main__":
    main()