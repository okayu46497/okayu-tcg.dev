import sqlite3

def search_db():
    conn = sqlite3.connect("cards_v2.db")
    cursor = conn.cursor()
    
    # 1. Search for Jashin
    cursor.execute("SELECT card_id, card_name FROM cards WHERE card_name LIKE ?", ("%ジャシン%",))
    rows = cursor.fetchall()
    print("=== Matches for 'ジャシン' ===")
    for r in rows:
        print(f"ID: {r[0]} | Name: {r[1]}")
        
    # 2. Search for Abyssbell (アビスベル)
    cursor.execute("SELECT card_id, card_name FROM cards WHERE card_name LIKE ?", ("%アビスベル%",))
    rows2 = cursor.fetchall()
    print("\n=== Matches for 'アビスベル' ===")
    for r in rows2:
        print(f"ID: {r[0]} | Name: {r[1]}")
        
    conn.close()

if __name__ == "__main__":
    search_db()
