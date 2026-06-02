import sqlite3
import requests
import json
import time
import sys
import os
import asyncio
from pathlib import Path

# パス設定
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "cards_v2.db"
CARDS_JSON_PATH = BASE_DIR / "data" / "cards.json"
DECKS_JSON_PATH = BASE_DIR / "data" / "decks.json"

sys.path.append(str(BASE_DIR))
import app

def check_missing_info():
    print("=== 1. Card Info Missing Check ===")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    queries = {
        "card_name_missing (card_name IS NULL OR card_name = '')": "SELECT COUNT(*) FROM cards WHERE card_name IS NULL OR card_name = '';",
        "image_url_missing (image_url IS NULL OR image_url = '')": "SELECT COUNT(*) FROM cards WHERE image_url IS NULL OR image_url = '';",
        "ability_text_missing (ability_text IS NULL)": "SELECT COUNT(*) FROM cards WHERE ability_text IS NULL;",
        "civilization_missing (civilization IS NULL)": "SELECT COUNT(*) FROM cards WHERE civilization IS NULL;",
        "card_type_missing (card_type IS NULL)": "SELECT COUNT(*) FROM cards WHERE card_type IS NULL;"
    }
    
    for key, q in queries.items():
        cursor.execute(q)
        cnt = cursor.fetchone()[0]
        print(f"  {key}: {cnt}")
        
    conn.close()

def check_urls():
    print("\n=== 2 & 3. Image and Detail URL Survival Check (Random 100) ===")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT card_name, image_url, detail_url FROM cards WHERE image_url IS NOT NULL AND detail_url IS NOT NULL ORDER BY RANDOM() LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    
    img_status = {"200": 0, "404": 0, "others": 0}
    detail_status = {"200": 0, "404": 0, "redirect": 0, "others": 0}
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    print("  Testing 100 URLs...")
    for idx, (name, img_url, detail_url) in enumerate(rows):
        # 画像URLテスト
        try:
            r_img = requests.get(img_url, headers=headers, timeout=5)
            if r_img.status_code == 200:
                img_status["200"] += 1
            elif r_img.status_code == 404:
                img_status["404"] += 1
            else:
                img_status["others"] += 1
        except Exception:
            img_status["others"] += 1
            
        # 詳細URLテスト
        try:
            r_det = requests.get(detail_url, headers=headers, timeout=5, allow_redirects=False)
            if r_det.status_code == 200:
                detail_status["200"] += 1
            elif 300 <= r_det.status_code < 400:
                detail_status["redirect"] += 1
            elif r_det.status_code == 404:
                detail_status["404"] += 1
            else:
                detail_status["others"] += 1
        except Exception:
            detail_status["others"] += 1
            
    print(f"  Image URL Status: 200={img_status['200']}, 404={img_status['404']}, others={img_status['others']}")
    print(f"  Detail URL Status: 200={detail_status['200']}, 404={detail_status['404']}, redirect={detail_status['redirect']}, others={detail_status['others']}")

def list_duplicates():
    print("\n=== 4. Duplicate Card Names and IDs ===")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT card_name, COUNT(*)
        FROM cards
        GROUP BY card_name
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC;
    """)
    duplicates = cursor.fetchall()
    
    print(f"  Duplicate Card Names count: {len(duplicates)}")
    for name, cnt in duplicates:
        cursor.execute("SELECT card_id, card_type, cost, power FROM cards WHERE card_name = ?", (name,))
        cards = cursor.fetchall()
        print(f"  - Card Name: '{name}' (Appears {cnt} times)")
        for cid, ctype, cost, power in cards:
            print(f"    -> card_id: '{cid}', Type: {ctype}, Cost: {cost}, Power: {power}")
            
    conn.close()

async def test_api_performance():
    print("\n=== 5. API Response Size and Performance ===")
    queries = ["ボルメテウス", "ドラゴン", ""]
    
    for q in queries:
        t0 = time.perf_counter()
        results = await app.search_cards_v2(q=q)
        t1 = time.perf_counter()
        
        json_str = json.dumps(results, ensure_ascii=False)
        size_kb = len(json_str.encode('utf-8')) / 1024
        duration_ms = (t1 - t0) * 1000
        
        print(f"  Query: '{q}' -> Count: {len(results)}, Size: {size_kb:.2f} KB, Duration: {duration_ms:.2f} ms")

def check_memory():
    print("\n=== 6. Process Memory Usage ===")
    try:
        import psutil
        process = psutil.Process(os.getpid())
        rss_mb = process.memory_info().rss / 1024 / 1024
        print(f"  RSS Memory Usage: {rss_mb:.2f} MB")
        print(f"  Python Process Total Memory (VIRT): {process.memory_info().vms / 1024 / 1024:.2f} MB")
    except ImportError:
        print("  psutil not installed. Executing wmic command...")
        import subprocess
        try:
            pid = os.getpid()
            out = subprocess.check_output(f'wmic process where processid={pid} get WorkingSetSize', shell=True).decode()
            print("  wmic output (Working Set Size in bytes):")
            print(out.strip())
        except Exception as e:
            print(f"  Failed to get memory info: {e}")

async def run_simulation():
    print("\n=== 7. Operational Simulation (New Expansion) ===")
    import shutil
    
    shutil.copy(str(CARDS_JSON_PATH), str(CARDS_JSON_PATH) + ".bak")
    shutil.copy(str(DECKS_JSON_PATH), str(DECKS_JSON_PATH) + ".bak")
    shutil.copy(str(DB_PATH), str(DB_PATH) + ".bak")
    
    try:
        dummy_manual_card = {
            "id": 99999,
            "name": "超神龍シミュレーションドラゴン",
            "civilization": "fire",
            "card_type": "creature",
            "cost": 7,
            "power": "9000",
            "text": "手動ダミー",
            "image": "dummy.jpg"
        }
        manual_cards = app.load_cards()
        manual_cards.append(dummy_manual_card)
        app.save_cards(manual_cards)
        print("  [Step 1] Added dummy manual card: '超神龍シミュレーションドラゴン' to cards.json.")

        decks = app.load_decks()
        target_deck = None
        for d in decks:
            if d["id"] == 65:
                target_deck = d
                break
        
        if target_deck:
            target_deck["cards"].append(99999)
            target_deck["cards"].append(99999)
            with open(DECKS_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(decks, f, ensure_ascii=False, indent=2)
            print("  [Step 2] Added dummy card ID 99999 reference to Deck ID 65.")

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cards (card_id, card_name, civilization, card_type, cost, power, race, ability_text, image_url, detail_url)
            VALUES ('dm26sim-001', '超神龍シミュレーションドラゴン', 'fire', 'creature', 7, '9000', 'アポロニア・ドラゴン', '公式効果', 'https://dm.takaratomy.co.jp/wp-content/card/cardimage/dummy.jpg', 'https://dm.takaratomy.co.jp/card/detail/?id=dm26sim-001')
        """)
        conn.commit()
        conn.close()
        print("  [Step 3] Inserted matching official card '超神龍シミュレーションドラゴン' (ID: dm26sim-001) into cards_v2.db.")

        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT card_id FROM cards WHERE card_id = 'dm26sim-001'")
        assert cursor.fetchone() is not None
        conn.close()
        print("  [Step 4] Incremental crawler mock check passed.")

        import sys
        sys.path.append(str(BASE_DIR / "scratch"))
        import merge_duplicates
        merge_duplicates.main()
        print("  [Step 5] merge_duplicates.py completed.")

        with open(CARDS_JSON_PATH, "r", encoding="utf-8") as f:
            c_list = json.load(f)
        assert not any(c["id"] == 99999 for c in c_list), "Error: Dummy card 99999 was not deleted from cards.json"
        
        with open(DECKS_JSON_PATH, "r", encoding="utf-8") as f:
            d_list = json.load(f)
        
        target_deck_after = None
        for d in d_list:
            if d["id"] == 65:
                target_deck_after = d
                break
                
        assert target_deck_after is not None
        official_ref_count = target_deck_after["cards"].count('dm26sim-001')
        manual_ref_count = target_deck_after["cards"].count(99999)
        print(f"  [Step 6] Verification: Deck ID 65 has {official_ref_count} official refs and {manual_ref_count} manual refs.")
        assert official_ref_count == 2
        assert manual_ref_count == 0

        app.load_cards_v2()
        results = await app.search_cards_v2(q="超神龍シミュレーション")
        assert len(results) == 1
        assert results[0]["card_id"] == "dm26sim-001"
        assert results[0]["is_official"] == True
        print(f"  [Step 7] Verification: Search API successfully returned single official record: {results[0]['card_name']} (ID: {results[0]['card_id']})")
        
        print("\n[SUCCESS] New expansion simulation passed with zero data corruption!")

    finally:
        shutil.move(str(CARDS_JSON_PATH) + ".bak", str(CARDS_JSON_PATH))
        shutil.move(str(DECKS_JSON_PATH) + ".bak", str(DECKS_JSON_PATH))
        shutil.move(str(DB_PATH) + ".bak", str(DB_PATH))
        print("  Original environment fully restored.")

async def run_all():
    check_missing_info()
    check_urls()
    list_duplicates()
    await test_api_performance()
    check_memory()
    await run_simulation()

if __name__ == "__main__":
    asyncio.run(run_all())
