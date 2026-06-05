import sqlite3

def dump_utf8():
    conn = sqlite3.connect("cards_v2.db")
    cursor = conn.cursor()
    
    # Select all rows matching %アビス% or %ジャシン%
    cursor.execute("SELECT card_id, card_name, civilization, card_type, cost, power FROM cards WHERE card_name LIKE ? OR card_name LIKE ?", ("%アビス%", "%ジャシン%"))
    rows = cursor.fetchall()
    
    with open("scratch/abyssbell_names.txt", "w", encoding="utf-8") as f:
        f.write("=== Abyss / Jashin Cards in cards_v2.db ===\n\n")
        for r in rows:
            f.write(f"ID: {r[0]}\n")
            f.write(f"Name: {r[1]}\n")
            f.write(f"Civilization: {r[2]}\n")
            f.write(f"Type: {r[3]}\n")
            f.write(f"Cost: {r[4]}\n")
            f.write(f"Power: {r[5]}\n")
            f.write("-" * 40 + "\n")
            
    print("Dumped card names to scratch/abyssbell_names.txt")
    conn.close()

if __name__ == "__main__":
    dump_utf8()
