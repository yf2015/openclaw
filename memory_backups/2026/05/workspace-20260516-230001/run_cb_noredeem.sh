#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/cb_noredeem_$(date +%Y%m%d_%H%M).log"
echo "[$(date)] 开始执行不强赎双策略..." >> "$LOG"
python3 "$SCRIPT_DIR/scripts/cb_noredeem_strategy.py" >> "$LOG" 2>&1
echo "[$(date)] 执行完成" >> "$LOG"
