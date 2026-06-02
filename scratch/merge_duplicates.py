import json
import sqlite3
import re
from pathlib import Path

# パス設定
BASE_DIR = Path(__file__).parent.parent
CARDS_JSON_PATH = BASE_DIR / "data" / "cards.json"
DECKS_JSON_PATH = BASE_DIR / "data" / "decks.json"
DB_PATH = BASE_DIR / "cards_v2.db"

def normalize_name(name):
    """カード名の正規化（突合の精度を上げるため）"""
    if not name:
        return ""
    name = name.replace("　", "").replace(" ", "")
    name = name.translate(str.maketrans(
        '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ',
        '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    ))
    return name.lower().strip()

def main():
    print("=== Card Database Merge & Deduplication Script ===")
    
    if not CARDS_JSON_PATH.exists():
        print(f"Error: {CARDS_JSON_PATH} not found.")
        return
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found. Please crawl official cards first.")
        return

    # 1. 公式カードマスタの読み込み
    print("Loading official master cards from cards_v2.db...")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT card_id, card_name FROM cards")
    official_cards = cursor.fetchall()
    conn.close()
    
    official_map = {}
    for cid, name in official_cards:
        norm_name = normalize_name(name)
        if norm_name not in official_map:
            official_map[norm_name] = cid
            
    print(f"Loaded {len(official_map)} unique official card names.")

    # 2. ユーザー登録カード (手動) の読み込み
    print(f"Loading user-registered cards from {CARDS_JSON_PATH}...")
    with open(CARDS_JSON_PATH, "r", encoding="utf-8") as f:
        manual_cards = json.load(f)
        
    print(f"Loaded {len(manual_cards)} manual cards.")

    # 3. 重複検知とマッピングの構築
    duplicate_mappings = {}
    remaining_manual_cards = []
    
    for card in manual_cards:
        mid = card["id"]
        mname = card.get("name", "")
        norm_mname = normalize_name(mname)
        
        if norm_mname in official_map:
            official_id = official_map[norm_mname]
            duplicate_mappings[mid] = official_id
            print(f"  [Duplicate Found] Manual ID: {mid} ('{mname}') matches Official ID: '{official_id}'")
        else:
            remaining_manual_cards.append(card)
            
    print(f"\nTotal duplicates found: {len(duplicate_mappings)}")
    
    if not duplicate_mappings:
        print("No duplicates found. Nothing to merge.")
        return

    # 4. デッキデータ (decks.json) のマイグレーション
    if DECKS_JSON_PATH.exists():
        print(f"\nMigrating deck data in {DECKS_JSON_PATH}...")
        with open(DECKS_JSON_PATH, "r", encoding="utf-8") as f:
            decks = json.load(f)
            
        migrated_decks_count = 0
        total_replacements = 0
        
        for deck in decks:
            original_cards = deck.get("cards", [])
            new_cards = []
            replacements_in_deck = 0
            
            for cid in original_cards:
                if cid in duplicate_mappings:
                    new_cards.append(duplicate_mappings[cid])
                    replacements_in_deck += 1
                    total_replacements += 1
                else:
                    new_cards.append(cid)
                    
            if replacements_in_deck > 0:
                deck["cards"] = new_cards
                migrated_decks_count += 1
                print(f"  Deck '{deck['name']}' (ID: {deck['id']}, Owner: {deck['owner']}): Replaced {replacements_in_deck} cards.")
                
        if migrated_decks_count > 0:
            with open(DECKS_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(decks, f, ensure_ascii=False, indent=2)
            print(f"[SUCCESS] Updated {migrated_decks_count} decks. Total {total_replacements} card reference(s) migrated.")
        else:
            print("No decks referenced the duplicate cards. Deck migration skipped.")
    else:
        print(f"\nDeck file {DECKS_JSON_PATH} not found. Skipping deck migration.")

    # 5. 重複した手動登録カードを cards.json から削除
    print(f"\nCleaning up cards.json...")
    with open(CARDS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(remaining_manual_cards, f, ensure_ascii=False, indent=2)
        
    print(f"[SUCCESS] Saved {len(remaining_manual_cards)} remaining manual cards to cards.json (Removed {len(duplicate_mappings)} duplicate(s)).")
    print("\n=== Merge & Deduplication Complete ===")

if __name__ == "__main__":
    main()
