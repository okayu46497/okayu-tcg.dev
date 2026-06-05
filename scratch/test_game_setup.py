import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

import app

def test_game_setup():
    print("=== Testing game setup for 黒単アビス ===")
    
    # 1. Load decks
    decks = app.load_decks()
    
    # 2. Get 黒単アビス
    abyss_deck = None
    for d in decks:
        if d["id"] == 65: # ID 65 is 黒単アビス owned by okayu
            abyss_deck = d
            break
            
    assert abyss_deck is not None, "黒単アビス deck not found!"
    print(f"Loaded deck '{abyss_deck['name']}' (ID: {abyss_deck['id']}, Owner: {abyss_deck['owner']})")
    print(f"Cards count in deck object: {abyss_deck['card_count']}")
    print(f"Cards: {abyss_deck['cards']}")
    
    # 3. Create PlayerState and setup
    player = app.PlayerState(player_id="okayu_id", name="okayu", deck_card_ids=abyss_deck["cards"])
    player.setup()
    
    print("\nPlayer State after setup:")
    print(f"  Deck size: {len(player.deck)}")
    print(f"  Hand size: {len(player.hand)}")
    print(f"  Shields size: {len(player.shields)}")
    
    # Assertions
    assert len(player.deck) == 30, f"Expected deck size 30, got {len(player.deck)}"
    assert len(player.hand) == 5, f"Expected hand size 5, got {len(player.hand)}"
    assert len(player.shields) == 5, f"Expected shields size 5, got {len(player.shields)}"
    
    print("\n[SUCCESS] Game setup test passed! No card was skipped.")

if __name__ == "__main__":
    test_game_setup()
