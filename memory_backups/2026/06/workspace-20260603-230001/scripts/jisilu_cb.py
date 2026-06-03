#!/usr/bin/env python3
"""
集思录可转债数据获取脚本
数据存储: SQLite (jisilu.db) + JSON备份
用法: python3 jisilu_cb.py
"""
import requests, json, sqlite3, os, sys
from datetime import datetime

# ── 配置 ─────────────────────────────────────────
KBZW_SESSION = "t8ulaqqcm77mpmkrcnltr74di2"
KBZW_USER_LOGIN = "7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5arrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR"
DB_PATH = '/root/.openclaw/workspace/jisilu.db'
JSON_BACKUP = '/root/.openclaw/workspace/jisilu_cb_data.json'

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.jisilu.cn/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

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
            "最后更新": b.get("last_time"),
        })
    return result

def save_to_sqlite(conn, idx, bonds):
    """将数据写入 SQLite（upsert 模式）"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    today = datetime.now().strftime('%Y-%m-%d')

    # 安全提取日期：仅当 last_update 确实为 YYYY-MM-DD 格式才使用，否则默认今天
    def safe_date(raw):
        s = str(raw or '')[:10]
        return s if s.startswith(('20', '19')) else today

    trade_date = safe_date(bonds[0].get('最后更新', now)) if bonds else today

    # 指数温度写入 index_stats
    if idx.get('更新时间'):
        conn.execute("""
            INSERT INTO index_stats (stat_date, index_name, temperature, avg_price,
                avg_premium_rt, avg_dblow, avg_ytm_rt, cb_count)
            VALUES (?, 'jisilu_cb', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stat_date) DO UPDATE SET
                temperature = excluded.temperature, avg_price = excluded.avg_price,
                avg_premium_rt = excluded.avg_premium_rt, avg_dblow = excluded.avg_dblow,
                avg_ytm_rt = excluded.avg_ytm_rt, cb_count = excluded.cb_count
        """, [
            trade_date,
            float(str(idx.get('温度', '0°')).replace('°', '')),
            idx.get('平均价格'),
            float(str(idx.get('平均溢价率', '0%')).replace('%', '')),
            idx.get('双低均值'),
            float(str(idx.get('YTM均值', '0%')).replace('%', '')),
            idx.get('转债数量')
        ])

    rows = 0
    for b in bonds:
        code = b['债券代码']
        name = b['债券名称']

        # securities upsert
        conn.execute("""
            INSERT INTO securities (sec_code, sec_name, sec_type, data_source, updated_at)
            VALUES (?, ?, 'cb', 'jisilu', ?)
            ON CONFLICT(sec_code, sec_type) DO UPDATE SET
                sec_name = excluded.sec_name, updated_at = excluded.updated_at
        """, [code, name, now])

        # daily_quotes upsert
        last_update = b.get('最后更新') or ''
        td = safe_date(last_update)

        conn.execute("""
            INSERT INTO daily_quotes (
                sec_code, trade_date, close, premium_rt, dblow, ytm_rt,
                turnover_rt, volume, convert_value, bond_value
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sec_code, trade_date) DO UPDATE SET
                close = excluded.close, premium_rt = excluded.premium_rt,
                dblow = excluded.dblow, ytm_rt = excluded.ytm_rt,
                turnover_rt = excluded.turnover_rt, volume = excluded.volume,
                convert_value = excluded.convert_value, bond_value = excluded.bond_value
        """, [
            code, td,
            b.get('现价'), b.get('溢价率%'), b.get('双低'),
            b.get('YTM'), b.get('换手率%'), b.get('成交额(万)'),
            b.get('转股价值'), b.get('债现价')
        ])
        rows += 1

    conn.commit()
    return rows

def print_table(rows, headers=None):
    """简易表格打印"""
    if not rows:
        return
    keys = list(rows[0].keys()) if headers is None else headers
    col_widths = {k: max(len(str(k)), max(len(str(r.get(k, "-"))) for r in rows)) + 2 for k in keys}
    header_line = " | ".join(str(k).center(col_widths[k]) for k in keys)
    sep = "-+-".join("-" * col_widths[k] for k in keys)
    print(header_line)
    print(sep)
    for row in rows[:50]:
        print(" | ".join(str(row.get(k, "-")).ljust(col_widths[k]) for k in keys))
    if len(rows) > 50:
        print(f"... (共 {len(rows)} 只转债，仅显示前50只)")

def main():
    print(f"集思录可转债数据 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    s = get_session()
    conn = get_conn()

    # 1. 指数概览
    print("\n【转债指数概览】")
    idx = fetch_index_quote(s)
    for k, v in idx.items():
        print(f"  {k}: {v}")

    # 2. 双低排行榜（前20）
    print("\n【双低排行榜 Top20】（价格+溢价率，越低越安全）")
    bonds = fetch_cb_list(s)
    print_table(bonds, bonds[0].keys() if bonds else [])

    # 3. 保存到 SQLite（主要存储）
    rows = save_to_sqlite(conn, idx, bonds)
    print(f"\n✓ SQLite 写入完成: {rows} 条转债记录")

    # 4. JSON 备份（可选，留作兼容）
    out = {"index": idx, "bonds": bonds, "fetch_time": datetime.now().isoformat()}
    with open(JSON_BACKUP, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"✓ JSON 备份已保存: {JSON_BACKUP}（共 {len(bonds)} 只转债）")

    conn.close()

if __name__ == "__main__":
    main()