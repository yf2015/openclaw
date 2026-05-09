#!/usr/bin/env python3
"""
集思录不强赎公告推送
每天 08:30 检索近7天集思录"不赎回"相关公告，推送完整标题
优化：只检查 price 150-300 区间且 redeem_status 计数≥10 的 bond
"""

import requests, re, json, datetime as dt, time
from urllib.request import Request, urlopen

KBZW_SESSION = 't8ulaqqcm77mpmkrcnltr74di2'
KBZW_USER_LOGIN = '7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR'
DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.jisilu.cn/',
}

CACHE_FILE = '/root/.openclaw/workspace/jisilu_cb_data.json'
CACHE_MAX_AGE_HOURS = 6

def make_session():
    ss = requests.Session()
    ss.headers.update(HEADERS)
    ss.cookies.set('kbzw__Session', KBZW_SESSION, domain='www.jisilu.cn', path='/')
    ss.cookies.set('kbzw__user_login', KBZW_USER_LOGIN, domain='www.jisilu.cn', path='/')
    return ss

def get_cached_bonds():
    try:
        mtime = dt.datetime.fromtimestamp(__import__('os').path.getmtime(CACHE_FILE))
        age = (dt.datetime.now() - mtime).total_seconds() / 3600
        if age < CACHE_MAX_AGE_HOURS:
            with open(CACHE_FILE) as f:
                d = json.load(f)
            print(f'  [cache] {len(d["bonds"])} bonds, age {age:.1f}h')
            return d['bonds'], d['name_map']
    except Exception:
        pass
    return None, None

def save_bonds_cache(bonds, name_map):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({'bonds': bonds, 'name_map': name_map}, f)
    except Exception:
        pass

def extract_announcements(html):
    rows = re.findall(
        r'<div class="grid-row">\s*'
        r'<div class="grid-col-9"><a[^>]+href="([^"]+)"[^>]*>([^<]+)</a></div>\s*'
        r'<div class="grid-col-3">(\d{4}-\d{2}-\d{2})</div>\s*</div>',
        html
    )
    return [{"url": u, "title": t.strip(), "date": d} for u, t, d in rows]

def is_no_redeem_decision(title):
    if "不提前赎回" not in title and "不赎回" not in title:
        return False
    exclude = ["提示性公告", "核查意见", "受托管理", "预计满足", "可能满足", "预计触发",
               "发行结果", "发行公告", "付息", "评级", "募集说明书", "路演"]
    return not any(k in title for k in exclude)

def get_redeem_count(ss, bid):
    try:
        r = ss.get(f'https://www.jisilu.cn/data/convert_bond_detail/{bid}', timeout=8)
        m = re.search(r'id="redeem_status"[^>]*>(.*?)</td>', r.text, re.DOTALL)
        if not m:
            return 0
        status = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        cnt_m = re.search(r'(\d+)\s*/\s*(\d+)', status)
        return int(cnt_m.group(1)) if cnt_m else 0
    except Exception:
        return 0

def dingtalk_send(msg):
    payload = json.dumps({
        'msgtype': 'markdown',
        'markdown': {'title': '集思录不强赎公告', 'text': msg},
        'at': {'isAtAll': False}
    })
    req = Request(DINGTALK_WEBHOOK, data=payload.encode('utf-8'),
                  headers={'Content-Type': 'application/json'})
    try:
        resp = urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as e:
        return {'error': str(e)}

def main():
    now = dt.datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')
    print(f'[{now_str}] 集思录不强赎公告检索开始...')

    ss = make_session()

    bonds, name_map = get_cached_bonds()
    if bonds is None:
        print('  [fetch] 获取转债列表...')
        bonds = []
        seen_ids = set()
        for page in range(1, 15):
            r = ss.get(f'https://www.jisilu.cn/webapi/cb/list/?page={page}&page_size=500', timeout=10)
            data = r.json()
            chunk = data.get('data', [])
            if not chunk:
                break
            for b in chunk:
                if b['bond_id'] not in seen_ids:
                    seen_ids.add(b['bond_id'])
                    bonds.append(b)
            print(f'  page {page}: +{len(chunk)}, total {len(bonds)}')
            if len(chunk) < 30:
                break

        print('  [fetch] 提取转债名称...')
        name_map = {}
        for i, b in enumerate(bonds[:50]):
            if i % 10 == 0:
                print(f'    {i}/50')
            try:
                r2 = ss.get(f'https://www.jisilu.cn/data/convert_bond_detail/{b["bond_id"]}', timeout=5)
                m = re.search(r'<title>([^<]+)</title>', r2.text)
                if m:
                    name_map[b['bond_id']] = m.group(1).split('-')[0].strip()
            except Exception:
                pass

        save_bonds_cache(bonds, name_map)

    print(f'  转债总数: {len(bonds)}, 已有名称: {len(name_map)}')

    week_ago = (dt.datetime.now() - dt.timedelta(days=7)).strftime('%Y-%m-%d')
    results = []

    # 策略：price 150-300 的活跃 bond 才可能发布不强赎公告
    candidate_bonds = [b for b in bonds if 150 <= b.get('price', 0) <= 300]
    print(f'  候选 bond（价格150-300）: {len(candidate_bonds)} 只')

    scanned = 0
    for b in candidate_bonds:
        bid = b['bond_id']
        cnt = get_redeem_count(ss, bid)
        scanned += 1
        if scanned % 20 == 0:
            print(f'  已扫描: {scanned}/{len(candidate_bonds)}')
        if cnt < 10:
            continue
        try:
            r = ss.get(f'https://www.jisilu.cn/data/convert_bond_detail/{bid}', timeout=8)
            annos = extract_announcements(r.text)
            for a in annos:
                if a['date'] < week_ago:
                    continue
                if is_no_redeem_decision(a['title']):
                    results.append({
                        'bond_nm': name_map.get(bid, '-'),
                        'bond_id': bid,
                        'count': cnt,
                        'date': a['date'],
                        'title': a['title'],
                        'url': f"https://www.jisilu.cn{a['url']}",
                    })
                    print(f'    命中: {name_map.get(bid,bid)} [{cnt}/15] | {a["date"]} | {a["title"][:50]}')
        except Exception:
            continue

    print(f'  扫描完成: {scanned} 只, 命中 {len(results)} 条')

    if not results:
        msg = f"## 集思录不强赎公告\n{now_str}  近7天无不强赎公告"
    else:
        lines = [f"## 集思录不强赎公告"]
        for r in sorted(results, key=lambda x: x['date'], reverse=True):
            lines.append(f"{r['date']}  {r['title']}")
        msg = '\n'.join(lines)

    print('=' * 60)
    print(msg)
    resp = dingtalk_send(msg)
    print(f'[DingTalk] {resp}')
    return results

if __name__ == '__main__':
    main()