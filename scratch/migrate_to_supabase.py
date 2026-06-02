import json
import os
import requests
from pathlib import Path

# パス設定
BASE_DIR = Path(__file__).parent.parent
CARDS_JSON_PATH = BASE_DIR / "data" / "cards.json"
DECKS_JSON_PATH = BASE_DIR / "data" / "decks.json"

# ローカル実行時の手動指定または環境変数の読み込み
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://pvwiojdoiheamfhshgvx.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

def migrate_cards():
    print("\n--- Migrating cards.json to Supabase user_cards ---")
    if not CARDS_JSON_PATH.exists():
        print(f"Error: {CARDS_JSON_PATH} not found. Skipping card migration.")
        return
        
    with open(CARDS_JSON_PATH, "r", encoding="utf-8") as f:
        cards = json.load(f)
        
    print(f"Loaded {len(cards)} cards from local cards.json.")
    
    # 1. 一旦Supabase上の全データを削除
    print("Clearing existing user_cards in Supabase...")
    del_url = f"{SUPABASE_URL}/rest/v1/user_cards?id=gt.0"
    del_resp = requests.delete(del_url, headers=get_headers(), timeout=10)
    print(f"Delete response: {del_resp.status_code}")
    
    # 2. データをDB構造に整形
    db_cards = []
    for c in cards:
        db_cards.append({
            "id": c["id"],
            "name": c["name"],
            "civilization": c.get("civilization"),
            "card_type": c.get("card_type"),
            "cost": c.get("cost"),
            "power": str(c.get("power")) if c.get("power") is not None else None,
            "text": c.get("text", ""),
            "race": c.get("race"),
            "image": c.get("image")
        })
        
    # 3. バルクインサート
    if db_cards:
        print(f"Uploading {len(db_cards)} cards to user_cards...")
        ins_url = f"{SUPABASE_URL}/rest/v1/user_cards"
        ins_resp = requests.post(ins_url, json=db_cards, headers=get_headers(), timeout=10)
        print(f"Insert response: {ins_resp.status_code}")
        if ins_resp.status_code in (200, 201):
            print("[SUCCESS] Cards migration completed successfully!")
        else:
            print(f"[ERROR] Failed to insert cards: {ins_resp.text}")
    else:
        print("No cards to migrate.")

def migrate_decks():
    print("\n--- Migrating decks.json to Supabase user_decks ---")
    if not DECKS_JSON_PATH.exists():
        print(f"Error: {DECKS_JSON_PATH} not found. Skipping deck migration.")
        return
        
    with open(DECKS_JSON_PATH, "r", encoding="utf-8") as f:
        decks = json.load(f)
        
    print(f"Loaded {len(decks)} decks from local decks.json.")
    
    # 1. 一旦Supabase上の全データを削除
    print("Clearing existing user_decks in Supabase...")
    del_url = f"{SUPABASE_URL}/rest/v1/user_decks?id=gt.0"
    del_resp = requests.delete(del_url, headers=get_headers(), timeout=10)
    print(f"Delete response: {del_resp.status_code}")
    
    # 2. データをDB構造に整形
    db_decks = []
    for d in decks:
        db_decks.append({
            "id": d["id"],
            "name": d["name"],
            "owner": d["owner"],
            "cards": d["cards"],  # リストがそのままJSONとして挿入される
            "card_count": d["card_count"],
            "sleeve_type": d.get("sleeve_type", "normal"),
            "sleeve_image": d.get("sleeve_image"),
            "created_at": d.get("created_at")
        })
        
    # 3. バルクインサート
    if db_decks:
        print(f"Uploading {len(db_decks)} decks to user_decks...")
        ins_url = f"{SUPABASE_URL}/rest/v1/user_decks"
        ins_resp = requests.post(ins_url, json=db_decks, headers=get_headers(), timeout=10)
        print(f"Insert response: {ins_resp.status_code}")
        if ins_resp.status_code in (200, 201):
            print("[SUCCESS] Decks migration completed successfully!")
        else:
            print(f"[ERROR] Failed to insert decks: {ins_resp.text}")
    else:
        print("No decks to migrate.")

def main():
    print("=== Supabase Data Migration Utility ===")
    global SUPABASE_KEY
    
    if not SUPABASE_KEY:
        # もし環境変数になければ、対話入力（または促すメッセージ）
        # ただし非対話モードで実行されるため、入力を求めるのは避けエラーにする
        print("[ERROR] SUPABASE_KEY environment variable is not set.")
        print("Please set it in your environment before running this script.")
        print("Example (PowerShell): $env:SUPABASE_KEY='your-service-role-key'")
        return
        
    print(f"Target Supabase URL: {SUPABASE_URL}")
    migrate_cards()
    migrate_decks()
    print("\n=== Migration Process Finished ===")

if __name__ == "__main__":
    main()
