#!/usr/bin/env python3
"""
集思录提前赎回公告推送
- POST https://www.jisilu.cn/webapi/cb/announcement_list/
- 标题同时含'赎回'+'公告'的才计入
- 相同转债合并，正股+代码+名称
"""

import requests, re, datetime as dt
from collections import defaultdict

KBZW_SESSION = 't8ulaqqcm77mpmkrcnltr74di2'
KBZW_USER_LOGIN = '7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR'
DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488'

def fetch_announcements():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.jisilu.cn/',
        'Content-Type': 'application/x-www-form-urlencoded'
    })
    session.cookies.set('kbzw__Session', KBZW_SESSION, domain='www.jisilu.cn', path='/')
    session.cookies.set('kbzw__user_login', KBZW_USER_LOGIN, domain='www.jisilu.cn', path='/')

    payload = 'code=&title=&tp%5B0%5D=Y&important=false&type='
    r = session.post('https://www.jisilu.cn/webapi/cb/announcement_list/', data=payload, timeout=10)
    return r.json().get('data', [])

def filter_redeem(items):
    """同时含'提前赎回'和'公告'"""
    return [x for x in items if '提前赎回' in x.get('anno_title', '') and '公告' in x.get('anno_title', '')]

def merge_bonds(hits):
    """按转债ID分组，保留最新一条"""
    groups = defaultdict(list)
    for h in hits:
        groups[h['bond_id']].append(h)
    result = []
    for bid, group in groups.items():
        # 取最新一条
        latest = max(group, key=lambda x: x['anno_dt'])
        result.append({
            'bond_id': bid,
            'bond_nm': latest['bond_nm'],
            'stock_nm': latest['stock_nm'],
            'anno_dt': latest['anno_dt'],
            'anno_title': latest['anno_title'],
            'anno_url': latest['anno_url'],
        })
    return result

def format_redeem(bonds, today_str):
    if not bonds:
        return f"## 🔔 提前赎回公告\n\n**{today_str}** 今日无提前赎回公告"

    lines = [f"## 🔔 提前赎回公告", f"**{today_str}**", ""]
    for b in bonds:
        lines.append(f"### 🔴 {b['bond_nm']}({b['bond_id']}) {b['stock_nm']}")
        lines.append(f"{b['anno_dt']} [{b['anno_title']}]({b['anno_url']})")
        lines.append("")
    return '\n'.join(lines)

def send_dingtalk(text, title):
    payload = {
        'msgtype': 'markdown',
        'markdown': {'title': title, 'text': text}
    }
    resp = requests.post(DINGTALK_WEBHOOK, json=payload, timeout=10)
    return resp.json()

if __name__ == '__main__':
    today_str = dt.datetime.now().strftime('%Y年%m月%d日')
    print(f'[{today_str}] 提前赎回公告开始...')

    items = fetch_announcements()
    hits = filter_redeem(items)
    merged = merge_bonds(hits)
    print(f'  总公告: {len(items)} 条, 含赎回+公告: {len(hits)} 条, 合并后: {len(merged)} 只')

    msg = format_redeem(merged, today_str)
    result = send_dingtalk(msg, f'🔔 提前赎回公告 {today_str}')
    print(f'  推送结果: {result}')
    print(f'[{today_str}] 执行完成')
