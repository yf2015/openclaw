# cf_lianghua 代码包学习笔记
# 来源: /home/oyxf/cf_lianghua.zip
# 解压目录: /tmp/cf_lianghua/
# 整理日期: 2026-05-25

---

## 一、值得学习的免费接口和技巧

### 1. akshare — 替代付费问财的低成本方案

**来源**: `钉钉_THS_问答机器人/cf_etf.py`

akshare 是免费开源的财经数据包，提供了大量免费数据接口：

```python
import akshare as ak

# ETF历史数据
ak.fund_etf_hist_em(code, period, start_date, end_date, adjust="")

# 沪深可转债历史行情
ak.bond_zh_hs_cov_daily(code)  # code 格式: sh113534

# 可转债实时数据（集思录）
ak.bond_cb_jsl()

# A股每日行情
ak.stock_zh_a_daily(code, start_date, end_date, adjust="")

# 获取ETF列表
ak.fund_etf_fund_daily_em()  # 返回: 代码、简称

# 获取可转债列表
ak.bond_zh_cov()  # 返回: 债券简称

# 获取A股股票列表
ak.stock_info_a_code_name()
```

**关键思路**: 通过 `akshare` 可以绕过 `pywencai` 付费接口，实现：
- ETF 择时（均线判断）
- 可转债平均涨跌幅统计
- A股 K线数据拉取

---

### 2. 集思录 jsencrypt 加密登录（execjs 方案）

**来源**: `集思录_模拟登录/jsl_data.py`

集思录登录采用 RSA/jsencrypt 加密：
```python
import execjs

def decoder(text):
    with open('encode_jsl.txt', 'r', encoding='utf8') as f:
        source = f.read()
    ctx = execjs.compile(source)
    key = '397151C04723421F'
    return ctx.call('jslencode', text, key)  # 调用JS加密函数
```

**注意**: `encode_jsl.txt` 是加密 JS 源码，需要浏览器开发者工具提取。
当前我使用 Cookie 方案更简单，此方案作为知识储备保留。

---

### 3. 集思录公告 API（免费无需登录）

**来源**: `THS_钉钉_每日盘口推送/jsl_集思录.py`

```python
import requests, json, datetime

def jsl_公告():
    url = "https://www.jisilu.cn/webapi/cb/announcement_list/?="
    payload = "code=&title=%E8%B5%8E&tp%5B0%5D=Y&type="
    headers = {
        "authority": "www.jisilu.cn",
        "Cookie": "kbzw__Session=5bgkcjcijh75m1ggiii9nr1ji7; ...",  # 只需Session Cookie
        "User-Agent": "Apifox/1.0.0 ...",
        "content-type": "application/x-www-form-urlencoded",
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    re = json.loads(response.text)
    list = ''
    for i in re["data"]:
        if str(datetime.date.today()) == i["anno_dt"]:  # 过滤今日公告
            list += (i["bond_nm"] + "\n" + i["anno_title"] + "\n")
    return list
```

**价值**: 集思录公告是飞哥早间推送的数据来源之一，可作为补充。

---

### 4. 同花顺问财情绪指数（免费接口）

**来源**: `THS_钉钉_每日盘口推送/ths_同花顺.py` 的 `ths_qingxu()`

```python
import requests, json

def ths_qingxu():
    url = "http://q.10jqka.com.cn/api.php?t=indexflash&"
    headers = {
        "Accept": "*/*",
        "Referer": "http://q.10jqka.com.cn/",
        "X-Requested-With": "XMLHttpRequest",
    }
    # 需要从 pywencai 获取 hexin-v 等头信息（付费）
    # 思路：用 pywencai.headers.headers() 获取cookie后自己组装
    re = requests.get(url, headers=headers)
    re = json.loads(re.text)
    r1 = re["zdfb_data"]["znum"]   # 上涨家数
    r2 = re["zdfb_data"]["dnum"]   # 下跌家数
    r3 = re["zdt_data"]["last_zdt"]["ztzs"]  # 涨停数
    r4 = re["zdt_data"]["last_zdt"]["dtzs"]  # 跌停数
    r5 = re["dppj_data"]            # 情绪指数
```

**限制**: 依赖 pywencai 拿到 `hexin-v` 等签名头，付费接口。

---

### 5. 东方财富实时行情 API（免费）

**来源**: `BAK/20210416 弃 查询股票信息/ceshi.py`

```python
# 实时行情 — 东方财富接口
# type: 0=深圳 1=上海
url = 'http://push2.eastmoney.com/api/qt/stock/details/get?ut=fa5fd1943c7b386f172d6893dbfba10b&fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54,f55&pos=-11&secid={0}.{1}'.format(type, nol)

# 返回字段:
# prePrice = 开盘价, details[n] = 分时数据
# fields: f1=?, f2=?, f3=?, f4=? | f51=时间, f52=价格, f53=涨跌额, f54=涨跌幅, f55=成交量
```

---

### 6. Tushare 拉取可转债历史行情

**来源**: `Tushare/run.py`

```python
import tushare as ts

pro = ts.pro_api('your_token')

# 拉取可转债每日行情
df = pro.cb_daily(ts_code='113534.SH', ...)
# 字段: ts_code, trade_date, pre_close, open, high, low, close, change, pct_chg, vol, amount
```

**注意**: 需要 Tushare token（免费注册可得），数据质量较高。

---

### 7. 中国节假日判断（holidays 库）

**来源**: `THS_钉钉_每日盘口推送/tool_time.py` / `钉钉_THS_问答机器人/cf_time.py`

```python
import datetime, holidays

def is_trading_day():
    cn_holidays = holidays.China()
    today = datetime.date.today()
    if today in cn_holidays or today.weekday() > 4:
        return False  # 非交易日
    return True

def is_trading_time():
    now = datetime.datetime.now().time()
    start = datetime.time(9, 15)
    end = datetime.time(11, 30)
    if start <= now <= end:
        return True
    elif now.hour >= 13 and now.hour < 15:
        return True
    return False
```

---

### 8. 钉钉机器人消息推送（标准接口）

**来源**: `THS_钉钉_每日盘口推送/tool_robot.py`

```python
import requests

token = "your_token"
url = "https://oapi.dingtalk.com/robot/send?access_token={}".format(token)
headers = {"Content-Type": "application/json"}

def msg_Text(text):
    data = {
        "at": {"isAtAll": False},
        "text": {"content": text},
        "msgtype": "text",
    }
    return requests.post(url, json=data, headers=headers)

def msg_Markdown(title, text):
    data = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
    }
    return requests.post(url, json=data, headers=headers)

def msg_Link(text, title, picUrl, messageUrl):
    data = {
        "msgtype": "link",
        "link": {"text": text, "title": title, "picUrl": picUrl, "messageUrl": messageUrl},
    }
    return requests.post(url, json=data, headers=headers)
```

---

### 9. 雪球selenium爬虫方案（已弃用，了解思路）

**来源**: `BAK/2022年9月17日 chrom获取雪球数据/selenium_month.py`

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# 反爬配置
opt = Options()
opt.add_experimental_option('excludeSwitches', ['enable-automation'])
opt.add_argument("disable-blink-features=AutomationControlled")
opt.add_experimental_option('useAutomationExtension', False)
opt.page_load_strategy = 'normal'

web = webdriver.Chrome(options=opt, executable_path='...')
# 雪球K线API（需登录cookie）
url = 'https://stock.xueqiu.com/v5/stock/chart/kline.json?symbol=SH688776&begin=...&period=month&type=before&count=-284&indicator=kline,pe,pb,ps,pcf,market_capital,agt,ggt,balance'
```

**结论**: 雪球反爬严格，需要有效 cookie。当前 `jisilu_cb_data.db` 方案更稳定。

---

### 10. MySQL 数据库操作封装

**来源**: `集思录_获取指定转债30天数据/mysql_connector.py`

```python
import mysql.connector

def QUERY(sql):
    mycursor.execute(sql)
    mydb.commit()
    return mycursor.rowcount

def SELECT_ALL(sql):
    mycursor.execute(sql)
    return mycursor.fetchall()

def SELECT_A(sql):
    mycursor.execute(sql)
    return mycursor.fetchone()

def INSERT(sql, val):
    mycursor.execute(sql, val)
    mydb.commit()

def executemany(sql, val):
    # 批量插入
    mycursor.executemany(sql, val)
    mydb.commit()
```

---

## 二、排除的代码（价值低/已过时）

| 文件 | 排除原因 |
|------|----------|
| BAK/* 下所有代码 | 早期测试代码，2021~2022年，已弃用 |
| `ths_同花顺.py` | pywencai 付费接口，无法直接使用 |
| `集思录_模拟登录/encode_jsl.txt` | 缺失关键 JS 文件，无法独立运行 |
| `钉钉_THS_问答机器人/run.py` | Flask 钉钉机器人（独立部署），与我当前架构不兼容 |

---

## 三、可整合到现有系统的思路

1. **akshare 拉取 ETF/K线数据** → 替代或补充雪球接口
2. **集思录公告 API** → 早间推送内容补充
3. **东方财富实时行情** → 作为 stock-price-query 的备用数据源
4. **holidays 判断交易日** → 替换现有 is_trading_day() 逻辑

---

## 四、结合现有运行系统的整合分析

### 4.1 现有数据架构

```
数据源（集思录Cookie）
  ├── jisilu_cb.py              — 全量一次采集（rp=5000）
  ├── jisilu_cb_incremental.py  — 每日增量采集（10批×35条）
  └── jisilu_cb_enriched.py     — 带正股数据 enrichment

存储（jisilu.db SQLite）
  ├── cb_bond_list   — 343只转债目录
  └── daily_quotes   — 每日行情快照

策略/分析
  ├── cb_noredeem_strategy_v2.py  — B型不强赎V1+V2双策略
  ├── cb_momentum_strategy.py      — 动量策略
  ├── jisilu_redeem_analysis.py   — 已不强赎历史统计
  └── backtest_daily.py          — 回测计算

推送
  └── 钉钉 webhook（硬编码在各脚本内）
```

### 4.2 akshare 可补充的能力（待测试）


| 能力 | akshare 函数 | 对比现有方案 |
|------|-------------|-------------|
| ETF历史数据 | `ak.fund_etf_hist_em(code)` | 雪球K线需Cookie，akshare免费但数据质量待验 |
| 可转债历史行情 | `ak.bond_zh_hs_cov_daily(code)` | 现有集思录数据更权威 |
| 指数成分股列表 | `ak.index_weight_cons_df(idx)` | 回测计算可能需要替代雪球 |
| 个股实时行情 | `ak.stock_zh_a_spot_em()` | 东方财富接口备用 |

### 4.3 整合优先级

**不需要改动（现有方案更优）：**
- 集思录Cookie方案：简单稳定，不需切execjs
- SQLite存储：够用，迁MySQL成本高无必要
- 钉钉推送：已有完整实现
- 不强赎策略：V1+V2已跑通，不需换

**可能优化的地方：**
1. **指数数据来源**：backtest_daily.py 用selenium拉雪球K线，可研究用 akshare 替代
2. **ETF数据**：jisilu_lof_index_push.py 用集思录LOF接口，可对比 akshare 数据完整性
3. **集思录公告**：现有公告API可补充早间推送内容
4. **holidays库**：替代 jisilu_calendar.py 里的手动判断逻辑

### 4.4 关键结论

cf_lianghua 里 pywencai 付费接口是核心，但我的系统不依赖它是**正确选择**。东方财富实时行情API是好的备用数据源，值得记入 TOOLS.md。
