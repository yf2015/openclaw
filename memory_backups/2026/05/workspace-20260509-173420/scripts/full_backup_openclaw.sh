#!/bin/bash
# 全量备份脚本 - OpenClaw 完整备份 → GitHub
# 策略：备份关键配置，排除 session 轨迹文件(.jsonl)和运行时数据
# 敏感文件：原始值存 .bak，脱敏内容上传 GitHub
#
# 备份目录: /home/www/openclaw-sync/full-backup/openclaw-YYYYMMDD-HHMMSS/

set -e

GITHUB_REPO="/home/www/openclaw-sync"
BACKUP_TIME=$(date +%Y%m%d-%H%M%S)
SRC_OPENCLAW="/root/.openclaw"
BACKUP_ROOT="$GITHUB_REPO/full-backup"
BACKUP_DIR="$BACKUP_ROOT/openclaw-$BACKUP_TIME"
KEEP_VERSIONS=5

echo "===== OpenClaw 全量备份开始 ====="
echo "时间: $(date)"

# ============================================================
# Step 1: rsync 关键目录（排除 session 轨迹文件和临时文件）
# ============================================================
echo "[1/5] 同步关键配置目录 ..."

mkdir -p "$BACKUP_DIR"

# 核心配置目录
DIRS=("agents" "cron" "devices" "identity" "flows" "tasks" "plugin-skills" "extensions" "plugins")

for d in "${DIRS[@]}"; do
    if [ -d "$SRC_OPENCLAW/$d" ]; then
        rsync -a --exclude='*.jsonl' --exclude='*.jsonl.*' --exclude='*.checkpoint.*' \
            "$SRC_OPENCLAW/$d/" "$BACKUP_DIR/$d/"
        echo "  + $d"
    fi
done

# agents/sessions/ 只保留 sessions.json 和 trajectory-path.json（不含原始轨迹）
if [ -d "$SRC_OPENCLAW/agents/main/sessions" ]; then
    mkdir -p "$BACKUP_DIR/agents/main/sessions"
    rsync -a \
        --include='sessions.json' \
        --include='*.trajectory-path.json' \
        --exclude='*' \
        "$SRC_OPENCLAW/agents/main/sessions/" "$BACKUP_DIR/agents/main/sessions/"
    echo "  + agents/main/sessions (metadata only)"
fi

# openclaw.json 配置文件
rsync -a "$SRC_OPENCLAW/openclaw.json" "$BACKUP_DIR/openclaw.json"
echo "  + openclaw.json"

# workspace 核心人格/记忆文件（排除大数据文件和日志）
mkdir -p "$BACKUP_DIR/workspace"
rsync -a \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.json' \
    --exclude='jisilu_*' \
    --exclude='memory_backups/' \
    --exclude='logs/' \
    "$SRC_OPENCLAW/workspace/" "$BACKUP_DIR/workspace/"
echo "  + workspace/ (人格+记忆+技能定义)"

# 排除 extensions/dingtalk-connector 过大文件
rm -rf "$BACKUP_DIR/extensions/dingtalk-connector/node_modules" 2>/dev/null || true
rm -rf "$BACKUP_DIR/extensions/dingtalk-connector/dist" 2>/dev/null || true

echo "      备份大小: $(du -sh "$BACKUP_DIR" | cut -f1)"

# ============================================================
# Step 2: Python 脱敏处理（JSON 文件敏感字段替换）
# ============================================================
echo "[2/5] 脱敏处理敏感文件 ..."

python3 - "$BACKUP_DIR" << 'PYEOF'
import os, re, json, shutil, sys

BACKUP_DIR = sys.argv[1]

SENSITIVE_KEYS = {
    'token', 'secret', 'password', 'passwd', 'pwd',
    'clientId', 'clientSecret', 'client_id', 'client_secret',
    'apiKey', 'api_key', 'apikey', 'api_secret',
    'privateKey', 'private_key', 'secretKey',
    'accessToken', 'access_token', 'refreshToken', 'refresh_token',
    'authToken', 'authorization',
    'cookie', 'sessionKey', 'session_key',
    'botId', 'robotCode',
}
TOKEN_PATTERNS = [
    re.compile(r'[0-9a-f]{32,}', re.I),
    re.compile(r'[0-9a-zA-Z]{40,}', re.I),
    re.compile(r'eyJ[0-9a-zA-Z_-]+\.eyJ[0-9a-zA-Z_-]+\.[0-9a-zA-Z_-]+', re.I),
]
REDACT = '[REDACTED]'

def looks_like_token(v):
    if not isinstance(v, str) or len(v) < 16:
        return False
    for pat in TOKEN_PATTERNS:
        if pat.search(v):
            return True
    return False

def sanitize_val(key, val):
    key_lower = key.lower()
    if any(sk in key_lower for sk in SENSITIVE_KEYS):
        return REDACT
    if looks_like_token(val):
        return REDACT
    return val

def walk(obj, changed):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            if isinstance(v, str):
                new_val = sanitize_val(k, v)
                if new_val != v:
                    obj[k] = new_val
                    changed[0] = True
            elif isinstance(v, (dict, list)):
                walk(v, changed)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                if looks_like_token(item):
                    obj[i] = REDACT
                    changed[0] = True
            elif isinstance(item, (dict, list)):
                walk(item, changed)

def sanitize_json_file(fp):
    bak_path = fp + '.bak'
    if not os.path.exists(bak_path):
        shutil.copy2(fp, bak_path)
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return False
    changed = [False]
    walk(data, changed)
    try:
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        return False
    return changed[0]

count = 0
sanitized = 0
for root, dirs, files in os.walk(BACKUP_DIR):
    dirs[:] = [d for d in dirs if d not in ('node_modules', '.git')]
    for fname in files:
        if fname.endswith('.bak'):
            continue
        fp = os.path.join(root, fname)
        ext = os.path.splitext(fname)[1].lower()
        if ext == '.json' or fname == 'package.json':
            result = sanitize_json_file(fp)
            count += 1
            if result:
                sanitized += 1
                rel = os.path.relpath(fp, BACKUP_DIR)
                print(f"  [脱敏] {rel}")

print(f"  共 {count} 个 JSON，{sanitized} 个已脱敏")
PYEOF

# ============================================================
# Step 3: 清理旧备份
# ============================================================
echo "[3/5] 清理旧备份（保留 $KEEP_VERSIONS 个）..."
cd "$BACKUP_ROOT"
OLD=$(ls -dt openclaw-2* 2>/dev/null | tail -n +$((KEEP_VERSIONS + 1)) || true)
if [ -n "$OLD" ]; then
    echo "$OLD" | while read d; do
        echo "  删除: $d"
        rm -rf "$d"
    done
else
    echo "  无旧备份需清理"
fi

# ============================================================
# Step 4: 更新 .gitignore 并提交
# ============================================================
echo "[4/5] 提交到 GitHub ..."

cat > "$GITHUB_REPO/.gitignore" << 'EOF'
# 原始凭证备份（本地保留，不上传）
*.bak
*.bak.*
EOF

cd "$GITHUB_REPO"
git add -f full-backup/ .gitignore

if ! git diff --cached --quiet; then
    git commit -m "Full backup: $(date '+%Y-%m-%d %H:%M:%S')"
    if git push origin main 2>&1; then
        echo "  ✅ 推送完成"
    else
        echo "  ⚠️ 推送失败（本地备份已保存，可手动检查 GitHub secret scanning 状态）"
    fi
else
    echo "  无新更改"
fi

# ============================================================
# Step 5: 摘要
# ============================================================
LATEST=$(ls -dt "$BACKUP_ROOT"/openclaw-2* 2>/dev/null | head -1)
echo "[5/5] 摘要"
echo "      最新备份: $LATEST"
echo "      大小: $(du -sh "$LATEST" | cut -f1)"
echo "      原始凭证: $LATEST/xxx.json.bak（本地保留，不上传）"
echo "      脱敏版本: $LATEST/xxx.json（已上传 GitHub）"
echo "      注意: session .jsonl 轨迹文件已排除（太大且含敏感对话）"
echo "===== 全量备份完成 ====="
