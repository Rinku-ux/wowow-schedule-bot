#!/bin/bash
set -e

# Chromium をインストール
apt update
apt install -y chromium-browser

# スクリプトを実行
python wowow_schedule.py
