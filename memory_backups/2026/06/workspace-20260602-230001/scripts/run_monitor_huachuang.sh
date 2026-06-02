#!/bin/bash
# 北方华创盯盘脚本wrapper
# 直接调用monitor脚本，结果推送到钉钉
cd /root/.openclaw/workspace
python3 scripts/monitor_north_huachuang.py 002371 北方华创 2>&1