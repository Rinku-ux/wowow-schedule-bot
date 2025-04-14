import logging
import time
from datetime import datetime, timedelta
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# 設定
SPREADSHEET_ID = "1lkshTdrk5gVUpSUe9-xTpq438xQQh_SBGcKXfBboH7s"
SERVICE_ACCOUNT_FILE = "credentials1.json"
SHEET_NAME = "アニマックス"
URL = "https://www.animax.co.jp/programs/schedule_weekly"

# ログ設定
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

def fetch_thumbnail_url(driver, program_url):
    """
    番組URLにアクセスしてサムネイル画像のURLを取得する関数
    """
    thumbnail_url = ''
    try:
        # 新しいタブを開く
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[1])
        driver.get(program_url)

        # ページが完全に読み込まれるまで待機
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.p-detail-block.block-thumbnail.pc-order-1"))
        )

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 指定されたHTML構造からサムネイル画像を取得
        img_tag = soup.select_one('div.p-detail-block.block-thumbnail.pc-order-1 figure.p-detail-img img')
        if img_tag and 'src' in img_tag.attrs:
            thumbnail_url = img_tag['src']
            logging.debug(f"サムネURL取得: {thumbnail_url}")
        else:
            logging.warning(f"サムネイル画像が見つかりませんでした: {program_url}")

    except Exception as e:
        logging.error(f"サムネURL取得中にエラーが発生しました: {e}")
    finally:
        # タブを閉じて元のタブに戻る
        driver.close()
        driver.switch_to.window(driver.window_handles[0])

    return thumbnail_url

def fetch_animax_schedule(driver):
    """
    アニマックスの番組表から番組を取得し、48件ごとに日付を割り当てる関数
    """
    programs = []

    try:
        driver.get(URL)
        logging.info("ページ読み込み開始")

        # ページが完全に読み込まれるまで待機
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "js-program-contents-weekly"))
        )

        # 現在の日付を取得 (例: "4月14日(月)")
        today = datetime.now()
        weekday_map = {
            0: '月',  # Monday
            1: '火',
            2: '水',
            3: '木',
            4: '金',
            5: '土',
            6: '日'
        }
        today_str = f"{today.month}月{today.day}日({weekday_map[today.weekday()]})"
        logging.debug(f"今日の日付: {today_str}")

        # 日付ヘッダーをすべて取得してログに出力（デバッグ用）
        all_day_headers = driver.find_elements(By.CSS_SELECTOR, "#js-program-header a")
        logging.debug("利用可能な日付ヘッダー:")
        for header in all_day_headers:
            header_text = header.text.strip()
            logging.debug(f" - {header_text}")

        # 今日の日付に対応するヘッダーを検索
        day_header = None
        for header in all_day_headers:
            header_text = header.text.strip()
            if today_str == header_text:
                day_header = header
                break

        if not day_header:
            # 部分一致で再試行
            pattern = re.compile(rf"{today.month}月{today.day}日\s*\({weekday_map[today.weekday()]}\)")
            for header in all_day_headers:
                header_text = header.text.strip()
                if pattern.search(header_text):
                    day_header = header
                    break

        if not day_header:
            logging.error(f"今日の日付 '{today_str}' のヘッダーが見つかりませんでした。")
            return programs

        logging.info(f"今日の日付ヘッダー '{today_str}' をクリックします。")

        # スクロールして可視化
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", day_header)
        time.sleep(1)  # スクロールアニメーションのための待機

        # JavaScriptを使用してクリック
        try:
            driver.execute_script("arguments[0].click();", day_header)
            logging.debug("JavaScriptを使用してヘッダーをクリックしました。")
        except Exception as e:
            logging.warning(f"JavaScriptクリックに失敗しました: {e}")
            driver.save_screenshot("click_js_error.png")
            logging.debug("スクリーンショットを 'click_js_error.png' として保存しました。")

        # もしJavaScriptクリックがうまくいかない場合、ActionChainsを使用
        try:
            actions = ActionChains(driver)
            actions.move_to_element(day_header).click().perform()
            logging.debug("ActionChainsを使用してヘッダーをクリックしました。")
        except Exception as e:
            logging.warning(f"ActionChainsクリックに失敗しました: {e}")
            driver.save_screenshot("click_actionchains_error.png")
            logging.debug("スクリーンショットを 'click_actionchains_error.png' として保存しました。")

        # 番組セクションがロードされるまで待機
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "m-program-weekly--program"))
        )

        # ページソースを取得
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 番組セルを取得（すべて取得）
        program_cells = soup.select('.m-program-weekly--program')
        logging.debug(f"取得した番組セルの数: {len(program_cells)}")

        for index, cell in enumerate(program_cells, start=1):
            try:
                time_tag = cell.select_one('.m-program-weekly-time')
                title_tag = cell.select_one('h3')
                episode_tag = cell.select_one('.m-program-weekly-episode')
                url_tag = cell.select_one('a')

                program_url = url_tag['href'] if url_tag else ''
                if program_url and not program_url.startswith('http'):
                    program_url = "https://www.animax.co.jp" + program_url  # 相対URLを絶対URLに変換

                # サムネURL取得関数を呼び出す
                thumbnail_url = fetch_thumbnail_url(driver, program_url) if program_url else ''

                # 48件ごとに日付を変更
                day_offset = (index - 1) // 48  # 0から始まる
                date_for_program = today + timedelta(days=day_offset)
                date_str = f"{date_for_program.month}月{date_for_program.day}日({weekday_map[date_for_program.weekday()]})"

                program = {
                    '日付': date_str,
                    '時間': time_tag.get_text(strip=True) if time_tag else '',
                    'タイトル': title_tag.get_text(strip=True) if title_tag else '',
                    '話数': episode_tag.get_text(strip=True) if episode_tag else '',
                    # '番組URL': program_url,  # 番組URLは不要なのでコメントアウト
                    'サムネURL': thumbnail_url,  # サムネURLを追加
                }

                logging.debug(f"{index}番目の番組取得: {program}")
                programs.append(program)

            except Exception as e:
                logging.warning(f"番組データ解析エラー ({index}番目): {e}")

    except Exception as e:
        logging.error(f"スケジュールページの取得中にエラーが発生しました: {e}")

    return programs

def write_to_spreadsheet(programs):
    """
    取得した番組データをGoogleスプレッドシートに書き込む関数
    """
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        gc = gspread.authorize(creds)

        sh = gc.open_by_key(SPREADSHEET_ID)

        try:
            worksheet = sh.worksheet(SHEET_NAME)
            sh.del_worksheet(worksheet)
            logging.debug(f"既存のシート '{SHEET_NAME}' を削除しました。")
            time.sleep(2)
        except Exception as e:
            logging.debug(f"シート '{SHEET_NAME}' が存在しない可能性があります: {e}")

        sheet = sh.add_worksheet(title=SHEET_NAME, rows="1000", cols="10")
        logging.debug(f"新しいシート '{SHEET_NAME}' を作成しました。")
        time.sleep(2)

        # ヘッダーを追加
        sheet.append_row(["日付", "時間", "タイトル", "話数", "サムネURL"])

        # データを整形
        data = [[
            prog['日付'],
            prog['時間'],
            prog['タイトル'],
            prog['話数'],
            prog['サムネURL']
        ] for prog in programs]

        if data:
            # バッチ更新を利用してデータを書き込む
            sheet.batch_update([
                {
                    'range': f"A2:E{len(data)+1}",
                    'values': data,
                    'majorDimension': 'ROWS'
                }
            ])
            logging.info(f"✅ '{SHEET_NAME}' に {len(data)} 件書き込み完了")
        else:
            logging.warning("書き込むデータが存在しません。")

    except Exception as e:
        logging.error(f"スプレッドシートへの書き込み中にエラーが発生しました: {e}")

# メイン処理
def main():
    """
    メイン関数：番組表の取得とスプレッドシートへの書き込みを実行
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')  # 画面サイズを大きく設定
    options.add_argument('--disable-gpu')  # GPUを無効化
    options.add_argument('--disable-extensions')  # 拡張機能を無効化
    options.add_argument('--start-maximized')  # 最大化で起動

    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    try:
        programs = fetch_animax_schedule(driver)

        if programs:
            logging.info(f"取得番組数: {len(programs)}")
            write_to_spreadsheet(programs)
        else:
            logging.error("番組データを取得できませんでした。")
    finally:
        driver.quit()
        logging.debug("WebDriver を終了しました。")

if __name__ == "__main__":
    main()
