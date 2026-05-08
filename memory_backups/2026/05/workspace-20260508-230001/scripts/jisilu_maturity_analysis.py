#!/usr/bin/env python3
"""
强赎债券：强势日期与到期日关系分析
- 获取每只强赎转债的到期日
- 获取公告前尽可能多的K线历史
- 分析强势日（涨幅>3%）在"剩余年限"轴上的分布
"""
import requests, re, json, time
from datetime import datetime

KBZW_SESSION = 't8ulaqqcm77mpmkrcnltr74di2'
KBZW_USER_LOGIN = '7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.jisilu.cn/',
    'X-Requested-With': 'XMLHttpRequest',
}

def s():
    ss = requests.Session()
    ss.headers.update(HEADERS)
    ss.cookies.set('kbzw__Session', KBZW_SESSION, domain='www.jisilu.cn', path='/')
    ss.cookies.set('kbzw__user_login', KBZW_USER_LOGIN, domain='www.jisilu.cn', path='/')
    return ss

def get_maturity_dt(ss, bond_id):
    """从详情页提取到期日"""
    try:
        r = ss.get(f'https://www.jisilu.cn/data/convert_bond_detail/{bond_id}', timeout=8)
        m = re.search(r'id="maturity_dt"[^>]*>(\d{4}-\d{2}-\d{2})', r.text)
        if m:
            return m.group(1)
    except:
        pass
    return None

def get_all_klines(ss, bond_id, end_date):
    """获取从end_date往前尽可能多的K线（多次请求攒够）"""
    # 集思录每次返回30条，按日期降序
    # 用不同的时间范围尝试拉取更多历史
    all_klines = []
    seen = set()

    for offset_days in [0, 30, 60, 90, 120, 180, 240, 300]:
        from datetime import timedelta
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

    # 去重+排序
    all_klines.sort(key=lambda x: x['date'])
    return all_klines

# ── 主程序 ─────────────────────────────────────────────────
ss = s()

# 加载已有分析数据中的强赎样本
with open('/root/.openclaw/workspace/jisilu_redeem_analysis.json') as f:
    data = json.load(f)

redeem_samples = data.get('强赎样本', [])
redeem_ids = [s['bond_id'] for s in redeem_samples if s.get('bond_id')]

print(f'共 {len(redeem_ids)} 只强赎转债，开始获取到期日和K线...')

# ── Step 1: 获取所有强赎转债的到期日 ──────────────────────
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

# ── Step 2: 获取K线，计算每个强势日的"剩余天数" ─────────────
print('\n分析强势日与到期日关系...')

# 强势日定义：日涨幅 > 3%
STRONG_RETURN = 3.0
STRONG_VOL = 5.0  # 巨量：成交量为均量3倍以上

strong_days_by_remaining = []  # (remaining_years, return_pct, volume_ratio, bond_id, date)
bond_klines_cache = {}

for item in redeem_samples:
    bid = item['bond_id']
    ann_date = item.get('announce_date', '')
    if bid not in bond_maturity:
        continue
    mat_date = bond_maturity[bid]

    # 获取K线
    if bid not in bond_klines_cache:
        klines = get_all_klines(ss, bid, ann_date)
        bond_klines_cache[bid] = klines
    else:
        klines = bond_klines_cache[bid]

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

        # 只保留到期前5年内的数据
        if remaining_years <= 0 or remaining_years > 5:
            continue

        # 日收益率
        if i == 0:
            ret = 0
        else:
            ret = (prices[i] - prices[i-1]) / prices[i-1] * 100

        vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 0

        # 强势日
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

# ── Step 3: 分剩余年限区间统计 ─────────────────────────────────
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

# ── Step 4: 强势日 vs 到期日 统计结论 ─────────────────────────
print('\n' + '='*60)
print('【强势日与到期日关系分析】')
print('='*60)

# 各区间强势日占比
total_strong = len(strong_days_by_remaining)
total_bonds = len(set(r['bond_id'] for r in strong_days_by_remaining))

print(f'\n强势日定义：涨幅≥{STRONG_RETURN}% 或成交量≥{STRONG_VOL}倍均量')
print(f'覆盖债券数：{total_bonds} 只')
print(f'强势日总记录：{total_strong} 条')

print('\n各区间强势日频率:')
for (lo, hi), recs in sorted(bin_stats.items()):
    bond_count = len(set(r['bond_id'] for r in recs))
    freq_per_bond = len(recs) / max(1, bond_count)
    pct = len(recs) / total_strong * 100 if total_strong > 0 else 0
    print(f'  剩余 {lo:.1f}~{hi:.1f}年: {len(recs):>4} 条 ({pct:5.1f}%) | 覆盖{bond_count}只债 | 每只平均{freq_per_bond:.1f}次')

# 最近1年 vs 1-2年 vs 2年+ 对比
recent = sum(len(v) for k, v in bin_stats.items() if k[0] <= 1)
mid = sum(len(v) for k, v in bin_stats.items() if 1 < k[0] <= 2)
far = sum(len(v) for k, v in bin_stats.items() if k[0] > 2)
print(f'\n剩余 <1年  强势日: {recent} 条 ({recent/total_strong*100:.1f}%)')
print(f'剩余 1~2年 强势日: {mid} 条 ({mid/total_strong*100:.1f}%)')
print(f'剩余 >2年  强势日: {far} 条 ({far/total_strong*100:.1f}%)')

# ── Step 5: 保存结果 ─────────────────────────────────────────
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

print(f'\n已保存: /root/.openclaw/workspace/jisilu_maturity_analysis.json')