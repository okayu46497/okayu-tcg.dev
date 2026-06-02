import sqlite3
import json
import shutil
import sys
from pathlib import Path

# バックアップを取る
shutil.copy("data/cards.json", "data/cards.json.bak")
shutil.copy("data/decks.json", "data/decks.json.bak")
shutil.copy("cards_v2.db", "cards_v2.db.bak")

try:
    # 1. cards_v2.db に「百発人形マグナム」を挿入
    conn = sqlite3.connect("cards_v2.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cards (card_id, card_name, civilization, card_type, cost, power, race, ability_text, image_url, detail_url)
        VALUES ('test-magnum-id', '百発人形マグナム', 'darkness', 'creature', 4, '4000', 'デスパペット', '能力テキスト', 'http://dummy', 'http://dummy-detail')
    """)
    conn.commit()
    conn.close()
    print("Inserted dummy '百発人形マグナム' into cards_v2.db.")

    # 2. merge_duplicates.py をロードして実行する
    sys.path.append("scratch")
    import merge_duplicates
    merge_duplicates.main()

    # 3. 検証
    # cards.json から ID=1 (百発人形マグナム) が消えていること
    with open("data/cards.json", "r", encoding="utf-8") as f:
        cards = json.load(f)
    magnum_exists = any(c["id"] == 1 for c in cards)
    print(f"Magnum exists in cards.json: {magnum_exists} (Expected: False)")
    assert not magnum_exists

    # decks.json 内で 'test-magnum-id' が使われていること
    with open("data/decks.json", "r", encoding="utf-8") as f:
        decks = json.load(f)
    
    magnum_migrated = False
    for deck in decks:
        if "test-magnum-id" in deck.get("cards", []):
            magnum_migrated = True
            print(f"Deck '{deck['name']}' (ID: {deck['id']}) successfully has migrated ID 'test-magnum-id'.")
    
    assert magnum_migrated

    print("\n[SUCCESS] merge_duplicates.py test passed completely!")

finally:
    # 元に戻す
    shutil.move("data/cards.json.bak", "data/cards.json")
    shutil.move("data/decks.json.bak", "data/decks.json")
    shutil.move("cards_v2.db.bak", "cards_v2.db")
    print("Restored original files.")
