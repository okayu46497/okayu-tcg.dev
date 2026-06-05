import os
import requests
from dotenv import load_dotenv

# Let's search app.py for SUPABASE_URL / KEY or load them from environment
# Let's read app.py to find how they are loaded

def check_supabase():
    # Read app.py to extract Supabase credentials
    url = None
    key = None
    with open("app.py", "r", encoding="utf-8") as f:
        for line in f:
            if "SUPABASE_URL =" in line or "SUPABASE_URL=" in line:
                url = line.split("=")[1].strip().strip('"').strip("'")
            if "SUPABASE_KEY =" in line or "SUPABASE_KEY=" in line:
                key = line.split("=")[1].strip().strip('"').strip("'")
                
    if not url or not key:
        print("Could not find Supabase credentials in app.py")
        return
        
    print(f"Connecting to Supabase: {url}")
    
    # Query official_cards from Supabase REST API
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}"
    }
    
    # Search for abyssbell in Supabase
    search_url = f"{url}/rest/v1/official_cards?name=ilike.*アビスベル*&select=id,name"
    resp = requests.get(search_url, headers=headers)
    if resp.status_code == 200:
        cards = resp.json()
        print(f"Found {len(cards)} cards on Supabase matching 'アビスベル':")
        for c in cards:
            print(f"ID: {c['id']} | Name: {c['name']}")
    else:
        print(f"Failed to query Supabase (status={resp.status_code}): {resp.text}")

if __name__ == "__main__":
    check_supabase()
