#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/jisilu_calendar_$(date +%Y%m%d_%H%M).log"
echo "[$(date)] 集思录日历开始..." >> "$LOG"
python3 "$SCRIPT_DIR/scripts/jisilu_calendar.py" >> "$LOG" 2>&1
echo "[$(date)] 执行完成" >> "$LOG"
