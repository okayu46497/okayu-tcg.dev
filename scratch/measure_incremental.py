import time
import sqlite3
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "cards_v2.db"

def measure_case_a():
    print("=== Case A: Database is Up-to-date (New Cards: 0) ===")
    t0 = time.perf_counter()
    
    # クローラーを増分モードで実行 (全件スキャンだが連続5件登録済みで即終了する)
    # ページ数制限やキーワードなしでそのまま走らせる
    result = subprocess.run(
        ["python", "collect_cards.py", "-i"],
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR)
    )
    
    t1 = time.perf_counter()
    duration = t1 - t0
    
    print(f"  Execution Time: {duration:.2f} seconds")
    # ログ出力の最後のほうを表示
    lines = result.stdout.strip().split("\n")
    print("  Output logs:")
    for line in lines[-5:]:
        print(f"    {line}")

def measure_case_b():
    print("\n=== Case B: Missing 10 Cards in Local DB (New Cards: 10) ===")
    
    # バックアップ
    shutil.copy(str(DB_PATH), str(DB_PATH) + ".bak")
    
    try:
        # 最新の10レコードを削除する
        # （公式サイトの新着順に並んでいる最初の10レコードを消すことで、増分クロールがその10レコードを再フェッチする）
        # ただし新着のIDが分からないので、検索結果の1ページ目（50件）のうち、適当な10レコードを削除する
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # 実際に公式サイトの1ページ目に出てくる最新カードをクロールして特定するのがベスト
        # ここでは、前回のボルメテウス収集等で入った、あるいは cards_v2.db に登録されている中から
        # 公式サイトの1ページ目に確実に出現するカードを10件特定し、削除する。
        # 簡易的に、公式検索の1ページ目をフェッチして、出現するIDの上位10件をDBから一時削除する
        import requests, re
        url = 'https://dm.takaratomy.co.jp/card/'
        headers = {'User-Agent': 'Mozilla/5.0', 'X-Requested-With': 'XMLHttpRequest'}
        response = requests.post(url, data={'pagenum': '1'}, headers=headers, timeout=10)
        found_ids = re.findall(r"href=['\"]/card/detail/\?id=([^'\"]+?)['\"]", response.text)
        
        target_ids = found_ids[:10]
        print(f"  Identified {len(target_ids)} new cards to remove for simulation: {target_ids}")
        
        # DBから削除
        for cid in target_ids:
            cursor.execute("DELETE FROM cards WHERE card_id = ?", (cid,))
        conn.commit()
        conn.close()
        
        t0 = time.perf_counter()
        
        # クローラーを起動
        result = subprocess.run(
            ["python", "collect_cards.py", "-i"],
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR)
        )
        
        t1 = time.perf_counter()
        duration = t1 - t0
        
        print(f"  Execution Time for 10 cards fetch: {duration:.2f} seconds")
        lines = result.stdout.strip().split("\n")
        print("  Output logs:")
        for line in lines[-8:]:
            print(f"    {line}")
            
    finally:
        # 元に戻す
        shutil.move(str(DB_PATH) + ".bak", str(DB_PATH))
        print("  Original database fully restored.")

if __name__ == "__main__":
    measure_case_a()
    measure_case_b()
