import sys
import os
import unittest

# Add workspace directory to path
sys.path.append(r"c:\Users\keita\OneDrive\ドキュメント\vscode\デュエマ")

from app import GameRoom, PlayerState

class TestShieldBreaksAndTriggers(unittest.TestCase):
    def setUp(self):
        self.room = GameRoom("test_room")
        self.p1 = self.room.add_player("player1", "Alice")
        self.p2 = self.room.add_player("player2", "Bob")
        
        # Setup active turn
        self.room.phase = "playing"
        self.room.player_order = ["player1", "player2"]
        self.room.turn_player_id = "player1"

    def test_action_break_shields_no_trigger(self):
        """S・トリガーなしのシールドを2枚ブレイクし、両方が手札に入り、トリガープロンプトが付かないことを確認"""
        attacker = {
            "uuid": "attacker_uuid",
            "name": "W-Breaker Dragon",
            "ability_text": "＊W・ブレイカー",
            "power": "6000",
            "card_type": "creature"
        }
        self.p1.battle_zone.append(attacker)
        
        shields = [
            {"uuid": "shield_1", "name": "Normal Shield 1", "ability_text": "ただのクリーチャー", "card_type": "creature"},
            {"uuid": "shield_2", "name": "Normal Shield 2", "ability_text": "ただの呪文", "card_type": "spell"},
            {"uuid": "shield_3", "name": "Normal Shield 3", "ability_text": "ただの盾", "card_type": "creature"}
        ]
        self.p2.shields = list(shields)
        
        # Alice attacks Bob with W-Breaker
        self.room.current_attack = {
            "attacker_uuid": "attacker_uuid",
            "target_uuid": "shield_1",
            "target_zone": "shields",
            "attacked_player_id": "player2",
            "break_count": 2,
            "message": "Aliceのクリーチャーが攻撃しています！"
        }
        
        # Alice (player1) confirms Bob's shield_1 and shield_2 to break
        res_confirm = self.room.action_confirm_shield_break(
            player_id="player1",
            card_uuids=["shield_1", "shield_2"]
        )
        self.assertTrue(res_confirm.get("success"))
        
        # Bob (player2) decides to break to hand
        res = self.room.action_break_shields(
            player_id="player2",
            to_zone="hand"
        )
        
        self.assertTrue(res.get("success"))
        self.assertEqual(len(self.p2.shields), 1)
        self.assertEqual(self.p2.shields[0]["uuid"], "shield_3")
        
        self.assertEqual(len(self.p2.hand), 2)
        for card in self.p2.hand:
            self.assertNotIn("trigger_prompt", card)
            self.assertNotIn("face_up", card)
            self.assertNotIn("hidden", card)

        self.assertIsNone(self.room.current_attack) # 攻撃状態がクリアされていること

    def test_action_break_shields_with_trigger(self):
        """S・トリガーありのシールドをブレイクした際、手札内で trigger_prompt が付くことを確認"""
        attacker = {
            "uuid": "attacker_uuid",
            "name": "Attacker",
            "ability_text": "",
            "power": "3000",
            "card_type": "creature"
        }
        self.p1.battle_zone.append(attacker)
        
        shields = [
            {"uuid": "shield_trigger", "name": "Aqua Surfer", "ability_text": "■S・トリガー\n■このクリーチャーが出たとき、相手のクリーチャーを戻す", "card_type": "creature"},
            {"uuid": "shield_normal", "name": "Normal Shield", "ability_text": "効果なし", "card_type": "creature"}
        ]
        self.p2.shields = list(shields)
        
        self.room.current_attack = {
            "attacker_uuid": "attacker_uuid",
            "target_uuid": "shield_trigger",
            "target_zone": "shields",
            "attacked_player_id": "player2",
            "break_count": 1,
            "message": "攻撃されました！"
        }
        
        # Alice (player1) confirms Bob's shield_trigger to break
        res_confirm = self.room.action_confirm_shield_break(
            player_id="player1",
            card_uuids=["shield_trigger"]
        )
        self.assertTrue(res_confirm.get("success"))
        
        # Bob (player2) decides to break to hand
        res = self.room.action_break_shields(
            player_id="player2",
            to_zone="hand"
        )
        
        self.assertTrue(res.get("success"))
        card_in_hand = self.p2.hand[0]
        self.assertEqual(card_in_hand["uuid"], "shield_trigger")
        self.assertTrue(card_in_hand.get("trigger_prompt"))

    def test_action_resolve_trigger_spell(self):
        """S・トリガー呪文の使用・不使用の解決テスト"""
        # 手札にトリガープロンプト付き呪文を配置
        trigger_spell = {
            "uuid": "trigger_spell_uuid",
            "name": "Natural Trap",
            "card_type": "spell",
            "ability_text": "■S・トリガー\n■相手のクリーチャーをマナゾーンに置く",
            "trigger_prompt": True
        }
        self.p2.hand.append(trigger_spell)
        
        # Use = True の場合
        res = self.room.action_resolve_trigger(
            player_id="player2",
            card_uuid="trigger_spell_uuid",
            use=True
        )
        self.assertTrue(res.get("success"))
        # 呪文は手札から消え、墓地に移動しているはず
        self.assertNotIn(trigger_spell, self.p2.hand)
        self.assertIn(trigger_spell, self.p2.graveyard)
        self.assertNotIn("trigger_prompt", trigger_spell) # プロンプトが消えていること
        
        # Use = False (見送り) の場合
        trigger_spell_2 = {
            "uuid": "trigger_spell_uuid_2",
            "name": "Natural Trap 2",
            "card_type": "spell",
            "ability_text": "■S・トリガー",
            "trigger_prompt": True
        }
        self.p2.hand.append(trigger_spell_2)
        res2 = self.room.action_resolve_trigger(
            player_id="player2",
            card_uuid="trigger_spell_uuid_2",
            use=False
        )
        self.assertTrue(res2.get("success"))
        # 手札に残るが、trigger_prompt は消えているはず
        self.assertIn(trigger_spell_2, self.p2.hand)
        self.assertNotIn(trigger_spell_2, self.p2.graveyard)
        self.assertNotIn("trigger_prompt", trigger_spell_2)

    def test_action_resolve_trigger_creature(self):
        """S・トリガー通常召喚の解決テストおよび自動効果発動の連動テスト"""
        # 登場時ドロー効果を持つS・トリガークリーチャー
        trigger_creature = {
            "uuid": "trigger_creature_uuid",
            "name": "Draw Surfer",
            "card_type": "creature",
            "ability_text": "■S・トリガー\n■このクリーチャーが出たとき、カードを１枚引く。",
            "trigger_prompt": True
        }
        self.p2.hand.append(trigger_creature)
        
        # 山札にドロー用のカードを用意
        self.p2.deck.append({"uuid": "drawn_card_uuid", "name": "Drawn Card"})
        
        res = self.room.action_resolve_trigger(
            player_id="player2",
            card_uuid="trigger_creature_uuid",
            use=True
        )
        self.assertTrue(res.get("success"))
        # バトルゾーンに出る
        self.assertIn(trigger_creature, self.p2.battle_zone)
        self.assertNotIn(trigger_creature, self.p2.hand)
        self.assertNotIn("trigger_prompt", trigger_creature)
        
        # 連動した自動ドロー効果により、カードが1枚引かれていること
        self.assertEqual(len(self.p2.hand), 1)
        self.assertEqual(self.p2.hand[0]["uuid"], "drawn_card_uuid")

    def test_allow_trigger_false(self):
        """allow_trigger=Falseで手札に加えた場合、トリガー能力があっても trigger_prompt が設定されないことを確認"""
        trigger_card = {
            "uuid": "trigger_card_uuid",
            "name": "Shield Trigger Card",
            "ability_text": "■S・トリガー",
            "card_type": "creature"
        }
        self.p2.shields.append(trigger_card)
        
        # 移動アクションを実行 (allow_trigger=False)
        res = self.room.action_move_card(
            player_id="player2",
            card_uuid="trigger_card_uuid",
            from_zone="shields",
            to_zone="hand",
            allow_trigger=False
        )
        
        self.assertTrue(res.get("success"))
        card_in_hand = self.p2.hand[0]
        self.assertEqual(card_in_hand["uuid"], "trigger_card_uuid")
        self.assertNotIn("trigger_prompt", card_in_hand)

    def test_automate_card_effect_draw(self):
        """召喚時に「カードをN枚引く」効果が自動発動することを確認"""
        card = {
            "uuid": "summon_card",
            "name": "Draw Beast",
            "card_type": "creature",
            "ability_text": "このクリーチャーが出たとき、カードを２枚引く。"
        }
        self.p1.hand.append(card)
        
        # 山札にカードをセット
        self.p1.deck = [
            {"uuid": "d1", "name": "Card 1"},
            {"uuid": "d2", "name": "Card 2"},
            {"uuid": "d3", "name": "Card 3"}
        ]
        
        # 召喚アクションを実行。本来は app.py 側で `action_summon` された時に `_automate_card_effect` が走る
        # テストとして直接 action_summon を走らせる
        # `action_summon` 内で _find_and_remove から hand のカードを抜いて battle_zone に置く処理がある
        # その後 `_automate_card_effect` が呼ばれる
        
        # room.players['player1'].mana_zone に十分なカードを置く（コスト足りるため）
        self.p1.mana_zone = [{"uuid": f"mana_{i}"} for i in range(5)]
        
        # 手札から削除してバトルゾーンに置く
        self.p1.hand.remove(card)
        self.p1.battle_zone.append(card)
        logs = self.room._automate_card_effect("player1", card)
        
        self.assertEqual(len(self.p1.hand), 2)
        # デッキは末尾から pop するので、d3, d2 が引かれているはず
        self.assertEqual(self.p1.hand[0]["uuid"], "d3")
        self.assertEqual(self.p1.hand[1]["uuid"], "d2")
        self.assertEqual(len(self.p1.deck), 1)
        self.assertEqual(self.p1.deck[0]["uuid"], "d1")
        
        self.assertTrue(any("カードを 2 枚引きました" in log for log in logs))

    def test_automate_card_effect_mana(self):
        """召喚時に「山札の上からN枚をマナゾーンに置く」効果が自動発動することを確認"""
        card = {
            "uuid": "mana_boost_card",
            "name": "Bronze-Arm Tribe",
            "card_type": "creature",
            "ability_text": "このクリーチャーが出たとき、山札の上から１枚目をマナゾーンに置く。"
        }
        self.p1.deck = [
            {"uuid": "m1", "name": "Mana Card 1"},
            {"uuid": "m2", "name": "Mana Card 2"}
        ]
        
        logs = self.room._automate_card_effect("player1", card)
        
        # マナゾーンが1枚増えている
        self.assertEqual(len(self.p1.mana_zone), 1)
        self.assertEqual(self.p1.mana_zone[0]["uuid"], "m2") # デッキ末尾がpopされるためm2が入る
        self.assertEqual(len(self.p1.deck), 1)
        self.assertTrue(any("マナゾーンに置きました" in log for log in logs))

    def test_automate_card_effect_shield(self):
        """召喚時に「山札の上から1枚目をシールドゾーンに置く」効果が自動発動することを確認"""
        card = {
            "uuid": "shield_maker",
            "name": "Shield Beast",
            "card_type": "creature",
            "ability_text": "このクリーチャーが出たとき、山札の上から1枚目をシールドゾーンに置く。"
        }
        self.p1.deck = [{"uuid": "s1", "name": "Shield Card"}]
        
        logs = self.room._automate_card_effect("player1", card)
        
        self.assertEqual(len(self.p1.shields), 1)
        self.assertEqual(self.p1.shields[0]["uuid"], "s1")
        self.assertFalse(self.p1.shields[0].get("face_up")) # 裏向きであること
        self.assertEqual(len(self.p1.deck), 0)
        self.assertTrue(any("シールド化しました" in log for log in logs))

    def test_automate_card_effect_discard(self):
        """召喚時に「相手は手札を1枚捨てる」効果が自動発動することを確認"""
        card = {
            "uuid": "discard_beast",
            "name": "Gost",
            "card_type": "creature",
            "ability_text": "このクリーチャーが出たとき、相手は自身の手札を1枚選んで捨てる。"
        }
        # 相手の手札をセット
        self.p2.hand = [
            {"uuid": "h1", "name": "Hand 1"},
            {"uuid": "h2", "name": "Hand 2"}
        ]
        
        logs = self.room._automate_card_effect("player1", card)
        
        # 相手の手札が1枚減り、墓地へ移動していること
        self.assertEqual(len(self.p2.hand), 1)
        self.assertEqual(len(self.p2.graveyard), 1)
        self.assertTrue(any("墓地に捨てました" in log for log in logs))

if __name__ == '__main__':
    unittest.main()
