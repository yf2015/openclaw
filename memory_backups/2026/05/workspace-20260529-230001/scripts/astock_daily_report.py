#!/usr/bin/env python3
"""
A股每日盘后分析报告生成器
通过 OpenClaw Gateway Tool Invoke API 调用 web_search 获取数据
生成精美单页 HTML 报告 + 钉钉推送
"""

import json
import urllib.request
import urllib.error
import datetime as dt
import re
import os

# ============ 配置 ============
GATEWAY_URL = "http://127.0.0.1:18789"
DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488'
REPORT_DIR = "/home/www/toolbox-api/static/stock/panhoufenxi"

# ============ 工具函数 ============

def get_gateway_token():
    try:
        with open("/root/.openclaw/openclaw.json") as f:
            config = json.load(f)
        return config.get('gateway', {}).get('auth', {}).get('token', '')
    except:
        return None

def tool_invoke(tool_name, args=None):
    token = get_gateway_token()
    if not token:
        return {"error": "No token"}
    url = f"{GATEWAY_URL}/tools/invoke"
    payload = {"tool": tool_name, "args": args or {}}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    })
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()}"}
    except Exception as e:
        return {"error": str(e)}

def web_search(query, count=8, date_after=None):
    args = {"query": query, "count": count}
    if date_after:
        args["date_after"] = date_after
    result = tool_invoke("web_search", args)
    if result.get("ok"):
        return extract_search_content(result.get("result", {}))
    print(f"Web search error: {result.get('error')}")
    return []

def dingtalk_send(title, text):
    payload = json.dumps({
        'msgtype': 'markdown',
        'markdown': {'title': title, 'text': text},
        'at': {'isAtAll': False}
    })
    req = urllib.request.Request(DINGTALK_WEBHOOK, data=payload.encode('utf-8'),
        headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read().decode())
        if result.get('errcode') != 0:
            print(f"DingTalk error: {result}")
        return result
    except Exception as e:
        print(f"DingTalk send failed: {e}")
        return {'error': str(e)}

def extract_content_from_marked(text):
    if not text:
        return ''
    match = re.search(r'>>>([\s\S]*?)\n<<<END_EXTERNAL', text)
    content = match.group(1) if match else text
    content = content.strip()
    content = re.sub(r'^[\s\n]*Source:\s*Web\s*Search\s*[-–]+\s*', '', content, flags=re.IGNORECASE)
    return content.strip()

def extract_search_content(result_payload):
    results = []
    if isinstance(result_payload, dict):
        details = result_payload.get('details', {})
        results = details.get('results', [])
        if not results:
            content = result_payload.get('content', [])
            if content and isinstance(content[0], dict):
                text = content[0].get('text', '')
                try:
                    parsed = json.loads(text)
                    results = parsed.get('results', [])
                except:
                    pass
    elif isinstance(result_payload, list):
        results = result_payload

    items = []
    for r in results[:8]:
        title = extract_content_from_marked(r.get('title', ''))
        desc = extract_content_from_marked(r.get('description', ''))
        site = r.get('siteName', '')
        items.append({
            'title': title[:150] if title else '(无标题)',
            'desc': desc[:600] if desc else '(无描述)',
            'source': site or '未知来源'
        })
    return items

# ============ HTML 报告生成 ============

def parse_indices(market_data):
    """从市场数据中解析各指数信息"""
    # 优先使用包含"收盘"的条目
    close_texts = []
    other_texts = []
    for item in market_data:
        if item['desc'] and ('收盘' in item['desc'] or '截至收盘' in item['desc']):
            close_texts.append(item['desc'])
        elif item['desc']:
            other_texts.append(item['desc'])
    text = '\n'.join(close_texts + other_texts)

    indices = {}

    # 复合正则：处理多种格式
    # 格式1: "上证指数收报4077.28点(-2.04%)" 或 "(-2.04%)"
    # 格式2: "上证指数跌2.04%，报4077.28点"
    # 格式3: "沪指跌幅2.04%，报4077.28点"
    # 格式4: "沪指跌2.04%报4077.28点"

    index_defs = [
        ('上证指数', [r'上证[指数]*[^跌\d]*?([\d,.]+)[点]*\s*[(-]([.-]?\d+\.?\d*)%?', r'沪指[跌幅]?([.-]?\d+\.?\d*)%?[^报]*?报?([\d,.]+)']),
        ('深证成指', [r'深证成指[^跌\d]*?([\d,.]+)[点]*\s*[(-]([.-]?\d+\.?\d*)%?', r'深证成指[跌幅]?([.-]?\d+\.?\d*)%?[^报]*?报?([\d,.]+)']),
        ('创业板指', [r'创业板指[^跌\d]*?([\d,.]+)[点]*\s*[(-]([.-]?\d+\.?\d*)%?', r'创业板指[跌幅]?([.-]?\d+\.?\d*)%?[^报]*?报?([\d,.]+)']),
        ('科创50', [r'科创50[^跌\d]*?([\d,.]+)[点]*\s*[(-]([.-]?\d+\.?\d*)%?']),
        ('沪深300', [r'沪深300[^跌\d]*?([\d,.]+)[点]*\s*[(-]([.-]?\d+\.?\d*)%?']),
        ('北证50', [r'北证50[^跌\d]*?([\d,.]+)[点]*\s*[(-]([.-]?\d+\.?\d*)%?']),
    ]

    for name, patterns in index_defs:
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                groups = m.groups()
                if len(groups) == 2:
                    # 格式1: point, pct
                    indices[name] = {'point': groups[0], 'pct': groups[1]}
                elif len(groups) == 4:
                    # 格式2: pct, point
                    indices[name] = {'point': groups[3], 'pct': groups[1]}
                break

    # 成交额 - 精确匹配全市场/两市数据
    all_text = '\n'.join(item['desc'] for item in market_data if item['desc'])
    vol_m = re.search(r'全市场成交额(\d+)亿元', all_text)
    if not vol_m:
        vol_m = re.search(r'两市成交金额([\d,.]+万亿)', all_text)
    if not vol_m:
        vol_m = re.search(r'全市场成交额([\d,.]+)', all_text)
    indices['成交额'] = (vol_m.group(1) + '亿元') if vol_m else None

    # 上涨/下跌家数 - 精确匹配全市场数据
    up_m = re.search(r'全市场超?(\d+)只个股?上涨', all_text)
    if not up_m:
        up_m = re.search(r'上涨个股[仅有]?(\d+)', all_text)
    indices['上涨'] = up_m.group(1).replace(',', '') if up_m else None

    down_m = re.search(r'全市场超?(\d+)只个股?下跌', all_text)
    if not down_m:
        down_m = re.search(r'下跌个股[约]?(\d+)', all_text)
    if not down_m:
        down_m = re.search(r'近(\d+)只个股?下跌', all_text)
    indices['下跌'] = down_m.group(1).replace(',', '') if down_m else None

    # 上涨家数 - 优先从收盘数据，其次从早盘数据
    up_m = re.search(r'上涨个股[仅]?(\d+)', all_text)
    if not up_m:
        up_m = re.search(r'(\d+)只个股?上涨', all_text)
    indices['上涨'] = up_m.group(1).replace(',', '') if up_m else None

    return indices

def format_pct(pct_str):
    """格式化涨跌幅"""
    try:
        pct = float(pct_str)
        return f"{pct:+.2f}%"
    except:
        return pct_str

def generate_html_report(date_str, market_data, money_flow, news):
    """生成精美单页 HTML 报告"""
    indices = parse_indices(market_data)

    # 指数卡片HTML
    index_cards_html = ""
    index_map = {
        '上证指数': 'sh000001',
        '深证成指': 'sz399001',
        '创业板指': 'sz399006',
        '科创50': 'sh000688',
        '沪深300': 'sh000300',
        '北证50': 'sz899050',
    }
    for name in ['上证指数', '深证成指', '创业板指', '科创50', '沪深300']:
        if name in indices:
            info = indices[name]
            pct = info.get('pct', '0')
            is_down = float(pct) < 0 if pct.replace('.', '').replace('-', '').isdigit() else False
            cls = "down" if is_down else "up"
            index_cards_html += f"""
            <div class="index-card">
                <div class="index-name">{name}</div>
                <div class="index-point">{info.get('point', '-')}</div>
                <div class="index-pct {cls}">{format_pct(pct)}</div>
            </div>"""

    # 资金流向HTML
    flow_html = ""
    for item in money_flow[:6]:
        if item['desc']:
            flow_html += f"<li><span class='flow-source'>{item['source']}</span><p>{item['desc'][:250]}</p></li>"

    # 新闻HTML
    news_html = ""
    for i, item in enumerate(news[:6], 1):
        news_html += f"""
        <div class="news-item">
            <span class="news-num">{i}</span>
            <div class="news-content">
                <div class="news-title">{escape_html(item['title'])}</div>
                <div class="news-desc">{escape_html(item['desc'][:300])}</div>
                <span class="news-source">{escape_html(item['source'])}</span>
            </div>
        </div>"""

    # 市场详情HTML
    detail_rows = []
    if indices.get('成交额'):
        detail_rows.append(f"<tr><td>成交额</td><td>{indices['成交额']}</td></tr>")
    if indices.get('上涨'):
        detail_rows.append(f"<tr><td>上涨个股</td><td class='up'>{indices['上涨']} 只</td></tr>")
    if indices.get('下跌'):
        detail_rows.append(f"<tr><td>下跌个股</td><td class='down'>{indices['下跌']} 只</td></tr>")

    market_details_html = '\n'.join(detail_rows) if detail_rows else "<tr><td colspan='2'>数据整理中...</td></tr>"

    # 涨跌停数据
    limit_text = ''
    for item in market_data:
        if item['desc'] and ('涨停' in item['desc'] or '跌停' in item['desc']):
            limit_text += item['desc'][:300] + ' '

    generated_time = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股盘后分析 {date_str}</title>
<style>
  :root {{
    --bg-primary: #0f1419;
    --bg-card: #1a2332;
    --bg-card-hover: #1e2a3a;
    --text-primary: #e7e9ea;
    --text-secondary: #8b98a5;
    --accent-red: #f4212e;
    --accent-green: #00ba7c;
    --accent-blue: #1d9bf0;
    --accent-orange: #ff7a00;
    --border-color: #2f3d50;
    --radius: 12px;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    padding: 20px;
    min-height: 100vh;
  }}
  .container {{ max-width: 900px; margin: 0 auto; }}

  /* Header */
  .header {{
    text-align: center;
    padding: 30px 0 20px;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 30px;
  }}
  .header h1 {{
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 8px;
    background: linear-gradient(135deg, var(--accent-blue), #a0cfff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}
  .header .date {{
    color: var(--text-secondary);
    font-size: 14px;
  }}

  /* Section */
  .section {{ margin-bottom: 28px; }}
  .section-title {{
    font-size: 16px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .section-title::before {{
    content: '';
    display: inline-block;
    width: 4px;
    height: 16px;
    background: var(--accent-blue);
    border-radius: 2px;
  }}

  /* Index Cards */
  .index-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
  }}
  .index-card {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 16px;
    text-align: center;
    transition: all 0.2s;
  }}
  .index-card:hover {{
    background: var(--bg-card-hover);
    transform: translateY(-2px);
  }}
  .index-name {{
    font-size: 13px;
    color: var(--text-secondary);
    margin-bottom: 8px;
  }}
  .index-point {{
    font-size: 20px;
    font-weight: 700;
    margin-bottom: 4px;
  }}
  .index-pct {{
    font-size: 14px;
    font-weight: 600;
  }}
  .index-pct.up {{ color: var(--accent-green); }}
  .index-pct.down {{ color: var(--accent-red); }}

  /* Stats Table */
  .stats-table {{
    width: 100%;
    border-collapse: collapse;
    background: var(--bg-card);
    border-radius: var(--radius);
    overflow: hidden;
  }}
  .stats-table td {{
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color);
    font-size: 14px;
  }}
  .stats-table tr:last-child td {{ border-bottom: none; }}
  .stats-table td:first-child {{ color: var(--text-secondary); width: 30%; }}
  .stats-table td:last-child {{ font-weight: 600; }}
  .stats-table .up {{ color: var(--accent-green); }}
  .stats-table .down {{ color: var(--accent-red); }}

  /* Flow List */
  .flow-list {{
    background: var(--bg-card);
    border-radius: var(--radius);
    overflow: hidden;
    border: 1px solid var(--border-color);
  }}
  .flow-list li {{
    padding: 14px 16px;
    border-bottom: 1px solid var(--border-color);
    list-style: none;
    font-size: 13px;
  }}
  .flow-list li:last-child {{ border-bottom: none; }}
  .flow-source {{
    font-weight: 600;
    color: var(--accent-blue);
    margin-bottom: 4px;
    display: block;
  }}
  .flow-list p {{
    color: var(--text-secondary);
    line-height: 1.5;
    margin-top: 4px;
  }}

  /* News */
  .news-list {{
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .news-item {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 16px;
    display: flex;
    gap: 14px;
    transition: all 0.2s;
  }}
  .news-item:hover {{
    background: var(--bg-card-hover);
    border-color: var(--accent-blue);
  }}
  .news-num {{
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    background: var(--accent-blue);
    color: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
  }}
  .news-content {{ flex: 1; min-width: 0; }}
  .news-title {{
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 6px;
    line-height: 1.4;
  }}
  .news-desc {{
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.5;
    margin-bottom: 8px;
  }}
  .news-source {{
    font-size: 11px;
    color: var(--text-secondary);
    background: rgba(255,255,255,0.05);
    padding: 2px 8px;
    border-radius: 4px;
  }}

  /* Limit info */
  .limit-box {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 16px;
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.6;
  }}

  /* Footer */
  .footer {{
    text-align: center;
    padding: 30px 0 20px;
    color: var(--text-secondary);
    font-size: 12px;
    border-top: 1px solid var(--border-color);
    margin-top: 40px;
  }}
  .footer .tag {{
    display: inline-block;
    background: var(--accent-blue);
    color: white;
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 11px;
    margin-bottom: 8px;
  }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>A股每日盘后分析</h1>
    <div class="date">{date_str} · 自动生成</div>
  </div>

  <div class="section">
    <div class="section-title">主要指数</div>
    <div class="index-grid">
      {index_cards_html or '<div class="index-card"><div class="index-name">数据加载中...</div></div>'}
    </div>
  </div>

  <div class="section">
    <div class="section-title">市场概况</div>
    <table class="stats-table">
      {market_details_html}
    </table>
  </div>

  {limit_text and f'''
  <div class="section">
    <div class="section-title">涨跌停概况</div>
    <div class="limit-box">{escape_html(limit_text[:500])}</div>
  </div>''' or ''}

  <div class="section">
    <div class="section-title">资金动向</div>
    <ul class="flow-list">
      {flow_html or '<li><p>数据加载中...</p></li>'}
    </ul>
  </div>

  <div class="section">
    <div class="section-title">今日重大新闻</div>
    <div class="news-list">
      {news_html or '<div class="news-item"><div class="news-content"><div class="news-title">数据加载中...</div></div></div>'}
    </div>
  </div>

</div>

<div class="footer">
  <div class="tag">OpenClaw 自动生成</div>
  <div>生成时间: {generated_time}</div>
</div>

</body>
</html>"""
    return html

def escape_html(text):
    """转义HTML特殊字符"""
    if not text:
        return ''
    return (text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#39;'))

# ============ 数据获取 ============

def get_market_close_data(date_str):
    print(f"正在搜索 {date_str} A股收盘数据...")
    return web_search(f"{date_str} A股 收盘 上证指数 深证成指 创业板 涨跌幅", count=8)

def get_money_flow(date_str):
    print(f"正在搜索 {date_str} A股主力资金流向...")
    return web_search(f"{date_str} A股 主力资金 净流入 净流出 行业板块", count=6)

def get_major_news(date_str):
    print(f"正在搜索 {date_str} A股重大新闻事件...")
    return web_search(f"{date_str} A股 重大新闻 市场事件 财经", count=6)

# ============ 主程序 ============

def main():
    print(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] A股日报开始生成...")

    today = dt.datetime.now().strftime('%Y-%m-%d')
    yesterday = (dt.datetime.now() - dt.timedelta(days=1)).strftime('%Y-%m-%d')
    search_date = yesterday if dt.datetime.now().hour < 15 else today

    market_data = get_market_close_data(search_date)
    money_flow = get_money_flow(search_date)
    news = get_major_news(search_date)

    # 生成 HTML 报告
    os.makedirs(REPORT_DIR, exist_ok=True)
    html_report = generate_html_report(search_date, market_data, money_flow, news)
    html_path = os.path.join(REPORT_DIR, f"{search_date}.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_report)
    print(f"HTML 报告已保存: {html_path}")

    # 钉钉推送（保留简短摘要）
    dingtalk_text = f"""📊 **A股盘后 {search_date}**

指数: 上证 {market_data[0]['desc'][:80] if market_data else '数据加载中'}...

💰 资金: {money_flow[0]['desc'][:100] if money_flow else '数据加载中'}...

📰 新闻: {news[0]['title'] if news else '数据加载中'}

📁 [查看完整报告](http://121.41.72.70:9002/stock/{search_date}.html)"""

    print("正在发送到钉钉...")
    result = dingtalk_send(f"📊 A股盘后 {search_date}", dingtalk_text)

    if result.get('errcode') == 0:
        print(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 完成!")
    else:
        print(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 钉钉发送失败: {result}")

    return result

if __name__ == '__main__':
    main()
