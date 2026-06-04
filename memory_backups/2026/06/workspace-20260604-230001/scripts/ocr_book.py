#!/usr/bin/env python3
"""
书籍深度学习工具 - 扫描版PDF OCR提取
支持中文扫描PDF，逐页OCR后合并为可读文本
"""

import subprocess, os, sys, re
from pathlib import Path
from pypdf import PdfReader
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

PDF_PATH = "/home/www/toolbox-api/data/李大霄投资战略 精装版(1).pdf"
OUT_TXT = "/home/www/toolbox-api/data/_learned/li_daxiao_ocr.txt"
TMP_DIR = "/tmp/pdf_ocr"
START_PAGE = 1  # 从第1页开始（TOC一般在前面）
END_PAGE = 298

os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)

def ocr_page(page_num):
    """OCR单页，返回提取的文字"""
    try:
        png = f"{TMP_DIR}/page_{page_num:04d}.png"
        # 转PNG
        r1 = subprocess.run(
            ['pdftoppm', '-r', '120', '-f', str(page_num), '-l', str(page_num),
             '-png', PDF_PATH, f"{TMP_DIR}/page_{page_num:04d}"],
            capture_output=True, timeout=30
        )
        # tesseract OCR
        r2 = subprocess.run(
            ['tesseract', png, 'stdout', '-l', 'chi_sim', '--psm', '6', '-c', 'preserve_interword_spaces=1'],
            capture_output=True, text=True, timeout=60
        )
        txt = r2.stdout.strip()
        return page_num, txt
    except Exception as e:
        return page_num, f"[OCR失败: {e}]"

def main():
    print(f"开始OCR《李大霄投资战略》({START_PAGE}~{END_PAGE}页)...")
    all_text = []
    total = END_PAGE - START_PAGE + 1
    done = 0

    for pn in range(START_PAGE, END_PAGE + 1):
        pn, txt = ocr_page(pn)
        all_text.append(f"\n=== 第{pn}页 ===\n{txt}")
        done += 1
        if done % 20 == 0:
            print(f"  进度: {done}/{total} ({done*100//total}%)")

    full_text = "\n".join(all_text)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write(full_text)

    # 统计字数
    char_count = len(re.sub(r'\s+', '', full_text))
    print(f"OCR完成! 输出: {OUT_TXT}")
    print(f"总文字量: 约{char_count}字")

if __name__ == "__main__":
    main()