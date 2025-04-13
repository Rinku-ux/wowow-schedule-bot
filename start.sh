#!/bin/bash
set -e

# パッケージ情報更新＆必要な依存ライブラリインストール
apt-get update
apt-get install -y wget gnupg2 \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils

# Google の公開鍵登録
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -

# Google Chrome リポジトリ追加
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

apt-get update
apt-get install -y google-chrome-stable

# インストール確認：実行ファイルのパスをログに出力
echo "Installed chrome paths:"
which google-chrome-stable || true
which google-chrome || true

# Pythonスクリプト実行
python wowow_schedule.py
