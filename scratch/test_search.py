import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

import app

async def test_search():
    print(f"Total Combined Cards: {len(app.ALL_CARDS_COMBINED)}")
    
    # Check specific official cards
    test_ids = ["dmart25-006", "dm26sd1-m010", "dm22rp1-or1", "dm26sd1-s002F"]
    for cid in test_ids:
        card = next((x for x in app.ALL_CARDS_COMBINED if x.get('card_id') == cid), None)
        if card:
            print(f"\nCard: {card['card_name']} ({card['card_id']})")
            print(f"  text: {repr(card.get('text'))}")
            print(f"  ability_text: {repr(card.get('ability_text'))}")
        else:
            print(f"\nCard {cid} NOT FOUND in combined cards!")

if __name__ == "__main__":
    asyncio.run(test_search())


if __name__ == "__main__":
    asyncio.run(test_search())




