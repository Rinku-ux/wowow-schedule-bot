#!/bin/bash
set -e

apt-get update
apt-get install -y wget gnupg2
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
apt-get update
apt-get install -y google-chrome-stable

echo "Checking chrome installation paths:"
which google-chrome-stable || true
which google-chrome || true

python wowow_schedule.py
