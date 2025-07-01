import logging
import time
from datetime import datetime, timedelta
import os
import gspread
import logging

def find_chrome_binary():
    """Google Chromeのバイナリパスを自動検出する"""
    candidates = ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]
    for path in candidates:
        if os.path.exists(path):
            logging.info(f"Chrome binary found: {path}")
            return path
    raise FileNotFoundError("Google Chrome binary not found.")

chrome_binary = find_chrome_binary()

# Python側の日付処理をJSTに固定
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
def fetch_schedule_multiple_days(start_date, days=1):
    """指定された開始日から指定された日数分の番組表を取得する"""
    url = f"https://www.wowow.co.jp/schedule/{start_date}"
    logging.debug(f"初期アクセス: {url}")

    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--lang=ja-JP')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.7049.84 Safari/537.36')
    options.binary_location = chrome_binary

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    # ブラウザのタイムゾーンをJSTに設定
    driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {"timezoneId": "Asia/Tokyo"})

    all_programs = []
    # 文字列の開始日からdatetimeオブジェクトを生成
    current_date_obj = datetime.strptime(start_date, "%Y%m%d")

    try:
        driver.get(url)
        for day in range(days):
            logging.debug(f"[{day+1}日目] ページ読み込み待機...")
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "mdl__program-table"))
            )

            soup = BeautifulSoup(driver.page_source, "html.parser")
            program_cells = soup.select('.mdl__program-table td.__prime, .mdl__program-table td.__live, .mdl__program-table td.__cinema')

            display_date = current_date_obj.strftime("%Y/%m/%d")

            for cell in program_cells:
                try:
                    time_tag = cell.select_one('.__time')
                    title_tag = cell.select_one('.__title-text')
                    img_tag = cell.select_one('.__thumb img')
                    desc_tag = cell.select_one('.__lead p')

                    channel_class = next((cls for cls in cell["class"] if cls in CHANNEL_MAP), "不明")
                    channel_name = CHANNEL_MAP.get(channel_class, "不明")
                    
                    raw_time = time_tag.text.strip() if time_tag else ''

                    program = {
                        'チャンネル': channel_name,
                        '日付': display_date,
                        '時間': raw_time,
                        'タイトル': title_tag.text.strip() if title_tag else '',
                        '画像URL': img_tag['src'].strip() if img_tag and img_tag.has_attr('src') else '',
                        '説明': desc_tag.text.strip() if desc_tag else '',
                    }
                    logging.debug(f"番組取得: [{program['チャンネル']}] {program['日付']} {program['時間']} - {program['タイトル']}")
                    all_programs.append(program)
                except Exception as e:
                    logging.warning(f"番組データ解析エラー: {e}")

            # 次の日のために日付を1日進める
            current_date_obj += timedelta(days=1)

            # 最終日以外なら、翌日のリンクに移動
            if day < days - 1:
                try:
                    next_link = driver.find_element(By.CSS_SELECTOR, 'a.btn__more-view')
                    next_link_url = next_link.get_attribute('href')
                    logging.debug(f"翌日リンクへ移動: {next_link_url}")
                    driver.get(next_link_url)
                    time.sleep(3) # ページの読み込み待ち
                except Exception as e:
                    logging.warning(f"翌日リンク取得エラー（最終日？）: {e}")
                    break
    finally:
        driver.quit()

    return all_programs

# ========== スプレッドシート書き込み ==========
def write_to_spreadsheet(programs):
    """取得した番組データをスプレッドシートに書き込む"""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(SPREADSHEET_ID)

    # 既存のシートを一度削除し、新しいシートを作成
    for sheet_name in SHEET_NAMES:
        try:
            worksheet_to_delete = sh.worksheet(sheet_name)
            sh.del_worksheet(worksheet_to_delete)
            logging.info(f"シート '{sheet_name}' を削除しました。")
            time.sleep(2)
        except gspread.WorksheetNotFound:
            logging.info(f"シート '{sheet_name}' は存在しないため、削除をスキップします。")
        except Exception as e:
            logging.error(f"シート '{sheet_name}' の削除中にエラー: {e}")
            pass
        
        # 新しいシートを作成してヘッダーを書き込む
        sheet = sh.add_worksheet(title=sheet_name, rows="1000", cols="10")
        sheet.append_row(["日付", "時間", "タイトル", "説明", "画像URL"])
        logging.info(f"シート '{sheet_name}' を作成し、ヘッダーを書き込みました。")
        time.sleep(2)

    # チャンネルごとにデータを振り分け
    separated = {"WOWOWプライム": [], "WOWOWライブ": [], "WOWOWシネマ": []}
    for prog in programs:
        if prog['チャンネル'] in separated:
            separated[prog['チャンネル']].append([prog['日付'], prog['時間'], prog['タイトル'], prog['説明'], prog['画像URL']])
    
    # 各シートにデータを一括で書き込み
    for sheet_name, data in separated.items():
        if not data:
            logging.info(f"シート '{sheet_name}' に書き込むデータはありません。")
            continue
        try:
            sheet = sh.worksheet(sheet_name)
            # ヘッダーがあるのでA2から書き込み
            sheet.update(f"A2:E{len(data)+1}", data)
            logging.info(f"✅ {sheet_name} に {len(data)} 件書き込み完了")
            time.sleep(2)
        except Exception as e:
            logging.error(f"シート '{sheet_name}' への書き込み中にエラー: {e}")


# ========== メイン処理 ==========
def main():
    """スクリプトのメイン実行関数"""
    today = datetime.now().strftime("%Y%m%d")
    # ★★★★★ 修正点: 取得日数を1日に変更 ★★★★★
    programs = fetch_schedule_multiple_days(today, days=1)
    if programs:
        logging.info(f"🎬 取得番組総数: {len(programs)}")
        write_to_spreadsheet(programs)
    else:
        logging.error("番組データを取得できませんでした。")

if __name__ == "__main__":
    main()
