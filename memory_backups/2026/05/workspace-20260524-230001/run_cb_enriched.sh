#!/bin/bash
# 集思录转债增强版数据采集 - wrapper script
cd /root/.openclaw/workspace
python3 scripts/jisilu_cb_enriched.py >> logs/cb_enriched.log 2>&1