#!/bin/bash
# 双向同步脚本 - OpenClaw Workspace ↔ GitHub

GITHUB_REPO="/home/www/openclaw-sync"
LOCAL_WORKSPACE="/root/.openclaw/workspace"
BACKUP_DATE=$(date +%Y/%m)
BACKUP_DIR="$GITHUB_REPO/memory_backups/$BACKUP_DATE/workspace-$(date +%Y%m%d-%H%M%S)"

echo "===== 双向同步开始 ====="
echo "时间: $(date)"

cd "$GITHUB_REPO"

# 拉取远程最新更改
echo "[1/4] 拉取远程更改..."
git pull origin main 2>&1

# 检查远程是否有新备份
LATEST_REMOTE=$(ls -td "$GITHUB_REPO"/memory_backups/*/workspace-* 2>/dev/null | head -1)
if [ -n "$LATEST_REMOTE" ] && [ "$LATEST_REMOTE" != "$(ls -td "$GITHUB_REPO"/memory_backups/*/workspace-* 2>/dev/null | head -1)" ]; then
    echo "[2/4] 发现远程更新，合并到本地..."
    rsync -av --ignore-existing "$LATEST_REMOTE"/. "$LOCAL_WORKSPACE/"
fi

# 备份本地当前工作区
echo "[3/4] 备份本地工作区..."
mkdir -p "$BACKUP_DIR"
rsync -av --exclude='node_modules' --exclude='.git' --exclude='__pycache__' --exclude='.openclaw' "$LOCAL_WORKSPACE/" "$BACKUP_DIR/"

# 提交并推送
cd "$GITHUB_REPO"
git add .

if ! git diff --cached --quiet; then
    echo "[4/4] 推送更改到GitHub..."
    git commit -m "Sync: $(date '+%Y-%m-%d %H:%M:%S')"
    git push origin main
    echo "推送完成"
else
    echo "[4/4] 没有新更改，跳过推送"
fi

echo "===== 同步完成 ====="
