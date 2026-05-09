#!/bin/bash
# 可转债策略每周一定时执行
# 下周执行时自动计算正确的周区间

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$SCRIPT_DIR/logs/cb_strategy_$(date +%Y%m%d_%H%M).log"

echo "[$(date)] 开始执行可转债策略" >> "$LOG"
python3 "$SCRIPT_DIR/scripts/cb_momentum_strategy.py" >> "$LOG" 2>&1
echo "[$(date)] 执行完成" >> "$LOG"
