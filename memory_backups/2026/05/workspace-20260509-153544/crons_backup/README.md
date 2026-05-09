# Crons 备份

定时任务文件，恢复时执行：
```bash
sudo cp openclaw-cb-noredeem /etc/cron.d/openclaw-cb-noredeem
sudo cp openclaw-cb-strategy /etc/cron.d/openclaw-cb-strategy
sudo systemctl restart cron
```

包含：
- **openclaw-cb-noredeem**: 不强赎策略 + 集思录日历 + 提前赎回公告 + GitHub备份
- **openclaw-cb-strategy**: 可转债动量策略（每周一）