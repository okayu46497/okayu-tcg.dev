import sqlite3
import re
import sys
from collections import Counter
from pathlib import Path

# Windowsターミナルでの文字化けを防ぐためUTF-8出力を強制
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def main():
    db_path = Path(__file__).parent.parent / "cards_v2.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    
    # ブレイカーを含むテキストをすべて取得
    c.execute("SELECT ability_text FROM cards WHERE ability_text LIKE '%ブレイカー%'")
    rows = c.fetchall()
    conn.close()
    
    # 「◯◯・ブレイカー」または「◯◯ブレイカー」を抽出する正規化パターン
    # カタカナ、英数字、漢字、全角・半角の記号を含める
    pattern = re.compile(r'([A-Za-z0-9\u30a0-\u30ff\u3040-\u309f\u4e00-\u9faf\uff21-\uff3a\uff41-\uff5a\uff10-\uff19・\uff65\-]+ブレイカー)')
    
    breakers = []
    for (text,) in rows:
        if not text:
            continue
        matches = pattern.findall(text)
        for match in matches:
            # トリミングとクリーニング
            cleaned = match.strip()
            # 「〜のブレイカー」「〜するブレイカー」のような助詞や動詞で始まる不要なマッチを簡易的に除外
            if any(cleaned.startswith(x) for x in ["が", "を", "に", "で", "と", "の", "は", "か"]):
                cleaned = cleaned[1:]
            
            # あまりにも長すぎるマッチは誤検知なので除外
            if len(cleaned) <= 15:
                breakers.append(cleaned)
                
    counter = Counter(breakers)
    
    print("=== Unique Breakers Count & Variety ===")
    print(f"Total entries analyzed: {len(rows)}")
    print(f"Total individual matches: {len(breakers)}")
    print(f"Unique breaker variants found: {len(counter)}")
    print("-" * 50)
    
    # 頻度順に上位50件を表示
    for name, count in counter.most_common(50):
        print(f"  {name}: {count} cards")

if __name__ == "__main__":
    main()
