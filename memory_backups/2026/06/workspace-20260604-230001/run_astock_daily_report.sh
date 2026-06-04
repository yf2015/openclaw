#!/bin/bash
# A股每日盘后分析报告推送
# 运行时间: A股交易日 16:05（收盘后约1小时，数据较全）
# 依赖: Python3, OpenClaw Gateway API, DingTalk Webhook

LOGFILE="/root/.openclaw/workspace/logs/astock_daily_report.log"
LOCKFILE="/root/.openclaw/workspace/logs/astock_daily_report.lock"
PYTHON_SCRIPT="/root/.openclaw/workspace/scripts/astock_daily_report.py"

# 防重入锁
if [ -f "$LOCKFILE" ]; then
    LOCK_AGE=$(($(date +%s) - $(stat -c %Y "$LOCKFILE" 2>/dev/null || echo 0)))
    if [ "$LOCK_AGE" -lt 300 ]; then
        echo "[$(date)] 任务已在运行中，跳过" >> "$LOGFILE"
        exit 0
    fi
fi
touch "$LOCKFILE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始生成A股盘后分析..." >> "$LOGFILE"

# 运行Python脚本
python3 "$PYTHON_SCRIPT" >> "$LOGFILE" 2>&1

EXIT_CODE=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 任务完成，退出码: $EXIT_CODE" >> "$LOGFILE"

rm -f "$LOCKFILE"
exit $EXIT_CODE
