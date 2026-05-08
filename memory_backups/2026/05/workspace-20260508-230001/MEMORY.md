# MEMORY.md - Long-term Memory

_精选自 daily memory 日志的长期记忆_

## 用户背景
- 全栈工程师，主用 Python/FastAPI
- 集思录账号: 17621765877（cookie已持久化）
- 时区: Asia/Shanghai

## 系统状态
- OpenClaw 已更新至 2026.4.22
- gateway.auth.rateLimit 已配置（安全加固）
- channels.dingtalk-connector.groupPolicy 已改为 allowlist
- 钉钉连接器正常运行

## 重要习惯/偏好
- 直接给结论，不绕弯子
- 用 SSH 认证，不用 HTTPS token 在 URL 里
- 重要操作先问，破坏性操作更要问

## GitHub 同步
- 仓库: git@github.com:yf2015/openclaw.git
- 定时: 每小时整点自动同步
- 已排除敏感文件（脚本含 token、logs 等）

## 可转债策略
- 脚本: `scripts/cb_noredeem_strategy.py`
- 警示阈值: 华兴转债(118003) 14/15
- 定时推送: 1:00, 8:00, 10:30, 12:00, 14:00, 16:00, 22:00

## 教训/已知问题
- 强推(`git push --force`)会抹掉历史，操作前确认分支状态
- HTTPS 443 端口间歇性超时，SSH 22 端口正常
- 不强赎样本偏少（14只），扩大范围可提高统计显著性
- **日志维护不能断**：上次日志4/22，今天5/8，16天空白。cron心跳虽在运行但未写日志。以后每次心跳应简短记录，无日志=失控。
## 2026-05-08 晚间复盘补充
- 4/22~5/8期间16天空档，根因：cron心跳写日志机制在4/22后丢失
- 复盘cron(每天晚间)和日常cron心跳是两个独立机制
- 待主动确认：集思录推送(4/22后)、toolbox-api状态(4/21后)
