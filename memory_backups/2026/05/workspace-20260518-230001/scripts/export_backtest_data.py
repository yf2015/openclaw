#!/usr/bin/env python3
"""
回测历史数据整理工具
将 logs/cb_noredeem_*.log 解析为结构化 CSV，便于后续回测分析
"""

import re, csv
from pathlib import Path

LOG_DIR = Path("/root/.openclaw/workspace/logs")
OUT_CSV = Path("/root/.openclaw/workspace/backtest_data/historical_trades.csv")
OUT_META = Path("/root/.openclaw/workspace/backtest_data/push_metadata.csv")

# ── 解析单条日志文件 ──────────────────────────────────────
def parse_log(fp):
    content = fp.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'\[(\d{4}-\d{2}-\d{2})', content)
    if not m:
        return None, []
    date_str = m.group(1)

    pattern = r'命中:\s*([^ (]+)\((\d{6})\)\s*\((\d+),\s*(\d+)\)\s*溢价:([-\d.]+)%'
    hits = []
    for m2 in re.finditer(pattern, content):
        hits.append({
            "name": m2.group(1).strip(),
            "code": m2.group(2),
            "cnt": int(m2.group(3)),
            "cnt_max": int(m2.group(4)),
            "premium_rt": float(m2.group(5)),
        })
    return date_str, hits


# ── 主逻辑 ────────────────────────────────────────────────
def main():
    logs = sorted(LOG_DIR.glob("cb_noredeem_*.log"))
    print(f"发现 {len(logs)} 个日志文件")

    rows = []
    meta_rows = []
    seen_dates = set()

    for fp in logs:
        date_str, hits = parse_log(fp)
        if not date_str:
            continue

        for hit in hits:
            rows.append({
                "date": date_str,
                "log_file": fp.name,
                "name": hit["name"],
                "code": hit["code"],
                "cnt": hit["cnt"],
                "cnt_max": hit["cnt_max"],
                "premium_rt": hit["premium_rt"],
            })

        if date_str not in seen_dates:
            seen_dates.add(date_str)
            tm = re.search(r'(\d{2}:\d{2}:\d{2})', content[:200] if 'content' in dir() else "")
            meta_rows.append({
                "date": date_str,
                "push_time": "",
                "log_file": fp.name,
                "hit_count": len(hits),
                "bonds": "|".join(h["name"] for h in hits),
            })

    if rows:
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["date","log_file","name","code","cnt","cnt_max","premium_rt"])
            w.writeheader()
            w.writerows(rows)
        print(f"  历史交易CSV: {OUT_CSV} ({len(rows)} 条记录)")

    if meta_rows:
        with open(OUT_META, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["date","push_time","log_file","hit_count","bonds"])
            w.writeheader()
            w.writerows(meta_rows)
        print(f"  推送元数据CSV: {OUT_META} ({len(meta_rows)} 天)")

    print("完成!")

if __name__ == "__main__":
    main()