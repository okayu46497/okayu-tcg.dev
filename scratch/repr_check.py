import sqlite3

def repr_check():
    conn = sqlite3.connect("cards_v2.db")
    cursor = conn.cursor()
    cursor.execute("SELECT card_id, card_name FROM cards WHERE card_id = 'dmart25-002'")
    row = cursor.fetchone()
    if row:
        print(f"Original ID: {row[0]}")
        print(f"Name repr: {repr(row[1])}")
        try:
            # Let's see if the name was incorrectly encoded as Shift-JIS or CP932 and then decoded as UTF-8
            # or if it's CP932 decoded as something else
            raw_bytes = row[1].encode('utf-8')
            print(f"UTF-8 encoded bytes: {raw_bytes.hex()}")
        except Exception as e:
            print(f"Error encoding: {e}")
            
    conn.close()

if __name__ == "__main__":
    repr_check()
