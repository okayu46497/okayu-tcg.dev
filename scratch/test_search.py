import asyncio
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

import app

async def test_search():
    print(f"Total Combined Cards: {len(app.ALL_CARDS_COMBINED)}")
    print(f"Migration Map Items count: {len(app.MIGRATION_MAP)}")
    for k, v in app.MIGRATION_MAP.items():
        print(f"  {k} -> {v}")
        
    print("\n--- Testing fallback aliases ---")
    # Test looking up manual IDs that are masked
    test_ids = [1, 6, 10, 11, 12, 13]
    for cid in test_ids:
        card = app.CARD_MAP_COMBINED.get(cid)
        if card:
            print(f"ID {cid} -> Found card: {card['card_id']} ({card['card_name']}) | Official: {card['is_official']}")
        else:
            print(f"ID {cid} -> NOT FOUND!")

    print("\n--- Testing load_decks() migration ---")
    # Before loading, let's backup decks.json in memory
    backup = None
    if app.DECKS_PATH.exists():
        with open(app.DECKS_PATH, "r", encoding="utf-8") as f:
            backup = json.load(f)
            
    print("Executing load_decks()...")
    decks = app.load_decks()
    
    print("\nAfter migration check:")
    for d in decks:
        if d["name"] == "黒単アビス":
            print(f"Deck '{d['name']}' (ID: {d['id']}, Owner: {d['owner']}):")
            print(f"Cards in deck: {d['cards'][:15]}... (total {len(d['cards'])})")
            
    # Check if cards are still numbers or string IDs
    has_ints = any(isinstance(c, int) for d in decks for c in d["cards"])
    print(f"Any integer card IDs left in loaded decks? {has_ints}")
    
    # Restore the backup to avoid permanent changes to decks.json if not desired yet
    # Actually, we want to write it out to verify it works, but let's see.
    if backup:
        with open(app.DECKS_PATH, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=2)
        print("Restored backup of decks.json to keep it clean during testing.")

if __name__ == "__main__":
    asyncio.run(test_search())



