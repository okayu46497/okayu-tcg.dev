import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

import app

async def test_search():
    print(f"Total Combined Cards: {len(app.ALL_CARDS_COMBINED)}")
    
    # Check if a card has both text and ability_text keys
    if len(app.ALL_CARDS_COMBINED) > 0:
        c = app.ALL_CARDS_COMBINED[0]
        print(f"Card example: {c.get('card_name')} ({c.get('card_id')})")
        print(f"  Has 'text' key? {'text' in c}")
        print(f"  Has 'ability_text' key? {'ability_text' in c}")
        print(f"  text: {c.get('text')[:30] if c.get('text') else None}...")
        print(f"  ability_text: {c.get('ability_text')[:30] if c.get('ability_text') else None}...")
        
        # Test finding cards and declaring their text
        print("\nChecking test official card (百発人形マグナム) text property:")
        magnum = next((x for x in app.ALL_CARDS_COMBINED if x.get('card_id') == 'dmex17-Cho10'), None)
        if magnum:
            print(f"Found {magnum['card_name']}!")
            print(f"  text: {magnum.get('text')}")
            print(f"  ability_text: {magnum.get('ability_text')}")
        else:
            print("Magnum not found!")

if __name__ == "__main__":
    asyncio.run(test_search())




