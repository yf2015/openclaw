#!/usr/bin/env python3
"""
B型不强赎博弈策略 V2 —— 基于回测规律优化的评分模型
─────────────────────────────────────────────────
V1规律（唯计数排序，问题明显）:
  - 星球13/15排第一 → -13.46%
  - 严牌 8/15排第二 → +16.98%(单日最高)

V2改进方向（从回测数据提炼）:
  1. 负溢价 > 正溢价（负溢价=溢价修复空间大，大股东更愿博弈）
  2. 计数8~12为黄金区间（够触发但未停牌，性价比最高）
  3. 超触发幅度适中（超太多=正股已在高位，大股东没动力了）
  4. 规模小 → 炒作成本低，拉升容易
  5. 高股东配售 → 大股东有充足动力拉升正股+不强赎

评分公式:
  score = premium_score(35) + count_score(25) + trigger_score(20) + scale_score(10) + sh_score(10)
"""

import requests, re, json, datetime as dt
from pathlib import Path
from urllib.request import Request, urlopen

KBZW_SESSION = 't8ulaqqcm77mpmkrcnltr74di2'
KBZW_USER_LOGIN = '7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR'
DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488'


LOG_DIR = Path('/root/.openclaw/workspace/logs')
META_CSV = Path('/home/www/toolbox-api/static/stock/huice/push_metadata.csv')


# ── 统一写入工具（print写文件双写）────────────────────
class DualWriter:
    def __init__(self, fp):
        self.fp = fp
    def write(self, msg):
        print(msg, end='', flush=True)
        self.fp.write(msg)
    def flush(self):
        self.fp.flush()

def make_writer(now_dt):
    ts = now_dt.strftime('%Y%m%d_%H%M')
    log_path = LOG_DIR / f'cb_noredeem_{ts}.log'
    fp = open(log_path, 'w', encoding='utf-8')
    return DualWriter(fp), log_path

def append_metadata(date_str, log_name, hit_count, hit_names, errcode):
    """写入 push_metadata.csv（errcode=0才写）"""
    if errcode != 0:
        return
    hit_str = '|'.join(hit_names[:3]) if hit_names else ''
    META_CSV.parent.mkdir(parents=True, exist_ok=True)
    mode = 'a' if META_CSV.exists() else 'w'
    with open(META_CSV, mode, encoding='utf-8') as f:
        f.write(f'{date_str},,{log_name},{hit_count},{hit_str}\n')



def fmt(v, d=2):
    try:
        return str(round(float(v), d))
    except:
        return '-'


def dingtalk_send(msg):
    payload = json.dumps({
        'msgtype': 'markdown',
        'markdown': {'title': 'B型不强赎博弈 V2', 'text': msg},
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


# ═══════════════════════════════════════════════════════════
# V2 评分引擎 —— 核心改进
# ═══════════════════════════════════════════════════════════
def calc_v2_score(r):
    """
    V2综合评分（满分100）
    ─────────────────────
    溢价得分 (35分): 负溢价最优，零溢价次之，正溢价扣分
    计数得分 (25分): 8~12为黄金区间；13+扣分（停牌风险）
    超触发得分 (20分): 适中(10~60%)最优；超太高说明已在高位
    规模得分 (10分): 越小越容易拉升
    股东配比得分 (10分): 越高越有动力拉升
    """
    premium = r.get('premium') or 0
    cnt = r['count']
    at = r.get('above_trigger') or 0
    scale = r.get('curr_iss_amt') or 99
    sh = r.get('shareholder_ratio') or 0

    # ── 溢价得分 ──────────────────────────────
    if premium < 0:
        # 负溢价：溢价越负得分越高（修复空间大）
        # 最多35分，-2%对应35分，0%对应17.5分线性
        prem_score = 17.5 + (-premium) * 17.5 / 2
        prem_score = min(35, prem_score)
    else:
        # 正溢价：溢价越高越差
        prem_score = max(0, 17.5 - premium * 8.75)

    # ── 计数得分 ──────────────────────────────
    c = cnt[0]
    if 8 <= c <= 12:
        count_score = 25  # 黄金区间：够触发但不停牌
    elif c < 8:
        count_score = max(5, 10 + (c - 5) * 3)  # 偏低：5~13分
    else:
        # 13+：接近触发，停牌风险大，扣分
        count_score = max(0, 15 - (c - 12) * 5)  # 13分→10分，14分→5分，15分→0分

    # ── 超触发得分 ────────────────────────────
    # 回测发现：超触发太高（如盈峰100%）实为大股东强赎动机强，
    # 但正股已在高位，风险大；适中(10~60%)性价比最高
    if 10 <= at <= 60:
        trigger_score = 20
    elif at < 10:
        trigger_score = 10 + at * 1.0
    else:
        # 超触发 > 60%，正股已在高位，大股东没动力了
        trigger_score = max(0, 20 - (at - 60) * 0.3)

    # ── 规模得分 ──────────────────────────────
    if scale <= 2:
        scale_score = 10
    elif scale <= 4:
        scale_score = 7
    elif scale <= 7:
        scale_score = 4
    else:
        scale_score = 1

    # ── 股东配比得分 ──────────────────────────
    if sh >= 80:
        sh_score = 10
    elif sh >= 60:
        sh_score = 7
    elif sh >= 40:
        sh_score = 4
    else:
        sh_score = 1

    total = prem_score + count_score + trigger_score + scale_score + sh_score
    r['_v2_score'] = round(total, 1)
    r['_prem_score'] = round(prem_score, 1)
    r['_count_score'] = round(count_score, 1)
    r['_trigger_score'] = round(trigger_score, 1)
    r['_scale_score'] = round(scale_score, 1)
    r['_sh_score'] = round(sh_score, 1)
    return r


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


def build_report_v1(results, today_dt):
    """V1原始报告（唯计数排序）"""
    now_str = today_dt.strftime('%Y-%m-%d %H:%M')
    msg = '## B型不强赎博弈 V1\n'
    msg += '**执行时间:** ' + now_str + '\n'
    msg += '**排序逻辑:** 按X/Y计数降序\n'

    if not results:
        return msg + '\n今日无符合条件的标的'

    r1 = results[0]
    r2 = results[1] if len(results) > 1 else results[0]
    n1, n2 = r1['name'], r2['name']

    msg += '\n## 双债对比\n'
    c1, c2 = r1['count'], r2['count']
    cnt1 = str(c1[0]) + '/' + str(c1[1]) + (' 🔴极高风险' if c1[0] >= 14 else '')
    cnt2 = str(c2[0]) + '/' + str(c2[1])
    a1 = fmt(r1.get('above_trigger'), 1)
    a2 = fmt(r2.get('above_trigger'), 1)

    msg += '| 维度 | ' + n1 + ' | ' + n2 + ' |\n'
    msg += '|---|---|---|' + '\n'
    msg += '| 风险等级 | ' + cnt1 + ' | ' + cnt2 + ' |\n'
    msg += '| 现价 | ' + fmt(r1.get('price')) + '元 | ' + fmt(r2.get('price')) + '元 |\n'
    msg += '| 溢价率 | ' + fmt(r1.get('premium')) + '% | ' + fmt(r2.get('premium')) + '% |\n'
    msg += '| 正股超触发 | ' + a1 + '% | ' + a2 + '% |\n'
    msg += '| 剩余规模 | ' + scale_tag(r1) + ' | ' + scale_tag(r2) + ' |\n'
    msg += '| 正股ROE | ' + roe_tag(r1) + ' | ' + roe_tag(r2) + ' |\n'
    msg += '| 主体评级 | ' + rating_tag(r1) + ' | ' + rating_tag(r2) + ' |\n'
    msg += '| ST/退市风险 | ' + st_risk_tag(r1) + ' | ' + st_risk_tag(r2) + ' |\n'

    return msg


def build_report_v2(results, today_dt):
    """V2增强报告（综合评分）"""
    now_str = today_dt.strftime('%Y-%m-%d %H:%M')
    msg = '## B型不强赎博弈 V2\n'
    msg += '**执行时间:** ' + now_str + '\n'
    msg += '**排序逻辑:** 综合评分（负溢价+黄金计数+适中超触发+小规模+高股东配比）\n'

    if not results:
        return msg + '\n今日无符合条件的标的'

    r1 = results[0]
    r2 = results[1] if len(results) > 1 else results[0]
    n1, n2 = r1['name'], r2['name']

    msg += '\n## V2双债对比\n'
    c1, c2 = r1['count'], r2['count']
    cnt1 = str(c1[0]) + '/' + str(c1[1])
    cnt2 = str(c2[0]) + '/' + str(c2[1])
    a1 = fmt(r1.get('above_trigger'), 1)
    a2 = fmt(r2.get('above_trigger'), 1)

    msg += '| 维度 | ' + n1 + ' | ' + n2 + ' |\n'
    msg += '|---|---|---|' + '\n'
    msg += '| **V2评分** | **' + fmt(r1['_v2_score']) + '** | **' + fmt(r2['_v2_score']) + '** |\n'
    msg += '| 风险等级 | ' + cnt1 + ' | ' + cnt2 + ' |\n'
    msg += '| 溢价得分 | ' + fmt(r1['_prem_score']) + ' | ' + fmt(r2['_prem_score']) + ' |\n'
    msg += '| 计数得分 | ' + fmt(r1['_count_score']) + ' | ' + fmt(r2['_count_score']) + ' |\n'
    msg += '| 超触发得分 | ' + fmt(r1['_trigger_score']) + ' | ' + fmt(r2['_trigger_score']) + ' |\n'
    msg += '| 现价 | ' + fmt(r1.get('price')) + '元 | ' + fmt(r2.get('price')) + '元 |\n'
    msg += '| 溢价率 | ' + fmt(r1.get('premium')) + '% | ' + fmt(r2.get('premium')) + '% |\n'
    msg += '| 正股超触发 | ' + a1 + '% | ' + a2 + '% |\n'
    msg += '| 剩余规模 | ' + scale_tag(r1) + ' | ' + scale_tag(r2) + ' |\n'
    msg += '| 正股ROE | ' + roe_tag(r1) + ' | ' + roe_tag(r2) + ' |\n'
    msg += '| 主体评级 | ' + rating_tag(r1) + ' | ' + rating_tag(r2) + ' |\n'
    msg += '| ST/退市风险 | ' + st_risk_tag(r1) + ' | ' + st_risk_tag(r2) + ' |\n'

    return msg


def main(now_dt=None):
    if now_dt is None:
        now_dt = dt.datetime.now()
    now_str = now_dt.strftime('%Y-%m-%d %H:%M')

    writer, log_path = make_writer(now_dt)
    writer.write('[' + now_str + '] B型不强赎博弈策略 V1+V2 开始...\n')

    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.jisilu.cn/'})
    session.cookies.set('kbzw__Session', KBZW_SESSION, domain='www.jisilu.cn', path='/')
    session.cookies.set('kbzw__user_login', KBZW_USER_LOGIN, domain='www.jisilu.cn', path='/')

    bonds = get_list(session)
    writer.write('  全量: ' + str(len(bonds)) + ' 只\n')

    today_dt = now_dt
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

        # ── 评级过滤：排除A级以下 ───────────────────────
        rating_v = str(detail.get('rating') or '-').strip()
        bad_ratings = {'A-', 'BBB+', 'BBB', 'BBB-', 'BB+', 'BB', 'BB-', 'B+', 'B', 'B-',
                       'CCC+', 'CCC', 'CCC-', 'CC', 'C', 'D', '-', ''}
        if rating_v in bad_ratings:
            writer.write(f'  排除 {detail["name"]}({bid}) 评级{rating_v} 不合格\n')
            continue

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
            r = {
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
            }
            calc_v2_score(r)   # 计算V2评分
            results.append(r)
            writer.write('  命中: ' + detail['name'] + '(' + bid + ') ' + str(cnt) + ' 溢价:' + str(round(premium, 2)) + '% → V2评分:' + fmt(r['_v2_score']) + '\n')

    # ── V1排序（唯计数）─────────────────────────────
    v1_results = sorted(results, key=lambda x: x['count'][0] if x['count'] else 0, reverse=True)
    # ── V2排序（综合评分）──────────────────────────
    v2_results = sorted(results, key=lambda x: x['_v2_score'], reverse=True)

    top2_v1 = v1_results[:2]
    top2_v2 = v2_results[:2]
    writer.write('  最终命中: ' + str(len(results)) + ' 只\n')
    writer.write('  V1 top2: ' + ', '.join(r['name'] for r in top2_v1) + '\n')
    writer.write('  V2 top2: ' + ', '.join(r['name'] for r in top2_v2) + '\n\n')

    # ── 推送 ────────────────────────────────────────
    report_v1 = build_report_v1(top2_v1, today_dt)
    report_v2 = build_report_v2(top2_v2, today_dt)

    # 对比摘要
    v1_names = [r['name'] for r in top2_v1]
    v2_names = [r['name'] for r in top2_v2]
    diff_note = ''
    if v1_names != v2_names:
        diff_note = '\n\n**⚠️ V1/V2 排序差异:** V1推荐' + '，V2推荐' + '。请对照关注。'

    full_report = report_v1 + '\n---\n' + report_v2 + diff_note

    writer.write('\n' + '=' * 60 + '\n')
    writer.write(full_report + '\n')
    resp = dingtalk_send(full_report)
    writer.write('[DingTalk] ' + str(resp) + '\n')
    writer.write(f'[{now_str}] 执行完成\n')
    writer.fp.close()


    # ── push_metadata.csv（钉钉发送成功后）──
    v1_names = [r['name'] for r in top2_v1]
    v2_names = [r['name'] for r in top2_v2]
    all_names = v1_names + v2_names
    errcode = resp.get('errcode', -1)
    date_str = now_dt.strftime('%Y-%m-%d')
    append_metadata(date_str, log_path.name, len(results), all_names, errcode)


    return {'v1': v1_results, 'v2': v2_results}


if __name__ == '__main__':
    main()