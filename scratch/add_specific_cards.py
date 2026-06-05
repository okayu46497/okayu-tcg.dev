import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

import collect_cards

def add_cards():
    target_ids = [
        "dm22rp1-or1",
        "dm22rp1-or2",
        "dm22rp2-or1",
        "dm22rp2-or2",
        "dm23rp1-or1",
        "dm23rp1-or2",
        "dm23rp2-or1",
        "dm23rp2-or2",
        "dm23rp3-or1",
        "dm23rp3-or2",
        "dm23rp4-or1",
        "dm23rp4-or2"
    ]
    
    conn = sqlite3.connect("cards_v2.db")
    cursor = conn.cursor()
    
    added_count = 0
    for cid in target_ids:
        # Check if already exists
        cursor.execute("SELECT card_id FROM cards WHERE card_id = ?", (cid,))
        if cursor.fetchone():
            print(f"Card {cid} already exists in local DB.")
            continue
            
        print(f"Fetching details for {cid}...")
        card_data = collect_cards.parse_card_detail(cid)
        if card_data and "Unknown" not in card_data["card_name"]:
            cursor.execute("""
                INSERT INTO cards (card_id, card_name, civilization, card_type, cost, power, race, ability_text, image_url, detail_url)
                VALUES (:card_id, :card_name, :civilization, :card_type, :cost, :power, :race, :ability_text, :image_url, :detail_url)
            """, card_data)
            conn.commit()
            added_count += 1
            print(f"  [SAVED] {card_data['card_name']} (ID: {cid})")
        else:
            print(f"  [FAILED/SKIPPED] {cid}")
            
    print(f"\nDone. Added {added_count} cards to local SQLite.")
    conn.close()

if __name__ == "__main__":
    add_cards()
