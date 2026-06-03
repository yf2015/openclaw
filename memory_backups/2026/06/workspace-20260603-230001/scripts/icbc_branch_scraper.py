#!/usr/bin/env python3
"""
ICBC上海网点爬虫
使用 Playwright 渲染 ICBC 网点查询页，提取所有网点基础信息
"""
import asyncio, json, re, sqlite3
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright

# ── 输出配置 ──────────────────────────────────────────────
DB_PATH = Path("/home/www/toolbox-api/data/icbc_branches.db")
OUT_JSON = Path("/home/www/toolbox-api/data/icbc_branches.json")

# ── ICBC 网点查询页 ────────────────────────────────────────
ICBC_BRANCH_URL = "https://www.icbc.com.cn/webpage/branch/"

# ── 解析字段（从 Vue 组件 data 中提取）────────────────────
async def scrape_icbc_branches():
    branches = []
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = await context.new_page()

        # 捕获 console 错误
        page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)

        print("🌐 打开 ICBC 网点页面...")
        await page.goto(ICBC_BRANCH_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)  # 等待 Vue 渲染

        # ── 选择「上海」 ─────────────────────────────────
        print("  选择上海市...")
        try:
            # 点击省份下拉
            await page.click(".el-select", timeout=5000)
            await asyncio.sleep(1)
            # 输入搜索
            await page.fill(".el-select-dropdown__search-input", "上海")
            await asyncio.sleep(1)
            # 点击第一个选项
            items = page.locator(".el-select-dropdown__item")
            count = await items.count()
            if count > 0:
                await items.first.click()
                await asyncio.sleep(2)
                print(f"  已选择上海，共找到 {count} 个候选")
        except Exception as e:
            print(f"  省份选择失败（继续尝试）: {e}")

        # ── 点击搜索 ────────────────────────────────────
        try:
            search_btn = page.locator("button:has-text('搜索'), .el-button:has-text('搜索')")
            if await search_btn.count() > 0:
                await search_btn.first.click()
                print("  已点击搜索")
                await asyncio.sleep(3)
        except Exception as e:
            print(f"  搜索按钮点击失败: {e}")

        # ── 提取数据 ────────────────────────────────────
        print("  开始提取网点数据...")

        # 尝试从 Vue 组件提取数据
        data = await page.evaluate("""
            () => {
                // 尝试找 Vue 实例
                const els = document.querySelectorAll('[class*="branch"], [class*="wangdian"]');
                // 打印所有文本内容
                return document.body.innerText.substring(0, 5000);
            }
        """)
        print(f"  页面文本（前500字）: {data[:300]}")

        # ── 兜底：直接搜索全部上海网点（不选城市）───────
        print("  重新加载页面（不选城市，搜索全部）...")
        await page.goto(ICBC_BRANCH_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # 尝试直接填充搜索框
        try:
            inputs = await page.query_selector_all("input")
            for inp in inputs:
                placeholder = await inp.get_attribute("placeholder") or ""
                print(f"    input placeholder: {placeholder}")
        except:
            pass

        # 获取完整页面文本，找所有网点名称
        full_text = await page.inner_text("body")
        # 找「支行」关键词附近的文本块
        zhi_hang_blocks = re.findall(r'.{0,30}支行.{0,60}', full_text)
        print(f"  找到「支行」相关文本块: {len(zhi_hang_blocks)}")
        for b in zhi_hang_blocks[:5]:
            print(f"    {b}")

        # ── 尝试提取分页表格 ────────────────────────────
        table_text = await page.inner_text(".el-table, .el-table__body, [class*=table]")
        print(f"  表格内容: {table_text[:500]}")

        await browser.close()

    print(f"\n✅ 抓取完成，共获取 {len(branches)} 条网点记录")
    return branches, errors


def save_to_db(branches: list):
    """存入 SQLite"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bank_branches (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT,
            code         TEXT,
            address      TEXT,
            district     TEXT,
            city         TEXT,
            phone        TEXT,
            business_hours TEXT,
            lng          REAL,
            lat          REAL,
            bank_type    TEXT DEFAULT '工商银行',
            source       TEXT,
            created_at   TEXT
        )
    """)
    c.execute("DELETE FROM bank_branches WHERE bank_type='工商银行'")
    for b in branches:
        c.execute("""
            INSERT INTO bank_branches
                (name, code, address, district, city, phone,
                 business_hours, lng, lat, bank_type, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '工商银行', 'icbc.com.cn', ?)
        """, (
            b.get("name"), b.get("code"), b.get("address"),
            b.get("district"), b.get("city", "上海"),
            b.get("phone"), b.get("hours"),
            b.get("lng"), b.get("lat"),
            datetime.now().isoformat(),
        ))
    conn.commit()
    print(f"  SQLite: {DB_PATH} ({len(branches)} 条)")
    conn.close()


if __name__ == "__main__":
    branches, errors = asyncio.run(scrape_icbc_branches())

    if branches:
        save_to_db(branches)
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(branches, f, ensure_ascii=False, indent=2)
        print(f"  JSON: {OUT_JSON}")
    else:
        print("\n⚠️ 未获取到数据，打印错误日志:")
        for e in errors[:10]:
            print(f"  {e}")

    if errors:
        with open("/root/.openclaw/workspace/logs/icbc_scraper.log", "w", encoding="utf-8") as f:
            f.write("\n".join(errors))
