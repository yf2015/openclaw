#!/usr/bin/env python3
"""
B型策略转债 K线数据获取
- 日K + 15分K 来源: Sina (https://quotes.sina.cn)
- 覆盖区间: 2026-04-22 → 2026-05-14
- 目标标的: 从日志提取的19只转债
"""

import sqlite3, time, datetime as dt, logging
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import requests

# ── 日志配置 ──────────────────────────────────────────────
LOG_FILE = Path(__file__).parent.parent / "logs" / "fetch_cb_klines.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8", mode="w"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("fetch_cb_klines")

DB_PATH  = Path(__file__).parent.parent / "jisilu.db"
START    = "2026-04-22"
END      = "2026-05-14"

# ── 目标转债 (从日志提取, 去重) ────────────────────────────
BONDS: List[Tuple[str, str]] = [
    ("超达转债",  "123187"), ("华兴转债",  "118003"), ("盈峰转债",  "127024"),
    ("瑞丰转债",  "123126"), ("帝欧转债",  "127047"), ("华特转债",  "118033"),
    ("翔丰转债",  "123225"), ("星球转债",  "118041"), ("博瑞转债",  "118004"),
    ("严牌转债",  "123243"), ("超声转债",  "127026"), ("洁美转债",  "128137"),
    ("京源转债",  "118016"), ("瑞科转债",  "118018"), ("金埔转债",  "123198"),
    ("利柏转债",  "111023"), ("艾迪转债",  "113644"), ("帝尔转债",  "123121"),
    ("永贵转债",  "123253"), ("佳力转债",  "113597"),
]

# ── Sina API helpers ──────────────────────────────────────
SINA_DAILY_URL  = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
SINA_MIN_URL    = SINA_DAILY_URL   # same endpoint, scale=15

Session = requests.Session()
Session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
})


def to_sina_code(code: str) -> str:
    code = code.strip().zfill(6)
    return f"sz{code}" if code.startswith(("1", "9")) else f"sh{code}"


def parse_sina_day(df: pd.DataFrame) -> pd.DataFrame:
    """处理日K DataFrame，列名可能是 'date'(akshare) 或 'day'(Sina直接API)"""
    if df.empty:
        return df
    # 统一列名
    if "date" in df.columns:
        df = df.rename(columns={"date": "trade_date"})
    elif "day" in df.columns:
        df = df.rename(columns={"day": "trade_date"})
    if "trade_date" not in df.columns:
        log.warning("  parse_sina_day: 无 'date'/'day' 列，现有列: %s", list(df.columns))
        return pd.DataFrame()
    # 统一转str
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[(df["trade_date"] >= START) & (df["trade_date"] <= END)]
    return df[["trade_date", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])


def parse_sina_min(df: pd.DataFrame) -> pd.DataFrame:
    """Sina分K: date_col='day' """
    if df.empty:
        return df
    df = df.rename(columns={"day": "trade_time"})
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["amount"] = pd.to_numeric(df.get("amount", 0), errors="coerce")
    # 过滤日期区间
    df = df[(df["trade_time"] >= f"{START} 09:00:00") & (df["trade_time"] <= f"{END} 16:00:00")]
    return df[["trade_time", "open", "high", "low", "close", "volume", "amount"]].dropna(subset=["close"])


def fetch_sina_daily(sina_code: str) -> pd.DataFrame:
    """使用akshare (含JS解密) 获取日K"""
    try:
        import akshare as ak
        df = ak.bond_zh_hs_cov_daily(symbol=sina_code)
        if df is None or df.empty:
            return pd.DataFrame()
        return parse_sina_day(df)
    except Exception as e:
        log.warning("  [日K] %s 失败: %s", sina_code, e)
        return pd.DataFrame()


def fetch_sina_15min(sina_code: str) -> pd.DataFrame:
    """Sina 15分K (datalen=300 ≈ 75个交易日，足够覆盖4/22-5/14)"""
    try:
        params = {"symbol": sina_code, "scale": "15", "ma": "no", "datalen": 300}
        r = Session.get(SINA_MIN_URL, params=params, timeout=15)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        return parse_sina_min(df)
    except Exception as e:
        log.warning("  [15分K] %s 失败: %s", sina_code, e)
        return pd.DataFrame()


# ── 数据库 ────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS klines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sec_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            amount REAL, turnover_rt REAL,
            source TEXT DEFAULT 'sina',
            UNIQUE(sec_code, trade_date, source)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS klines_15min (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sec_code TEXT NOT NULL,
            trade_time TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            source TEXT DEFAULT 'sina',
            UNIQUE(sec_code, trade_time, source)
        )
    """)
    conn.commit()
    return conn


UPSERT_DAILY = """
    INSERT INTO klines (sec_code,trade_date,open,high,low,close,volume,source)
    VALUES (?,?,?,?,?,?,?,'sina')
    ON CONFLICT(sec_code,trade_date,source)
    DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,
                   close=excluded.close,volume=excluded.volume
"""

UPSERT_15MIN = """
    INSERT INTO klines_15min (sec_code,trade_time,open,high,low,close,volume,amount,source)
    VALUES (?,?,?,?,?,?,?,?,'sina')
    ON CONFLICT(sec_code,trade_time,source)
    DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,
                   close=excluded.close,volume=excluded.volume,amount=excluded.amount
"""


def save_daily(conn, sec_code, df):
    if df.empty:
        return
    cur = conn.cursor()
    rows = [(sec_code, r.trade_date, r.open, r.high, r.low, r.close, r.volume)
            for r in df.itertuples()]
    cur.executemany(UPSERT_DAILY, rows)
    conn.commit()


def save_15min(conn, sec_code, df):
    if df.empty:
        return
    cur = conn.cursor()
    rows = [(sec_code, r.trade_time, r.open, r.high, r.low, r.close, r.volume, r.amount)
            for r in df.itertuples()]
    cur.executemany(UPSERT_15MIN, rows)
    conn.commit()


# ── 主流程 ────────────────────────────────────────────────
def main():
    log.info("═" * 60)
    log.info("B型策略K线获取 %s → %s", START, END)
    conn = init_db()

    stats = {"daily": 0, "min15": 0, "fail_daily": 0, "fail_min15": 0}

    for name, code in BONDS:
        sina = to_sina_code(code)
        log.info("[%s] %s(%s)", name, code, sina)

        # 日K
        df_d = fetch_sina_daily(sina)
        if not df_d.empty:
            save_daily(conn, code, df_d)
            stats["daily"] += 1
            log.info("  ✓ 日K %d 条  %s → %s",
                     len(df_d), df_d.iloc[0].trade_date, df_d.iloc[-1].trade_date)
        else:
            stats["fail_daily"] += 1
            log.warning("  ✗ 日K 无数据")

        time.sleep(0.3)

        # 15分K
        df_m = fetch_sina_15min(sina)
        if not df_m.empty:
            save_15min(conn, code, df_m)
            stats["min15"] += 1
            log.info("  ✓ 15分K %d 条  %s → %s",
                     len(df_m), df_m.iloc[0].trade_time[:16], df_m.iloc[-1].trade_time[:16])
        else:
            stats["fail_min15"] += 1
            log.warning("  ✗ 15分K 无数据")

        time.sleep(0.3)

    # 验证
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM klines WHERE source='sina'")
    n_daily = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT sec_code) FROM klines WHERE source='sina'")
    n_daily_bonds = cur.fetchone()[0]
    log.info("")
    log.info("═" * 60)
    log.info("入库结果:")
    log.info("  klines (日K)   : %d 条 / %d 只转债", n_daily, n_daily_bonds)
    try:
        cur.execute("SELECT COUNT(*) FROM klines_15min WHERE source='sina'")
        n_min = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT sec_code) FROM klines_15min WHERE source='sina'")
        n_min_bonds = cur.fetchone()[0]
        log.info("  klines_15min  : %d 条 / %d 只转债", n_min, n_min_bonds)
    except Exception as e:
        log.info("  klines_15min  : 错误 %s", e)

    log.info("═" * 60)
    conn.close()
    log.info("完成!")


if __name__ == "__main__":
    main()
