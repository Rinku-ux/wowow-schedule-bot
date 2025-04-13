#!/bin/bash
set -e

# 必要なものをインストール
apt update
apt install -y chromium chromium-driver

# パスを確認（オプション）
which chromium
which chromium-browser

# スクリプトを実行
python wowow_schedule.py
