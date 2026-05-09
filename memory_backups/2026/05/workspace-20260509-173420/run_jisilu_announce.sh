#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/jisilu_announce_$(date +%Y%m%d_%H%M).log"
echo "[$(date)] 开始检索不强赎公告..." >> "$LOG"
python3 "$SCRIPT_DIR/scripts/jisilu_no_redeem_announce.py" >> "$LOG" 2>&1
echo "[$(date)] 执行完成" >> "$LOG"