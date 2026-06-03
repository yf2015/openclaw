-- 001_initial_schema.sql
-- 集思录可转债数据库 - 初始结构
-- 兼容多数据源：转债、股票、LOF指数等

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;
PRAGMA temp_store = MEMORY;
PRAGMA auto_vacuum = INCREMENTAL;

-- ============================================================
-- 证券主表（债券/股票/LOF等通用）
-- ============================================================
CREATE TABLE IF NOT EXISTS securities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sec_code        TEXT NOT NULL UNIQUE,           -- 证券代码（如 123236, 600519）
    sec_name        TEXT NOT NULL,                  -- 证券名称
    sec_type        TEXT NOT NULL CHECK(sec_type IN (
                    'cb',       -- 可转债
                    'stock',    -- 正股/股票
                    'lof',      -- LOF基金
                    'index',    -- 指数
                    'bond'      -- 纯债
                )),
    listed_date     TEXT,                           -- 上市日期 (YYYY-MM-DD)
    delisted_date    TEXT,                           -- 退市日期，为空表示未退市
    underlying_code  TEXT,                           -- 正股代码（转债填写）
    underlying_name  TEXT,                           -- 正股名称（转债填写）
    maturity_date    TEXT,                           -- 到期日期（转债用）
    rating          TEXT,                           -- 评级
    face_value      REAL DEFAULT 100.0,             -- 面值，默认100
    currency        TEXT DEFAULT 'CNY',
    data_source     TEXT DEFAULT 'jisilu',          -- 数据来源
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(sec_code, sec_type)
);

CREATE INDEX IF NOT EXISTS idx_securities_type ON securities(sec_type);
CREATE INDEX IF NOT EXISTS idx_securities_underlying ON securities(underlying_code);

-- ============================================================
-- 可转债专用属性
-- ============================================================
CREATE TABLE IF NOT EXISTS cb_properties (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sec_code            TEXT NOT NULL REFERENCES securities(sec_code) ON DELETE CASCADE,
    convert_price       REAL,                           -- 转股价
    convert_ratio      REAL,                           -- 转股比例
    trigger_up          REAL,                           -- 强赎触发价
    trigger_down       REAL,                           -- 下修触发价
    back_to_price      REAL,                           -- 回售触发价
    coupon_records     TEXT,                           -- 票息记录 (JSON for flexibility)
    special_clause     TEXT,                           -- 特殊条款说明
    updated_at         TEXT DEFAULT (datetime('now')),
    UNIQUE(sec_code)
);

-- ============================================================
-- 日线行情（所有证券通用）
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_quotes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sec_code    TEXT NOT NULL,
    trade_date  TEXT NOT NULL,                        -- 交易日期 YYYY-MM-DD
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,                                 -- 收盘价
    volume      REAL,                                  -- 成交量
    amount      REAL,                                 -- 成交额（元）
    turnover_rt REAL,                                 -- 换手率%
    premium_rt  REAL,                                 -- 溢价率（转债）
    dblow       REAL,                                 -- 双低值（转债）
    ytm_rt      REAL,                                 -- 到期收益率（转债）
    bond_value  REAL,                                 -- 债现价（转债）
    convert_value REAL,                               -- 转股价值（转债）
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(sec_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_quotes_date ON daily_quotes(trade_date);
CREATE INDEX IF NOT EXISTS idx_quotes_code ON daily_quotes(sec_code);
CREATE INDEX IF NOT EXISTS idx_quotes_dblow ON daily_quotes(dblow) WHERE dblow IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quotes_turnover ON daily_quotes(turnover_rt) WHERE turnover_rt IS NOT NULL;

-- ============================================================
-- 指数温度（每日汇总）
-- ============================================================
CREATE TABLE IF NOT EXISTS index_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_date       TEXT NOT NULL UNIQUE,             -- 统计日期 YYYY-MM-DD
    index_name      TEXT NOT NULL DEFAULT 'jisilu_cb',
    temperature     REAL,                             -- 温度
    avg_price       REAL,                             -- 平均价格
    avg_premium_rt  REAL,                             -- 平均溢价率
    avg_dblow       REAL,                             -- 双低均值
    avg_ytm_rt      REAL,                             -- YTM均值
    cb_count        INTEGER,                          -- 转债数量
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- 强赎/不强赎 分析样本
-- ============================================================
CREATE TABLE IF NOT EXISTS redeem_samples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sec_code        TEXT NOT NULL REFERENCES securities(sec_code),
    label           TEXT NOT NULL CHECK(label IN ('redeem', 'no_redeem')),
    announce_date   TEXT,                             -- 公告日期
    title           TEXT,                             -- 公告标题
    url             TEXT,                             -- 公告链接
    redeem_date      TEXT,                             -- 强赎日期（label=redeem时）
    last_price      REAL,                             -- 强赎前的最后价格
    features        TEXT,                             -- 特征 JSON（区间涨跌幅、波动率等）
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(sec_code, label)
);

-- ============================================================
-- K线数据（用于技术分析）
-- ============================================================
CREATE TABLE IF NOT EXISTS klines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sec_code    TEXT NOT NULL,
    trade_date  TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    turnover_rt REAL,
    source      TEXT DEFAULT 'jisilu',
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(sec_code, trade_date, source)
);

CREATE INDEX IF NOT EXISTS idx_klines_date ON klines(trade_date);
CREATE INDEX IF NOT EXISTS idx_klines_code ON klines(sec_code);

-- ============================================================
-- 到期分析详细记录
-- ============================================================
CREATE TABLE IF NOT EXISTS maturity_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    sec_code            TEXT NOT NULL REFERENCES securities(sec_code),
    announce_date       TEXT,
    maturity_date       TEXT,
    trade_date          TEXT NOT NULL,
    remaining_years     REAL,
    price               REAL,
    return_pct          REAL,                         -- 收益率%
    volume_ratio        REAL,                         -- 成交量比
    is_strong_return    INTEGER,                      -- 强势日标记 (0/1)
    is_strong_volume    INTEGER,                      -- 放量日标记 (0/1)
    created_at          TEXT DEFAULT (datetime('now')),
    UNIQUE(sec_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_maturity_date ON maturity_records(trade_date);
CREATE INDEX IF NOT EXISTS idx_maturity_code ON maturity_records(sec_code);

-- ============================================================
-- 数据源追踪
-- ============================================================
CREATE TABLE IF NOT EXISTS data_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name     TEXT NOT NULL UNIQUE,
    source_url      TEXT,
    description     TEXT,
    enabled         INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO data_sources (source_name, source_url, description) VALUES
    ('jisilu', 'https://www.jisilu.cn', '集思录可转债数据');

-- ============================================================
-- 迁移记录
-- ============================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT DEFAULT (datetime('now'))
);