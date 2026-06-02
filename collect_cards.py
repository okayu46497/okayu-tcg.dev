import requests
import re
import time
import sqlite3
import os
import argparse
from urllib.parse import urljoin
from pathlib import Path

BASE_URL = "https://dm.takaratomy.co.jp/card/"
DETAIL_BASE_URL = "https://dm.takaratomy.co.jp/card/detail/"

# スクリプトの親ディレクトリを基準にする
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "cards_v2.db"

# サーバー負荷防止用のウェイト時間 (秒)
REQUEST_INTERVAL = 1.0

def init_db():
    """SQLite データベースとテーブルを初期化する"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            card_id TEXT PRIMARY KEY,
            card_name TEXT NOT NULL,
            civilization TEXT,
            card_type TEXT,
            cost INTEGER,
            power TEXT,
            race TEXT,
            ability_text TEXT,
            image_url TEXT,
            detail_url TEXT
        )
    """)
    conn.commit()
    return conn

def get_card_ids(conn, keyword=None, max_pages=None, incremental=False):
    """
    フェーズ1: 検索結果からカードID (および詳細URLのID) を一括収集する
    incremental=True の場合、すでにDBに登録されているIDが5件連続で検出された時点でクロールを即座に自動停止する
    """
    print(f"=== Phase 1: Collecting Card IDs (Keyword: {keyword}, Max Pages: {max_pages}, Incremental: {incremental}) ===")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://dm.takaratomy.co.jp/card/"
    }
    
    card_ids = []
    page = 1
    cursor = conn.cursor()
    
    while True:
        if max_pages and page > max_pages:
            print(f"Reached max page limit: {max_pages}")
            break
            
        print(f"Fetching search results page {page}...")
        data = {
            "pagenum": str(page)
        }
        if keyword:
            data["keyword"] = keyword
            data["keyword_type[]"] = "card_name"
            
        try:
            response = requests.post(BASE_URL, data=data, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"Failed to fetch page {page}. Status: {response.status_code}")
                break
                
            # HTML片から href='/card/detail/?id=...' 内の ID を正規表現で抽出
            found_ids = re.findall(r"href=['\"]/card/detail/\?id=([^'\"]+?)['\"]", response.text)
            if not found_ids:
                print("No more card IDs found. Fetching completed.")
                break
                
            page_added = 0
            already_exists_streak = 0
            stop_incremental = False
            
            for cid in found_ids:
                if cid not in card_ids:
                    card_ids.append(cid)
                    page_added += 1
                    
                    if incremental:
                        # DBに存在するかチェック
                        cursor.execute("SELECT card_id FROM cards WHERE card_id = ?", (cid,))
                        if cursor.fetchone():
                            already_exists_streak += 1
                            if already_exists_streak >= 5:
                                print(f"  [Incremental] Detected {already_exists_streak} consecutive already-existing card IDs. Stopping page scan.")
                                stop_incremental = True
                                break
                        else:
                            # 新規IDが見つかったらカウントをリセット
                            already_exists_streak = 0
                            
            print(f"  Page {page}: Found {len(found_ids)} IDs (Page Total: {len(card_ids)})")
            
            if stop_incremental:
                break
                
            # 安全のため少しウェイトを入れる
            time.sleep(REQUEST_INTERVAL)
            page += 1
            
        except Exception as e:
            print(f"Error during Phase 1: {e}")
            break
            
    print(f"Phase 1 finished. Collected {len(card_ids)} card IDs in total for processing.")
    return card_ids

def clean_html_tags(text):
    """HTMLタグをクリーニングしてプレーンテキストにする"""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<li>", "＊", text)
    text = re.sub(r"<[^>]+?>", "", text)
    return text.strip()

def parse_card_detail(card_id):
    """
    フェーズ2: 各詳細ページからHTMLをスクレイピングして項目をパースする
    """
    url = f"{DETAIL_BASE_URL}?id={card_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"  [Error] Failed to fetch detail for {card_id}. Status: {response.status_code}")
            return None
            
        html = response.text
        
        # 1. カード名
        name_match = re.search(r"class=['\"]card-name['\"]>([^<]+?)(?:<span|\n|</h3>)", html)
        card_name = name_match.group(1).strip() if name_match else None
        if not card_name:
            title_match = re.search(r"<title>([^|]+?)(?:\(|\|)", html)
            card_name = title_match.group(1).strip() if title_match else f"Unknown Card ({card_id})"
            
        # 2. カードタイプ
        type_match = re.search(r"class=['\"]type['\"]>([^<]+?)</td>", html)
        card_type = type_match.group(1).strip() if type_match else None
        
        # 3. 文明
        civil_match = re.search(r"class=['\"]civil['\"]>([^<]+?)</td>", html)
        civilization = civil_match.group(1).strip() if civil_match else None
        
        # 4. コスト
        cost_match = re.search(r"class=['\"]cost['\"]>([^<]+?)</td>", html)
        cost = None
        if cost_match:
            try:
                cost = int(cost_match.group(1).strip())
            except ValueError:
                pass
                
        # 5. パワー
        power_match = re.search(r"class=['\"]power['\"]>([^<]+?)</td>", html)
        power = power_match.group(1).strip() if power_match else None
        
        # 6. 種族
        race_match = re.search(r"class=['\"]race['\"]>([^<]+?)</td>", html)
        race = race_match.group(1).strip() if race_match else None
        
        # 7. 特殊能力 (ability_text)
        ability_match = re.search(r"class=['\"]skills full['\"]>(.+?)</td>", html, re.DOTALL)
        ability_text = clean_html_tags(ability_match.group(1)) if ability_match else ""
        
        # 8. 画像URL (詳細ページから実URLを取得して保存する - 推測生成ではなく実測・厳守)
        image_match = re.search(r"class=['\"]card-img['\"]>\s*<img\s+[^>]*?src=['\"]([^'\"]+?)['\"]", html)
        image_url = None
        if image_match:
            image_url = urljoin("https://dm.takaratomy.co.jp/", image_match.group(1).strip())
            
        return {
            "card_id": card_id,
            "card_name": card_name,
            "civilization": civilization,
            "card_type": card_type,
            "cost": cost,
            "power": power,
            "race": race,
            "ability_text": ability_text,
            "image_url": image_url,
            "detail_url": url
        }
        
    except Exception as e:
        print(f"  [Error] Parsing detail for {card_id}: {e}")
        return None

def verify_and_report_duplicates():
    """主キー card_id の重複検証を実施し、一意性をテストして報告する"""
    print("\n=== Phase 3: Verifying Card ID Uniqueness & Duplicates ===")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM cards")
    total_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT card_id) FROM cards")
    unique_count = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT card_id, COUNT(*) 
        FROM cards 
        GROUP BY card_id 
        HAVING COUNT(*) > 1
    """)
    duplicates = cursor.fetchall()
    
    print(f"Total Rows in Database: {total_count}")
    print(f"Unique Card IDs Count: {unique_count}")
    
    if total_count == unique_count and len(duplicates) == 0:
        print("  [SUCCESS] All Card IDs are completely unique! Zero duplicates found.")
    else:
        print(f"  [WARNING] Found {len(duplicates)} duplicate card IDs:")
        for cid, count in duplicates[:10]:
            print(f"    - ID: {cid} appears {count} times")
            
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Duel Masters card database collector script")
    parser.add_argument("--keyword", type=str, default=None, help="Keyword to filter cards (e.g. ボルメテウス)")
    parser.add_argument("--all", action="store_true", help="Scrape all official cards")
    parser.add_argument("--incremental", "-i", action="store_true", help="Stop crawling when 5 consecutive existing cards are found")
    parser.add_argument("--max-pages", type=int, default=None, help="Max search pages to collect")
    args = parser.parse_args()
    
    conn = init_db()
    
    # 1. カードID収集
    collected_ids = get_card_ids(
        conn, 
        keyword=args.keyword, 
        max_pages=args.max_pages, 
        incremental=args.incremental
    )
    
    if not collected_ids:
        print("No card IDs collected. Exiting.")
        conn.close()
        return
        
    # 2. 詳細情報取得とDB保存 (レジューム機能対応)
    print("\n=== Phase 2: Crawling & Saving Details (Resume Enabled) ===")
    cursor = conn.cursor()
    
    saved_count = 0
    skipped_count = 0
    
    for idx, cid in enumerate(collected_ids):
        # すでにDBに存在するかチェック
        cursor.execute("SELECT card_id FROM cards WHERE card_id = ?", (cid,))
        if cursor.fetchone():
            skipped_count += 1
            continue
            
        print(f"[{idx+1}/{len(collected_ids)}] Fetching details for {cid}...")
        card_data = parse_card_detail(cid)
        
        if card_data:
            cursor.execute("""
                INSERT INTO cards (card_id, card_name, civilization, card_type, cost, power, race, ability_text, image_url, detail_url)
                VALUES (:card_id, :card_name, :civilization, :card_type, :cost, :power, :race, :ability_text, :image_url, :detail_url)
            """, card_data)
            conn.commit()
            saved_count += 1
            print(f"  -> Saved: {card_data['card_name']} (Image: {card_data['image_url']})")
        else:
            print(f"  -> Failed to parse detail for {cid}")
            
        # サーバーへのマナーとしてウェイトを入れる
        time.sleep(REQUEST_INTERVAL)
        
    print(f"\nPhase 2 finished. Newly Saved: {saved_count}, Skipped (Already Exists): {skipped_count}")
    conn.close()
    
    # 3. 重複検証の実行 (必須要件)
    verify_and_report_duplicates()

if __name__ == "__main__":
    main()
