#!/usr/bin/env python3
"""
B型策略：即将触发强赎，博弈不强赎
- redeem_status含X/Y计数(非暂不强赎) + 溢价<2% + 正股超触发价
- 排除已公告强赎
钉钉格式: 标准markdown表格
"""

import requests, re, json, datetime as dt
from urllib.request import Request, urlopen

KBZW_SESSION = 't8ulaqqcm77mpmkrcnltr74di2'
KBZW_USER_LOGIN = '7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR'
DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488'


def fmt(v, d=2):
    try:
        return str(round(float(v), d))
    except:
        return '-'


def dingtalk_send(msg):
    payload = json.dumps({
        'msgtype': 'markdown',
        'markdown': {'title': 'B型不强赎博弈', 'text': msg},
        'at': {'isAtAll': False}
    })
    req = Request(DINGTALK_WEBHOOK,
                  data=payload.encode('utf-8'),
                  headers={'Content-Type': 'application/json'})
    try:
        resp = urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as e:
        return {'error': str(e)}


def get_detail(bid, session):
    url = 'https://www.jisilu.cn/data/convert_bond_detail/' + bid
    r = session.get(url, timeout=10)
    html = r.text
    result = {'html': html, 'bid': bid}
    m = re.search(r'<title>([^<]+)</title>', html)
    result['name'] = m.group(1).split('-')[0].strip() if m else bid
    pairs = re.findall(
        r'class="jisilu_title"[^>]*>([^<]+)</td>\s*<td[^>]*class="data_val"[^>]*>([^<]+)<',
        html
    )
    val_map = {k.strip(): v.strip() for k, v in pairs}

    def fv(key):
        raw = val_map.get(key, '')
        try:
            return float(re.search(r'[\d.]+', raw).group())
        except:
            return None

    result['orig_iss_amt'] = fv('发行规模(亿)')
    result['curr_iss_amt'] = fv('剩余规模(亿)')
    result['list_dt'] = val_map.get('上市日', '')
    result['remain_years'] = fv('剩余年限')
    result['convert_price'] = fv('转股价')
    result['force_redeem_price'] = fv('强赎触发价')
    result['redeem_price'] = fv('到期赎回价')
    result['stock_price'] = fv('正股价')
    result['stock_pb'] = fv('正股PB')
    result['stock_pe'] = fv('正股PE')
    result['stock_roe'] = val_map.get('正股ROE', '-')
    result['stock_region'] = val_map.get('地域', '-')
    result['rating'] = val_map.get('主体评级', '-')
    result['bond_rating'] = val_map.get('债券评级', '-')
    result['shareholder_ratio'] = fv('股东配售率')
    result['converted_ratio'] = fv('已转股比例')
    result['stock_nm_raw'] = val_map.get('正股名称', '') or val_map.get('正股', '')

    m = re.search(r'id="redeem_status"[^>]*>(.*?)</td>', html, re.DOTALL)
    raw = m.group(1).strip() if m else ''
    result['redeem_status'] = re.sub(r'<[^>]+>', '', raw).strip()
    return result


def get_list(session):
    r = session.get('https://www.jisilu.cn/webapi/cb/list/', timeout=10)
    return r.json().get('data', [])


def parse_count(status):
    m = re.search(r'(\d+)\s*/\s*(\d+)', status)
    return (int(m.group(1)), int(m.group(2))) if m else None


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except:
        return default


# ── tag functions ──────────────────────────────────────────
def roe_tag(r):
    v = str(r.get('stock_roe') or '-')
    return v + (' ✅' if '-' not in v else ' 🔴')


def scale_tag(r):
    v = r.get('curr_iss_amt') or 0
    return fmt(v) + '亿' + (' ✅' if v <= 3 else (' 🟡' if v <= 7 else ''))


def yrs_tag(r):
    v = r.get('remain_years') or 0
    return fmt(v) + '年' + (' ✅' if v >= 3 else (' ⚠️' if v >= 2 else ' 🔴'))


def sh_tag(r):
    v = r.get('shareholder_ratio') or 0
    return fmt(v) + '%' + (' 🔴极高' if v >= 80 else (' 🟡' if v >= 50 else ''))


def conv_tag(r):
    v = r.get('converted_ratio') or 0
    return fmt(v) + '%' + (' 🔴极低' if v < 30 else (' 🟡' if v < 60 else ''))


def rating_tag(r):
    v = str(r.get('rating') or '-')
    return v + (' ✅' if v == 'AA' else ' 🔴')


def gamble_tag(r):
    c = r['count']
    total = 0
    if c[0] <= 9:
        total += 20
    if '-' not in str(r.get('stock_roe') or '-'):
        total += 20
    if (r.get('premium') or 0) < 2:
        total += 15
    if (r.get('shareholder_ratio') or 0) >= 70:
        total += 15
    if (r.get('remain_years') or 0) >= 2:
        total += 10
    if total >= 65:
        return '⭐⭐⭐⭐⭐'
    elif total >= 45:
        return '⭐⭐⭐⭐'
    elif total >= 25:
        return '⭐⭐⭐'
    else:
        return '⭐⭐'


def gamble_risk(r):
    c = r['count']
    tags = []
    if c[0] >= 13:
        tags.append('接近触发')
    if (r.get('premium') or 0) < 0:
        tags.append('负溢价')
    if '-' in str(r.get('stock_roe') or '-'):
        tags.append('ROE亏')
    return '/'.join(tags) if tags else ''


def st_risk_tag(r):
    parts = []
    nm = str(r.get('stock_nm_raw') or '')
    if nm.startswith('*') or nm.startswith('ST') or 'ST' in nm:
        parts.append('🔴正股ST')
    roe_v = str(r.get('stock_roe') or '')
    try:
        if '-' not in roe_v and float(roe_v) < -10:
            parts.append('🔴ROE极差')
    except:
        pass
    rating_v = str(r.get('rating') or '')
    if rating_v in ('A-', 'BBB', 'BB', 'B', 'CCC', 'CC', 'C'):
        parts.append('🟡评级差')
    return '/'.join(parts) if parts else '✅无异常'


def build_report(results, today_dt):
    now_str = today_dt.strftime('%Y-%m-%d %H:%M')
    msg = '## B型不强赎博弈策略\n'
    msg += '**执行时间:** ' + now_str + '\n'
    msg += '**策略逻辑:** X/Y强赎计数 + 溢价<2% + 正股超触发价\n'

    if not results:
        return msg + '\n今日无符合条件的标的'

    r1 = results[0]
    r2 = results[1] if len(results) > 1 else results[0]
    r3 = results[2] if len(results) > 2 else results[0]
    n1, n2, n3 = r1['name'], r2['name'], r3['name']

    # ── 三债简洁对比 ──
    msg += '\n## 三债对比\n'
    c1, c2, c3 = r1['count'], r2['count'], r3['count']
    cnt1 = str(c1[0]) + '/' + str(c1[1]) + (' 🔴极高风险' if c1[0] >= 14 else '')
    cnt2 = str(c2[0]) + '/' + str(c2[1])
    cnt3 = str(c3[0]) + '/' + str(c3[1])
    a1 = fmt(r1.get('above_trigger'), 1)
    a2 = fmt(r2.get('above_trigger'), 1)
    a3 = fmt(r3.get('above_trigger'), 1)

    msg += '| 维度 | ' + n1 + ' | ' + n2 + ' | ' + n3 + ' |\n'
    msg += '|---|---|---|---|' + '\n'
    msg += '| 风险等级 | ' + cnt1 + ' | ' + cnt2 + ' | ' + cnt3 + ' |\n'
    msg += '| 现价 | ' + fmt(r1.get('price')) + '元 | ' + fmt(r2.get('price')) + '元 | ' + fmt(r3.get('price')) + '元 |\n'
    msg += '| 溢价率 | ' + fmt(r1.get('premium')) + '% | ' + fmt(r2.get('premium')) + '% | ' + fmt(r3.get('premium')) + '% |\n'
    msg += '| 正股超触发 | ' + a1 + '% | ' + a2 + '% | ' + a3 + '% |\n'
    msg += '| 剩余规模 | ' + scale_tag(r1) + ' | ' + scale_tag(r2) + ' | ' + scale_tag(r3) + ' |\n'
    msg += '| 剩余年限 | ' + yrs_tag(r1) + ' | ' + yrs_tag(r2) + ' | ' + yrs_tag(r3) + ' |\n'
    msg += '| 已转股比例 | ' + conv_tag(r1) + ' | ' + conv_tag(r2) + ' | ' + conv_tag(r3) + ' |\n'
    msg += '| 股东配售率 | ' + sh_tag(r1) + ' | ' + sh_tag(r2) + ' | ' + sh_tag(r3) + ' |\n'
    msg += '| 正股ROE | ' + roe_tag(r1) + ' | ' + roe_tag(r2) + ' | ' + roe_tag(r3) + ' |\n'
    msg += '| 主体评级 | ' + rating_tag(r1) + ' | ' + rating_tag(r2) + ' | ' + rating_tag(r3) + ' |\n'
    msg += '| ST/退市风险 | ' + st_risk_tag(r1) + ' | ' + st_risk_tag(r2) + ' | ' + st_risk_tag(r3) + ' |\n'
    msg += '| 博弈价值 | ' + gamble_tag(r1) + ' | ' + gamble_tag(r2) + ' | ' + gamble_tag(r3) + ' |\n'

    # 博弈逻辑
    msg += '\n**博弈逻辑:**\n'
    for r, n in [(r1, n1), (r2, n2), (r3, n3)]:
        c = r['count']
        a = fmt(r.get('above_trigger'), 1)
        sh = fmt(r.get('shareholder_ratio'))
        risk = gamble_risk(r)
        if c[0] >= 13:
            msg += '- **' + n + ':** 计数' + str(c[0]) + '/' + str(c[1]) + '，随时可能公告→停牌风险高；若宣布不强赎→溢价修复空间大'
        else:
            msg += '- **' + n + ':** 正股超触发' + a + '%，股东配售率' + sh + '%，大股东有充足动力拉升+不强赎'
        if risk:
            msg += '（风险:' + risk + '）'
        msg += '\n'

    return msg


def main():
    now = dt.datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')
    print('[' + now_str + '] B型不强赎博弈策略开始...')

    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.jisilu.cn/'})
    session.cookies.set('kbzw__Session', KBZW_SESSION, domain='www.jisilu.cn', path='/')
    session.cookies.set('kbzw__user_login', KBZW_USER_LOGIN, domain='www.jisilu.cn', path='/')

    bonds = get_list(session)
    print('  全量: ' + str(len(bonds)) + ' 只')

    today_dt = dt.datetime.now()
    results = []

    for b in bonds:
        bid = b['bond_id']
        price = safe_float(b.get('price'))
        premium = safe_float(b.get('premium_rt'))

        if not (140 <= price <= 280):
            continue
        if premium >= 2:
            continue

        detail = get_detail(bid, session)
        scale = detail.get('curr_iss_amt')
        status = detail.get('redeem_status', '')

        if not scale or scale >= 10:
            continue

        list_dt = detail.get('list_dt', '')
        if list_dt:
            try:
                ldt = dt.datetime.strptime(list_dt, '%Y-%m-%d')
                months = (today_dt.year - ldt.year) * 12 + (today_dt.month - ldt.month)
                if months < 6:
                    continue
            except:
                pass

        conv_price = detail.get('convert_price')
        force_price = detail.get('force_redeem_price')

        if conv_price and force_price and premium > -100:
            cv = price / (1 + premium / 100)
            stock_est = round(cv / 100 * conv_price, 2)
        else:
            stock_est = None

        above_trigger = None
        if stock_est and force_price and force_price > 0:
            above_trigger = round((stock_est - force_price) / force_price * 100, 2)

        is_no_redeem = '暂不强赎' in status or '不行使' in status
        is_announced = '已公告' in status and '强赎' in status
        cnt = parse_count(status)

        if is_announced:
            continue
        if cnt and not is_no_redeem and above_trigger is not None and above_trigger >= 0:
            results.append({
                'bid': bid,
                'name': detail['name'],
                'price': price,
                'premium': premium,
                'count': cnt,
                'above_trigger': above_trigger,
                'curr_iss_amt': detail.get('curr_iss_amt'),
                'remain_years': detail.get('remain_years'),
                'convert_price': conv_price,
                'force_redeem_price': force_price,
                'redeem_price': detail.get('redeem_price'),
                'stock_price': stock_est,
                'stock_pb': detail.get('stock_pb'),
                'stock_pe': detail.get('stock_pe'),
                'stock_roe': detail.get('stock_roe'),
                'stock_nm_raw': detail.get('stock_nm_raw'),
                'rating': detail.get('rating'),
                'bond_rating': detail.get('bond_rating'),
                'shareholder_ratio': detail.get('shareholder_ratio'),
                'converted_ratio': detail.get('converted_ratio'),
            })
            print('  命中: ' + detail['name'] + '(' + bid + ') ' + str(cnt) + ' 溢价:' + str(round(premium, 2)) + '%')

    results.sort(key=lambda x: x['count'][0] if x['count'] else 0, reverse=True)
    top3 = results[:3]
    print('  最终: ' + str(len(results)) + ' 只，取前' + str(len(top3)))
    report = build_report(top3, today_dt)

    print('')
    print('=' * 60)
    print(report)
    resp = dingtalk_send(report)
    print('')
    print('[DingTalk] ' + str(resp))
    return results


if __name__ == '__main__':
    main()
