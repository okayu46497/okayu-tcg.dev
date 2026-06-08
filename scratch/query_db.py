import sqlite3
from pathlib import Path

def main():
    db_path = Path(__file__).parent.parent / "cards_v2.db"
    out_path = Path(__file__).parent / "break_ability_results.txt"
    
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    
    query = "SELECT card_name, card_id FROM cards WHERE ability_text LIKE '%ブレイク%' OR ability_text LIKE '%ブレイカー%'"
    c.execute(query)
    rows = c.fetchall()
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Total Matches (with 'ブレイク' or 'ブレイカー' in ability_text): {len(rows)}\n")
        f.write("-" * 50 + "\n")
        for idx, (name, cid) in enumerate(rows):
            f.write(f"{idx + 1}: {name} ({cid})\n")
            
    print(f"Successfully wrote {len(rows)} results to {out_path.name}")
    conn.close()

if __name__ == "__main__":
    main()



