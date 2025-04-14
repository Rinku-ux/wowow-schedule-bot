import logging
import time
from datetime import datetime, timedelta
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import pytz  # タイムゾーン管理のために追加

def find_chrome_binary():
    candidates = ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]
    for path in candidates:
        if os.path.exists(path):
            logging.info(f"Chrome binary found: {path}")
            return path
    raise FileNotFoundError("Google Chrome binary not found.")

chrome_binary = find_chrome_binary()

# タイムゾーンを明示的に設定
tokyo = pytz.timezone('Asia/Tokyo')
start_date = datetime.now(tokyo).replace(hour=0, minute=0, second=0, microsecond=0)

# ========== 設定 ==========
SPREADSHEET_ID = "1lkshTdrk5gVUpSUe9-xTpq438xQQh_SBGcKXfBboH7s"
SERVICE_ACCOUNT_FILE = "credentials1.json"  # JSON認証情報ファイルのパス
SHEET_NAMES = ["WOWOWプライム", "WOWOWライブ", "WOWOWシネマ"]

# ========== ログ設定 ==========
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

CHANNEL_MAP = {
    "__prime": "WOWOWプライム",
    "__live": "WOWOWライブ",
    "__cinema": "WOWOWシネマ"
}

# ========== 番組表取得 ==========
def fetch_schedule_multiple_days(start_date, days=2):
    all_programs = []
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--lang=ja-JP')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.7049.84 Safari/537.36')
    options.binary_location = chrome_binary  # 自動検出したパスを利用

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    # 重要：ブラウザ内のタイムゾーンを JST に設定
    driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {"timezoneId": "Asia/Tokyo"})

    try:
        for day in range(days):
            current_date = start_date + timedelta(days=day)
            formatted_date = current_date.strftime('%Y%m%d')
            display_date = current_date.strftime('%Y/%m/%d')
            url = f"https://www.wowow.co.jp/schedule/{formatted_date}"
            logging.debug(f"アクセス: {url}")

            driver.get(url)

            logging.debug(f"[{day+1}日目 ({display_date})] ページ読み込み待機...")
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "mdl__program-table"))
            )

            soup = BeautifulSoup(driver.page_source, "html.parser")
            prime_cells = soup.select('.mdl__program-table td.__prime, .mdl__program-table td.__live, .mdl__program-table td.__cinema')

            for cell in prime_cells:
                try:
                    time_tag = cell.select_one('.__time')
                    title_tag = cell.select_one('.__title-text')
                    img_tag = cell.select_one('.__thumb img')
                    desc_tag = cell.select_one('.__lead p')

                    channel_class = next((cls for cls in cell.get("class", []) if cls in CHANNEL_MAP), "不明")
                    channel_name = CHANNEL_MAP.get(channel_class, "不明")

                    # 時刻の補正が必要な場合はここで行う（例: 1時間補正）
                    raw_time = time_tag.text.strip() if time_tag else ''
                    corrected_time = raw_time  # 必要に応じて補正

                    program = {
                        'チャンネル': channel_name,
                        '日付': display_date,  # 各日に対する正確な日付を設定
                        '時間': corrected_time,
                        'タイトル': title_tag.text.strip() if title_tag else '',
                        '画像URL': img_tag['src'].strip() if img_tag and img_tag.has_attr('src') else '',
                        '説明': desc_tag.text.strip() if desc_tag else '',
                    }
                    logging.debug(f"番組取得: [{program['チャンネル']}] {program['時間']} - {program['タイトル']}")
                    all_programs.append(program)
                except Exception as e:
                    logging.warning(f"番組データ解析エラー: {e}")

            # 一日ごとの処理の後に一時停止
            time.sleep(2)
    finally:
        driver.quit()

    return all_programs

# ========== スプレッドシート書き込み ==========
def write_to_spreadsheet(programs):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(SPREADSHEET_ID)
    for sheet_name in SHEET_NAMES:
        try:
            worksheet = sh.worksheet(sheet_name)
            sh.del_worksheet(worksheet)
            logging.debug(f"既存のシート '{sheet_name}' を削除しました。")
            time.sleep(1)
        except Exception:
            logging.debug(f"シート '{sheet_name}' が存在しないため削除スキップ。")
            pass
        sheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="10")
        time.sleep(1)
        sheet.append_row(["日付", "時間", "タイトル", "説明", "画像URL"])
        logging.debug(f"シート '{sheet_name}' にヘッダーを追加しました。")

    separated = {"WOWOWプライム": [], "WOWOWライブ": [], "WOWOWシネマ": []}
    for prog in programs:
        if prog['チャンネル'] in separated:
            separated[prog['チャンネル']].append([prog['日付'], prog['時間'], prog['タイトル'], prog['説明'], prog['画像URL']])

    for sheet_name, data in separated.items():
        if not data:
            logging.info(f"シート '{sheet_name}' に書き込むデータがありません。")
            continue
        sheet = sh.worksheet(sheet_name)
        # Google Sheetsのバッチサイズの制限に注意（ここでは一括で追加）
        sheet.update(f"A2:E{len(data)+1}", data)
        logging.info(f"✅ シート '{sheet_name}' に {len(data)} 件書き込み完了")
        time.sleep(1)

# ========== メイン ==========
def main():
    # タイムゾーンを考慮して開始日を取得
    today = datetime.now(tokyo).replace(hour=0, minute=0, second=0, microsecond=0)
    logging.info(f"スケジュール取得開始日: {today.strftime('%Y/%m/%d')}")
    programs = fetch_schedule_multiple_days(today, days=2)
    if programs:
        logging.info(f"🎉 取得番組数: {len(programs)}")
        write_to_spreadsheet(programs)
    else:
        logging.error("番組データを取得できませんでした。")

if __name__ == "__main__":
    main()
