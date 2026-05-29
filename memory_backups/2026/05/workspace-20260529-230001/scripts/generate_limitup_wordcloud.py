#!/usr/bin/env python3
"""
涨停关键词词云生成器
- 通过 pywencai 查询当日涨停股票
- 提取涨停原因关键词
- 生成词云图片并保存
"""

import os
import re
import datetime as dt
import jieba
import wordcloud
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import Counter

# ============ 配置 ============
CLOUD_DIR = "/home/www/toolbox-api/stock/wordcloud"
os.makedirs(CLOUD_DIR, exist_ok=True)

# 自定义停用词（常见无意义词）
STOPWORDS = {
    '的', '了', '是', '在', '和', '与', '或', '为', '等', '及', '对', '将', '把', '被',
    '由', '从', '到', '以', '于', '之', '因', '让', '使', '令',
    '这只', '该股', '个股', '股票', '今日', '涨停', '连续', '日', '天',
    '公司', '股份', '有限公司', '集团', '股份公司', 'A股', '上证', '深证', '创业板',
    '科创', '市场', '交易', '收盘', '涨跌幅', '股价', '涨幅', '成交量', '成交额',
    '万', '亿', '元', '股', '版', '块', '概念', '什么', '哪些', '怎么',
    '吗', '呢', '啊', '吧', '哦', '嗯', '哈', '呀', '哇', '哟',
    '披露', '公告', '表示', '称', '根据', '通过', '进行', '发布', '显示', '数据',
    '相关', '人士', '此前', '目前', '现在', '昨日', '盘中',
    '涨停原因', '涨停类别', '类别', '原因', '说明', '详情', '解释',
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
    'N', 'ST',
}

# 自定义词典（加入常见金融术语）
CUSTOM_WORDS = [
    '人工智能', '新能源汽车', '锂电池', '储能', '光伏', '风电',
    '半导体', '芯片', '集成电路', '国产替代', '算力', 'AI',
    '机器人', '低空经济', 'eVTOL', '商业航天', '卫星互联网',
    '创新药', '医疗器械', '中药', '疫苗', '合成生物',
    '量子科技', '脑机接口', '固态电池', '钠离子', 'HJT',
    'TOPCon', 'BC电池', '钙钛矿', '碳化硅', 'SiC',
    '小米汽车', '华为汽车', '比亚迪', '特斯拉', '宁德时代',
    'DeepSeek', 'R1', '大模型', 'Agent', 'AIAgent',
    '消费电子', '折叠屏', '屏下摄像', '星闪', '卫星通话',
    '银行', '保险', '券商', '多元金融',
    '中字头', '央企', '国企改革', '资产重组', '并购',
    '新型电力', '虚拟电厂', '电力改革',
    '一带一路', '自贸区', '海南', '跨境电商',
    'Sora', '多模态', '文生视频', '视频生成',
]

for w in CUSTOM_WORDS:
    jieba.add_word(w, freq=100)

# ============ 数据获取 ============

def fetch_limitup_stocks():
    """通过 pywencai 查询当日涨停股票"""
    import pywencai
    today = dt.datetime.now().strftime('%Y%m%d')
    print(f"[词云] 查询 {today} 涨停股票...")

    try:
        result = pywencai.get(query=f'{today} 涨停', loop=True)
        if result is None or result.empty:
            print("[词云] pywencai 无数据，尝试备用查询")
            result = pywencai.get(query='今日涨停', loop=True)

        print(f"[词云] 获取到 {len(result) if result is not None else 0} 条涨停记录")
        return result
    except Exception as e:
        print(f"[词云] pywencai 查询失败: {e}")
        return None


def extract_keywords_from_result(df):
    """从涨停数据中提取关键词"""
    if df is None or df.empty:
        return []

    print(f"[词云] 提取涨停关键词...  columns: {list(df.columns[:10])}")
    keywords = []

    reason_col = None
    for col in df.columns:
        col_str = str(col)
        if '涨停原因类别' in col_str:
            reason_col = col
            print(f"[词云] 找到涨停原因列: {col_str}")
            break

    if reason_col:
        reasons = df[reason_col].dropna().astype(str).tolist()
    else:
        print(f"[词云] 未找到原因列，用所有字符串列")
        reasons = []
        for col in df.columns:
            if df[col].dtype == object:
                reasons.extend(df[col].dropna().astype(str).tolist())

    for r in reasons:
        r = str(r).strip()
        if len(r) > 1 and r not in ('nan', 'None'):
            keywords.append(r)

    return keywords


def fetch_reason_list_via_web():
    """通过网页抓取获取当日涨停原因列表（pywencai失败时的备用方案）"""
    print("[词云] 备用：从东方财富网页抓取涨停原因...")
    try:
        import requests
        url = "https://data.10jqka.com.cn/ipo/xgpx/field/zdf/order/desc/page/1/ajax/1/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://data.10jqka.com.cn/ipo/xgpx/',
        }
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        rows = data.get('data', []) if isinstance(data, dict) else []
        keywords = []
        for row in rows:
            if isinstance(row, dict):
                reason = row.get('zt_reason', row.get('reason', ''))
                if reason:
                    keywords.append(str(reason))
        print(f"[词云] 东方财富获取到 {len(keywords)} 条原因")
        return keywords
    except Exception as e:
        print(f"[词云] 东方财富抓取失败: {e}")
        return []


# ============ 词云生成 ============

def build_wordfreq(keywords):
    """将关键词列表转换为词频统计"""
    text = ' '.join(keywords)
    words = jieba.cut(text)
    filtered = []
    for w in words:
        w = w.strip()
        if w and len(w) >= 2 and w not in STOPWORDS and not w.isdigit():
            if re.search(r'[\u4e00-\u9fff]', w):
                filtered.append(w)
    return Counter(filtered)


def generate_wordcloud(wordfreq, output_path, date_str):
    """生成词云图片"""
    if not wordfreq:
        print("[词云] 无关键词数据")
        return False

    print(f"[词云] 生成词云... 共 {sum(wordfreq.values())} 个词")
    bg_color = '#0f1419'

    wc = wordcloud.WordCloud(
        width=900,
        height=500,
        background_color=bg_color,
        max_words=80,
        max_font_size=120,
        min_font_size=14,
        font_path='/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        colormap='RdYlGn_r',
        prefer_horizontal=0.7,
        scale=2,
        stopwords=STOPWORDS,
        collocations=False,
    )

    wc.generate_from_frequencies(wordfreq)
    wc.to_file(output_path)
    print(f"[词云] 词云已保存: {output_path}")

    # 生成带标题版本（跳过matplotlib，用纯色背景图片替代）
    # 词云本身已有深色背景+白字，直接使用即可
    print(f"[词云] 词云图片就绪: {output_path}")

    return True


# ============ 主程序 ============

def main():
    today = dt.datetime.now().strftime('%Y-%m-%d')
    cloud_file = os.path.join(CLOUD_DIR, f"{today}.png")
    titled_file = cloud_file.replace('.png', '_titled.png')

    if os.path.exists(cloud_file):
        print(f"[词云] 今日词云已存在: {cloud_file}")
        return cloud_file, today

    # 1. 获取涨停数据
    df = fetch_limitup_stocks()

    # 2. 提取关键词
    if df is not None and not df.empty:
        keywords = extract_keywords_from_result(df)
    else:
        keywords = fetch_reason_list_via_web()

    if not keywords:
        print("[词云] 未能获取涨停关键词，使用备用词")
        keywords = ['人工智能', '新能源汽车', '半导体', '芯片', 'DeepSeek', '大模型',
                   '机器人', '低空经济', '创新药', '固态电池']

    # 3. 构建词频
    wordfreq = build_wordfreq(keywords)
    if not wordfreq:
        print("[词云] 词频为空，使用备用词")
        keywords = ['人工智能', '新能源汽车', '半导体', '芯片', 'DeepSeek', '大模型',
                   '机器人', '低空经济', '创新药', '固态电池']
        wordfreq = build_wordfreq(keywords)
    print(f"[词云] TOP20高频词: {wordfreq.most_common(20)}")

    # 4. 生成词云
    ok = generate_wordcloud(wordfreq, cloud_file, today)

    if ok:
        return cloud_file, today
    return None, today


if __name__ == '__main__':
    path, date = main()
    if path:
        print(f"\n词云生成成功: {path}")