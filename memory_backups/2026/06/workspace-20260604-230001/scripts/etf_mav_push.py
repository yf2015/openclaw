#!/usr/bin/env python3
"""
ETF MAV 波动分析每日推送
标的: 588200（科创50）、159516（纳指ETF）
每日收盘后（15:05）分析当日波动，发送钉钉通知
"""

import sys, json
from pathlib import Path

# ── 监控标的配置 ──────────────────────────────────────────
MONITORED_ETFS = [
    ("588200", "科创50ETF"),
    ("159516", "纳指ETF"),
]

DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=82229bd3340908b815989af583820aa5dd5d5598673f9469f55bc3c78d46c488"

# ── 导入 MAV 模块 ─────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.cb_etf_mav import analyze, format_result


def dingtalk_send(text: str) -> dict:
    import requests
    from urllib.request import Request, urlopen
    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {"title": "📊 ETF MAV 波动日报", "text": text},
        "at": {"isAtAll": False},
    })
    req = Request(
        DINGTALK_WEBHOOK,
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def build_report(results: list) -> str:
    """构建钉钉 Markdown 报告"""
    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    header = (
        f"## 📊 ETF MAV 波动日报\n"
        f"**{ts}**\n\n"
        f"| 标的 | 代码 | 收盘价 | 涨跌 | MAV20 | MAV60 | ratio | 信号 |\n"
        f"|---|---|---|---|---|---|---|---|\n"
    )

    rows = []
    for r in results:
        if "error" in r:
            rows.append(f"| {r.get('name','?')} | {r['code']} | — | — | — | — | — | ❌ {r['error']} |")
            continue

        sig_map = {
            "🔔 极端下跌": "🔴 极端下跌",
            "🔔 明显下跌": "🟠 明显下跌",
            "📉 跌破均值": "🟡 跌破均值",
            "✅ 正常下跌": "⚪ 正常下跌",
            "✅ 正常上涨": "⚪ 正常上涨",
            "📈 突破均值": "🟢 突破均值",
            "⚠️ 明显上涨": "🟠 明显上涨",
            "⚠️ 极端上涨": "🔴 极端上涨",
            "观望": "⚪ 观望",
        }
        sig = sig_map.get(r["signal"], r["signal"])

        change_emoji = "🔴" if r["today_change_pct"] < 0 else "🟢"
        rows.append(
            f"| {r.get('name','?')} | `{r['code']}` | "
            f"**{r['last_close']:.3f}** | "
            f"{change_emoji} {r['today_change_pct']:+.2f}% | "
            f"{r['mav20']*100:.2f}% | {r['mav60']*100:.2f}% | "
            f"{r['mav20_60_ratio']:.2f} | {sig} |"
        )

    return header + "\n".join(rows)


def main():
    print(f"[ETF MAV] 开始分析 {len(MONITORED_ETFS)} 只标的...")

    results = []
    name_map = dict(MONITORED_ETFS)

    for code, name in MONITORED_ETFS:
        print(f"  分析 {name}({code})...")
        r = analyze(code, "etf", fetch_days=80)
        r["name"] = name
        results.append(r)
        print(f"    信号: {r.get('signal', 'error: '+str(r.get('error')))}")

    # 打印控制台
    for r in results:
        print(format_result(r))
        print()

    # 发送钉钉
    report = build_report(results)
    resp = dingtalk_send(report)
    errcode = resp.get("errcode", -1)
    print(f"[钉钉] errcode={errcode}")
    if errcode != 0:
        print(f"    发送失败: {resp}")

    return results


if __name__ == "__main__":
    main()