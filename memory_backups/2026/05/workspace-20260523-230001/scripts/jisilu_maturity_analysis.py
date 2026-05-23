#!/usr/bin/env python3
"""
强赎债券：强势日期与到期日关系分析
数据存储: SQLite (jisilu.db) + JSON备份
"""
import requests, re, json, time, sqlite3
from datetime import datetime, timedelta

KBZW_SESSION = 't8ulaqqcm77mpmkrcnltr74di2'
KBZW_USER_LOGIN = '7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR'
DB_PATH = '/root/.openclaw/workspace/jisilu.db'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.jisilu.cn/',
    'X-Requested-With': 'XMLHttpRequest',
}

STRONG_RETURN = 3.0
STRONG_VOL = 5.0

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

def s():
    ss = requests.Session()
    ss.headers.update(HEADERS)
    ss.cookies.set('kbzw__Session', KBZW_SESSION, domain='www.jisilu.cn', path='/')
    ss.cookies.set('kbzw__user_login', KBZW_USER_LOGIN, domain='www.jisilu.cn', path='/')
    return ss

def get_maturity_dt(ss, bond_id):
    try:
        r = ss.get(f'https://www.jisilu.cn/data/convert_bond_detail/{bond_id}', timeout=8)
        m = re.search(r'id="maturity_dt"[^>]*>(\d{4}-\d{2}-\d{2})', r.text)
        if m:
            return m.group(1)
    except:
        pass
    return None

def get_all_klines(ss, bond_id, end_date):
    all_klines = []
    seen = set()
    for offset_days in [0, 30, 60, 90, 120, 180, 240, 300]:
        end = datetime.strptime(end_date, '%Y-%m-%d')
        start = (end - timedelta(days=offset_days+60)).strftime('%Y-%m-%d')
        try:
            r = ss.get(
                f'https://www.jisilu.cn/data/cbnew/detail_hist/{bond_id}?display=day',
                timeout=8
            )
            d = r.json()
            rows = d.get('rows', [])
            if not rows:
                break
            for row in rows:
                cell = row.get('cell', {})
                td = cell.get('last_chg_dt', '')
                if td and td not in seen:
                    seen.add(td)
                    p = cell.get('price', '')
                    v = cell.get('volume', '')
                    if td and p:
                        all_klines.append({'date': td, 'price': float(p), 'volume': float(v) if v else 0})
        except:
            continue
        time.sleep(0.3)
    all_klines.sort(key=lambda x: x['date'])
    return all_klines

def save_to_sqlite(conn, bond_maturity, strong_days_by_remaining):
    """将到期分析结果写入 SQLite"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    count = 0

    # 更新 securities 的 maturity_date
    for bid, mat_date in bond_maturity.items():
        conn.execute("""
            INSERT INTO securities (sec_code, sec_name, sec_type, maturity_date, data_source, updated_at)
            VALUES (?, ?, 'cb', ?, 'jisilu', ?)
            ON CONFLICT(sec_code, sec_type) DO UPDATE SET
                maturity_date = excluded.maturity_date, updated_at = excluded.updated_at
        """, [bid, '-', mat_date, now])

    # 写入 maturity_records
    for rec in strong_days_by_remaining:
        conn.execute("""
            INSERT INTO maturity_records (
                sec_code, announce_date, maturity_date, trade_date,
                remaining_years, price, return_pct, volume_ratio,
                is_strong_return, is_strong_volume
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sec_code, trade_date) DO UPDATE SET
                price = excluded.price, return_pct = excluded.return_pct,
                volume_ratio = excluded.volume_ratio,
                is_strong_return = excluded.is_strong_return,
                is_strong_volume = excluded.is_strong_volume
        """, [
            rec['bond_id'],
            rec.get('announce_date'),
            rec.get('maturity_date'),
            rec['trade_date'],
            rec['remaining_years'],
            rec['price'],
            rec['return_pct'],
            rec['volume_ratio'],
            1 if rec.get('is_strong_return') else 0,
            1 if rec.get('is_strong_volume') else 0
        ])
        count += 1

    conn.commit()
    return count

# ── 主程序 ─────────────────────────────────────────────────
ss = s()
conn = get_conn()

with open('/root/.openclaw/workspace/jisilu_redeem_analysis.json') as f:
    data = json.load(f)

redeem_samples = data.get('强赎样本', [])
redeem_ids = [s['bond_id'] for s in redeem_samples if s.get('bond_id')]

print(f'共 {len(redeem_ids)} 只强赎转债，开始获取到期日和K线...')

print('\n获取到期日数据...')
bond_maturity = {}
for i, bid in enumerate(redeem_ids):
    if i % 10 == 0:
        print(f'  {i}/{len(redeem_ids)}')
    dt = get_maturity_dt(ss, bid)
    if dt:
        bond_maturity[bid] = dt
    time.sleep(0.3)

print(f'成功获取到期日: {len(bond_maturity)} / {len(redeem_ids)}')

print('\n分析强势日与到期日关系...')

strong_days_by_remaining = []

for item in redeem_samples:
    bid = item['bond_id']
    ann_date = item.get('announce_date', '')
    if bid not in bond_maturity:
        continue
    mat_date = bond_maturity[bid]

    klines = get_all_klines(ss, bid, ann_date)
    if len(klines) < 5:
        continue

    prices = [k['price'] for k in klines]
    volumes = [k['volume'] for k in klines]
    avg_vol = sum(volumes) / len(volumes) if volumes else 1

    mat = datetime.strptime(mat_date, '%Y-%m-%d')

    for i, k in enumerate(klines):
        trade_date = k['date']
        if not trade_date:
            continue
        td = datetime.strptime(trade_date, '%Y-%m-%d')
        remaining_years = (mat - td).days / 365.0

        if remaining_years <= 0 or remaining_years > 5:
            continue

        if i == 0:
            ret = 0
        else:
            ret = (prices[i] - prices[i-1]) / prices[i-1] * 100

        vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 0

        is_strong_ret = ret >= STRONG_RETURN
        is_strong_vol = vol_ratio >= STRONG_VOL

        if is_strong_ret or is_strong_vol:
            strong_days_by_remaining.append({
                'bond_id': bid,
                'announce_date': ann_date,
                'maturity_date': mat_date,
                'trade_date': trade_date,
                'remaining_years': round(remaining_years, 2),
                'price': prices[i],
                'return_pct': round(ret, 2),
                'volume_ratio': round(vol_ratio, 2),
                'is_strong_return': is_strong_ret,
                'is_strong_volume': is_strong_vol,
            })

print(f'强势日记录总数: {len(strong_days_by_remaining)} 条')

# 统计输出
print('\n按剩余年限统计强势日分布:')
print(f'{"剩余年限区间":<15} {"强势日数量":>8} {"平均涨幅":>10} {"平均量比":>10} {"样本债券数":>10}')
print('-'*60)

from collections import defaultdict
import statistics

bins = [(0, 0.5), (0.5, 1), (1, 2), (2, 3), (3, 5)]
bin_stats = defaultdict(list)

for rec in strong_days_by_remaining:
    ry = rec['remaining_years']
    for lo, hi in bins:
        if lo <= ry < hi:
            bin_stats[(lo, hi)].append(rec)
            break

for lo, hi in bins:
    recs = bin_stats[(lo, hi)]
    if not recs:
        print(f'  {lo:.1f}~{hi:.1f}年        {0:>8}  {"-":>10}  {"-":>10}  {0:>10}')
    else:
        bond_set = set(r['bond_id'] for r in recs)
        avg_ret = statistics.mean([r['return_pct'] for r in recs])
        avg_vr = statistics.mean([r['volume_ratio'] for r in recs])
        label = f'{lo:.1f}~{hi:.1f}年'
        print(f'  {label:<15} {len(recs):>8}  {avg_ret:>9.2f}%  {avg_vr:>9.2f}x  {len(bond_set):>10}')

print('\n' + '='*60)
print('【强势日与到期日关系分析】')
print('='*60)

total_strong = len(strong_days_by_remaining)
total_bonds = len(set(r['bond_id'] for r in strong_days_by_remaining))

print(f'\n强势日定义：涨幅>={STRONG_RETURN}% 或成交量>={STRONG_VOL}倍均量')
print(f'覆盖债券数：{total_bonds} 只')
print(f'强势日总记录：{total_strong} 条')

print('\n各区间强势日频率:')
for (lo, hi), recs in sorted(bin_stats.items()):
    bond_count = len(set(r['bond_id'] for r in recs))
    freq_per_bond = len(recs) / max(1, bond_count)
    pct = len(recs) / total_strong * 100 if total_strong > 0 else 0
    print(f'  剩余 {lo:.1f}~{hi:.1f}年: {len(recs):>4} 条 ({pct:5.1f}%) | 覆盖{bond_count}只债 | 每只平均{freq_per_bond:.1f}次')

recent = sum(len(v) for k, v in bin_stats.items() if k[0] <= 1)
mid = sum(len(v) for k, v in bin_stats.items() if 1 < k[0] <= 2)
far = sum(len(v) for k, v in bin_stats.items() if k[0] > 2)
print(f'\n剩余 <1年  强势日: {recent} 条 ({recent/total_strong*100:.1f}%)')
print(f'剩余 1~2年 强势日: {mid} 条 ({mid/total_strong*100:.1f}%)')
print(f'剩余 >2年  强势日: {far} 条 ({far/total_strong*100:.1f}%)')

# 保存到 SQLite
count = save_to_sqlite(conn, bond_maturity, strong_days_by_remaining)
print(f'\n✓ SQLite 写入完成: {count} 条到期记录')

# JSON 备份
output = {
    '分析时间': datetime.now().isoformat(),
    '强势日定义': f'涨幅>={STRONG_RETURN}% or 量比>={STRONG_VOL}x',
    '覆盖债券数': total_bonds,
    '强势日总数': total_strong,
    '各区间统计': {f'{k[0]}~{k[1]}年': len(v) for k, v in bin_stats.items()},
    '详细记录': strong_days_by_remaining,
    '到期日数据': bond_maturity,
}

with open('/root/.openclaw/workspace/jisilu_maturity_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'✓ JSON 备份已保存: /root/.openclaw/workspace/jisilu_maturity_analysis.json')

conn.close()