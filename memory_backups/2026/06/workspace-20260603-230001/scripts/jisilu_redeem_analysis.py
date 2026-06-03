#!/usr/bin/env python3
"""
集思录 - 强赎/不强赎公告K线分析 v4
数据存储: SQLite (jisilu.db) + JSON备份
"""
import requests, json, re, time, sqlite3, os
from datetime import datetime, timedelta
import statistics

KBZW_SESSION = "t8ulaqqcm77mpmkrcnltr74di2"
KBZW_USER_LOGIN = "7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR"
DB_PATH = '/root/.openclaw/workspace/jisilu.db'

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.jisilu.cn/",
    "X-Requested-With": "XMLHttpRequest",
}

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

def make_session():
    ss = requests.Session()
    ss.headers.update(HEADERS)
    ss.cookies.set("kbzw__Session", KBZW_SESSION, domain="www.jisilu.cn", path="/")
    ss.cookies.set("kbzw__user_login", KBZW_USER_LOGIN, domain="www.jisilu.cn", path="/")
    return ss

def extract_announcements(html):
    rows = re.findall(
        r'<div class="grid-row">\s*'
        r'<div class="grid-col-9"><a[^>]+href="([^"]+)"[^>]*>([^<]+)</a></div>\s*'
        r'<div class="grid-col-3">(\d{4}-\d{2}-\d{2})</div>\s*</div>',
        html
    )
    return [{"url": u, "title": t.strip(), "date": d} for u, t, d in rows]

def is_redeem_decision(title):
    if "赎回" not in title:
        return False
    exclude = ["提示性公告", "核查意见", "受托管理", "预计满足", "可能满足",
               "预计触发", "转股情况公告", "付息公告", "评级报告", "上市保荐",
               "募集资金", "发行结果", "发行公告", "募集说明书", "法律意见书",
               "路演公告", "中签率", "中签号码", "发行保荐书"]
    return not any(k in title for k in exclude)

def is_no_redeem_decision(title):
    if "不提前赎回" not in title and "不赎回" not in title:
        return False
    exclude = ["提示性公告", "核查意见", "受托管理", "预计满足", "可能满足", "预计触发"]
    return not any(k in title for k in exclude)

def get_kline(ss, bond_id, lookback=15):
    for attempt in range(2):
        try:
            r = ss.get(
                f"https://www.jisilu.cn/data/cbnew/detail_hist/{bond_id}?display=day",
                timeout=15
            )
            d = r.json()
            rows = d.get("rows", [])
            if not rows:
                return None
            klines = []
            for row in rows:
                cell = row.get("cell", {})
                td = cell.get("last_chg_dt", "")
                if td:
                    klines.append({
                        "trade_date": td,
                        "price": cell.get("price", ""),
                        "open": cell.get("open", ""),
                        "high": cell.get("high", ""),
                        "low": cell.get("low", ""),
                        "close": cell.get("price", ""),
                        "volume": cell.get("volume", ""),
                        "amount": cell.get("amount", ""),
                        "turnover_rt": cell.get("turnover_rt", ""),
                    })
            klines.sort(key=lambda x: x["trade_date"])
            if len(klines) >= lookback:
                return klines[-lookback:]
            elif len(klines) >= 5:
                return klines
            return None
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            return None
    return None

def extract_features(klines):
    if not klines or len(klines) < 5:
        return None
    try:
        prices = [float(k["price"]) for k in klines if k.get("price")]
        volumes = [float(k["volume"]) for k in klines if k.get("volume")]
        if len(prices) < 5:
            return None
        returns = [(prices[j]-prices[j-1])/prices[j-1]*100 for j in range(1, len(prices))]
        total_return = (prices[-1]-prices[0])/prices[0]*100
        vol = statistics.stdev(returns) if len(returns)>1 else 0
        avg_vol = sum(volumes)/len(volumes) if volumes else 0
        amounts = [prices[i] * volumes[i] for i in range(len(prices))]
        mid = len(amounts) // 2
        amt_ratio = sum(amounts[mid:]) / (sum(amounts[:mid]) + 0.01) if mid > 0 else 0
        late_vol = sum(volumes[-3:])/3 if len(volumes)>=3 else avg_vol
        vol_ratio = late_vol/(avg_vol+0.01)
        max_up = max(returns) if returns else 0
        max_down = min(returns) if returns else 0
        last3_up = sum(1 for r in returns[-3:] if r>0) if len(returns)>=3 else 0
        turnovers = [float(k.get("turnover_rt", 0)) for k in klines if k.get("turnover_rt")]
        avg_to = sum(turnovers)/len(turnovers) if turnovers else 0
        return {
            "区间涨跌幅": round(total_return, 2),
            "波动率": round(vol, 2),
            "成交额比": round(amt_ratio, 2),
            "量比": round(vol_ratio, 2),
            "最大单日涨幅": round(max_up, 2),
            "最大单日跌幅": round(max_down, 2),
            "最后3天上涨天数": last3_up,
            "均换手率": round(avg_to, 2),
            "起始价": round(prices[0], 2),
            "结束价": round(prices[-1], 2),
            "样本天数": len(klines),
        }
    except Exception:
        return None

def save_to_sqlite(conn, results):
    """将分析结果写入 SQLite"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    count = 0
    for label, label_val in [("强赎", "redeem"), ("不强赎", "no_redeem")]:
        for item in results[label]:
            code = item.get("bond_id", "")
            if not code:
                continue
            # securities upsert
            conn.execute("""
                INSERT INTO securities (sec_code, sec_name, sec_type, data_source, updated_at)
                VALUES (?, ?, 'cb', 'jisilu', ?)
                ON CONFLICT(sec_code, sec_type) DO UPDATE SET updated_at = excluded.updated_at
            """, [code, item.get('bond_nm', '-'), now])

            # redeem_samples upsert
            features_json = json.dumps(item.get("features", {}), ensure_ascii=False)
            conn.execute("""
                INSERT INTO redeem_samples (sec_code, label, announce_date, title, url, features)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(sec_code, label) DO UPDATE SET
                    announce_date = excluded.announce_date,
                    title = excluded.title, url = excluded.url, features = excluded.features
            """, [code, label_val, item.get("announce_date"), item.get("title"),
                  item.get("url"), features_json])

            # klines upsert
            for kline in item.get("klines", []):
                conn.execute("""
                    INSERT INTO klines (sec_code, trade_date, open, high, low, close, volume, amount, turnover_rt, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'jisilu')
                    ON CONFLICT(sec_code, trade_date, source) DO UPDATE SET
                        open = excluded.open, high = excluded.high, low = excluded.low,
                        close = excluded.close, volume = excluded.volume,
                        amount = excluded.amount, turnover_rt = excluded.turnover_rt
                """, [code, kline.get("trade_date"), kline.get("open"),
                      kline.get("high"), kline.get("low"), kline.get("close"),
                      kline.get("volume"), kline.get("amount"), kline.get("turnover_rt")])
            count += 1
    conn.commit()
    return count

def stat(label, items):
    if not items:
        print(f"\n{label}组: 无数据")
        return
    feats = [it["features"] for it in items]
    n = len(feats)
    avg = lambda k: sum(f[k] for f in feats)/n
    print(f"\n{label}组 (样本数={n})")
    print(f"  区间涨跌幅均值   : {avg('区间涨跌幅'):.2f}%")
    print(f"  波动率均值       : {avg('波动率'):.2f}%")
    print(f"  成交额比(后/前)  : {avg('成交额比'):.2f}")
    print(f"  量比(末期/均量)  : {avg('量比'):.2f}")
    print(f"  最大单日涨幅均值 : {avg('最大单日涨幅'):.2f}%")
    print(f"  最大单日跌幅均值 : {avg('最大单日跌幅'):.2f}%")
    print(f"  最后3天上涨天数   : {avg('最后3天上涨天数'):.1f}天")
    print(f"  均换手率         : {avg('均换手率'):.2f}%")
    print(f"  平均起始价       : {avg('起始价'):.2f}元")
    print(f"  平均结束价       : {avg('结束价'):.2f}元")

# ── 主程序 ─────────────────────────────────────────────────
print("="*60)
print("集思录可转债强赎/不强赎 K线规律分析")
print("="*60)

ss = make_session()
conn = get_conn()

r = ss.get("https://www.jisilu.cn/webapi/cb/list/", timeout=10)
bonds = r.json().get("data", [])
bond_ids = [b["bond_id"] for b in bonds]
print(f"转债总数: {len(bond_ids)}")

r2 = ss.get("https://www.jisilu.cn/data/cbnew_ajax/get_cb_autocomplete/", timeout=10)
name_map = {it["bond_id"]: it["bond_nm"] for it in json.loads(r2.text)}

half_year = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

redeem_map = {}
no_redeem_map = {}

for i, bond_id in enumerate(bond_ids):
    if i % 30 == 0:
        print(f"  扫描: {i}/{len(bond_ids)}")
    try:
        r = ss.get(f"https://www.jisilu.cn/data/convert_bond_detail/{bond_id}", timeout=6)
        if r.status_code != 200:
            continue
        annos = extract_announcements(r.text)
        for a in annos:
            if a["date"] < half_year:
                continue
            if is_redeem_decision(a["title"]) and bond_id not in redeem_map:
                redeem_map[bond_id] = {"bond_id": bond_id, "bond_nm": name_map.get(bond_id, "-"),
                                       "announce_date": a["date"], "title": a["title"], "url": a["url"]}
            elif is_no_redeem_decision(a["title"]) and bond_id not in no_redeem_map:
                no_redeem_map[bond_id] = {"bond_id": bond_id, "bond_nm": name_map.get(bond_id, "-"),
                                          "announce_date": a["date"], "title": a["title"], "url": a["url"]}
    except Exception:
        continue

print(f"\n强赎决议: {len(redeem_map)} 只")
print(f"不强赎决议: {len(no_redeem_map)} 只")

print("\n强赎转债清单:")
for bid, v in list(redeem_map.items())[:10]:
    print(f"  {bid} {v['bond_nm']} | {v['announce_date']} | {v['title']}")

print("\n获取K线数据...")
results = {"强赎": [], "不强赎": []}

for label, bond_map in [("强赎", redeem_map), ("不强赎", no_redeem_map)]:
    items = list(bond_map.values())
    print(f"\n{label}组: {len(items)} 只")
    for idx, item in enumerate(items):
        if idx % 10 == 0:
            print(f"  {idx}/{len(items)}")
        bond_id = item["bond_id"]
        klines = get_kline(ss, bond_id)
        if klines:
            feats = extract_features(klines)
            if feats:
                item["features"] = feats
                item["klines"] = klines
                results[label].append(item)
                f = feats
                print(f"  ✓ {bond_id} {item['bond_nm']} | {item['announce_date']} | "
                      f"涨跌:{f['区间涨跌幅']}% 波动:{f['波动率']} 量比:{f['量比']}")
        time.sleep(0.3)

print(f"\n有效样本: 强赎={len(results['强赎'])} 不强赎={len(results['不强赎'])}")

print("\n" + "="*70)
print("【强赎 vs 不强赎 15日K线规律分析报告】")
print("="*70)

stat("强赎", results["强赎"])
stat("不强赎", results["不强赎"])

# 保存到 SQLite
count = save_to_sqlite(conn, results)
print(f"\n✓ SQLite 写入完成: {count} 条样本记录")

# JSON 备份（兼容）
out = {"分析时间": datetime.now().isoformat(), "强赎样本": results["强赎"], "不强赎样本": results["不强赎"]}
with open("/root/.openclaw/workspace/jisilu_redeem_analysis.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"✓ JSON 备份已保存: /root/.openclaw/workspace/jisilu_redeem_analysis.json")

conn.close()