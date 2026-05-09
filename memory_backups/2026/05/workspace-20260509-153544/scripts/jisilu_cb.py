#!/usr/bin/env python3
"""
集思录可转债数据获取脚本
用法: python3 jisilu_cb.py
"""
import requests, json, sys
from datetime import datetime

# ── Cookie 配置 ─────────────────────────────────────────
# 请从浏览器 F12 → Application → Cookies → www.jisilu.cn 复制以下两个值
KBZW_SESSION = "t8ulaqqcm77mpmkrcnltr74di2"
KBZW_USER_LOGIN = "7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5arrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR"

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.jisilu.cn/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

def get_session():
    s = requests.Session()
    s.headers.update(BASE_HEADERS)
    s.cookies.set("kbzw__Session", KBZW_SESSION, domain="www.jisilu.cn", path="/")
    s.cookies.set("kbzw__user_login", KBZW_USER_LOGIN, domain="www.jisilu.cn", path="/")
    return s

def fetch_index_quote(s):
    r = s.get("https://www.jisilu.cn/webapi/cb/index_quote/", timeout=10)
    d = r.json().get("data", {})
    return {
        "指数": d.get("cur_index"),
        "温度": f"{d.get('temperature')}°",
        "平均价格": d.get("avg_price"),
        "平均溢价率": f"{d.get('avg_premium_rt')}%",
        "双低均值": d.get("avg_dblow"),
        "YTM均值": f"{d.get('avg_ytm_rt')}%",
        "转债数量": d.get("count"),
        "更新时间": d.get("last_time"),
    }

def fetch_cb_list(s):
    r = s.get("https://www.jisilu.cn/webapi/cb/list/", timeout=10)
    bonds = r.json().get("data", [])

    # 尝试获取名称（autocomplete 有20只）
    r2 = s.get("https://www.jisilu.cn/data/cbnew_ajax/get_cb_autocomplete/", timeout=10)
    try:
        name_map = {item["bond_id"]: item["bond_nm"] for item in json.loads(r2.text)}
    except Exception:
        name_map = {}

    # 按双低排序（价格+溢价率，越低越好）
    bonds.sort(key=lambda x: float(x.get("dblow") or 9999))

    result = []
    for b in bonds:
        bond_id = b.get("bond_id", "")
        result.append({
            "债券代码": bond_id,
            "债券名称": name_map.get(bond_id, "-"),
            "现价": b.get("price"),
            "涨跌%": b.get("increase_rt"),
            "转股价值": b.get("convert_value"),
            "溢价率%": b.get("premium_rt"),
            "双低": b.get("dblow"),
            "债现价": b.get("bond_value"),
            "YTM": b.get("ytm_rt"),
            "成交额(万)": b.get("volume"),
            "换手率%": b.get("turnover_rt"),
            "最后更新": b.get("last_time"),
        })
    return result

def print_table(rows, headers):
    """简易表格打印"""
    keys = list(rows[0].keys()) if rows else []
    if not keys:
        return
    col_widths = {k: max(len(str(k)), max(len(str(r.get(k, ""))) for r in rows)) + 2 for k in keys}

    header_line = " | ".join(str(k).center(col_widths[k]) for k in keys)
    sep = "-+-".join("-" * col_widths[k] for k in keys)
    print(header_line)
    print(sep)
    for row in rows[:50]:  # 最多显示50行
        print(" | ".join(str(row.get(k, "-")).ljust(col_widths[k]) for k in keys))
    if len(rows) > 50:
        print(f"... (共 {len(rows)} 只转债，仅显示前50只)")

def main():
    print(f"集思录可转债数据 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    s = get_session()

    # 1. 指数概览
    print("\n【转债指数概览】")
    idx = fetch_index_quote(s)
    for k, v in idx.items():
        print(f"  {k}: {v}")

    # 2. 双低排行榜（前20）
    print("\n【双低排行榜 Top20】（价格+溢价率，越低越安全）")
    bonds = fetch_cb_list(s)
    print_table(bonds, bonds[0].keys() if bonds else [])

    # 3. 保存完整数据
    out = {"index": idx, "bonds": bonds, "fetch_time": datetime.now().isoformat()}
    out_file = "/root/.openclaw/workspace/jisilu_cb_data.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n完整数据已保存: {out_file}（共 {len(bonds)} 只转债）")

if __name__ == "__main__":
    main()
