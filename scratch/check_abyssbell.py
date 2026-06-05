import sqlite3

def check():
    conn = sqlite3.connect("cards_v2.db")
    cursor = conn.cursor()
    cursor.execute("SELECT card_id, card_name FROM cards WHERE card_name LIKE ?", ("%アビスベル%",))
    rows = cursor.fetchall()
    print("Found cards matching '%アビスベル%':")
    for r in rows:
        print(f"ID: {r[0]} | Name: {r[1]}")
    
    # Also search for similar variations
    cursor.execute("SELECT card_id, card_name FROM cards WHERE card_name LIKE ?", ("%アビス%",))
    rows_abyss = cursor.fetchall()
    print(f"Total matching '%アビス%': {len(rows_abyss)}")
    print("First 10 matches:")
    for r in rows_abyss[:10]:
        print(f"ID: {r[0]} | Name: {r[1]}")

    conn.close()

if __name__ == "__main__":
    check()
