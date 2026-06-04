#!/usr/bin/env python3
"""
fill_klines_sina.py
用 Sina 财经 API 批量补填转债日线数据，覆盖 2026-04-22 ~ 2026-06-01 区间
数据写入 jisilu.db 的 klines_xq 表，source='akshare'
"""

import os, sys, time, sqlite3, datetime as dt
import requests
import py_mini_racer
from akshare.stock.cons import hk_js_decode

DB_PATH   = "/root/.openclaw/workspace/jisilu.db"
START_DATE = dt.date(2026, 4, 22)
END_DATE   = dt.date(2026, 6, 1)
BATCH_SLEEP = 0.2   # 每只债休息秒（防封）
BATCH_LIMIT = 200   # 每批最多采多少只

js_ctx = None

def get_js():
    global js_ctx
    if js_ctx is None:
        js_ctx = py_mini_racer.MiniRacer()
        js_ctx.eval(hk_js_decode)
    return js_ctx


def fetch_sina_cb(code):
    """从 Sina 财经获取单只转债日线，范围 2026-04-22 ~ 2026-06-01"""
    sym = ('sh' + code) if code.startswith(('11', '13')) else ('sz' + code)
    d = dt.datetime.now().strftime('%Y_%m_%d')
    url = f'https://finance.sina.com.cn/realstock/company/{sym}/hisdata/klc_kl.js?d={d}'
    try:
        r = requests.get(url,
                        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'},
                        timeout=15)
        if r.status_code != 200 or len(r.text) < 200:
            return None
        js = get_js()
        raw = r.text.split('=')[1].split(';')[0].replace('"', '')
        data = js.call('d', raw)
        return data
    except Exception as e:
        return None


def filter_range(rows):
    """过滤出指定日期区间的行"""
    result = []
    for row in rows:
        d = str(row.get('date', ''))[:10]
        if d >= START_DATE.isoformat() and d <= END_DATE.isoformat():
            result.append({
                'trade_date': d,
                'open':   round(float(row['open']), 3),
                'high':   round(float(row['high']), 3),
                'low':    round(float(row['low']), 3),
                'close':  round(float(row['close']), 3),
                'volume': int(row['volume']),
                'amount': 0,
            })
    return result


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 读取转债列表
    cur.execute('SELECT bond_id FROM cb_bond_list ORDER BY bond_id')
    all_codes = [r[0] for r in cur.fetchall()]
    print(f'转债总数: {len(all_codes)}')

    # 检查已有数据量（避免重复插）
    cur.execute("""
        SELECT COUNT(*) FROM klines_xq
        WHERE source='akshare'
        AND trade_date >= ? AND trade_date <= ?
    """, (START_DATE.isoformat(), END_DATE.isoformat()))
    already = cur.fetchone()[0]
    print(f'已入库: {already} 条')

    total_fetched = 0
    total_rows = 0
    failed = []

    for i, code in enumerate(all_codes):
        rows_raw = fetch_sina_cb(code)
        if rows_raw is None:
            failed.append(code)
            print(f'  [{i+1}/{len(all_codes)}] {code}: 拉取失败')
            continue

        rows = filter_range(rows_raw)
        if not rows:
            print(f'  [{i+1}/{len(all_codes)}] {code}: 无目标区间数据')
            continue

        for row in rows:
            cur.execute("""
                INSERT INTO klines_xq (sec_code,trade_date,open,high,low,close,volume,amount,source)
                VALUES (?,?,?,?,?,?,?,?,'akshare')
                ON CONFLICT(sec_code,trade_date,source)
                DO UPDATE SET open=excluded.open, high=excluded.high,
                              low=excluded.low, close=excluded.close,
                              volume=excluded.volume, amount=excluded.amount
            """, (code, row['trade_date'], row['open'], row['high'],
                  row['low'], row['close'], row['volume'], row['amount']))
        conn.commit()
        total_fetched += 1
        total_rows += len(rows)
        print(f'  [{i+1}/{len(all_codes)}] {code}: {len(rows)} 条入库')

        if (i + 1) % BATCH_LIMIT == 0:
            print(f'  --- 已处理 {i+1} 只，休息2秒 ---')
            time.sleep(2)

        time.sleep(BATCH_SLEEP)

    conn.close()

    print()
    print(f'===== 完成 =====')
    print(f'成功拉取: {total_fetched}/{len(all_codes)} 只')
    print(f'总入库行: {total_rows} 条')
    print(f'失败列表: {failed}')


if __name__ == '__main__':
    main()