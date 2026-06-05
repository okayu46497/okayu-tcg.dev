import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

import app

async def test_search():
    print(f"Total Combined Cards: {len(app.ALL_CARDS_COMBINED)}")
    
    # 1. Search directly in memory using Python list comprehension
    matches_py = [
        c for c in app.ALL_CARDS_COMBINED
        if "アビスベル" in c["card_name"]
    ]
    print(f"Python search 'アビスベル' count: {len(matches_py)}")
    for c in matches_py:
        print(f"Py Match: ID: {c['card_id']} | Name: {c['card_name']}")

    # 2. Search using the FastAPI app search_cards_v2 function
    matches_api = await app.search_cards_v2(q="アビスベル")
    print(f"FastAPI search_cards_v2(q='アビスベル') count: {len(matches_api)}")
    for c in matches_api:
        print(f"API Match: ID: {c['card_id']} | Name: {c['card_name']}")
        
    # Let's inspect the first card's details
    if matches_py:
        card = matches_py[0]
        print(f"Keys: {list(card.keys())}")
        print(f"card_name: '{card.get('card_name')}'")

if __name__ == "__main__":
    asyncio.run(test_search())
