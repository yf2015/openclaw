#!/usr/bin/env python3
"""
集思录投资日历推送
- 每个A股交易日9:00获取当日日历
- 格式化后推送到钉钉
"""

import requests, re, datetime as dt

KBZW_SESSION = 't8ulaqqcm77mpmkrcnltr74di2'
KBZW_USER_LOGIN = '7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSQ'
DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488'

def fetch_calendar():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.jisilu.cn/'})
    session.cookies.set('kbzw__Session', KBZW_SESSION, domain='www.jisilu.cn', path='/')
    session.cookies.set('kbzw__user_login', KBZW_USER_LOGIN, domain='www.jisilu.cn', path='/')

    today = dt.datetime.now()
    start = int(dt.datetime(today.year, today.month, today.day, 0, 0, 0).timestamp())
    end = int(dt.datetime(today.year, today.month, today.day, 23, 59, 59).timestamp())
    url = f'https://www.jisilu.cn/data/calendar/get_calendar_data/?qtype=CNV&start={start}&end={end}&_={int(dt.datetime.now().timestamp()*1000)}'

    r = session.get(url, timeout=10)
    return r.json()

def format_calendar(events, today_str):
    if not events:
        return f"## 📅 今日投资日历\n\n**{today_str}** 今日无转债相关事件"

    lines = [f"## 📅 今日投资日历"]
    lines.append(f"**日期**: {today_str}")
    lines.append(f"**事件数**: {len(events)}")
    lines.append("")

    for e in events:
        title = e['title']
        desc = re.sub('<[^>]+>', ' ', e.get('description', '')).strip().replace('\r\n', ' | ')
        emoji = '🔴' if '最后交易日' in title else ('⚠️' if '赎回' in title else '📌')
        lines.append(f"{emoji} **{title}**")
        lines.append(f"   代码: `{e['code']}`")
        for part in desc.split('|'):
            part = part.strip()
            if part:
                lines.append(f"   {part}")
        lines.append("")

    return '\n'.join(lines)

def send_dingtalk(text):
    payload = {
        'msgtype': 'markdown',
        'markdown': {
            'title': f'📅 今日投资日历',
            'text': text
        }
    }
    resp = requests.post(DINGTALK_WEBHOOK, json=payload, timeout=10)
    return resp.json()

if __name__ == '__main__':
    today_str = dt.datetime.now().strftime('%Y年%m月%d日')
    print(f'[{today_str}] 集思录日历开始...')

    events = fetch_calendar()
    print(f'  今日事件: {len(events)} 条')

    msg = format_calendar(events, today_str)
    result = send_dingtalk(msg)
    print(f'  推送结果: {result}')
    print(f'[{today_str}] 执行完成')
