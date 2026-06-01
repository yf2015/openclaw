#!/usr/bin/env python3
"""
补数据脚本：重跑 05-25～06-01 每个交易日的 V1+V2 信号并写入 log
用于补全 cb_noredeem_*.log 文件，修复回测数据链

注意：用当天集思录最新数据作为"历史信号"的近似（转债详情本身不随历史变化）
"""
import sys, datetime as dt
sys.path.insert(0, __file__.rsplit('/', 1)[0])

import cb_noredeem_strategy_v2 as strat

TRADING_DAYS = [
    dt.date(2026, 5, 25),
    dt.date(2026, 5, 26),
    dt.date(2026, 5, 27),
    dt.date(2026, 5, 28),
    dt.date(2026, 5, 29),
    dt.date(2026, 6,  1),
]
# 每个交易日跑两个时间点
TIME_SLOTS = [(9, 15), (14, 5)]

def main():
    total = len(TRADING_DAYS) * len(TIME_SLOTS)
    print(f'补数据范围：{TRADING_DAYS[0]} ~ {TRADING_DAYS[-1]}，共 {len(TRADING_DAYS)} 天 × {len(TIME_SLOTS)} 个时间点 = {total} 次')

    for date in TRADING_DAYS:
        for hour, minute in TIME_SLOTS:
            now_dt = dt.datetime(date.year, date.month, date.day, hour, minute)
            ts = now_dt.strftime('%Y-%m-%d %H:%M')
            print(f'\n>>> 正在补跑: {ts} ...', flush=True)
            try:
                result = strat.main(now_dt=now_dt)
                v1 = [r['name'] for r in result.get('v1', [])]
                v2 = [r['name'] for r in result.get('v2', [])]
                print(f'    V1 top2: {v1[:2]}')
                print(f'    V2 top2: {v2[:2]}')
            except Exception as e:
                print(f'    ⚠️ 异常: {e}', flush=True)

    print('\n✅ 补数据完成')

if __name__ == '__main__':
    main()