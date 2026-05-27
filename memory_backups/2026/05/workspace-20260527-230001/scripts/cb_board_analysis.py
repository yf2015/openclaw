#!/usr/bin/env python3
"""
可转债板块对比分析 - 基于历史时序数据
分析：主板 vs 创业板 vs 科创板 vs 中小板 的转债价格/溢价率/换手率等指标
用法: python3 scripts/cb_board_analysis.py
"""
import json, math
from datetime import datetime, timedelta

# ── 加载数据 ─────────────────────────────────────────────
with open("/root/.openclaw/workspace/jisilu_cb_enriched.json") as f:
    enriched = json.load(f)

with open("/root/.openclaw/workspace/jisilu_board_daily.json") as f:
    daily = json.load(f)

bonds = enriched["bonds"]

# ── 今日快照统计 ─────────────────────────────────────────

print("=" * 70)
print("【可转债板块对比分析报告】")
print(f"数据日期: {enriched['fetch_time'][:10]} | 转债总数: {len(bonds)} 只")
print("=" * 70)

def stat(board):
    bs = [b for b in bonds if b.get("所属板块") == board]
    n = len(bs)
    if n == 0:
        return None, None, None, None

    prices = [float(b["现价"]) for b in bs if b.get("现价")]
    premiums = [float(b["溢价率%"]) for b in bs if b.get("溢价率%")]
    turnovers = [float(b["换手率%"]) for b in bs if b.get("换手率%")]
    volumes = [float(b["成交额(万)"]) for b in bs if b.get("成交额(万)")]

    avg_p = sum(prices)/len(prices) if prices else 0
    avg_prem = sum(premiums)/len(premiums) if premiums else 0
    avg_to = sum(turnovers)/len(turnovers) if turnovers else 0
    avg_vol = sum(volumes)/len(volumes) if volumes else 0

    return n, round(avg_p, 2), round(avg_prem, 2), round(avg_to, 2), round(avg_vol, 2)

print(f"\n{'板块':<12} {'数量':>5} {'均价':>8} {'平均溢价率':>10} {'均换手率':>8} {'均成交额万':>10}")
print("-" * 65)

boards = ["主板(上海)", "主板(深圳)", "创业板", "科创板", "中小板", "other"]
stats = {}
for board in boards:
    r = stat(board)
    if r and r[0]:
        n, avg_p, avg_prem, avg_to, avg_vol = r
        stats[board] = {"n": n, "avg_price": avg_p, "avg_premium": avg_prem, "avg_turnover": avg_to, "avg_vol": avg_vol}
        print(f"  {board:<10} {n:>5} {avg_p:>8.2f} {avg_prem:>10.2f}% {avg_to:>8.2f}% {avg_vol:>10.2f}")

# ── 时序分析（历史趋势）──────────────────────────────────

records = daily.get("records", [])
print(f"\n\n【历史时序统计】共 {len(records)} 天数据")
print("=" * 70)

if len(records) >= 2:
    # 对比最早和最新
    earliest = records[0]
    latest = records[-1]
    print(f"\n统计周期: {earliest['date']} → {latest['date']} (共{len(records)}天)\n")

    # 涨跌统计（按板块）
    print(f"{'板块':<12} {'期初数量':>8} {'期末数量':>8} {'价格变化':>10} {'溢价率变化':>12}")
    print("-" * 65)

    all_boards = set(list(earliest["board_stats"].keys()) + list(latest["board_stats"].keys()))
    for board in sorted(all_boards):
        e = earliest["board_stats"].get(board, {})
        l = latest["board_stats"].get(board, {})
        e_cnt = e.get("count", 0)
        l_cnt = l.get("count", 0)
        e_p = e.get("avg_price", 0)
        l_p = l.get("avg_price", 0)
        e_prem = e.get("avg_premium", 0)
        l_prem = l.get("avg_premium", 0)

        p_chg = l_p - e_p
        prem_chg = l_prem - e_prem

        print(f"  {board:<10} {e_cnt:>8} {l_cnt:>8} {p_chg:>+10.2f} {prem_chg:>+12.2f}%")

    # 算每日变化趋势（如果有连续数据）
    print("\n\n【连续数据趋势】（每日变化）")
    if len(records) >= 5:
        print(f"{'日期':<12} {'创业板均溢价':>12} {'科创板均溢价':>12} {'主板均溢价':>12} {'创业板均价格':>12} {'科创板均价格':>12}")
        print("-" * 80)
        for rec in records[-10:]:  # 最近10天
            bs = rec.get("board_stats", {})
            cy = bs.get("创业板", {}).get("avg_premium", 0)
            kc = bs.get("科创板", {}).get("avg_premium", 0)
            zy = bs.get("主板(上海)", {}).get("avg_premium", 0)
            cy_p = bs.get("创业板", {}).get("avg_price", 0)
            kc_p = bs.get("科创板", {}).get("avg_price", 0)
            print(f"  {rec['date']:<12} {cy:>12.2f}% {kc:>12.2f}% {zy:>12.2f}% {cy_p:>12.2f} {kc_p:>12.2f}")
else:
    print("⚠️ 时序数据不足（需要连续运行几天后才能分析趋势）")
    print("   当前仅有1天数据，无法做趋势分析")
    print("   建议将 jisilu_cb_enriched.py 加入每日 cron 任务")

# ── 综合结论 ─────────────────────────────────────────────

print("\n" + "=" * 70)
print("【综合分析结论】")
print("=" * 70)

def welch_t(v1, v2):
    n1, n2 = len(v1), len(v2)
    if n1 < 3 or n2 < 3:
        return 0, 1
    m1, m2 = sum(v1)/n1, sum(v2)/n2
    var1 = sum((x-m1)**2 for x in v1)/(n1-1) if n1 > 1 else 0
    var2 = sum((x-m2)**2 for x in v2)/(n2-1) if n2 > 1 else 0
    se = math.sqrt(var1/n1 + var2/n2)
    t = (m1 - m2)/se if se > 0 else 0
    num = (var1/n1 + var2/n2)**2
    denom = (var1/n1)**2/(n1-1) + (var2/n2)**2/(n2-1) if n1>1 and n2>1 else 0.0001
    df = max(1, num/denom)
    z = abs(t)
    p = 2 * (1 - 0.5 * (1 + z/math.sqrt(z**2+1))**2) if z < 30 else 0
    p = max(0.0001, min(0.9999, p))
    return round(t, 3), round(p, 5)

# 重点比：创业板 vs 主板(上海)
def get_board_bonds(board):
    return [b for b in bonds if b.get("所属板块") == board]

def board_features(board, field):
    bs = get_board_bonds(board)
    vals = [float(b[field]) for b in bs if b.get(field) and str(b[field]).replace('.','').replace('-','').isdigit()]
    return vals

print("\n▶ 创业板 vs 主板(上海) 对比:\n")

for field, label in [("现价", "价格"), ("溢价率%", "溢价率"), ("换手率%", "换手率"), ("成交额(万)", "成交额")]:
    v1 = board_features("创业板", field)
    v2 = board_features("主板(上海)", field)
    if len(v1) < 3 or len(v2) < 3:
        continue
    t, p = welch_t(v1, v2)
    avg1 = sum(v1)/len(v1)
    avg2 = sum(v2)/len(v2)
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    print(f"  {label}: 创业板均值={avg1:.2f} vs 主板均值={avg2:.2f}, 差值={avg1-avg2:+.2f}, t={t}, p={p:.4f} {sig}")

print("\n▶ 科创板 vs 主板(上海) 对比:\n")
for field, label in [("现价", "价格"), ("溢价率%", "溢价率"), ("换手率%", "换手率"), ("成交额(万)", "成交额")]:
    v1 = board_features("科创板", field)
    v2 = board_features("主板(上海)", field)
    if len(v1) < 3 or len(v2) < 3:
        continue
    t, p = welch_t(v1, v2)
    avg1 = sum(v1)/len(v1)
    avg2 = sum(v2)/len(v2)
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    print(f"  {label}: 科创板均值={avg1:.2f} vs 主板均值={avg2:.2f}, 差值={avg1-avg2:+.2f}, t={t}, p={p:.4f} {sig}")

print("\n注: * p<0.05 显著, ** p<0.01 高度显著, *** p<0.001 极显著")
print("=" * 70)