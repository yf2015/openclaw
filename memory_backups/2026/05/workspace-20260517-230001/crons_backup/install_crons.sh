#!/bin/bash
# Cron 任务恢复脚本
# 用法: bash install_crons.sh

CRON_DIR="/etc/cron.d"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/crons_backup"

echo "===== 安装定时任务 ====="

for file in "$BACKUP_DIR"/openclaw-cb-*; do
    name=$(basename "$file")
    echo "安装 $name ..."
    sudo cp "$file" "$CRON_DIR/$name"
    sudo chmod 644 "$CRON_DIR/$name"
done

echo "===== 完成 ====="
ls -la "$CRON_DIR"/openclaw-cb-*