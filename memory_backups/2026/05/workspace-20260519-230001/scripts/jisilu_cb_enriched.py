#!/usr/bin/env python3
"""
集思录可转债数据获取【增强版】- 同步获取正股代码/名称
用法: python3 jisilu_cb_enriched.py
"""
import requests, re, json, time
from datetime import datetime

KBZW_SESSION = "t8ulaqqcm77mpmkrcnltr74di2"
KBZW_USER_LOGIN = "7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR"

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
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

# ── 工具函数 ─────────────────────────────────────────────

def get_board(stock_code):
    """根据股票代码判断所属板块"""
    if stock_code is None:
        return "unknown"
    code = str(stock_code)
    if code.startswith("688"):
        return "科创板"
    elif code.startswith("300"):
        return "创业板"
    elif code.startswith("002") or code.startswith("001"):
        return "中小板"
    elif code.startswith("000") or code.startswith("001"):
        return "主板(深圳)"
    elif code.startswith("600") or code.startswith("601") or code.startswith("603"):
        return "主板(上海)"
    else:
        return "other"


def fetch_bond_detail(s, bond_id):
    """
    抓取转债详情页，提取正股代码和名称
    Returns: {"stock_code": "300740", "stock_nm": "水羊股份"}
    """
    try:
        r = s.get(f"https://www.jisilu.cn/data/convert_bond_detail/{bond_id}", timeout=8)
        html = r.text

        # 提取正股代码: /data/stock/XXXXXX
        m = re.search(r'/data/stock/(\d{6})', html)
        stock_code = m.group(1) if m else None

        # 提取正股名称: <span class="font_16">公司名<sup...
        m2 = re.search(r'font_16">([^<]+)</span>\s*(\d{6})', html)
        stock_nm = m2.group(1).strip() if m2 else None

        # 备用: 直接从链接文本提取
        if not stock_nm:
            m3 = re.search(r'target="_blank"[^>]+>\s*<span[^>]*>([^<]+)</span>\s*(\d{6})', html)
            if m3:
                stock_nm = m3.group(1).strip()

        return {"stock_code": stock_code, "stock_nm": stock_nm}
    except Exception as e:
        return {"stock_code": None, "stock_nm": None}


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
    """获取转债列表 + 基本行情"""
    r = s.get("https://www.jisilu.cn/webapi/cb/list/", timeout=10)
    bonds = r.json().get("data", [])

    # 名称映射（autocomplete 只有20条，仅作为补充）
    r2 = s.get("https://www.jisilu.cn/data/cbnew_ajax/get_cb_autocomplete/", timeout=10)
    try:
        name_map = {item["bond_id"]: item["bond_nm"] for item in json.loads(r2.text)}
    except Exception:
        name_map = {}

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
            "正股价": b.get("sprice"),        # 集思录list接口已有
            "正股涨跌%": b.get("sincrease_rt"),
            "最后更新": b.get("last_time"),
        })
    return result


def main():
    print(f"【集思录可转债增强版】 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    s = get_session()

    # 1. 指数概览
    print("\n[1] 获取指数概览...")
    idx = fetch_index_quote(s)
    for k, v in idx.items():
        print(f"   {k}: {v}")

    # 2. 转债列表
    print("\n[2] 获取转债列表...")
    bonds = fetch_cb_list(s)
    print(f"   共 {len(bonds)} 只转债")

    # 3. 逐只抓取正股信息（仅限双低Top50，避免超时）
    print("\n[3] 逐只抓取正股信息（双低Top50，每30只报告进度）...")
    top50 = bonds[:50]   # 只处理Top50，平衡覆盖率和速度
    success = 0
    fail = 0
    for i, bond in enumerate(top50):
        bond_id = bond["债券代码"]
        if i % 30 == 0:
            print(f"   进度: {i}/{len(top50)}")

        info = fetch_bond_detail(s, bond_id)
        bond["正股代码"] = info["stock_code"]
        bond["正股名称"] = info["stock_nm"]
        bond["所属板块"] = get_board(info["stock_code"])

        if info["stock_code"]:
            success += 1
        else:
            fail += 1

        time.sleep(0.15)  # 0.25→0.15，加速采集

    print(f"   正股提取完成: 成功 {success} 只 / 失败 {fail} 只")

    # 4. 统计板块分布
    print("\n[4] 板块分布统计:")
    board_count = {}
    for b in bonds:
        board = b.get("所属板块", "unknown")
        board_count[board] = board_count.get(board, 0) + 1
    for board, cnt in sorted(board_count.items(), key=lambda x: -x[1]):
        pct = cnt / len(bonds) * 100
        print(f"   {board}: {cnt} 只 ({pct:.1f}%)")

    # 5. 打印前20双低（带正股信息）
    print("\n[5] 双低排行榜 Top20（含正股）:")
    print(f"{'代码':<8} {'名称':<10} {'现价':>7} {'溢价率':>8} {'正股代码':<8} {'板块':<10}")
    print("-" * 70)
    for b in bonds[:20]:
        print(f"{b['债券代码']:<8} {b['债券名称']:<10} {b['现价'] or '-':>7} "
              f"{b['溢价率%'] or '-':>8} {b.get('正股代码') or '-':<8} {b.get('所属板块') or '-':<10}")

    # 6. 保存
    out = {
        "index": idx,
        "bonds": bonds,
        "fetch_time": datetime.now().isoformat(),
        "summary": {
            "total": len(bonds),
            "success_stock_code": success,
            "fail_stock_code": fail,
            "board_dist": board_count,
        }
    }
    out_file = "/root/.openclaw/workspace/jisilu_cb_enriched.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 数据已保存: {out_file}")

    # 7. 追加到时序文件（每日一条）
    daily_file = "/root/.openclaw/workspace/jisilu_board_daily.json"
    try:
        with open(daily_file) as f:
            daily = json.load(f)
    except Exception:
        daily = {"records": []}

    # 今天日期的数据（重复执行时更新当天）
    today = datetime.now().strftime("%Y-%m-%d")
    daily["records"] = [r for r in daily["records"] if r.get("date") != today]

    board_stats = {}
    for board, cnt in board_count.items():
        board_bonds = [b for b in bonds if b.get("所属板块") == board]
        prices = [float(b["现价"]) for b in board_bonds if b.get("现价")]
        premiums = [float(b["溢价率%"]) for b in board_bonds if b.get("溢价率%")]
        turnovers = [float(b["换手率%"]) for b in board_bonds if b.get("换手率%")]

        board_stats[board] = {
            "count": cnt,
            "avg_price": round(sum(prices)/len(prices), 2) if prices else 0,
            "avg_premium": round(sum(premiums)/len(premiums), 2) if premiums else 0,
            "avg_turnover": round(sum(turnovers)/len(turnovers), 2) if turnovers else 0,
        }

    daily["records"].append({
        "date": today,
        "board_stats": board_stats,
    })
    daily["last_update"] = datetime.now().isoformat()

    with open(daily_file, "w", encoding="utf-8") as f:
        json.dump(daily, f, ensure_ascii=False, indent=2)
    print(f"✅ 时序数据已更新: {daily_file}")

if __name__ == "__main__":
    main()