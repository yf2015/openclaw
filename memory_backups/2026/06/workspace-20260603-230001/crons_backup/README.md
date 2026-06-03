# Crons 备份

定时任务文件，恢复时执行：
```bash
sudo cp openclaw-cb-noredeem /etc/cron.d/openclaw-cb-noredeem
sudo cp openclaw-cb-strategy /etc/cron.d/openclaw-cb-strategy
sudo chmod 644 /etc/cron.d/openclaw-cb-*
sudo systemctl restart cron
```

包含：
- **openclaw-cb-noredeem**: 不强赎策略 + 集思录日历 + 提前赎回公告 + GitHub备份 + 每周日志轮转
- **openclaw-cb-strategy**: 可转债动量策略（每周一）

日志轮转脚本：`scripts/rotate_logs.sh`（每周日 00:00 执行）