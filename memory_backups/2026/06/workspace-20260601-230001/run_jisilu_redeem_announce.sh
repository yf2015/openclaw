#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/jisilu_redeem_announce_$(date +%Y%m%d_%H%M).log"
echo "[$(date)] 提前赎回公告开始..." >> "$LOG"
python3 "$SCRIPT_DIR/scripts/jisilu_redeem_announce.py" >> "$LOG" 2>&1
echo "[$(date)] 执行完成" >> "$LOG"
