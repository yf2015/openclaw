#!/usr/bin/env python3
"""
B型不强赎策略每日回测计算
- 每天3:30补充计算前一交易日的模拟交易结果
- 更新 bt_report.html 并推送到nginx
- 发送钉钉通知
"""

import sqlite3, math, re, requests, subprocess, time
from pathlib import Path
from datetime import datetime, timedelta

# ── 配置 ──────────────────────────────────────────────────
DB            = "/root/.openclaw/workspace/jisilu.db"
LOG_DIR       = "/root/.openclaw/workspace/logs"
HTML_OUT      = "/home/nginx/html/bt_report.html"
XUEQIU_COOKIE = ("cookiesu=961758080079192; smidV2=202509171134430b0ac92e2906e4dd1c0c6e9809aaae6d00eff38c47c24f5b0; "
                 "device_id=3078cef59e80cae65b2b2c71f9b77fee; s=b311uqbwlu; "
                 "bid=541d8de100a8c29e125708cfe7f96ddd_miodcq2g; "
                 "acw_tc=276082b617788294868185739e8df02e2a37aa14ac2c4d9f8d4f7a796446b8; remember=1; "
                 "xq_a_token=f01bb3cd73323fe9d18a97114619ae05439c6792; "
                 "xqat=f01bb3cd73323fe9d18a97114619ae05439c6792; "
                 "xq_id_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ1aWQiOjQwNzgxNTQwMTgsImlzcyI6InVjIiwiZXhwIjoxNzgxNDIxNTA2LCJjdGMiOjE3Nzg4Mjk1MDY5MDcsImNpZCI6ImQ5ZDBuNEFadXAifQ.jO4NPFye0pzyZq8IR_b_FyabDxYCyM6d_rJ0gl_532vOy7jp7tXfeRZKBJj79L4Ph2Wby3UWAPMZ6WYCYFRRiZ-fe53YyizSPxO5WxE1GQpvcocRhzMJ1rV5MNJXJNsiOXp9Ik4T3_yWKuowF28mT0ZH2pHFiQYbyuGM2CbgtdaRFunfbfTsLu4GhKfhcwVOjOkdrebjGzXLoWXXUOoabc23QcHpHDxJkINzA95GQW-SBU1WDWXnRFB6PQm1_W-JYoo7zwcy9J9jk0Sp0DNnA87I0MNEDcykdTCtJgUDl-SIwl-16hVm7OpN9_piO1_rNlsMaMBA2flmvYI8NO1ltQ; "
                 "xq_r_token=33a6806973373a4b0eb7b0c55d484e27d1943b23; xq_is_login=1; u=4078154018; is_overseas=0; "
                 ".thumbcache_f24b8bbe5a5934237bbc0eda20c1b6e7=AOBLXo0v71DOqIuNAWonnulJEQE/jQn0AjQioGVrHcK+5xufQP2NyK16OKzeqpCg3AGRiq5z5sJwggfy0ckcHw==; "
                 "ssxmod_itna2=1-QqRxyDRmDQubG0D2exmx3qWqeGq0jfQDXDUM4iQGgfDFqAPeDHK_pBfepQQBBiYRGi4D8/o8GxrDGbn4r=s4cETeg9cMHitqRQiSyP4D; "
                 "ssxmod_itna=1-QqRxyDRmDQubG0D2exmx3qWqeGq0jfQDXDUM4iQGgfDFqAPeDHK_pBfepQQBBiYRGi4D8/o8DvCDBTRYDSxD=HDK4GT_C=mu_CDj20_Q=p0Wxxo_ijiduIY7tYu4pq5QWgCH1afI6mIyo2Don9sBhvYox0aDmKDU=D4o34DxaPD5xDTDWeDGDD3DmmwDiyPD0KDjngAIzSvDYPDEnoDaxDbDiWvH4GCiDDCi2YDwp4AdDDzd0lqDYnibikUQ9MPeTSDg/HvD7H3DlaKGXivD5/Bdj8U8Vvj31oDXPNDv1SPjSY22D8LA3MrzTmexHiibRDCjxxKbqSRibu4=iKY0DC0DRrqRin9rKb48B4YPxDG_Gpmde0G_izcMzgksT4xYQteGN32DyEd5ox1oQ1hqKGDEo5MA5VYYCYqRreTmDtQxxEmKoGYmYr_qbix=xrNlw_YAUALdiDD")
WEBHOOK      = "https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488"
INITIAL      = 300_000.0
FEE          = 0.0005
SLIP         = 0.001

NAME_TO_CODE = {
    "超达转债":"123187","华兴转债":"118003","盈峰转债":"127024","瑞丰转债":"123126",
    "帝欧转债":"127047","华特转债":"118033","翔丰转债":"123225","星球转债":"118041",
    "博瑞转债":"118004","严牌转债":"123243","超声转债":"127026","洁美转债":"128137",
    "京源转债":"118016","瑞科转债":"118018","金埔转债":"123198","利柏转债":"111023",
    "艾迪转债":"113644","帝尔转债":"123121","永贵转债":"123253","佳力转债":"113597",
}

# ── 日志扫描 ─────────────────────────────────────────────
def build_daily_bonds():
    daily = {}
    for log in Path(LOG_DIR).glob("cb_noredeem_*.log"):
        m = re.search(r"cb_noredeem_(\d{8})_", log.name)
        if not m:
            continue
        date_str = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}"
        content  = log.read_text(encoding="utf-8")
        hits     = re.findall(r"命中: ([^(]+)\(([^)]+)\) \((\d+), (\d+)\)", content)
        bonds    = sorted(
            [(int(c1), nm.strip(), cd.strip()) for nm, cd, c1, c2 in hits],
            key=lambda x: -x[0]
        )
        daily[date_str] = bonds
    return daily

# ── K线补采（强制覆盖）────────────────────────────────────
def ensure_prices(conn, date):
    cur = conn.cursor()
    print(f"  [{date}] 从雪球补采K线（强制覆盖）...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Cookie": XUEQIU_COOKIE,
        "Referer": "https://xueqiu.com",
    }
    url = "https://stock.xueqiu.com/v5/stock/chart/kline.json"
    ts     = int(datetime.strptime(date, "%Y-%m-%d").timestamp() * 1000)
    end_ts = int((datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).timestamp() * 1000)

    fetched = 0
    for name, code in NAME_TO_CODE.items():
        ex  = "SH" if code.startswith(("11", "13")) else "SZ"
        sym = f"{ex}{code}"
        params = {
            "symbol": sym, "begin": str(ts), "end": str(end_ts),
            "period": "day", "type": "before", "count": -10,
            "indicator": "kline", "extend": "unlimited"
        }
        try:
            r     = requests.get(url, params=params, headers=headers, timeout=10)
            d     = r.json()
            items = (d.get("data") or {}).get("item") or []
            if not items:
                continue
            cols = (d.get("data") or {}).get("column") or []
            tsi,oi,hi,li,ci,vi,ai = (cols.index(x) for x in
                ["timestamp","open","high","low","close","volume","amount"])
            for row in items:
                trade_date = datetime.fromtimestamp(row[tsi]/1000).strftime("%Y-%m-%d")
                cur.execute("""
                    INSERT INTO klines_xq (sec_code,trade_date,open,high,low,close,volume,amount,source)
                    VALUES (?,?,?,?,?,?,?,?,'xueqiu')
                    ON CONFLICT(sec_code,trade_date,source)
                    DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,
                                  close=excluded.close,volume=excluded.volume,amount=excluded.amount
                """, (code, trade_date, row[oi], row[hi], row[li], row[ci], row[vi], row[ai]))
            conn.commit()
            fetched += 1
        except Exception as e:
            print(f"    补采失败 {name}({sym}): {e}")
        time.sleep(0.3)
    print(f"  补采完成: {fetched} 只转债")

# ── 回测引擎 ─────────────────────────────────────────────
# G1: 前1只满仓(100%)    G2: 前2只均仓(50/50)    G3: 前2只(2/3+1/3)
GROUPS = [
    (1, [1.0]),           # G1
    (2, [0.5, 0.5]),      # G2
    (2, [2/3, 1/3]),      # G3
]

def run_backtest(daily_bonds, price_map):
    def _one(n, weights):
        dates   = sorted(daily_bonds.keys())
        capital = INITIAL
        results = []
        for date in dates:
            bonds = daily_bonds[date][:n]
            valid = [(b, price_map[(b[2], date)]) for b in bonds
                     if (b[2], date) in price_map]
            if not valid:
                results.append({"date": date, "trades": [],
                                 "day_pnl": 0, "capital": capital})
                continue

            day_pnl = 0
            trades  = []
            for i, (b, (op, cp)) in enumerate(valid):
                alloc = capital * weights[i]
                bp    = op * (1 + SLIP)
                sp    = cp * (1 - SLIP)
                shares= int(alloc / bp)
                cost  = shares * bp * (1 + FEE)
                rev   = shares * sp * (1 - FEE)
                pnl   = rev - cost
                day_pnl += pnl
                trades.append({
                    "Name": b[1], "Code": b[2], "Cnt": b[0],
                    "Buy": bp, "Sell": sp, "Shares": shares,
                    "Cost": cost, "Rev": rev, "Pnl": pnl,
                    "AllocPct": weights[i]*100,
                })
            capital += day_pnl
            results.append({"date": date, "trades": trades,
                             "day_pnl": day_pnl, "capital": capital})
        return results

    def _stats(res):
        peak, max_dd = INITIAL, 0
        for d in res:
            if d["capital"] > peak: peak = d["capital"]
            dd = (peak - d["capital"]) / peak * 100
            if dd > max_dd: max_dd = dd
        returns = [d["day_pnl"]/(d["capital"]-d["day_pnl"])*100
                   for d in res if d["day_pnl"] != 0]
        mean = sum(returns)/len(returns) if returns else 0
        std  = math.sqrt(sum((r-mean)**2 for r in returns)/len(returns)) if returns else 0
        sharpe    = mean/std*math.sqrt(252) if std else 0
        total_ret = (res[-1]["capital"] - INITIAL) / INITIAL * 100
        ann       = (res[-1]["capital"]/INITIAL)**(252/len(res)) - 1
        return {"capital": res[-1]["capital"], "total_ret": total_ret,
                "ann": ann*100, "max_dd": max_dd, "sharpe": sharpe,
                "results": res}

    return [_stats(_one(g[0], g[1])) for g in GROUPS]

# ── HTML生成 ─────────────────────────────────────────────
def badge(cnt):
    cls = "badge-danger" if cnt >= 14 else ("badge-warn" if cnt >= 10 else "")
    extra = " " + cls if cls else ""
    return f'<span class="badge{extra}">{cnt}/15</span>'

def make_rows(results):
    rows = []
    for d in results:
        cap     = d["capital"]
        day_pnl = d["day_pnl"]
        day_ret = day_pnl/(cap-day_pnl)*100 if day_pnl != 0 else 0
        if not d["trades"]:
            rows.append(
                f'<tr class="no-signal">'
                f'<td class="date">{d["date"]}</td>'
                f'<td colspan="4" class="text-center text-muted">— 休市 / 无信号 —</td>'
                f'<td class="text-right">—</td>'
                f'<td class="text-right text-muted">0.00%</td>'
                f'<td class="text-right fw-bold">{cap:,.0f}</td>'
                f'</tr>'
            )
            continue
        first = True
        for t in d["trades"]:
            cls       = "up" if t["Pnl"] > 0 else "down"
            date_cell = f'<td class="date">{d["date"]}</td>' if first else '<td></td>'
            ret_cell  = (f'<td class="text-right {cls}">{day_ret:+.2f}%</td>'
                         f'<td class="text-right fw-bold">{cap:,.0f}</td>') if first else '<td></td><td></td>'
            rows.append(
                f'<tr class="{cls}">'
                f'{date_cell}'
                f'<td>{badge(t["Cnt"])}<br><span class="alloc">{t["AllocPct"]:.1f}%</span></td>'
                f'<td>{t["Name"]}<br><span class="code">{t["Code"]}</span></td>'
                f'<td class="text-right">{t["Buy"]:.3f}</td>'
                f'<td class="text-right">{t["Sell"]:.3f}</td>'
                f'<td class="text-right {cls}">{t["Pnl"]:+,.2f}</td>'
                f'{ret_cell}'
                f'</tr>'
            )
            first = False
    return "\n".join(rows)

def section_html(gid, label, st):
    return (
        f'<h2 class="section-title" id="g{gid}">{label}</h2>\n<table>\n'
        '<thead><tr>'
        '<th>日期</th><th>计数/仓位</th><th>标的</th>'
        '<th class="text-right">买价</th><th class="text-right">卖价</th>'
        '<th class="text-right">PnL</th><th class="text-right">日收益</th>'
        '<th class="text-right">结余资金</th>'
        '</tr></thead>\n<tbody>\n'
        + make_rows(st["results"]) +
        '</tbody>\n</table>\n<div class="stat-card">\n'
        f'<span class="stat-label">最终资金</span>\n'
        f'<span class="stat-value">{st["capital"]:,.2f}</span>\n'
        f'<span class="stat-sub">总收益 {st["total_ret"]:+.2f}% &nbsp; '
        f'年化 {st["ann"]:+.2f}% &nbsp; 最大回撤 {st["max_dd"]:.2f}% &nbsp; '
        f'夏普 {st["sharpe"]:.4f}</span>\n</div>'
    )

def build_html(results):
    s1, s2, s3 = results
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return (
        '<!DOCTYPE html>\n'
        '<html lang="zh">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>B型不强赎策略回测报告</title>\n'
        '<style>\n'
        '*{box-sizing:border-box;margin:0;padding:0}\n'
        'body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#0d1117;color:#e6edf3;font-size:14px}\n'
        '.wrap{max-width:1400px;margin:0 auto;padding:24px 16px}\n'
        'h1{font-size:22px;font-weight:700;color:#58a6ff;margin-bottom:4px}\n'
        '.sub{color:#8b949e;font-size:13px;margin-bottom:8px}\n'
        '.nav{margin-bottom:24px}\n'
        '.nav a{display:inline-block;padding:6px 16px;background:#21262d;border:1px solid #30363d;border-radius:6px;color:#58a6ff;text-decoration:none;font-size:13px;margin-right:8px}\n'
        '.nav a:hover{background:#30363d}\n'
        'table{width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden;margin-bottom:8px}\n'
        'th{background:#21262d;color:#8b949e;font-size:11px;text-transform:uppercase;letter-spacing:1px;padding:10px 12px;text-align:left}\n'
        'th.text-right{text-align:right}\n'
        'td{padding:9px 12px;border-top:1px solid #21262d;vertical-align:top}\n'
        'td.text-right{text-align:right}\n'
        '.date{color:#58a6ff;font-weight:600;white-space:nowrap}\n'
        'tr.up td{color:#3fb950} tr.down td{color:#f85149}\n'
        'tr.no-signal td{color:#484f58;font-style:italic}\n'
        '.badge{display:inline-block;padding:1px 6px;border-radius:10px;font-size:11px;font-weight:600}\n'
        '.badge-danger{background:#3d1f1f;color:#f85149}\n'
        '.badge-warn{background:#3d2e0a;color:#d29922}\n'
        '.badge{background:#21262d;color:#8b949e}\n'
        '.code{font-size:11px;color:#8b949e}\n'
        '.alloc{font-size:10px;color:#8b949e;display:block;margin-top:1px}\n'
        '.fw-bold{font-weight:700}\n'
        '.text-muted{color:#8b949e}\n'
        '.text-center{text-align:center}\n'
        '.section-title{font-size:18px;font-weight:700;color:#e6edf3;margin:32px 0 12px;border-left:4px solid #58a6ff;padding-left:12px}\n'
        '.stat-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px 20px;margin-bottom:32px;font-size:13px;color:#8b949e}\n'
        '.stat-label{color:#8b949e;margin-right:8px}\n'
        '.stat-value{font-size:18px;font-weight:700;color:#3fb950;margin-right:12px}\n'
        '.stat-sub{color:#8b949e}\n'
        '.summary-table{width:100%;border-collapse:collapse}\n'
        '.summary-table td{padding:10px 14px;border-top:1px solid #30363d}\n'
        '.summary-table tr:first-child td{border-top:none}\n'
        '.footer{text-align:center;color:#484f58;font-size:12px;padding:32px 0 16px}\n'
        '</style>\n'
        '</head>\n'
        '<body>\n'
        '<div class="wrap">\n'
        '<div class="nav">\n'
        '<a href="#g1">G1</a>\n'
        '<a href="#g2">G2</a>\n'
        '<a href="#g3">G3</a>\n'
        '<a href="#summary">汇总</a>\n'
        '</div>\n'
        '<h1>📊 B型不强赎策略回测报告</h1>\n'
        f'<p class="sub">区间：2026-04-22 → {datetime.now().strftime("%Y-%m-%d")} &nbsp;|&nbsp; 初始资金：300,000 元 &nbsp;|&nbsp; 每日收盘价结算</p>\n'
        f'<p class="sub">最后更新：{now} &nbsp;|&nbsp; 数据来源：雪球K线 + 集思录信号</p>\n'
        + section_html(1, "G1 前 1 只（满仓 100%）", s1)
        + section_html(2, "G2 前 2 只（均仓 50/50）", s2)
        + section_html(3, "G3 前 2 只（2/3 + 1/3）", s3)
        + '<h2 class="section-title" id="summary">汇总对比</h2>\n'
        '<table class="summary-table">\n<thead><tr>'
        '<th>组别</th><th class="text-right">最终资金</th>'
        '<th class="text-right">总收益</th><th class="text-right">年化收益</th>'
        '<th class="text-right">最大回撤</th><th class="text-right">夏普比率</th>'
        '</tr></thead>\n<tbody>\n'
        f'<tr><td>G1 前1只满仓</td><td class="text-right" style="color:#3fb950;font-weight:700">{s1["capital"]:,.2f}</td>'
        f'<td class="text-right" style="color:#3fb950">+{s1["total_ret"]:.2f}%</td>'
        f'<td class="text-right">+{s1["ann"]:.2f}%</td><td class="text-right">-{s1["max_dd"]:.2f}%</td>'
        f'<td class="text-right">{s1["sharpe"]:.4f}</td></tr>\n'
        f'<tr><td>G2 前2只均仓</td><td class="text-right">{s2["capital"]:,.2f}</td>'
        f'<td class="text-right">+{s2["total_ret"]:.2f}%</td>'
        f'<td class="text-right">+{s2["ann"]:.2f}%</td><td class="text-right">-{s2["max_dd"]:.2f}%</td>'
        f'<td class="text-right">{s2["sharpe"]:.4f}</td></tr>\n'
        f'<tr><td>G3 前2只(2/3+1/3)</td><td class="text-right">{s3["capital"]:,.2f}</td>'
        f'<td class="text-right">+{s3["total_ret"]:.2f}%</td>'
        f'<td class="text-right">+{s3["ann"]:.2f}%</td><td class="text-right">-{s3["max_dd"]:.2f}%</td>'
        f'<td class="text-right">{s3["sharpe"]:.4f}</td></tr>\n'
        '</tbody>\n</table>\n'
        f'<div class="footer">生成：{now} &nbsp;|&nbsp; 本报告仅供策略研究，不构成投资建议</div>\n'
        '</div>\n'
        '</body>\n'
        '</html>\n'
    )

# ── 主流程 ────────────────────────────────────────────────
def main():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] B型策略每日回测开始...")

    daily_bonds = build_daily_bonds()
    print(f"  历史交易日: {len(daily_bonds)} 天")

    conn = sqlite3.connect(DB)
    cur  = conn.cursor()
    cur.execute("SELECT sec_code,trade_date,open,close FROM klines_xq WHERE source='xueqiu'")
    price_map = {(r[0], r[1]): (float(r[2]), float(r[3])) for r in cur.fetchall()}
    print(f"  K线记录: {len(price_map)} 条")

    if daily_bonds:
        latest = max(daily_bonds.keys())
        ensure_prices(conn, latest)
        cur.execute("SELECT sec_code,trade_date,open,close FROM klines_xq WHERE source='xueqiu'")
        price_map = {(r[0], r[1]): (float(r[2]), float(r[3])) for r in cur.fetchall()}

    results = run_backtest(daily_bonds, price_map)
    conn.close()

    html = build_html(results)
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML已写入: {HTML_OUT} ({len(html):,} bytes)")

    subprocess.run(["docker", "cp", HTML_OUT, "nginx:/usr/share/nginx/html/bt_report.html"],
                   capture_output=True)
    print("  复制到nginx容器完成")

    s1, s2, s3 = results
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "📊 B型策略每日回测已更新",
            "text": (
                f"## ✅ B型策略回测已更新\n\n"
                f"**更新日期**: {ts}\n\n"
                f"| 组别 | 最终资金 | 总收益 | 夏普 |\n"
                f"|------|----------|--------|-----|\n"
                f"| G1 前1只满仓 | {s1['capital']:,.0f} | {s1['total_ret']:+.2f}% | {s1['sharpe']:.4f} |\n"
                f"| G2 前2只均仓 | {s2['capital']:,.0f} | {s2['total_ret']:+.2f}% | {s2['sharpe']:.4f} |\n"
                f"| G3 2/3+1/3 | {s3['capital']:,.0f} | {s3['total_ret']:+.2f}% | {s3['sharpe']:.4f} |\n\n"
                f"👉 查看: http://47.101.71.63/bt_report.html"
            )
        }
    }
    r = requests.post(WEBHOOK, json=payload, timeout=10)
    print(f"  钉钉: {r.json()}")

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 完成!")


if __name__ == "__main__":
    main()