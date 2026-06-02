import time
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "cards_v2.db"
CARDS_JSON_PATH = BASE_DIR / "data" / "cards.json"

def measure():
    print("=== Start Time and Index Build Time Measurement ===")
    
    # 1. データベース接続およびフェッチの測定
    t0 = time.perf_counter()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cards")
    rows = cursor.fetchall()
    ALL_CARDS_V2 = [dict(r) for r in rows]
    CARD_MAP_V2 = {c["card_id"]: c for c in ALL_CARDS_V2}
    conn.close()
    t1 = time.perf_counter()
    
    db_load_time_ms = (t1 - t0) * 1000
    print(f"  SQLite cards_v2.db load time: {db_load_time_ms:.2f} ms ({len(ALL_CARDS_V2)} cards)")
    
    # 2. cards.json ロードの測定
    t2 = time.perf_counter()
    with open(CARDS_JSON_PATH, "r", encoding="utf-8") as f:
        import json
        ALL_CARDS = json.load(f)
    t3 = time.perf_counter()
    
    json_load_time_ms = (t3 - t2) * 1000
    print(f"  data/cards.json load time: {json_load_time_ms:.2f} ms ({len(ALL_CARDS)} cards)")
    
    # 3. ハイブリッド統合インデックス構築の測定
    t4 = time.perf_counter()
    combined_list = []
    combined_map = {}
    
    for card in ALL_CARDS_V2:
        card_copy = dict(card)
        card_copy["is_official"] = True
        combined_list.append(card_copy)
        combined_map[card_copy["card_id"]] = card_copy

    official_names = {c["card_name"].strip().lower() for c in ALL_CARDS_V2}

    for card in ALL_CARDS:
        card_name = card.get("name", "").strip()
        card_name_lower = card_name.lower()
        if card_name_lower in official_names:
            continue
        card_copy = {
            "card_id": str(card["id"]),
            "id": card["id"],
            "card_name": card_name,
            "civilization": card.get("civilization"),
            "card_type": card.get("card_type"),
            "cost": card.get("cost"),
            "power": card.get("power"),
            "race": card.get("race"),
            "ability_text": card.get("text", ""),
            "image_url": f"/static/cards/{card.get('image')}" if card.get("image") else "/static/通常裏面画像.jpg",
            "is_official": False
        }
        combined_list.append(card_copy)
        combined_map[card["id"]] = card_copy
        combined_map[str(card["id"])] = card_copy
        
    t5 = time.perf_counter()
    
    index_build_time_ms = (t5 - t4) * 1000
    print(f"  Hybrid combined index build time: {index_build_time_ms:.2f} ms ({len(combined_list)} combined cards)")
    
    total_startup_ms = db_load_time_ms + json_load_time_ms + index_build_time_ms
    print(f"  Total loading & initialization time: {total_startup_ms:.2f} ms")

if __name__ == "__main__":
    measure()
