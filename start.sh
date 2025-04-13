#!/bin/bash
set -e

# 必要なツールをインストール
apt-get update
apt-get install -y wget gnupg2

# Googleの公開鍵を登録
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -

# Google Chromeリポジトリを追加
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

# パッケージ情報更新＆Google Chromeインストール
apt-get update
apt-get install -y google-chrome-stable

# インストールしたパスを確認（任意）
which google-chrome-stable

# スクリプト実行
python wowow_schedule.py
