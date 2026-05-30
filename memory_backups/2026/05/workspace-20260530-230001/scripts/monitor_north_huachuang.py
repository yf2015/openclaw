#!/usr/bin/env python3
"""
北方华创(002371) 盯盘脚本
基于日本蜡烛图技术分析，监控关键价位和形态预警
推送钉钉告警
"""

import sys
import json
import re
import time
import urllib.request
import urllib.error
from datetime import datetime

DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488"

# ========== 行情获取 ==========

def get_stock_data(code: str) -> dict:
    """获取股票实时数据（腾讯财经接口）"""
    url = f"https://qt.gtimg.cn/q=sz{code}" if code.startswith(("0", "3")) else f"https://qt.gtimg.cn/q=sh{code}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=8)
        raw = resp.read().decode('gbk')
        # 解析：v_sz002371="...name,code,price,close,open,vol,..."
        m = re.search(r'="([^"]+)"', raw)
        if not m:
            return {}
        fields = m.group(1).split('~')
        if len(fields) < 50:
            return {}
        return {
            'name': fields[1],
            'code': fields[2],
            'price': float(fields[3]),
            'close': float(fields[4]),   # 昨收
            'open': float(fields[5]),     # 开盘
            'vol': float(fields[6]),      # 成交量(手)
            'bid1': float(fields[9]),     # 买一
            'ask1': float(fields[19]),    # 卖一
            'high': float(fields[33]),    # 最高
            'low': float(fields[34]),     # 最低
            'date': fields[30],
            'time': fields[30],
        }
    except Exception as e:
        print(f"[ERROR] 获取行情失败: {e}", file=sys.stderr)
        return {}

def get_klines(code: str, count: int = 25) -> list:
    """获取近期K线数据（日K，前复权）—— 优先新浪，备用东方财富"""
    # 方法1：新浪日K（240分钟=日K）
    symbol = f"sz{code}" if code.startswith(("0", "3")) else f"sh{code}"
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=5&datalen={count}"
    try:
        import urllib.parse
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read().decode('gbk'))
        if data and isinstance(data, list):
            # 转换为统一格式
            return [{"day": k["day"], "open": float(k["open"]), "high": float(k["high"]),
                     "low": float(k["low"]), "close": float(k["close"]), "vol": float(k["volume"])}
                    for k in reversed(data)]  # 旧->新
    except Exception as e:
        print(f"[WARN] 新浪K线失败: {e}", file=sys.stderr)

    # 方法2：东方财富（备用）
    url2 = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    market = '1' if code.startswith(('6', '5', '9')) else '0'
    params = {
        'secid': f'{market}.{code}',
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'klt': '101', 'fqt': '1', 'lmt': str(count), 'end': '20500101'
    }
    try:
        req = urllib.request.Request(
            f"{url2}?{urllib.parse.urlencode(params)}",
            headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.eastmoney.com'}
        )
        resp = urllib.request.urlopen(req, timeout=8)
        raw_data = json.loads(resp.read().decode())
        klines = raw_data.get('data', {}).get('klines', [])
        return [parse_kline(k) for k in klines]
    except Exception as e2:
        print(f"[ERROR] 东方财富K线也失败: {e2}", file=sys.stderr)
    return []

# ========== 蜡烛图分析 ==========

def parse_kline(kline_str: str) -> dict:
    """解析K线字符串: 日期,开,高,低,收,量,额,... """
    parts = kline_str.split(',')
    return {
        'date': parts[0],
        'open': float(parts[1]),
        'high': float(parts[2]),
        'low': float(parts[3]),
        'close': float(parts[4]),
        'vol': float(parts[5]),
        'amount': float(parts[6]) if len(parts) > 6 else 0,
    }


def parse_kline_dict(k: dict) -> dict:
    """解析新浪K线字典格式"""
    return {
        'date': k['day'],
        'open': k['open'],
        'high': k['high'],
        'low': k['low'],
        'close': k['close'],
        'vol': k['vol'],
        'amount': 0,
    }

def detect_hammer_or_shooting_star(k: dict) -> str:
    """锤子线/上吊线/流星形态识别"""
    body = abs(k['close'] - k['open'])
    upper_shadow = k['high'] - max(k['close'], k['open'])
    lower_shadow = min(k['close'], k['open']) - k['low']
    if body == 0:
        return "十字线"
    ratio = body
    if lower_shadow > body * 2 and upper_shadow < body * 0.5:
        return "锤子线（看涨）"
    elif upper_shadow > body * 2 and lower_shadow < body * 0.5:
        return "上吊线（看跌）"
    elif upper_shadow > body * 2 and lower_shadow < body * 0.3:
        return "流星形态（看跌）"
    return ""

def detect_engulfing(klines: list) -> str:
    """吞没形态识别（需至少2根K线）"""
    if len(klines) < 2:
        return ""
    k1 = klines[-2]
    k2 = klines[-1]
    body1 = abs(k1['close'] - k1['open'])
    body2 = abs(k2['close'] - k2['open'])
    is_bearish1 = k1['close'] < k1['open']  # k1阴线
    is_bullish2 = k2['close'] > k2['open']  # k2阳线
    # 阳包阴（看涨）
    if is_bearish1 and is_bullish2:
        if k2['open'] < k1['close'] and k2['close'] > k1['open']:
            return "吞没形态（阳包阴·看涨）"
    # 阴包阳（看跌）
    is_bullish1 = k1['close'] > k1['open']
    is_bearish2 = k2['close'] < k2['open']
    if is_bullish1 and is_bearish2:
        if k2['open'] > k1['close'] and k2['close'] < k1['open']:
            return "吞没形态（阴包阳·看跌）"
    return ""

def detect_doji(k: dict, threshold: float = 0.1) -> bool:
    """十字线识别（实体极小）"""
    body = abs(k['close'] - k['open'])
    total_range = k['high'] - k['low']
    if total_range == 0:
        return False
    return body / total_range < threshold

def detect_gap_up(klines: list) -> bool:
    """向上跳空缺口（窗口）"""
    if len(klines) < 2:
        return False
    prev = klines[-2]
    curr = klines[-1]
    return curr['open'] > prev['high']

def analyze_candles(klines: list) -> dict:
    """综合蜡烛图分析"""
    result = {
        'alerts': [],
        'signals': [],
        'trend': 'unknown',
    }
    if len(klines) < 5:
        return result

    klines_recent = klines[-10:]  # 最近10根
    k = klines_recent[-1]  # 最新K线

    # 1. 锤子/上吊/流星
    pattern = detect_hammer_or_shooting_star(k)
    if pattern:
        result['alerts'].append(pattern)

    # 2. 吞没形态
    engulfing = detect_engulfing(klines_recent)
    if engulfing:
        result['alerts'].append(engulfing)

    # 3. 十字线预警
    if detect_doji(k):
        result['alerts'].append("⚠️ 十字线（谨慎）")

    # 4. 窗口（向上跳空）
    if detect_gap_up(klines_recent):
        result['alerts'].append("窗口（向上跳空·加速信号）")

    # 5. 量价背离检测（近5根）
    if len(klines_recent) >= 5:
        recent_5 = klines_recent[-5:]
        closes = [k['close'] for k in recent_5]
        vols = [k['vol'] for k in recent_5]
        max_close = max(closes)
        max_vol = max(vols)
        latest_close = closes[-1]
        latest_vol = vols[-1]
        # 价格创新高但量能未新高
        if latest_close > max_close * 0.99 and latest_vol < max_vol * 0.85:
            result['alerts'].append("⚠️ 量价背离（价格新高·量能萎缩）")

    # 6. 趋势判断（基于均线）
    if len(klines_recent) >= 5:
        ma5 = sum(klines_recent[-5:][i]['close'] for i in range(5)) / 5
        ma10 = sum(klines_recent[-10:][i]['close'] for i in range(10)) / 10 if len(klines_recent) >= 10 else ma5
        latest_close = klines_recent[-1]['close']
        if latest_close > ma5 > ma10:
            result['trend'] = '上升'
        elif latest_close < ma5 < ma10:
            result['trend'] = '下降'
        else:
            result['trend'] = '震荡'

    return result

# ========== 钉钉推送 ==========

def dingtalk_notify(title: str, msg: str, at_all: bool = False) -> bool:
    """推送钉钉消息"""
    payload = json.dumps({
        'msgtype': 'markdown',
        'markdown': {
            'title': title,
            'text': msg
        },
        'at': {'isAtAll': at_all}
    })
    try:
        req = urllib.request.Request(
            DINGTALK_WEBHOOK,
            data=payload.encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode())
        return result.get('errcode', 1) == 0
    except Exception as e:
        print(f"[ERROR] 钉钉推送失败: {e}", file=sys.stderr)
        return False

# ========== 主逻辑 ==========

def check_and_alert(stock_code: str = "002371", stock_name: str = "北方华创"):
    """执行一次检查并推送"""
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # 获取K线
    klines_raw = get_klines(stock_code, count=25)
    if not klines_raw:
        print(f"[{now_str}] 获取K线失败，跳过")
        return

    # 新浪接口返回dict，东方财富返回str，兼容处理
    klines = []
    for k in klines_raw:
        if isinstance(k, dict):
            klines.append(parse_kline_dict(k))
        else:
            klines.append(parse_kline(k))
    klines_rev = list(reversed(klines))  # 从旧到新排列

    latest = klines_rev[-1]
    prev = klines_rev[-2] if len(klines_rev) >= 2 else None

    # 行情数据
    quote = get_stock_data(stock_code)
    price = quote.get('price', latest['close'])
    open_price = quote.get('open', latest['open'])
    high = quote.get('high', latest['high'])
    low = quote.get('low', latest['low'])
    close_yest = quote.get('close', latest['close'])

    change = price - close_yest
    change_pct = (change / close_yest * 100) if close_yest else 0

    # 关键价位
    SUPPORT_1 = 640  # 强支撑
    SUPPORT_2 = 620  # 中支撑
    SUPPORT_3 = 600  # 止损线
    RESIST_1 = 656   # 昨日收盘/今日开盘区间
    RESIST_2 = 680   # 目标压力

    # 蜡烛图分析
    analysis = analyze_candles(klines_rev)

    # ========== 决策逻辑 ==========
    alerts = []
    severity = "normal"  # normal / warning / critical

    # 1. 价位预警
    if price < SUPPORT_3:
        alerts.append("🚨 跌破止损线600！建议短线清仓")
        severity = "critical"
    elif price < SUPPORT_2:
        alerts.append(f"⚠️ 跌破支撑2({SUPPORT_2})，减仓观察")
        severity = "warning"
    elif price < SUPPORT_1:
        alerts.append(f"⚠️ 触及支撑1({SUPPORT_1})，关注企稳信号")
        severity = "warning"
    elif price > RESIST_2:
        alerts.append(f"🎯 突破目标位{RESIST_2}，注意止盈")
        severity = "warning"

    # 2. 蜡烛图形态预警
    for alert in analysis['alerts']:
        if '量价背离' in alert or '十字线' in alert:
            alerts.append(alert)
            if severity == "normal":
                severity = "warning"
        elif '看跌' in alert or '黄昏' in alert or '流星' in alert or '乌云盖顶' in alert:
            alerts.append(f"🔴 {alert}")
            if severity in ("normal", "warning"):
                severity = "warning"
        else:
            alerts.append(alert)

    # 3. 大幅波动预警
    if abs(change_pct) >= 5:
        alerts.append(f"📊 振幅{change_pct:+.2f}%({'大幅上涨' if change_pct > 0 else '大幅下跌'})")
        if abs(change_pct) >= 7 and severity != "critical":
            severity = "warning"

    # 4. 跳空缺口预警
    if len(klines_rev) >= 2:
        prev_k = klines_rev[-2]
        gap_up = latest['open'] > prev_k['high']
        gap_down = latest['low'] < prev_k['open']
        if gap_up:
            alerts.append("↑ 向上跳空缺口，关注是否回补")
        elif gap_down:
            alerts.append("↓ 向下缺口，关注是否回补")

    # ========== 操作建议（基于规则） ==========
    # 读取规则文件获取当前操作建议
    rules_doc = ""
    try:
        rules_path = "/root/.openclaw/workspace/scripts/trading_rules_huachuang.md"
        with open(rules_path, 'r') as f:
            rules_doc = f.read()
    except:
        pass

    action_suggest = ""
    action_level = "none"  # none / watch / buy / sell / hold

    # —— 持仓后止损线判断（根据是否有持仓，这里是预判）——
    # —— 今日新建仓判断（根据开盘价和当前价）——
    if price < SUPPORT_3:
        action_suggest = "🚨 执行止损！跌破600，短线清仓"
        action_level = "sell_all"
    elif severity == "critical":
        action_suggest = "🚨 立即减仓，触发止损线"
        action_level = "sell"
    elif price > RESIST_2:
        action_suggest = "🎯 接近目标位680，适量止盈"
        action_level = "take_profit"
    elif "量价背离" in str(alerts):
        action_suggest = "⚠️ 量价背离，短线减仓≥50%"
        action_level = "sell_half"
    elif any("黄昏星" in a or "乌云盖顶" in a or "阴包阳" in a for a in alerts):
        action_suggest = "🔴 顶部反转形态，减仓≥50%"
        action_level = "sell_half"
    elif any("十字线" in a or "流星" in a for a in alerts):
        action_suggest = "⚠️ 犹豫形态，谨慎减仓1/3"
        action_level = "sell_third"
    elif price < SUPPORT_1:
        action_suggest = "⚠️ 触及支撑640，关注企稳信号（锤子线/吞没）才买入"
        action_level = "watch"
    elif price >= SUPPORT_1 and price <= RESIST_1 and action_level == "none":
        action_suggest = "📍 区间震荡，方向待确认，观望"
        action_level = "watch"
    elif analysis['trend'] == '上升' and price > RESIST_1 and severity == "normal":
        action_suggest = "✅ 趋势向上，耐心持有多头"
        action_level = "hold"
    else:
        action_suggest = "📊 趋势未破，观望等待信号"
        action_level = "watch"

    # ========== 推送内容 ==========

    if not alerts and action_level in ("hold", "none", "watch"):
        # 无特殊情况，简洁推送
        if quote:
            msg = f"## 📊 {stock_name}({stock_code})\n\n"
            msg += f"**现价: ¥{price:.2f}** {'↑' if change >= 0 else '↓'} {change_pct:+.2f}%\n"
            msg += f"**今高/今低: {high:.2f} / {low:.2f}**\n"
            msg += f"**趋势: {analysis['trend']}**\n\n"
            msg += f"无特殊预警信号，多头格局延续。\n\n"
            msg += f"> 🕐 {now_str}"
        else:
            msg = f"## 📊 {stock_name}({stock_code})\n\n"
            msg += f"**昨收/今开: {latest['close']:.2f} / {latest['open']:.2f}**\n"
            msg += f"**趋势: {analysis['trend']}**\n\n"
            msg += f"> 🕐 {now_str}"
    else:
        # 有预警 — 完整推送
        emoji = {"normal": "🟡", "warning": "🟠", "critical": "🔴"}[severity]
        action_emoji = {
            "none": "📊", "watch": "👀", "hold": "🟢",
            "buy": "✅", "sell_third": "⚠️", "sell_half": "🟠",
            "sell": "🔴", "sell_all": "🚨", "take_profit": "🎯"
        }.get(action_level, "📊")

        msg = f"## {emoji} {stock_name} 盯盘预警\n\n"
        msg += f"**现价: ¥{price:.2f}** {'↑' if change >= 0 else '↓'} {change_pct:+.2f}%\n"
        msg += f"**今高/今低: {high:.2f} / {low:.2f}**\n"
        msg += f"**趋势: {analysis['trend']}**\n\n"
        msg += f"### {action_emoji} 操作建议\n"
        msg += f"{action_suggest}\n\n"
        msg += f"### 🚨 预警信号\n"
        for a in alerts:
            msg += f"- {a}\n"
        msg += f"\n### 📍 关键价位参考\n"
        msg += f"- 压力2: {RESIST_2}（突破目标）\n"
        msg += f"- 压力1: {RESIST_1}（昨日高点）\n"
        msg += f"- 支撑1: {SUPPORT_1}\n"
        msg += f"- 支撑2: {SUPPORT_2}\n"
        msg += f"- 止损线: {SUPPORT_3}\n"
        msg += f"\n> 🕐 {now_str}"

    title = f"📊 {stock_name} {now.strftime('%H:%M')}"
    ok = dingtalk_notify(title, msg)
    print(f"[{now_str}] 检查完成 | 价格:{price:.2f} | 趋势:{analysis['trend']} | 预警:{len(alerts)} | 推送:{'✅' if ok else '❌'}")
    return alerts, severity


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "002371"
    name = sys.argv[2] if len(sys.argv) > 2 else "北方华创"
    check_and_alert(code, name)