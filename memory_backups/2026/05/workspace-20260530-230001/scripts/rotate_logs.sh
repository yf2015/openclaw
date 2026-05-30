#!/bin/bash
# 日志轮转脚本 - 每周自动执行
# 添加到 cron: 0 0 * * 0 root bash /root/.openclaw/workspace/scripts/rotate_logs.sh

LOG_DIR="/root/.openclaw/workspace/logs"
WEEK=$(date +%Y-W%V)

rotate_log() {
    local file="$1"
    if [ -f "$file" ] && [ $(wc -l < "$file" 2>/dev/null) -gt 0 ]; then
        local basename=$(basename "$file")
        local newname="${file%.log}_${WEEK}.log"
        mv "$file" "$newname"
        echo "[$(date)] 轮转: $basename -> $(basename $newname)"
    fi
}

for f in sync cb_noredeem cb_strategy jisilu_calendar jisilu_redeem_announce; do
    rotate_log "$LOG_DIR/${f}_cron.log"
done