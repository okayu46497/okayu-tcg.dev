import sys
import os
import unittest

# Add workspace directory to path
sys.path.append(r"c:\Users\keita\OneDrive\ドキュメント\vscode\デュエマ")

from app import GameRoom, PlayerState

class TestStackCards(unittest.TestCase):
    def setUp(self):
        self.room = GameRoom("test_room")
        self.p1 = self.room.add_player("player1", "Alice")
        self.p2 = self.room.add_player("player2", "Bob")
        
        # Setup active turn
        self.room.phase = "playing"
        self.room.player_order = ["player1", "player2"]
        self.room.turn_player_id = "player1"

    def test_stack_card_top_evolution(self):
        """上に重ねる（進化）のテスト"""
        # 進化元クリーチャーをバトルゾーンに配置
        base_creature = {
            "uuid": "base_uuid",
            "name": "Base Monster",
            "card_type": "creature"
        }
        self.p1.battle_zone.append(base_creature)
        
        # 進化クリーチャーを手札に配置
        evo_creature = {
            "uuid": "evo_uuid",
            "name": "Evolution Dragon",
            "card_type": "creature"
        }
        self.p1.hand.append(evo_creature)
        
        # 進化実行
        res = self.room.action_stack_card(
            player_id="player1",
            card_uuid="evo_uuid",
            target_uuid="base_uuid",
            stack_type="top"
        )
        
        self.assertTrue(res.get("success"))
        # 手札から消えていること
        self.assertNotIn(evo_creature, self.p1.hand)
        # バトルゾーンには evolution dragon のみが存在し、下に Base Monster が敷かれていること
        self.assertEqual(len(self.p1.battle_zone), 1)
        top_card = self.p1.battle_zone[0]
        self.assertEqual(top_card["uuid"], "evo_uuid")
        self.assertEqual(len(top_card.get("under_cards", [])), 1)
        self.assertEqual(top_card["under_cards"][0]["uuid"], "base_uuid")

        # ログの確認
        log_str = "\n".join(self.room.log)
        self.assertIn("Alice が Base Monster の上に Evolution Dragon を重ねました（進化）", log_str)

    def test_stack_card_bottom_underlay(self):
        """下に敷く（カードの下に置く）のテスト"""
        base_creature = {
            "uuid": "base_uuid",
            "name": "Target Monster",
            "card_type": "creature"
        }
        self.p1.battle_zone.append(base_creature)
        
        shield_card = {
            "uuid": "under_uuid",
            "name": "Under Shield Spell",
            "card_type": "spell"
        }
        self.p1.shields.append(shield_card)
        
        # 下に敷く実行
        res = self.room.action_stack_card(
            player_id="player1",
            card_uuid="under_uuid",
            target_uuid="base_uuid",
            stack_type="bottom"
        )
        
        self.assertTrue(res.get("success"))
        # シールドから消えていること
        self.assertNotIn(shield_card, self.p1.shields)
        # バトルゾーンのカードの下に入っていること
        top_card = self.p1.battle_zone[0]
        self.assertEqual(len(top_card.get("under_cards", [])), 1)
        self.assertEqual(top_card["under_cards"][0]["uuid"], "under_uuid")
        
        # ログの確認
        log_str = "\n".join(self.room.log)
        self.assertIn("Alice が Target Monster の下に Under Shield Spell を敷きました", log_str)

    def test_move_under_card_to_mana(self):
        """下層に敷かれているカードを個別にマナゾーンへ移動するテスト（透過的な再帰削除の検証）"""
        parent = {
            "uuid": "parent_uuid",
            "name": "Parent",
            "card_type": "creature",
            "under_cards": [
                {"uuid": "under1", "name": "Under Card 1", "card_type": "creature"},
                {"uuid": "under2", "name": "Under Card 2", "card_type": "spell"}
            ]
        }
        self.p1.battle_zone.append(parent)
        
        # under2をマナへ移動
        res = self.room.action_move_card(
            player_id="player1",
            card_uuid="under2",
            from_zone="battle",
            to_zone="mana"
        )
        
        self.assertTrue(res.get("success"))
        # マナゾーンに入っていること
        self.assertEqual(len(self.p1.mana_zone), 1)
        self.assertEqual(self.p1.mana_zone[0]["uuid"], "under2")
        
        # 親カードの下層リストから under2 が削除されていること
        top_card = self.p1.battle_zone[0]
        self.assertEqual(len(top_card["under_cards"]), 1)
        self.assertEqual(top_card["under_cards"][0]["uuid"], "under1")

    def test_auto_discard_under_cards_on_battle_leave(self):
        """一番上のメインクリーチャーがバトルゾーンを離れた際、下層カードが自動で持ち主の墓地へ送られるテスト"""
        parent = {
            "uuid": "parent_uuid",
            "name": "Parent Dragon",
            "card_type": "creature",
            "under_cards": [
                {"uuid": "under1", "name": "Evo Base 1", "card_type": "creature"},
                {"uuid": "under2", "name": "Evo Base 2", "card_type": "creature"}
            ]
        }
        self.p1.battle_zone.append(parent)
        
        # 一番上のメインクリーチャーを手札に戻す（ババアバウンスなどの再現）
        res = self.room.action_move_card(
            player_id="player1",
            card_uuid="parent_uuid",
            from_zone="battle",
            to_zone="hand"
        )
        
        self.assertTrue(res.get("success"))
        # 手札には Parent Dragon のみが戻る
        self.assertEqual(len(self.p1.hand), 1)
        self.assertEqual(self.p1.hand[0]["uuid"], "parent_uuid")
        self.assertNotIn("under_cards", self.p1.hand[0]) # under_cards キーは pop されていること
        
        # 下層にあった Evo Base 1, 2 は墓地に入っていること
        self.assertEqual(len(self.p1.graveyard), 2)
        grave_uuids = [c["uuid"] for c in self.p1.graveyard]
        self.assertIn("under1", grave_uuids)
        self.assertIn("under2", grave_uuids)
        
        # ログに自動墓地送りの記録があること
        log_str = "\n".join(self.room.log)
        self.assertIn("📁 Parent Dragon がバトルゾーンを離れたため、下に敷かれていたカード (Evo Base 1, Evo Base 2) は墓地へ送られました", log_str)

if __name__ == '__main__':
    unittest.main()
