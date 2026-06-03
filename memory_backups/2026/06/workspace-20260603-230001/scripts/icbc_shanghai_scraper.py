#!/usr/bin/env python3
"""
工商银行上海网点数据采集器
数据源: 上海本地宝 (sh.bendibao.com) ICBC网点列表页 AJAX接口
      → /wangdian/zhuanti_list.php?action=ajax
每次抓取100条，全量880条，9次请求
"""
import json, re, sqlite3, time
from datetime import datetime
from pathlib import Path
import urllib.parse

# ── 配置 ─────────────────────────────────────────────────
DB_PATH    = Path("/home/www/toolbox-api/data/bank_branches.db")
OUT_JSON   = Path("/home/www/toolbox-api/data/icbc_shanghai_branches.json")
BASE_URL   = "http://sh.bendibao.com/wangdian/zhuanti_list.php"
PAGESIZE   = 100
TOTAL_EST  = 880   # 首页返回的 count 字段
HEADERS    = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "http://sh.bendibao.com/cyfw/wangdian/236.shtm",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

# ── 上海区划映射（从地址中提取区名）──────────────────────
DISTRICT_KEYWORDS = [
    "浦东新区","黄浦区","静安区","徐汇区","长宁区","普陀区","虹口区",
    "杨浦区","闵行区","宝山区","嘉定区","松江区","青浦区","奉贤区",
    "金山区","崇明区",
]

def extract_district(address: str) -> str:
    """从地址字符串中提取区名"""
    for d in DISTRICT_KEYWORDS:
        if d in address:
            return d
    return "其他"

# ── 解析 AJAX 返回的 HTML ─────────────────────────────────
def parse_page(html: str) -> list:
    """
    解析 AJAX HTML，提取网点名称和地址
    每条记录结构:
      <ul class="show">
        <li class="li1"><a title="XXX支行" ...>XXX支行</a></li>
        <li class="li2"><a title="上海市XX区...">上海市XX区...</a></li>
        <li class="li4"><a ...>（电话，空）</a></li>
      </ul>
    """
    results = []
    # 匹配所有 <ul class="show">...<li class="li1">...<a title="名称" href="...">名称</a>...
    #                            <li class="li2">...<a title="地址" href="...">地址</a>...
    #                            <li class="li4">...<a>电话</a>...
    #                         </ul>
    ul_blocks = re.findall(r'<ul[^>]*>(.*?)</ul>', html, re.DOTALL)
    for block in ul_blocks:
        name = re.search(r'<li class="li1">.*?title="([^"]+)"', block)
        addr = re.search(r'<li class="li2">.*?title="([^"]+)"', block)
        # 电话在 li4，但通常为空
        tel  = re.search(r'<li class="li4"><a[^>]*>([^<]*)</a></li>', block)

        n = name.group(1).strip() if name else ""
        a = addr.group(1).strip() if addr else ""
        t = tel.group(1).strip() if tel else ""

        if n:
            results.append({
                "name":    n,
                "address": a,
                "phone":   t,
                "district": extract_district(a),
            })
    return results

# ── 爬取全量数据 ─────────────────────────────────────────
def fetch_all() -> list:
    all_branches = []
    page = 1
    total = 0

    while True:
        ts = int(time.time() * 1000)
        params = {
            "action": "ajax",
            "t": str(ts),
            "page": str(page),
            "id":    "",
            "bid":   "236",
            "classid": "230",
            "areaid":  "",
            "pathurl": "",
        }
        url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
        print(f"  抓取第 {page} 页...", end=" ", flush=True)

        import requests as _req
        try:
            resp = _req.get(url, headers=HEADERS, timeout=15)
            resp.encoding = "utf-8"
            raw = resp.text
        except Exception as e:
            print(f"失败: {e}")
            break
        # JSON 包裹：{"size":N,"count":N,"html":"<ul>..."}
        try:
            data = json.loads(raw)
            raw_html = data.get("html", "")
            count_m  = re.search(r'"count"\s*:\s*(\d+)', raw)
        except Exception:
            raw_html = raw
            count_m  = re.search(r'"count"\s*:\s*(\d+)', raw)

        if count_m and page == 1:
            total = int(count_m.group(1))
            print(f"总计 {total} 条")

        branches = parse_page(raw_html)
        if not branches:
            print("无数据，停止")
            break

        print(f"获得 {len(branches)} 条")
        all_branches.extend(branches)
        page += 1

        # 安全间隔
        time.sleep(0.5)

        # 已抓完
        if total > 0 and len(all_branches) >= total:
            print(f"抓取完成: {len(all_branches)}/{total}")
            break

        if page > 30:  # 兜底
            print("页数超限，停止")
            break

        if len(all_branches) >= total:
            print(f"抓取完成: {len(all_branches)}/{total}")
            break

        if page > 30:  # 兜底
            print("页数超限，停止")
            break

    return all_branches

# ── 去重 ─────────────────────────────────────────────────
def dedup(branches: list) -> list:
    seen = set()
    result = []
    for b in branches:
        key = b["name"]
        if key not in seen:
            seen.add(key)
            result.append(b)
    return result

# ── 保存到 SQLite ────────────────────────────────────────
def save_to_db(branches: list):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 建表（兼容原有 schema）
    c.execute("""
        CREATE TABLE IF NOT EXISTS bank_branches (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name        TEXT,
            city             TEXT,
            district         TEXT,
            address          TEXT,
            phone_lobby      TEXT,
            phone_counter    TEXT,
            phone_office     TEXT,
            manager_name     TEXT,
            manager_phone    TEXT,
            weekday_hours    TEXT,
            saturday_hours   TEXT,
            sunday_hours     TEXT,
            created_at       TEXT
        )
    """)

    # 写 ICBC 上海数据（先删后插）
    c.execute("DELETE FROM bank_branches WHERE bank_name='工商银行' AND city='上海'")

    for b in branches:
        c.execute("""
            INSERT INTO bank_branches
                (bank_name, city, district, address,
                 phone_lobby, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "工商银行",
            "上海",
            b["district"],
            b["address"],
            b["phone"] or None,
            datetime.now().isoformat(),
        ))

    conn.commit()
    c.execute("SELECT COUNT(*) FROM bank_branches WHERE bank_name='工商银行' AND city='上海'")
    count = c.fetchone()[0]
    conn.close()
    print(f"  SQLite: {DB_PATH} ({count} 条 ICBC 上海网点)")
    return count

# ── 主流程 ────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("ICBC 上海网点数据采集")
    print("=" * 50)

    branches = fetch_all()
    branches = dedup(branches)
    print(f"\n去重后: {len(branches)} 条")

    count = save_to_db(branches)

    # 保存原始 JSON 备份
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(branches, f, ensure_ascii=False, indent=2)
    print(f"  JSON备份: {OUT_JSON}")

    print(f"\n✅ 完成！共写入 {count} 条工商银行上海网点")
