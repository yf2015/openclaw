#!/usr/bin/env python3
"""
可转债 momentum 策略筛选（动态周计算版）
条件:
  - 价格区间: 150~250元
  - 转债溢价率 < 15%（上周五截面）
  - 剩余规模 < 10亿（详情页curr_iss_amt）
  - 上市时间 > 6个月
  - 上周成交额 > 10亿
  - (上周成交额 / 上上周成交额) > 1.5
  - 排除已公告强赎的债券（以redeem_status字段为准）
执行时间: 每周一凌晨3点
"""

import requests
import re
import json
import datetime as dt
from urllib.request import Request, urlopen

# ==== 配置 ====
KBZW_SESSION = 't8ulaqqcm77mpmkrcnltr74di2'
KBZW_USER_LOGIN = '7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR'
DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488'

# ==== 动态计算周区间 ====
def get_week_dates():
    today = dt.datetime.now()
    weekday = today.weekday()  # 0=周一
    last_monday = today - dt.timedelta(days=weekday + 7)
    last_sunday = last_monday + dt.timedelta(days=6)
    prev_monday = last_monday - dt.timedelta(days=7)
    prev_sunday = last_monday - dt.timedelta(days=1)
    return {
        'this_week_start': last_monday.strftime('%Y-%m-%d'),
        'this_week_end': last_sunday.strftime('%Y-%m-%d'),
        'prev_week_start': prev_monday.strftime('%Y-%m-%d'),
        'prev_week_end': prev_sunday.strftime('%Y-%m-%d'),
    }

def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except:
        return default

# ==== 核心：获取债券详情（每只必查） ====
def get_bond_detail(bid, session):
    """
    访问 https://www.jisilu.cn/data/convert_bond_detail/{bid}
    返回所有关键字段
    """
    url = f'https://www.jisilu.cn/data/convert_bond_detail/{bid}'
    r = session.get(url, timeout=10)
    html = r.text

    result = {
        'bid': bid,
        'name': None,
        'html': html,
        'curr_iss_amt': None,     # 剩余规模(亿)
        'list_dt': None,           # 上市日期
        'convert_price': None,     # 转股价格
        'force_redeem_price': None, # 强赎触发价
        'redeem_status': None,      # 强赎状态（唯一判断依据）
    }

    # 名称
    m = re.search(r'<title>([^<]+)</title>', html)
    if m:
        result['name'] = m.group(1).split('-')[0].strip()

    # 剩余规模
    m = re.search(r'id="curr_iss_amt"[^>]*>(\d+\.?\d*)', html)
    if m:
        result['curr_iss_amt'] = float(m.group(1))

    # 上市日期
    m = re.search(r'id="list_dt"[^>]*>(\d{4}-\d{2}-\d{2})', html)
    if m:
        result['list_dt'] = m.group(1)

    # 转股价格
    m = re.search(r'id="convert_price"[^>]*>(\d+\.?\d*)', html)
    if m:
        result['convert_price'] = float(m.group(1))

    # 强赎触发价
    m = re.search(r'id="force_redeem_price"[^>]*title="[\d.]+\s*×\s*\d+%?"[^>]*>\s*([\d.]+)', html)
    if m:
        result['force_redeem_price'] = float(m.group(1))

    # 强赎状态（最关键！）
    m = re.search(r'id="redeem_status"[^>]*>(.*?)</td>', html, re.DOTALL)
    if m:
        result['redeem_status'] = m.group(1).strip()

    return result

def is_redeem_announced(detail):
    """
    判断是否已公告强赎（唯一判断依据：redeem_status）
    返回 True = 已公告强赎（排除）
    返回 False = 未公告强赎（保留）
    """
    status = detail.get('redeem_status', '') or ''
    # "已公告 YYYY-MM-DD 强赎" → 排除
    if '已公告' in status and '强赎' in status:
        return True
    return False

def get_klines(bid, session):
    r = session.get(f'https://www.jisilu.cn/data/cbnew/detail_hist/{bid}?display=day', timeout=10)
    rows = r.json().get('rows', [])
    klines = []
    for row in rows:
        cell = row.get('cell', {})
        td = cell.get('last_chg_dt', '')
        if td:
            klines.append({
                'date': td,
                'price': float(cell.get('price', 0)),
                'volume': float(cell.get('volume', 0))
            })
    klines.sort(key=lambda x: x['date'])
    return klines

def weekly_vol(klines, start, end):
    return sum(k['volume'] for k in klines if start <= k['date'] <= end)

def dingtalk_send(msg):
    safe_msg = msg.replace('|', '｜')
    payload = json.dumps({
        'msgtype': 'markdown',
        'markdown': {'title': '可转债策略播报', 'text': safe_msg},
        'at': {'isAtAll': False}
    })
    req = Request(
        DINGTALK_WEBHOOK,
        data=payload.encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        resp = urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as e:
        return {'error': str(e)}

def analyze_bond(c, weeks, session):
    bid = c['bid']
    name = c['detail']['name']
    price = c['price']
    premium = c['premium']
    scale = c['scale']
    ratio = c['ratio']
    detail = c['detail']

    klines = get_klines(bid, session)
    risk_items = []
    signals = []

    # 溢价风险
    if premium < 0:
        risk_items.append(f'负溢价 {premium:.1f}%，溢价可能继续压缩或反转')
    elif premium > 10:
        risk_items.append(f'溢价率偏高 {premium:.1f}%，正股上涨传导效率低')

    # 价格风险
    if price > 220:
        risk_items.append(f'价格偏高 {price:.1f}元，债底保护极弱，双低值{price+premium:.0f}>240')
    elif price > 200:
        risk_items.append(f'价格偏高 {price:.1f}元，双低值{price+premium:.0f}')

    # 规模风险
    if scale < 3:
        risk_items.append(f'剩余规模仅 {scale:.1f}亿，易被炒作，波动剧烈')
    elif scale > 8:
        risk_items.append(f'规模偏大 {scale:.1f}亿，弹性一般')

    # 量比分析
    recent5 = klines[-5:] if len(klines) >= 5 else klines
    prev5 = klines[-10:-5] if len(klines) >= 10 else (klines[:-5] if len(klines) > 5 else [])
    if recent5 and prev5:
        avg5 = sum(k['volume'] for k in recent5) / len(recent5)
        avg_prev5 = sum(k['volume'] for k in prev5) / len(prev5)
        if avg_prev5 > 0 and avg5 / avg_prev5 > 2:
            signals.append(f'近5日均量较前5日放大 {avg5/avg_prev5:.1f}倍')

    # 近5日涨幅
    if len(recent5) >= 2:
        chg = (recent5[-1]['price'] - recent5[0]['price']) / recent5[0]['price'] * 100
        if chg > 15:
            risk_items.append(f'近5日涨幅 {chg:.1f}%，短期可能回调')
        elif chg > 5:
            signals.append(f'近5日涨幅 {chg:.1f}%')

    # 今日量比
    if klines and prev5:
        last_vol = klines[-1]['volume']
        avg_prev = sum(k['volume'] for k in prev5) / len(prev5)
        if avg_prev > 0 and last_vol / avg_prev > 5:
            signals.append(f'今日成交量放大 {last_vol/avg_prev:.1f}倍')

    # 强赎状态（以redeem_status为准）
    status = detail.get('redeem_status', '') or ''
    if '已公告' in status and '强赎' in status:
        risk_items.append(f'🔴 已公告强赎！状态：{status}')
    elif '暂不强赎' in status or '不行使' in status:
        m = re.search(r'(\d{4}-\d{2}-\d{2})', status)
        restart = m.group(1) if m else '未知'
        risk_items.append(f'🔒 公司宣布暂不强赎，{restart}重新计数')
    elif '/' in status:
        m = re.search(r'(\d+)/(\d+)', status)
        if m:
            cur = int(m.group(1))
            tot = int(m.group(2))
            pct = cur / tot * 100
            if pct >= 70:
                risk_items.append(f'⚠️ 强赎计数 {cur}/{tot}，已过{pct:.0f}%，接近触发')

    # 正股与强赎触发价
    conv_price = detail.get('convert_price')
    force_price = detail.get('force_redeem_price')
    if conv_price and force_price:
        stock_est = price * 100 / conv_price if conv_price > 0 else 0
        above = stock_est - force_price
        if above > 0:
            signals.append(f'正股已超出强赎触发价 {above:.2f}元')
        else:
            signals.append(f'距强赎触发价还差 {abs(above):.2f}元')

    return risk_items, signals

def build_report(results, redeemed, weeks, today_str, session):
    if not results:
        return f"## 📊 可转债策略播报\n**{today_str}**\n\n未筛选到符合条件的转债"

    msg = f"## 📊 可转债策略播报\n**{today_str}**\n"
    msg += f"**上周范围:** {weeks['this_week_start']} ~ {weeks['this_week_end']}\n"
    msg += f"**筛选条件:** 价格150~250 | 溢价&lt;15% | 规模&lt;10亿 | 周成交额比&gt;1.5 | 排除已公告强赎\n\n"

    for i, c in enumerate(results, 1):
        name = c['detail']['name']
        bid = c['bid']
        price = c['price']
        premium = c['premium']
        scale = c['scale']
        ratio = c['ratio']

        risks, sigs = analyze_bond(c, weeks, session)

        emoji = '🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i <= 5 else '📌'

        msg += f"### {emoji} {name}（{bid}）\n"
        msg += f"| 指标 | 值 |\n|---|---|\n"
        msg += f"| 现价 | **{price:.2f}元** |\n"
        msg += f"| 溢价率 | {premium:.2f}% |\n"
        msg += f"| 剩余规模 | {scale:.1f}亿 |\n"
        msg += f"| 周成交额比 | **{ratio:.2f}x** |\n"
        msg += f"| 上周成交额 | {c.get('this_wk', 0)/10000:.1f}亿 |\n"

        if sigs:
            msg += f"\n**信号:**\n"
            for sig in sigs:
                msg += f"- {sig}\n"

        if risks:
            msg += f"\n**风险项:**\n"
            for r in risks:
                msg += f"- {r}\n"
        else:
            msg += f"\n**风险项:** 无明显风险\n"

        if price > 230:
            advice = "⚠️ 价格极高，债底保护极弱，谨慎"
        elif price > 220:
            advice = "⚠️ 价格偏高，建议回调后再考虑"
        elif premium < 0:
            advice = "⚠️ 负溢价，注意溢价收敛风险"
        elif ratio > 3:
            advice = "📈 资金动能强劲，重点关注"
        else:
            advice = "✅ 条件均衡，择机关注"
        msg += f"\n**操作建议:** {advice}\n\n---\n\n"

    if redeemed:
        msg += f"\n\n🚫 **已排除（已公告强赎）: {len(redeemed)} 只**\n"
        for c in redeemed[:10]:
            status = c['detail'].get('redeem_status', '')
            nm = c['detail']['name']
            msg += f"- {nm}（{c['bid']}） - {status}\n"

    return msg

def main():
    weeks = get_week_dates()
    today_str = dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f'[{today_str}] 可转债策略开始执行...')
    print(f'  上周: {weeks["this_week_start"]} ~ {weeks["this_week_end"]}')
    print(f'  上上周: {weeks["prev_week_start"]} ~ {weeks["prev_week_end"]}')

    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.jisilu.cn/'})
    session.cookies.set('kbzw__Session', KBZW_SESSION, domain='www.jisilu.cn', path='/')
    session.cookies.set('kbzw__user_login', KBZW_USER_LOGIN, domain='www.jisilu.cn', path='/')

    # 获取全量列表
    r = session.get('https://www.jisilu.cn/webapi/cb/list/', timeout=10)
    bonds = r.json().get('data', [])
    print(f'  全量转债: {len(bonds)} 只')

    today_dt = dt.datetime.now()

    # ========== 第一层粗筛 ==========
    # 条件：价格150-250 + 溢价<15%
    # 对每只候选债券单独请求详情页获取真实规模和上市日期
    candidates = []
    for b in bonds:
        bid = b['bond_id']
        price = safe_float(b.get('price'))
        premium = safe_float(b.get('premium_rt'))

        if not (150 <= price <= 250):
            continue
        if premium >= 15:
            continue

        # 每只债券必查详情页
        detail = get_bond_detail(bid, session)

        scale = detail.get('curr_iss_amt')
        if scale is None:
            scale = safe_float(b.get('convert_amt_ratio'))
        if scale is None or scale >= 10:
            continue

        # 上市时间 > 6个月
        list_dt_str = detail.get('list_dt')
        if list_dt_str:
            try:
                list_dt = dt.datetime.strptime(list_dt_str, '%Y-%m-%d')
                months = (today_dt.year - list_dt.year) * 12 + (today_dt.month - list_dt.month)
                if months < 6:
                    continue
            except:
                continue
        else:
            continue

        candidates.append({
            'bid': bid,
            'price': price,
            'premium': premium,
            'scale': scale,
            'detail': detail,
        })

    print(f'  第一层粗筛: {len(candidates)} 只')
    for c in candidates:
        nm = c["detail"]["name"]
        print("    " + nm + "（" + c["bid"] + "）价格:" + str(round(c["price"],2)) + " 溢价:" + str(round(c["premium"],1)) + "% 规模:" + str(c["scale"]) + "亿")

    # ========== 第二层：排除已公告强赎 ==========
    # 唯一判断依据：redeem_status 字段
    redeemed = []
    final = []
    for c in candidates:
        detail = c['detail']
        if is_redeem_announced(detail):
            redeemed.append(c)
        else:
            final.append(c)

    print(f'  排除已公告强赎: {len(redeemed)} 只')
    for c in redeemed:
        print(f'    ❌ {c["detail"]["name"]}（{c["bid"]}） - {c["detail"].get("redeem_status","")}')
    print(f'  剩余候选: {len(final)} 只')

    # ========== 第三层：周成交额比 ==========
    results = []
    for c in final:
        bid = c['bid']
        klines = get_klines(bid, session)
        this_wk = weekly_vol(klines, weeks['this_week_start'], weeks['this_week_end'])
        last_wk = weekly_vol(klines, weeks['prev_week_start'], weeks['prev_week_end'])

        if this_wk < 100000:
            continue
        ratio = this_wk / last_wk if last_wk > 0 else 0
        if ratio <= 1.5:
            continue

        c['this_wk'] = this_wk
        c['last_wk'] = last_wk
        c['ratio'] = ratio
        results.append(c)

    results.sort(key=lambda x: x['ratio'], reverse=True)
    print(f'  最终通过: {len(results)} 只')
    for r in results:
        print(f'    ✅ {r["detail"]["name"]}（{r["bid"]}）比值:{r["ratio"]:.2f}x')

    report = build_report(results, redeemed, weeks, today_str, session)
    print('\n' + '='*60)
    print(report)

    resp = dingtalk_send(report)
    print(f'\n[DingTalk] 发送结果: {resp}')
    return results, redeemed

if __name__ == '__main__':
    main()
