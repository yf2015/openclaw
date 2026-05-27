#!/usr/bin/env python3
"""
集思录 JSON → SQLite 迁移脚本
将所有 JSON 数据文件迁移到 jisilu.db
支持增量更新（upsert）
"""
import json, sqlite3, os, sys
from datetime import datetime

DB_PATH = '/root/.openclaw/workspace/jisilu.db'
BACKUP_DIR = '/root/.openclaw/workspace/backup/json_20260514'

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

def utc_now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# ─────────────────────────────────────────────────────────
# 1. 迁移 jisilu_cb_data.json → securities + daily_quotes
# ─────────────────────────────────────────────────────────
def migrate_cb_data(conn):
    path = f'{BACKUP_DIR}/jisilu_cb_data.json'
    with open(path) as f:
        data = json.load(f)

    bonds = data['bonds']
    index_data = data['index']
    fetch_time = data.get('fetch_time', utc_now())

    rows = 0
    for b in bonds:
        code = b['债券代码']
        name = b['债券名称']

        # securities upsert
        conn.execute("""
            INSERT INTO securities (sec_code, sec_name, sec_type, data_source, updated_at)
            VALUES (?, ?, 'cb', 'jisilu', ?)
            ON CONFLICT(sec_code, sec_type) DO UPDATE SET
                sec_name = excluded.sec_name, updated_at = excluded.updated_at
        """, [code, name, utc_now()])

        # daily_quotes upsert（使用 last_update 作为 trade_date）
        last_update = b.get('最后更新') or ''
        trade_date = last_update[:10] if last_update and len(last_update) >= 10 else datetime.now().strftime('%Y-%m-%d')

        conn.execute("""
            INSERT INTO daily_quotes (
                sec_code, trade_date, close, premium_rt, dblow, ytm_rt,
                turnover_rt, volume, amount, convert_value, bond_value
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sec_code, trade_date) DO UPDATE SET
                close = excluded.close, premium_rt = excluded.premium_rt,
                dblow = excluded.dblow, ytm_rt = excluded.ytm_rt,
                turnover_rt = excluded.turnover_rt, volume = excluded.volume,
                amount = excluded.amount, convert_value = excluded.convert_value,
                bond_value = excluded.bond_value
        """, [
            code, trade_date,
            b.get('现价'), b.get('溢价率%'), b.get('双低'),
            b.get('YTM'), b.get('换手率%'),
            b.get('成交额(万)'), None,  # amount 原始数据无
            b.get('转股价值'), b.get('债现价')
        ])
        rows += 1

    conn.commit()
    print(f"  ✓ jisilu_cb_data: {rows} 条转债记录迁移完成")
    return rows

# ─────────────────────────────────────────────────────────
# 2. 迁移 jisilu_redeem_analysis.json → redeem_samples + klines
# ─────────────────────────────────────────────────────────
def migrate_redeem_analysis(conn):
    path = f'{BACKUP_DIR}/jisilu_redeem_analysis.json'
    with open(path) as f:
        data = json.load(f)

    total = 0
    for label_key, label_val in [('强赎样本', 'redeem'), ('不强赎样本', 'no_redeem')]:
        records = data.get(label_key, [])
        for rec in records:
            code = rec.get('bond_id', '')
            if not code:
                continue

            # securities 记录
            conn.execute("""
                INSERT INTO securities (sec_code, sec_name, sec_type, data_source, updated_at)
                VALUES (?, ?, 'cb', 'jisilu', ?)
                ON CONFLICT(sec_code, sec_type) DO UPDATE SET updated_at = excluded.updated_at
            """, [code, rec.get('bond_nm', '-'), utc_now()])

            # redeem_samples upsert
            features_json = json.dumps(rec.get('features', {}), ensure_ascii=False)
            conn.execute("""
                INSERT INTO redeem_samples (sec_code, label, announce_date, title, url, features)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(sec_code, label) DO UPDATE SET
                    announce_date = excluded.announce_date,
                    title = excluded.title, url = excluded.url, features = excluded.features
            """, [code, label_val, rec.get('announce_date'), rec.get('title'),
                  rec.get('url'), features_json])

            # klines 写入
            for kline in rec.get('klines', []):
                conn.execute("""
                    INSERT INTO klines (sec_code, trade_date, open, high, low, close, volume, amount, turnover_rt, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'jisilu')
                    ON CONFLICT(sec_code, trade_date, source) DO UPDATE SET
                        open = excluded.open, high = excluded.high, low = excluded.low,
                        close = excluded.close, volume = excluded.volume,
                        amount = excluded.amount, turnover_rt = excluded.turnover_rt
                """, [code, kline.get('trade_date'), kline.get('open'),
                      kline.get('high'), kline.get('low'), kline.get('close'),
                      kline.get('volume'), kline.get('amount'), kline.get('turnover_rt')])
            total += 1

    conn.commit()
    print(f"  ✓ jisilu_redeem_analysis: {total} 条样本迁移完成（含K线）")
    return total

# ─────────────────────────────────────────────────────────
# 3. 迁移 jisilu_maturity_analysis.json → maturity_records
# ─────────────────────────────────────────────────────────
def migrate_maturity_analysis(conn):
    path = f'{BACKUP_DIR}/jisilu_maturity_analysis.json'
    with open(path) as f:
        data = json.load(f)

    records = data.get('详细记录', [])
    count = 0
    for rec in records:
        code = rec.get('bond_id', '')
        if not code:
            continue

        announce_date_val = rec.get('announce_date')
        announce_date_str = announce_date_val[:10] if announce_date_val and len(str(announce_date_val)) >= 10 else None

        conn.execute("""
            INSERT INTO securities (sec_code, sec_name, sec_type, maturity_date, data_source, updated_at)
            VALUES (?, ?, 'cb', ?, 'jisilu', ?)
            ON CONFLICT(sec_code, sec_type) DO UPDATE SET
                maturity_date = excluded.maturity_date, updated_at = excluded.updated_at
        """, [code, announce_date_str, rec.get('maturity_date'), utc_now()])

        conn.execute("""
            INSERT INTO maturity_records (
                sec_code, announce_date, maturity_date, trade_date,
                remaining_years, price, return_pct, volume_ratio,
                is_strong_return, is_strong_volume
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sec_code, trade_date) DO UPDATE SET
                price = excluded.price, return_pct = excluded.return_pct,
                volume_ratio = excluded.volume_ratio,
                is_strong_return = excluded.is_strong_return,
                is_strong_volume = excluded.is_strong_volume
        """, [
            code, announce_date_str,
            rec.get('maturity_date'), rec.get('trade_date'),
            rec.get('remaining_years'), rec.get('price'), rec.get('return_pct'),
            rec.get('volume_ratio'),
            1 if rec.get('is_strong_return') else 0,
            1 if rec.get('is_strong_volume') else 0
        ])
        count += 1

    conn.commit()
    print(f"  ✓ jisilu_maturity_analysis: {count} 条到期记录迁移完成")
    return count

# ─────────────────────────────────────────────────────────
# 4. 迁移 jisilu_cb_enriched.json → securities + daily_quotes（覆盖）
# ─────────────────────────────────────────────────────────
def migrate_cb_enriched(conn):
    path = f'{BACKUP_DIR}/jisilu_cb_enriched.json'
    with open(path) as f:
        data = json.load(f)

    bonds = data.get('bonds', [])
    count = 0
    for b in bonds:
        code = b.get('债券代码') or b.get('bond_id', '')
        if not code:
            continue

        trade_date = b.get('trade_date') or b.get('最后更新', '')[:10]
        if not trade_date or len(str(trade_date)) < 8:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        conn.execute("""
            INSERT INTO securities (sec_code, sec_name, sec_type, data_source, updated_at)
            VALUES (?, ?, 'cb', 'jisilu', ?)
            ON CONFLICT(sec_code, sec_type) DO UPDATE SET
                sec_name = excluded.sec_name, updated_at = excluded.updated_at
        """, [code, b.get('债券名称', b.get('bond_nm', '-')), utc_now()])

        conn.execute("""
            INSERT INTO daily_quotes (
                sec_code, trade_date, close, premium_rt, dblow, ytm_rt,
                turnover_rt, volume, amount, convert_value, bond_value
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sec_code, trade_date) DO UPDATE SET
                close = excluded.close, premium_rt = excluded.premium_rt,
                dblow = excluded.dblow, ytm_rt = excluded.ytm_rt,
                turnover_rt = excluded.turnover_rt, volume = excluded.volume,
                amount = excluded.amount, convert_value = excluded.convert_value,
                bond_value = excluded.bond_value
        """, [
            code, trade_date,
            b.get('现价') or b.get('close'),
            b.get('溢价率%') or b.get('premium_rt'),
            b.get('双低') or b.get('dblow'),
            b.get('YTM') or b.get('ytm_rt'),
            b.get('换手率%') or b.get('turnover_rt'),
            b.get('成交额(万)') or b.get('volume'),
            b.get('amount'),
            b.get('转股价值') or b.get('convert_value'),
            b.get('债现价') or b.get('bond_value')
        ])
        count += 1

    conn.commit()
    print(f"  ✓ jisilu_cb_enriched: {count} 条增强数据迁移完成")
    return count

# ─────────────────────────────────────────────────────────
# 5. 迁移 jisilu_board_daily.json → index_stats
# ─────────────────────────────────────────────────────────
def migrate_board_daily(conn):
    path = f'{BACKUP_DIR}/jisilu_board_daily.json'
    with open(path) as f:
        data = json.load(f)

    records = data.get('records', [])
    count = 0
    for rec in records:
        trade_date = rec.get('trade_date')
        if not trade_date:
            continue

        conn.execute("""
            INSERT INTO index_stats (stat_date, index_name, temperature, avg_price, avg_premium_rt, avg_dblow, avg_ytm_rt, cb_count)
            VALUES (?, 'jisilu_cb', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stat_date) DO UPDATE SET
                temperature = excluded.temperature, avg_price = excluded.avg_price,
                avg_premium_rt = excluded.avg_premium_rt, avg_dblow = excluded.avg_dblow,
                avg_ytm_rt = excluded.avg_ytm_rt, cb_count = excluded.cb_count
        """, [
            trade_date,
            rec.get('temperature'),
            rec.get('avg_price'),
            rec.get('avg_premium_rt'),
            rec.get('avg_dblow'),
            rec.get('avg_ytm_rt'),
            rec.get('cb_count')
        ])
        count += 1

    conn.commit()
    print(f"  ✓ jisilu_board_daily: {count} 条指数统计迁移完成")
    return count

# ─────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print("集思录 JSON → SQLite 迁移")
    print(f"数据库: {DB_PATH}")
    print(f"备份源: {BACKUP_DIR}")
    print(f"{'='*60}\n")

    conn = get_conn()
    start = datetime.now()

    migrate_cb_data(conn)
    migrate_redeem_analysis(conn)
    migrate_maturity_analysis(conn)
    migrate_cb_enriched(conn)
    migrate_board_daily(conn)

    elapsed = (datetime.now() - start).total_seconds()

    # 统计
    cur = conn.execute("SELECT COUNT(*) FROM securities")
    sec_count = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM daily_quotes")
    quote_count = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM klines")
    kline_count = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM redeem_samples")
    redeem_count = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM maturity_records")
    maturity_count = cur.fetchone()[0]

    print(f"\n{'='*60}")
    print(f"迁移完成！耗时 {elapsed:.1f} 秒")
    print(f"  securities:     {sec_count} 条")
    print(f"  daily_quotes:   {quote_count} 条")
    print(f"  klines:         {kline_count} 条")
    print(f"  redeem_samples: {redeem_count} 条")
    print(f"  maturity_records: {maturity_count} 条")
    print(f"{'='*60}\n")

    conn.close()

if __name__ == '__main__':
    main()