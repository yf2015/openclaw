#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/jisilu_lof_index_$(date +%Y%m%d_%H%M).log"
echo "[$(date)] 指数LOF推送开始..." >> "$LOG"
python3 "$SCRIPT_DIR/scripts/jisilu_lof_index_push.py" >> "$LOG" 2>&1
echo "[$(date)] 执行完成" >> "$LOG"
