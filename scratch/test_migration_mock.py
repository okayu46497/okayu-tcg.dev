import sys
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR / "scratch"))
sys.path.append(str(BASE_DIR))

import migrate_to_supabase

def run_mock_test():
    print("=== Supabase Migration Script Mock Testing ===")
    
    # 1. 移行対象のファイル実在確認
    assert migrate_to_supabase.CARDS_JSON_PATH.exists()
    assert migrate_to_supabase.DECKS_JSON_PATH.exists()
    
    with open(migrate_to_supabase.CARDS_JSON_PATH, "r", encoding="utf-8") as f:
        cards_data = json.load(f)
    with open(migrate_to_supabase.DECKS_JSON_PATH, "r", encoding="utf-8") as f:
        decks_data = json.load(f)
        
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
        # DELETE が2回呼ばれていること (cards と decks のクリア)
        assert mock_delete.call_count == 2
        # POST が2回呼ばれていること (cards と decks の挿入)
        assert mock_post.call_count == 2
        
        # 実際に送信されたデータを検証
        # 最初のPOST (cards)
        cards_post_call = mock_post.call_args_list[0]
        posted_cards = cards_post_call[1]["json"]
        print(f"Successfully mocked POST for {len(posted_cards)} cards.")
        assert len(posted_cards) == len(cards_data)
        
        # 2番目のPOST (decks)
        decks_post_call = mock_post.call_args_list[1]
        posted_decks = decks_post_call[1]["json"]
        print(f"Successfully mocked POST for {len(posted_decks)} decks.")
        assert len(posted_decks) == len(decks_data)
        
    print("\n[SUCCESS] Mock migration test passed successfully with 100% matched counts!")

if __name__ == "__main__":
    run_mock_test()
