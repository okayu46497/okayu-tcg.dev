import sys
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

import app

def test_direct():
    print(f"app.SUPABASE_URL = {app.SUPABASE_URL}")
    print(f"app.SUPABASE_KEY exists: {bool(app.SUPABASE_KEY)}")
    
    if not app.SUPABASE_KEY:
        print("SUPABASE_KEY is empty in this environment!")
        print("Checking if local sqlite contains abyssbell:")
        import sqlite3
        conn = sqlite3.connect("cards_v2.db")
        cursor = conn.cursor()
        cursor.execute("SELECT card_id, card_name FROM cards WHERE card_name LIKE '%アビスベル%'")
        rows = cursor.fetchall()
        for r in rows:
            print(f"Local SQLITE: ID: {r[0]} | Name: {r[1]}")
        conn.close()
        
        # Also check ALL_CARDS_COMBINED in memory!
        print(f"ALL_CARDS_COMBINED count: {len(app.ALL_CARDS_COMBINED)}")
        abyssbell_comb = [c for c in app.ALL_CARDS_COMBINED if "アビスベル" in c.get("card_name", "")]
        print(f"ALL_CARDS_COMBINED abyssbell count: {len(abyssbell_comb)}")
        for c in abyssbell_comb:
            print(f"Memory Combined: ID: {c.get('card_id')} | Name: {c.get('card_name')}")
        return

    headers = app.get_supabase_headers()
    search_url = f"{app.SUPABASE_URL}/rest/v1/official_cards?name=ilike.*アビスベル*&select=id,name"
    resp = requests.get(search_url, headers=headers)
    if resp.status_code == 200:
        cards = resp.json()
        print(f"Supabase matching 'アビスベル' count: {len(cards)}")
        for c in cards:
            print(f"Supabase: ID: {c['id']} | Name: {c['name']}")
    else:
        print(f"Failed to query Supabase (status={resp.status_code}): {resp.text}")

if __name__ == "__main__":
    test_direct()
