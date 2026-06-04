#!/usr/bin/env python3
"""
MAV (Mean Absolute Value) 波动率分析模块
- 计算标的每日涨跌幅绝对值的截尾均值（排除极值）
- 支持 ETF 和可转债双品种
- 20日（短期）/ 60日（中期）双周期交叉验证
- 用途: 上涨超均值降仓，下跌超均值抄底
"""

import numpy as np
import pandas as pd
import requests
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Literal

# ── 日志 ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("mav")

# ── 集思录 Cookie（转债数据） ──────────────────────────────
KBZW_SESSION = "t8ulaqqcm77mpmkrcnltr74di2"
KBZW_USER_LOGIN = "7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5arrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR"

# ── 公共 Sina API ────────────────────────────────────────
SINA_KLINE_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
_Sina_Session = requests.Session()
_Sina_Session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
})

def sina_code_for(code: str, market_type: str) -> str:
    """ETF/转债 → Sina 格式代码"""
    code = code.strip().zfill(6)
    if market_type == "etf":
        # 上交所: 510/511/512/513/515/588 开头
        # 深交所: 159/161/162/163/164/165 开头
        SH_ETF = ("510", "511", "512", "513", "515", "588")
        SZ_ETF = ("159", "161", "162", "163", "164", "165")
        if code.startswith(SH_ETF):
            return f"sh{code}"
        elif code.startswith(SZ_ETF):
            return f"sz{code}"
        elif code.startswith(("5", "9")):  # 其他上交所ETF
            return f"sh{code}"
        else:
            return f"sz{code}"  # 其他默认深交所
    else:  # cb，转债
        if code.startswith("11"):
            return f"sh{code}"
        else:
            return f"sz{code}"


def fetch_sina_daily(sina_code: str, datalen: int = 500) -> pd.DataFrame:
    """Sina K线接口，支持ETF和转债"""
    params = {"symbol": sina_code, "scale": "240", "ma": "no", "datalen": datalen}
    try:
        r = _Sina_Session.get(SINA_KLINE_URL, params=params, timeout=15)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return pd.DataFrame()
        records = []
        for row in rows:
            try:
                records.append({
                    "trade_date": row["day"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                })
            except (KeyError, ValueError):
                continue
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        return df.sort_values("trade_date").reset_index(drop=True)
    except Exception as e:
        log.warning("  [Sina %s] 获取失败: %s", sina_code, e)
        return pd.DataFrame()


# ── ETF 数据获取（直接用 Sina） ────────────────────────────
def fetch_etf_daily(code: str, days: int = 80) -> pd.DataFrame:
    sina_code = sina_code_for(code, "etf")
    df = fetch_sina_daily(sina_code, datalen=days + 10)
    if df.empty:
        return df
    return df.tail(days).reset_index(drop=True)


# ── 转债数据获取（Sina，优先本地积累，必要时网络拉取） ───────────────
def fetch_cb_daily_from_db(bid: str, days: int = 80) -> pd.DataFrame:
    """从本地 SQLite（jisilu.db）读取转债日K，兼容多种source"""
    db_path = Path("/root/.openclaw/workspace/jisilu.db")
    if not db_path.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT trade_date, close FROM klines
            WHERE sec_code = ? AND source IN ('sina', 'sina_agg', 'jisilu', 'xueqiu')
            ORDER BY trade_date DESC LIMIT ?
        """, (bid, days))
        rows = cur.fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["trade_date", "close"])
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        return df.sort_values("trade_date").reset_index(drop=True)
    except Exception as e:
        log.warning("  [DB %s] 读取失败: %s", bid, e)
        return pd.DataFrame()
    finally:
        conn.close()


def fetch_cb_daily_from_sina(bid: str, datalen: int = 500) -> pd.DataFrame:
    """从 Sina 一次性获取转债全量历史K线，存库并返回 DataFrame"""
    sina_code = sina_code_for(bid, "cb")
    df = fetch_sina_daily(sina_code, datalen=datalen)
    if df.empty:
        return df

    # 存入本地 SQLite
    db_path = Path("/root/.openclaw/workspace/jisilu.db")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # 存 OHLCV（以 sina 源）
        upsert = """
            INSERT INTO klines (sec_code, trade_date, open, high, low, close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'sina')
            ON CONFLICT(sec_code, trade_date, source)
            DO UPDATE SET open=excluded.open, high=excluded.high, low=excluded.low,
                          close=excluded.close, volume=excluded.volume
        """
        rows = [
            (bid, r.trade_date, r.open, r.high, r.low, r.close, r.volume)
            for r in df.itertuples()
        ]
        cur.executemany(upsert, rows)
        conn.commit()
        log.info("  [%s] Sina历史入库 %d 条 (%s ~ %s)",
                 bid, len(df), df.iloc[0]["trade_date"], df.iloc[-1]["trade_date"])
    except Exception as e:
        log.warning("  [%s] 入库失败: %s", bid, e)
    finally:
        conn.close()
    return df


def fetch_cb_daily(bid: str, days: int = 80) -> pd.DataFrame:
    """获取转债日K，优先本地积累 + Sina 补全
    - 本地够用 → 直接返回
    - 本地不足 → 从 Sina 拉取完整历史（最多500条），自动落库
    """
    df_local = fetch_cb_daily_from_db(bid, days=days)
    if len(df_local) >= days:
        return df_local.tail(days).reset_index(drop=True)
    # 本地不够，从 Sina 拉全量历史（500条），自动补库
    log.info("  [%s] 本地仅%d条，从Sina补全...", bid, len(df_local))
    df_full = fetch_cb_daily_from_sina(bid, datalen=500)
    if not df_full.empty:
        return df_full.tail(days).reset_index(drop=True)
    # 兜底：返回本地已有的
    return df_local.tail(days).reset_index(drop=True) if not df_local.empty else pd.DataFrame()


# ── 核心计算 ──────────────────────────────────────────────
def trimmed_mean_absolute(returns: np.ndarray, trim_ratio: float = 0.05) -> float:
    """
    截尾均值: 去掉最大和最小各 trim_ratio 比例后的均值
    排除单日暴涨暴跌对均值的干扰
    """
    if len(returns) < 10:
        return np.mean(returns) if len(returns) > 0 else 0.0
    n = len(returns)
    lo = int(n * trim_ratio)
    hi = n - int(n * trim_ratio)
    sorted_returns = np.sort(returns)
    trimmed = sorted_returns[lo:hi]
    return float(np.mean(trimmed)) if len(trimmed) > 0 else 0.0


def compute_mav(prices: pd.Series, period: int, trim_ratio: float = 0.05) -> float:
    """计算指定周期的 MAV（日均绝对波幅）"""
    if len(prices) < period + 5:
        return 0.0
    # 取最近 period 日
    recent = prices.tail(period).values
    # 日涨跌幅绝对值
    deltas = np.abs(np.diff(recent) / recent[:-1])
    return trimmed_mean_absolute(deltas, trim_ratio)


def compute_signals(
    mav20: float,
    mav60: float,
    today_change_pct: float,
) -> dict:
    """基于 MAV 判断信号
    today_change_pct: 今日涨跌幅（正=上涨，负=下跌）
    返回: signal, level, description
    """
    result = {
        "today_change_pct": today_change_pct,
        "mav20": mav20,
        "mav60": mav60,
        "signal": "观望",
        "level": 0,
        "description": "",
    }

    if mav20 == 0 or mav60 == 0:
        return result

    # 相对位置
    ratio_20_60 = mav20 / mav60 if mav60 > 0 else 1.0
    change_abs = abs(today_change_pct)

    # 今日涨跌幅相对 MAV 的倍数
    vs_mav20 = change_abs / mav20 if mav20 > 0 else 0.0
    vs_mav60 = change_abs / mav60 if mav60 > 0 else 0.0

    # vs_mav20/vs_mav60 调试日志
    log.info("  [信号] today_change=%.3f%% vs_mav20=%.2f vs_mav60=%.2f  threshold>=2.0 => %s",
            today_change_pct, vs_mav20, vs_mav60,
            "触发⚠️极端" if vs_mav20 >= 2.0 else ("触发⚠️明显" if vs_mav20 >= 1.5 else "未触发极端/明显"))

    if today_change_pct > 0:
        # ── 上涨 ──
        if vs_mav20 >= 2.0:
            result["signal"] = "⚠️ 极端上涨"
            result["level"] = 3
            result["description"] = f"今日涨幅({today_change_pct:.2f}%)超过20日MAV({mav20*100:.2f}%)的2倍以上，极端波动，强烈建议降仓"
        elif vs_mav20 >= 1.5:
            result["signal"] = "⚠️ 明显上涨"
            result["level"] = 2
            result["description"] = f"今日涨幅({today_change_pct:.2f}%)超过20日MAV({mav20*100:.2f}%)的1.5倍，动力偏强，建议适度降仓"
        elif vs_mav60 >= 1.5:
            result["signal"] = "📈 突破均值"
            result["level"] = 1
            result["description"] = f"涨幅({today_change_pct:.2f}%)超过60日MAV({mav60*100:.2f}%)的1.5倍，市场热度上升"
        else:
            result["signal"] = "✅ 正常上涨"
            result["level"] = 0
            result["description"] = f"涨幅({today_change_pct:.2f}%)在正常波动范围内，持有"

        # 热度预警
        if ratio_20_60 > 1.5:
            result["description"] += f"，短期波动加剧(ratio_20_60={ratio_20_60:.2f})"

    else:
        # ── 下跌 ──
        if vs_mav20 >= 2.0:
            result["signal"] = "🔔 极端下跌"
            result["level"] = -3
            result["description"] = f"今日跌幅({abs(today_change_pct):.2f}%)超过20日MAV({mav20*100:.2f}%)的2倍以上，超卖严重，留意抄底机会"
        elif vs_mav20 >= 1.5:
            result["signal"] = "🔔 明显下跌"
            result["level"] = -2
            result["description"] = f"今日跌幅({abs(today_change_pct):.2f}%)超过20日MAV({mav20*100:.2f}%)的1.5倍，偏离均值，可关注低吸机会"
        elif vs_mav60 >= 1.5:
            result["signal"] = "📉 跌破均值"
            result["level"] = -1
            result["description"] = f"跌幅({abs(today_change_pct):.2f}%)超过60日MAV({mav60*100:.2f}%)的1.5倍，注意止损"
        else:
            result["signal"] = "✅ 正常下跌"
            result["level"] = 0
            result["description"] = f"跌幅({abs(today_change_pct):.2f}%)在正常波动范围内，观望"

        # 冷清预警
        if ratio_20_60 < 0.7:
            result["description"] += f"，市场冷清(ratio_20_60={ratio_20_60:.2f})"

    return result


# ── 主分析函数 ────────────────────────────────────────────
def analyze(
    code: str,
    market_type: Literal["etf", "cb"],
    fetch_days: int = 100,
) -> dict:
    """
    入口函数
    code: ETF代码（如510300）或 转债bid（如118003）
    market_type: 'etf' 或 'cb'
    返回完整分析结果
    """
    log.info("[%s %s] 开始分析...", market_type.upper(), code)

    # 1. 获取数据
    if market_type == "etf":
        df = fetch_etf_daily(code, days=fetch_days)
    else:
        # 优先本地积累，本地不足则从 Sina 补全全量历史（自动存库）
        df = fetch_cb_daily(code, days=fetch_days)

    if df.empty or len(df) < 10:
        log.warning("  数据不足，无法计算")
        return {"error": f"数据不足（{len(df)}条），需要至少10条"}

    # 2. 计算 MAV
    prices = df["close"].astype(float)
    mav20 = compute_mav(prices, period=20)
    mav60 = compute_mav(prices, period=60)

    # 数据不足时用较短周期替代（graceful degradation）
    if mav20 == 0:
        mav20 = compute_mav(prices, period=10)  # 降级到10日
    if mav60 == 0:
        mav60 = compute_mav(prices, period=20)  # 降级到20日
    if mav20 == 0:
        return {"error": "MAV计算失败，数据严重不足"}

    # 3. 今日涨跌幅（取最后两天）
    if len(df) >= 2:
        p1 = float(df.iloc[-2]["close"])
        p2 = float(df.iloc[-1]["close"])
        today_change_pct = (p2 - p1) / p1 * 100
        last_date = df.iloc[-1]["trade_date"]
    else:
        today_change_pct = 0.0
        last_date = df.iloc[-1]["trade_date"]

    # 4. 信号判断
    signals = compute_signals(mav20, mav60, today_change_pct)

    # 5. 组装结果
    result = {
        "code": code,
        "market_type": market_type,
        "last_date": last_date,
        "last_close": float(df.iloc[-1]["close"]),
        "today_change_pct": round(today_change_pct, 3),
        "mav20": round(mav20 * 100, 3),          # 转为百分比，如 0.79 表示 0.79%
        "mav60": round(mav60 * 100, 3),
        "mav20_60_ratio": round(mav20 / mav60, 3) if mav60 > 0 else 0,
        **signals,
    }

    log.info(
        "  %s %s: 收盘=%.3f 涨跌=%+.2f%% MAV20=%.4f%% MAV60=%.4f%% ratio=%.3f 信号=%s",
        market_type.upper(), code, result["last_close"],
        today_change_pct, mav20*100, mav60*100, result["mav20_60_ratio"], signals["signal"],
    )
    return result


# ── 格式化输出 ────────────────────────────────────────────
def format_result(r: dict) -> str:
    if "error" in r:
        return f"❌ 错误: {r['error']}"

    signal_emoji = {
        "🔔 极端下跌": "🔴",
        "🔔 明显下跌": "🟠",
        "📉 跌破均值": "🟡",
        "✅ 正常下跌": "⚪",
        "✅ 正常上涨": "⚪",
        "📈 突破均值": "🟢",
        "⚠️ 明显上涨": "🟠",
        "⚠️ 极端上涨": "🔴",
        "观望": "⚪",
    }.get(r["signal"], "⚪")

    msg = (
        f"## 📊 MAV 波动分析\n"
        f"**{r['market_type'].upper()} {r['code']}** ({r['last_date']})\n\n"
        f"| 指标 | 值 |\n|---|---|\n"
        f"| 收盘价 | **{r['last_close']:.3f}** |\n"
        f"| 今日涨跌 | **{r['today_change_pct']:+.2f}%** |\n"
        f"| MAV(20日) | {r['mav20']*100:.2f}% |\n"
        f"| MAV(60日) | {r['mav60']*100:.2f}% |\n"
        f"| 短期/中期比 | {r['mav20_60_ratio']:.3f} |\n\n"
        f"**信号: {signal_emoji} {r['signal']}**\n\n"
        f"{r['description']}"
    )
    return msg


# ── 批量分析（转债/ETF组合）────────────────────────────────
def batch_analyze(
    items: list[tuple[str, Literal["etf", "cb"]]],
    fetch_days: int = 100,
) -> list[dict]:
    """批量分析多只标的
    items: [("510300","etf"), ("118003","cb"), ...]
    """
    results = []
    for code, mtype in items:
        r = analyze(code, mtype, fetch_days=fetch_days)
        results.append(r)
    return results


# ── 命令行入口 ────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("用法: python3 cb_etf_mav.py <etf_code> <etf|cb> [code2 type2 ...]")
        print("示例:")
        print("  python3 cb_etf_mav.py 510300 etf")
        print("  python3 cb_etf_mav.py 118003 cb")
        print("  python3 cb_etf_mav.py 510300 etf 159915 etf")
        sys.exit(1)

    args = sys.argv[1:]
    # 支持混合: python3 cb_etf_mav.py 510300 etf 118003 cb
    items = []
    i = 0
    while i + 1 < len(args):
        items.append((args[i], args[i + 1]))
        i += 2

    for code, mtype in items:
        r = analyze(code, mtype)
        print(format_result(r))
        print()