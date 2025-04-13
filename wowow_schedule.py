import logging
import time
from datetime import datetime, timedelta
import os
import gspread

# Python側の日付処理をJSTに固定（ただしこれだけではブラウザは変更されない）
os.environ['TZ'] = 'Asia/Tokyo'
time.tzset()

from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

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
    url = f"https://www.wowow.co.jp/schedule/{start_date}"
    logging.debug(f"初期アクセス: {url}")

    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--lang=ja-JP')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.7049.84 Safari/537.36')
    options.binary_location = "/usr/bin/chromium"

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    # 重要：ブラウザ内のタイムゾーンを JST に設定
    driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {"timezoneId": "Asia/Tokyo"})

    all_programs = []
    try:
        driver.get(url)
        for day in range(days):
            logging.debug(f"[{day+1}日目] ページ読み込み待機...")
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "mdl__program-table"))
            )

            soup = BeautifulSoup(driver.page_source, "html.parser")
            prime_cells = soup.select('.mdl__program-table td.__prime, .mdl__program-table td.__live, .mdl__program-table td.__cinema')

            # ※ この場合、日付は Python の datetime.now() から取得しています
            today_date = datetime.now().strftime("%Y/%m/%d")
            for cell in prime_cells:
                try:
                    time_tag = cell.select_one('.__time')
                    title_tag = cell.select_one('.__title-text')
                    img_tag = cell.select_one('.__thumb img')
                    desc_tag = cell.select_one('.__lead p')

                    channel_class = next((cls for cls in cell["class"] if cls in CHANNEL_MAP), "不明")
                    channel_name = CHANNEL_MAP.get(channel_class, "不明")

                    # もし時刻がずれている場合は、ここで後処理で補正可能
                    raw_time = time_tag.text.strip() if time_tag else ''
                    # 例として、もし1時間ずれている場合には補正する（必要に応じて調整）
                    # ここでは一度ログ出力だけしています
                    corrected_time = raw_time  # 必要なら後処理を追加

                    program = {
                        'チャンネル': channel_name,
                        '日付': today_date,
                        '時間': corrected_time,
                        'タイトル': title_tag.text.strip() if title_tag else '',
                        '画像URL': img_tag['src'].strip() if img_tag and img_tag.has_attr('src') else '',
                        '説明': desc_tag.text.strip() if desc_tag else '',
                    }
                    logging.debug(f"番組取得: [{program['チャンネル']}] {program['時間']} - {program['タイトル']}")
                    all_programs.append(program)
                except Exception as e:
                    logging.warning(f"番組データ解析エラー: {e}")

            # 翌日に移動
            try:
                next_link = driver.find_element(By.CSS_SELECTOR, 'a.btn__more-view')
                next_link_url = next_link.get_attribute('href')
                logging.debug(f"翌日リンクへ移動: {next_link_url}")
                driver.get(next_link_url)
                time.sleep(3)
            except Exception as e:
                logging.warning(f"翌日リンク取得エラー（最終日？）: {e}")
                break
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
            sh.del_worksheet(sh.worksheet(sheet_name))
            time.sleep(2)
        except Exception:
            pass
        sheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="10")
        time.sleep(2)
        sheet.append_row(["日付", "時間", "タイトル", "説明", "画像URL"])

    separated = {"WOWOWプライム": [], "WOWOWライブ": [], "WOWOWシネマ": []}
    for prog in programs:
        if prog['チャンネル'] in separated:
            separated[prog['チャンネル']].append([prog['日付'], prog['時間'], prog['タイトル'], prog['説明'], prog['画像URL']])
    for sheet_name, data in separated.items():
        if not data:
            continue
        sheet = sh.worksheet(sheet_name)
        sheet.batch_update([
            {
                'range': f"A2:E{len(data)+1}",
                'values': data,
                'majorDimension': 'ROWS'
            }
        ])
        logging.info(f"✅ {sheet_name} に {len(data)} 件書き込み完了")
        time.sleep(2)

# ========== メイン ==========
def main():
    today = datetime.now().strftime("%Y%m%d")
    programs = fetch_schedule_multiple_days(today, days=2)
    if programs:
        logging.info(f"🎬 取得番組数: {len(programs)}")
        write_to_spreadsheet(programs)
    else:
        logging.error("番組データを取得できませんでした。")

if __name__ == "__main__":
    main()
