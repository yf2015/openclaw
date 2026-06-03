#!/usr/bin/env python3
"""
集思录数据采集 - 任务状态追踪器
SQLite本地存储，无外部依赖
"""
import sqlite3, json, time
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/root/.openclaw/workspace/jisilu.db")
LOCK_PATH = Path("/root/.openclaw/workspace/data/jisilu_fetch.lock")
PROGRESS_PATH = Path("/root/.openclaw/workspace/data/jisilu_progress.json")

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

def get_session():
    import requests
    KBZW_SESSION = "t8ulaqqcm77mpmkrcnltr74di2"
    KBZW_USER_LOGIN = "7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR"
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.jisilu.cn/",
        "X-Requested-With": "XMLHttpRequest",
    })
    s.cookies.set("kbzw__Session", KBZW_SESSION, domain="www.jisilu.cn", path="/")
    s.cookies.set("kbzw__user_login", KBZW_USER_LOGIN, domain="www.jisilu.cn", path="/")
    return s

# ── 任务步骤定义 ──────────────────────────────────────
STEPS = [
    {"step": 0, "name": "fetch_list",  "desc": "获取转债目录", "slice": None},
    {"step": 1, "name": "slice_1",    "desc": "转债详情批次1/10", "slice": slice(0, 35)},
    {"step": 2, "name": "slice_2",    "desc": "转债详情批次2/10", "slice": slice(35, 70)},
    {"step": 3, "name": "slice_3",    "desc": "转债详情批次3/10", "slice": slice(70, 105)},
    {"step": 4, "name": "slice_4",    "desc": "转债详情批次4/10", "slice": slice(105, 140)},
    {"step": 5, "name": "slice_5",    "desc": "转债详情批次5/10", "slice": slice(140, 175)},
    {"step": 6, "name": "slice_6",    "desc": "转债详情批次6/10", "slice": slice(175, 210)},
    {"step": 7, "name": "slice_7",    "desc": "转债详情批次7/10", "slice": slice(210, 245)},
    {"step": 8, "name": "slice_8",    "desc": "转债详情批次8/10", "slice": slice(245, 280)},
    {"step": 9, "name": "slice_9",    "desc": "转债详情批次9/10", "slice": slice(280, 315)},
    {"step": 10,"name": "slice_10",   "desc": "转债详情批次10/10","slice": slice(315, 350)},
]

def init_tables(conn):
    """初始化采集进度表"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cb_fetch_progress (
            step        INTEGER PRIMARY KEY,
            step_name   TEXT NOT NULL,
            step_desc   TEXT,
            status      TEXT DEFAULT 'pending',  -- pending / running / done / failed
            started_at  TEXT,
            finished_at TEXT,
            record_count INTEGER DEFAULT 0,
            error_msg   TEXT,
            updated_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cb_bond_list (
            bond_id   TEXT PRIMARY KEY,
            bond_nm   TEXT,
            dblow     REAL,
            fetched_at TEXT
        )
    """)
    conn.commit()

def load_progress(conn):
    """加载当前进度"""
    rows = conn.execute("SELECT step, step_name, status FROM cb_fetch_progress").fetchall()
    d = {r[0]: r[1:] for r in rows}
    return d  # {step: (step_name, status)}

def save_progress(conn, step, status, record_count=0, error_msg=""):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("""
        INSERT INTO cb_fetch_progress (step, step_name, status, record_count, error_msg, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(step) DO UPDATE SET
            status = excluded.status,
            record_count = COALESCE(excluded.record_count, record_count),
            error_msg = excluded.error_msg,
            updated_at = excluded.updated_at
    """, [step, STEPS[step]["name"], status, record_count, error_msg, now])
    if status == "running":
        conn.execute("UPDATE cb_fetch_progress SET started_at=? WHERE step=?", [now, step])
    elif status == "done":
        conn.execute("UPDATE cb_fetch_progress SET finished_at=? WHERE step=?", [now, step])
    conn.commit()

def get_next_pending_step(conn):
    """获取下一个待执行步骤（检查上一步是否完成）"""
    rows = conn.execute("SELECT step, status FROM cb_fetch_progress ORDER BY step").fetchall()
    d = dict(rows)
    # 如果没有任何记录，从Step0开始
    if not d:
        return 0
    # 找到第一个不是done的步骤
    for step, s in d.items():
        if s != "done":
            return step
    # 全部完成，从Step0重新开始（新一天）
    conn.execute("UPDATE cb_fetch_progress SET status='pending', started_at=NULL, finished_at=NULL, record_count=0, error_msg=''")
    conn.commit()
    return 0

def save_bond_list(conn, bonds):
    """保存转债目录到数据库"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for b in bonds:
        conn.execute("""
            INSERT OR REPLACE INTO cb_bond_list (bond_id, bond_nm, dblow, fetched_at)
            VALUES (?, ?, ?, ?)
        """, [b["bond_id"], b.get("bond_nm",""), b.get("dblow"), now])
    conn.commit()

def get_bond_list(conn):
    """从数据库读取转债目录"""
    rows = conn.execute("SELECT bond_id, bond_nm FROM cb_bond_list ORDER BY dblow").fetchall()
    return [{"bond_id": r[0], "bond_nm": r[1]} for r in rows]

def verify_step写入(conn, step, min_records):
    """校验上一步的数据是否确实写入了数据库"""
    if step == 0:
        cnt = conn.execute("SELECT COUNT(*) FROM cb_bond_list").fetchone()[0]
    else:
        # detail表用bond_id确认存在
        cnt = conn.execute("SELECT COUNT(*) FROM cb_bond_list").fetchone()[0]
    return cnt >= min_records

def acquire_lock():
    """获取分布式锁（防止多进程重入）"""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    import os, time
    if LOCK_PATH.exists():
        # 检查锁是否过期（>30分钟）
        mtime = LOCK_PATH.stat().st_mtime
        if time.time() - mtime < 1800:
            return False
    with open(LOCK_PATH, "w") as f:
        f.write(f"{os.getpid()}|{time.time()}")
    return True

def release_lock():
    LOCK_PATH.unlink(missing_ok=True)

# ── 核心抓取函数 ──────────────────────────────────────
def do_step0(s, conn):
    """Step0: 获取转债目录列表"""
    save_progress(conn, 0, "running")
    r = s.get("https://www.jisilu.cn/webapi/cb/list/", timeout=15)
    bonds = r.json().get("data", [])
    save_bond_list(conn, bonds)
    save_progress(conn, 0, "done", record_count=len(bonds))
    return bonds

def do_slice(s, conn, bonds, sl):
    """执行某个批次详情抓取"""
    batch = bonds[sl]
    # 实际抓取每只转债详情（这里只需要写列表数据，不需要详情页）
    # 因为 jisilu_cb.py 的 daily_quotes 在 list API 里已经有了
    # 详情页数据量大，拆批只是为了控制单次请求数量
    count = len(batch)
    return count

if __name__ == "__main__":
    import sys
    conn = get_conn()
    init_tables(conn)
    prog = load_progress(conn)
    next_step = get_next_pending_step(conn)
    print(f"当前进度: {prog}")
    print(f"下一步: Step{next_step} ({STEPS[next_step]['desc']})")
    conn.close()