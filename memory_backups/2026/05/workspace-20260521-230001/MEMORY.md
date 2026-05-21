# MEMORY.md - Long-term Memory

_精选自 daily memory 日志的长期记忆_

## 用户背景
- 全栈工程师，主用 Python/FastAPI
- 集思录账号: 17621765877（cookie已持久化）
- 时区: Asia/Shanghai

## 系统状态
- OpenClaw 版本按需更新（用户无需求时不主动升级）
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

## 可转债策略（V1+V2双策略并行）
- 脚本: `scripts/cb_noredeem_strategy_v2.py`（V1+V2双策略并行推送）
- V1策略: X/Y计数降序（统计历史上不强赎天数概率）
- V2策略: 综合评分（负溢价35分+计数25分+超触发20分+规模10分+股东配比10分）
- 警示阈值: 华兴转债(118003) 14/15
- 定时推送: 9:15~15:15整点半点（共11次/日）+ 晚间22:05
- 集思录全量采集: 10批次×35条机制已跑通（5/20全部完成），双Cookie+rp=5000

## 教训/已知问题
- 强推(`git push --force`)会抹掉历史，操作前确认分支状态
- HTTPS 443 端口间歇性超时，SSH 22 端口正常
- 不强赎样本偏少（14只），扩大范围可提高统计显著性
- **日志维护不能断**：上次日志4/22，今天5/8，16天空白。cron心跳虽在运行但未写日志。以后每次心跳应简短记录，无日志=失控。
## 记忆文件体系
- `memory/YYYY-MM-DD.md` — 每日日志，心跳记录、复盘结论、系统状态
- `.learnings/corrections.md` — 自我纠正记录（长期有效教训，已从根目录迁移，2026-05-15）
- `.learnings/LEARNINGS.md` — 正面经验积累（新建，2026-05-15）
- `MEMORY.md` — 精选长期记忆
- `SOUL.md` / `AGENTS.md` — 人格和行为准则

## 2026-05-08 晚间复盘补充
- 4/22~5/8期间16天空档，根因：cron心跳写日志机制在4/22后丢失
- 复盘cron(每天晚间)和日常cron心跳是两个独立机制
- 待主动确认：集思录推送(4/22后)、toolbox-api状态(4/21后)

## 2026-05-09 补充
- GitHub备份边界：`.clawhub/` 和 `.openclaw/` 不备份（已记录），但skill内容是否需要备份待定
- **日志断档教训细化**：心跳cron写日志机制需在AGENTS.md中强制要求，否则无法追溯

## 复盘流程（永久规则）
- **复盘必须产生跟进**：待确认项48小时内无行动则升级为「未完成待处理」，不再无限期挂起
- **复盘缺失环节**：复盘流程本身缺少「落实检查」，待确认项应在下次复盘前实际检查，而非重复列出
- **建议需同步落地**：任何新建建议需同步实施或转cron，不可只写不执行

## 2026-05-12 三省吾身补充
- /ports 页面确认正常运行（toolbox-api 9002 + /ports 页面可访问）
- daily-memory cron 建议暂缓执行：需等用户明确需求
- heartbeat-state.json 不存在（4/22后心跳机制丢失的另一个证据）

## 2026-05-18 今日工作记录
- nginx容器重建，修复html目录映射（/home/nginx/html → /usr/share/nginx/html）
- 修复bt_report.conf：补root+try_files解决cb_strategy_log_viewer.html 404问题
- 回测计算：新增G2(第2只满仓)/G4(1只2/3+2只1/3)/G5(1只1/3+2只2/3)三组，共5组
- 创建cb_noredeem_strategy_v2.py（V1+V2双策略并行推送）
- V2评分体系：溢价35分+计数25分+超触发20分+规模10分+股东配比10分
- 创建export_backtest_data.py，归档1099条历史记录到backtest_data/
- cron任务整理：
  - V1+V2推送：9:15~15:15整点半点，共11次/日
  - 集思录采集：15:30+20:00保险，仅Top50+sleep 0.15s
  - run_cb_noredeem.sh改为调用cb_noredeem_strategy_v2.py
- 称呼确认：苑飞 = BOSS（老板）

