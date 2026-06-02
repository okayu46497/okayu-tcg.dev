import sys
import os
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR / "scratch"))
sys.path.append(str(BASE_DIR))

import migrate_to_supabase

def run_mock_test():
    print("=== Supabase Migration Script Mock Testing ===")
    
    # 1. 移行対象のファイル/DB実在確認
    assert migrate_to_supabase.CARDS_JSON_PATH.exists()
    assert migrate_to_supabase.DECKS_JSON_PATH.exists()
    assert migrate_to_supabase.DB_PATH.exists()
    
    with open(migrate_to_supabase.CARDS_JSON_PATH, "r", encoding="utf-8") as f:
        cards_data = json.load(f)
    with open(migrate_to_supabase.DECKS_JSON_PATH, "r", encoding="utf-8") as f:
        decks_data = json.load(f)
        
    conn = sqlite3.connect(str(migrate_to_supabase.DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cards")
    db_count = cursor.fetchone()[0]
    conn.close()
        
    print(f"Local cards_v2.db count: {db_count}")
    print(f"Local Cards count: {len(cards_data)}")
    print(f"Local Decks count: {len(decks_data)}")

    # 2. テスト用のダミー環境変数を設定
    migrate_to_supabase.SUPABASE_KEY = "test-service-role-key"
    
    # 3. requests の各メソッドを MagicMock でパッチ
    with patch("requests.delete") as mock_delete, patch("requests.post") as mock_post:
        # モックのレスポンスを設定
        mock_del_resp = MagicMock()
        mock_del_resp.status_code = 204
        mock_delete.return_value = mock_del_resp
        
        mock_ins_resp = MagicMock()
        mock_ins_resp.status_code = 201
        mock_post.return_value = mock_ins_resp
        
        # 移行スクリプトを実行
        migrate_to_supabase.main()
        
        # 4. 呼び出し回数と引数のアサーション
        # DELETE が3回呼ばれていること (official_cards, user_cards, user_decks のクリア)
        assert mock_delete.call_count == 3
        
        # POST が 12 (official_cards 12チャンク) + 1 (user_cards) + 1 (user_decks) = 14回 呼ばれていること
        # 11469 / 1000 = 12チャンク
        expected_chunks = (db_count + 999) // 1000
        expected_post_calls = expected_chunks + 2
        print(f"Expected POST call count: {expected_post_calls} (Actual: {mock_post.call_count})")
        assert mock_post.call_count == expected_post_calls
        
        # 実際に送信されたデータを検証
        # 最初のPOSTから12回分は official_cards チャンク
        total_posted_official = 0
        for i in range(expected_chunks):
            total_posted_official += len(mock_post.call_args_list[i][1]["json"])
            
        print(f"Successfully mocked POST for {total_posted_official} official cards across chunks.")
        assert total_posted_official == db_count
        
        # 次のPOSTは user_cards
        posted_user_cards = mock_post.call_args_list[expected_chunks][1]["json"]
        print(f"Successfully mocked POST for {len(posted_user_cards)} user cards.")
        assert len(posted_user_cards) == len(cards_data)
        
        # 最後のPOSTは user_decks
        posted_decks = mock_post.call_args_list[expected_chunks + 1][1]["json"]
        print(f"Successfully mocked POST for {len(posted_decks)} decks.")
        assert len(posted_decks) == len(decks_data)
        
    print("\n[SUCCESS] Mock migration test passed successfully with 100% matched counts for ALL tables!")

if __name__ == "__main__":
    run_mock_test()
