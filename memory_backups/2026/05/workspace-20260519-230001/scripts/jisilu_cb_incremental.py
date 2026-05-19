#!/usr/bin/env python3
"""
集思录可转债数据采集 - 增量分片版
每半小时执行一次，每次抓取一个批次，上一步成功才进入下一步
"""
import requests, json, sqlite3, time, sys, os
from datetime import datetime
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
KBZW_SESSION = "t8ulaqqcm77mpmkrcnltr74di2"
KBZW_USER_LOGIN = "7Obd08_P1ebax9aXXQ4dSg8qWRH0WPAmmrCW6c3q1e3Q6dvR1Yyllair186u0tyVrsWpqKbcw6WW2LLaotvN2Jqul9qnrJmcndbd3dPGpJ2vla-Sp7CUs46xtdLWoJqwo62Zq5qrrKWZnJ22tdfSlMbb8cvizdimqKaRkInL4uPN6OPqgsS1l6ijppGrgcvi45-tp5farJWgl7To0dzGy97XtOLgppepmKWqqZiJu6nIxsGVmdjgzduBvtzW49CZgbfh59jm0aaTqpilp6Goj6CBx9rbyuvVppepmKWqqZim1Mijqqmgp5ylkqSR"
DB_PATH = '/root/.openclaw/workspace/jisilu.db'
DATA_DIR = Path('/root/.openclaw/workspace/data')
DATA_DIR.mkdir(exist_ok=True)

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.jisilu.cn/",
    "X-Requested-With": "XMLHttpRequest",
}

# 状态文件
PROGRESS_FILE = DATA_DIR / "jisilu_fetch_progress.json"
LOCK_FILE     = DATA_DIR / "jisilu_fetch.lock"

# ── 步骤定义 ────────────────────────────────────────────
# Step0: 获取转债目录（一次）
# Step1-10: 分10批抓详情（每批35只，sleep 0.15s控频率）
SLICE_SIZE = 35
MAX_SLICES = 10

# ── 工具函数 ────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

def get_session():
    s = requests.Session()
    s.headers.update(BASE_HEADERS)
    s.cookies.set("kbzw__Session", KBZW_SESSION, domain="www.jisilu.cn", path="/")
    s.cookies.set("kbzw__user_login", KBZW_USER_LOGIN, domain="www.jisilu.cn", path="/")
    return s

def load_progress():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"step": 0, "phase": "list", "list_done": False, "slices": [False]*MAX_SLICES, "last_update": ""}

def save_progress(p):
    p["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    PROGRESS_FILE.write_text(json.dumps(p, ensure_ascii=False, indent=2))

def acquire_lock():
    """获取运行锁，防止并发重入"""
    if LOCK_FILE.exists():
        try:
            mtime = LOCK_FILE.stat().st_mtime
            if time.time() - mtime < 2400:  # 40分钟内不重复
                return False
        except: pass
    LOCK_FILE.write_text(f"{os.getpid()}|{time.time()}")
    return True

def release_lock():
    LOCK_FILE.unlink(missing_ok=True)

def init_tables(conn):
    """初始化表结构（幂等）"""
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    if "cb_bond_list" not in table_names:
        conn.execute("CREATE TABLE cb_bond_list (bond_id TEXT PRIMARY KEY, bond_nm TEXT, dblow REAL, premium_rt REAL, price REAL, volume REAL, shareholder_ratio REAL, fetched_at TEXT)")
    if "cb_fetch_log" not in table_names:
        conn.execute("CREATE TABLE cb_fetch_log (id INTEGER PRIMARY KEY AUTOINCREMENT, step INTEGER, phase TEXT, status TEXT, records INTEGER DEFAULT 0, error TEXT, run_at TEXT)")
    conn.commit()

def log_record(conn, step, phase, status, records=0, error=""):
    conn.execute("""
        INSERT INTO cb_fetch_log (step, phase, status, records, error, run_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [step, phase, status, records, error, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    conn.commit()

def count_in_db(conn, phase):
    if phase == "list":
        return conn.execute("SELECT COUNT(*) FROM cb_bond_list").fetchone()[0]
    return 0

# ── 核心抓取 ───────────────────────────────────────────
def fetch_list(s, conn):
    """Step0: 获取转债目录列表"""
    r = s.get("https://www.jisilu.cn/webapi/cb/list/", timeout=15)
    bonds = r.json().get("data", [])
    # 从autocomplete补充名称（仅20条，但能覆盖TOP债）
    name_map = {}
    try:
        r2 = s.get("https://www.jisilu.cn/data/cbnew_ajax/get_cb_autocomplete/", timeout=10)
        for it in json.loads(r2.text):
            name_map[it["bond_id"]] = it["bond_nm"]
    except Exception:
        pass
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for b in bonds:
        conn.execute("""
            INSERT OR REPLACE INTO cb_bond_list
            (bond_id, bond_nm, dblow, premium_rt, price, volume, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            b.get("bond_id",""),
            name_map.get(b.get("bond_id",""), "-"),
            b.get("dblow"),
            b.get("premium_rt"),
            b.get("price"),
            b.get("volume"),
            now
        ])
    conn.commit()
    return bonds

def fetch_detail(s, conn, bonds, sl):
    """Slice N: 抓取指定批次的转债详情"""
    batch = bonds[sl]
    records = 0
    for b in batch:
        bid = b.get("bond_id","")
        if not bid:
            continue
        try:
            r = s.get(f"https://www.jisilu.cn/data/convert_bond_detail/{bid}", timeout=10)
            html = r.text
            # 提取股东配售率
            import re
            m = re.search(r'股东配售率.*?class="data_val"[^>]*>([^<]+)<', html)
            if m:
                num_match = re.search(r'[\d.]+', m.group(1))
                sh = float(num_match.group()) if num_match else None
                conn.execute("UPDATE cb_bond_list SET shareholder_ratio=? WHERE bond_id=?", [sh, bid])
            time.sleep(0.15)  # 控频率
            records += 1
        except Exception as e:
            print(f"  detail error {bid}: {e}", file=sys.stderr)
    conn.commit()
    return records

def dingtalk_notify(msg):
    import re
    from urllib.request import Request, urlopen
    WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=82229b…c488"
    payload = json.dumps({
        'msgtype': 'markdown',
        'markdown': {'title': '📊 集思录采集', 'text': msg},
        'at': {'isAtAll': False}
    })
    try:
        req = Request(WEBHOOK, data=payload.encode('utf-8'),
                    headers={'Content-Type': 'application/json'})
        resp = urlopen(req, timeout=10)
        return json.loads(resp.read().decode())
    except Exception as e:
        return {'error': str(e)}

# ── 主逻辑 ─────────────────────────────────────────────
def main():
    if not acquire_lock():
        print("[SKIP] 任务正在执行中，跳过")
        return

    try:
        conn = get_conn()
        init_tables(conn)
        s = get_session()
        p = load_progress()

        print(f"[{datetime.now().strftime('%H:%M')}] 集思录采集 | 当前step={p['step']} phase={p['phase']}")

        # ── Step0: 获取目录 ──────────────────────────────
        if not p["list_done"]:
            try:
                bonds = fetch_list(s, conn)
                p["list_done"] = True
                p["step"] = 1
                save_progress(p)
                log_record(conn, 0, "list", "done", records=len(bonds))
                print(f"  Step0完成: 目录{len(bonds)}只")
                conn.close()
                return
            except Exception as e:
                log_record(conn, 0, "list", "failed", error=str(e))
                raise

        # ── Step1-10: 分批抓详情 ────────────────────────
        # 读取目录
        rows = conn.execute("SELECT bond_id, bond_nm FROM cb_bond_list ORDER BY dblow").fetchall()
        bonds = [{"bond_id": r[0], "bond_nm": r[1]} for r in rows]
        total = len(bonds)

        # 找到当前应执行的slice
        slice_idx = p["step"] - 1  # step 1-10 → slice 0-9
        if slice_idx < 0:
            slice_idx = 0

        # 跳过已完成的slice，但如果上一批次实际写入数据库数量=0则重新执行
        while slice_idx < MAX_SLICES:
            if not p["slices"][slice_idx]:
                break  # 找到未完成的
            slice_idx += 1

        if slice_idx >= MAX_SLICES:
            # 所有批次完成，重置
            p["step"] = 0
            p["phase"] = "list"
            p["list_done"] = False
            p["slices"] = [False] * MAX_SLICES
            save_progress(p)
            print("  [完成] 所有批次完毕，等待明天重新开始")
            conn.close()
            return

        sl = slice(slice_idx * SLICE_SIZE, (slice_idx + 1) * SLICE_SIZE)
        batch = bonds[sl]
        if not batch:
            p["slices"][slice_idx] = True
            save_progress(p)
            slice_idx += 1
            conn.close()
            return

        print(f"  执行 Slice{slice_idx+1}: bonds[{sl.start}:{sl.stop}] 共{len(batch)}只")

        try:
            records = fetch_detail(s, conn, bonds, sl)
            p["slices"][slice_idx] = True
            p["step"] = slice_idx + 2  # 下一个slice
            save_progress(p)
            log_record(conn, slice_idx+1, f"slice{slice_idx+1}", "done", records=records)
            print(f"  Slice{slice_idx+1}完成: 写库{records}条")

            # 全部完成通知
            if all(p["slices"]):
                msg = f"## ✅ 集思录数据采集完成\n\n| 项目 | 内容 |\n|------|------|\n| **总转债数** | {total} |\n| **采集时间** | {datetime.now().strftime('%Y-%m-%d %H:%M')} |\n| **状态** | 全部10批次完成 |\n\n> 明天自动重新开始"
                dingtalk_notify(msg)

        except Exception as e:
            log_record(conn, slice_idx+1, f"slice{slice_idx+1}", "failed", error=str(e))
            print(f"  Slice{slice_idx+1}失败: {e}")
            raise

        conn.close()

    finally:
        release_lock()

if __name__ == "__main__":
    main()