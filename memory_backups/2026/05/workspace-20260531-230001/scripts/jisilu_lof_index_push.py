#!/usr/bin/env python3
"""
指数LOF基金推送 - 每个交易日12:30执行
- 过滤条件：排除 开放申购 / 限额>=1万 / 成交<10万
- 过滤后=0条时推送未命中通知
- 过滤后>0条时推送完整表格（按成交额降序）
"""

import urllib.request, json, datetime as dt, re

KBZW_SESSION = 't8ulaqqcm77mpmkrcnltr74di2'
KBZW_USER_LOGIN = '7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSQ'
DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488'


def fetch_index_lof():
    cookie = f'kbzw__Session={KBZW_SESSION}; kbzw__user_login={KBZW_USER_LOGIN}'
    url = 'https://www.jisilu.cn/data/lof/index_lof_list/?rp=5000&page=1&sort=turnover_rate&order=desc'
    req = urllib.request.Request(url, headers={
        'Cookie': cookie,
        'User-Agent': 'Mozilla/5.0',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://www.jisilu.cn/data/lof/'
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read()).get('rows', [])


def apply_gt_1w(status):
    m = re.search(r'限(\d+)万', status)
    return m and int(m.group(1)) >= 1


def should_exclude(r):
    c = r['cell']
    s = c.get('apply_status', '')
    amt = float(c.get('amount', 0) or 0)
    if s == '开放申购':
        return True
    if apply_gt_1w(s):
        return True
    if amt < 10:
        return True
    return False


def build_message(rows, today_str):
    if not rows:
        return (f"## 📊 指数LOF基金\n\n**{today_str}**\n\n"
                f"❌ 今日无符合条件的LOF基金\n\n"
                f"（过滤条件：排除开放申购/限额>=1万/成交<10万）", True)

    lines = [
        f"## 📊 指数LOF基金（按成交额排序）",
        f"**{today_str}**  共{len(rows)}只（已过滤开放申购/限额>=1万/成交<10万）",
        "",
        "| 基金 | 代码 | 状态 | 成交(万) | 溢价率 |",
        "|------|------|------|---------|--------|"
    ]
    for r in rows:
        c = r['cell']
        amt = float(c.get('amount', 0) or 0)
        disc = c.get('discount_rt', '-') or '-'
        lines.append(f"| {c['fund_nm']} | {c['fund_id']} | {c['apply_status']} | {amt:.0f} | {disc} |")

    return '\n'.join(lines), False


def send_dingtalk(text, title):
    payload = {'msgtype': 'markdown', 'markdown': {'title': title, 'text': text}}
    req = urllib.request.Request(
        DINGTALK_WEBHOOK,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


if __name__ == '__main__':
    today_str = dt.datetime.now().strftime('%Y年%m月%d日')
    title = f'📊 指数LOF {today_str}'
    print(f'[{today_str}] 指数LOF推送开始...')

    rows = fetch_index_lof()
    filtered = [r for r in rows if not should_exclude(r)]
    filtered.sort(key=lambda x: float(x['cell'].get('amount', 0) or 0), reverse=True)

    print(f'  总数据: {len(rows)} 条, 过滤后: {len(filtered)} 条')

    text, is_empty = build_message(filtered, today_str)
    result = send_dingtalk(text, title)
    print(f'  推送结果: {result}')
    print(f'[{today_str}] 执行完成')
