"""バトル画面高機能拡張（効果パース、召喚緩和、手動バトル解決、カスタムスリーブ）の自動検証テスト"""
import sys
# 標準出力をUTF-8に設定（Windows環境での絵文字表示によるUnicodeEncodeError回避用）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import requests
import asyncio
import websockets
import json
import random

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

def get_auth_tokens():
    print("=== 1. ユーザー登録/ログイン ===")
    tokens = {}
    players = ["testp1", "testp2"]
    
    for name in players:
        # まず登録を試みる
        res = requests.post(f"{BASE_URL}/register", json={"name": name, "email": f"{name}@example.com", "password": "password123"})
        if res.status_code == 200:
            data = res.json()
            tokens[name] = data["token"]
            print(f"  登録成功: {name}, token={data['token']}")
        else:
            # 既に存在する場合はログインする
            res_login = requests.post(f"{BASE_URL}/login", json={"name": name, "password": "password123"})
            assert res_login.status_code == 200, f"ログイン失敗: {name}"
            data = res_login.json()
            tokens[name] = data["token"]
            print(f"  ログイン成功: {name}, token={data['token']}")
            
    return tokens["testp1"], tokens["testp2"]

def create_and_save_deck(token, name):
    print(f"=== 2. デッキの作成・保存 ({name}) ===")
    # APIから現在登録されている有効なカードリストを取得する
    res_cards = requests.get(f"{BASE_URL}/api/cards")
    assert res_cards.status_code == 200, "カード一覧の取得失敗"
    cards = res_cards.json()
    assert len(cards) > 0, "登録されているカードがありません"
    
    # [堅牢化] デッキに呪文(spell)カードを確実に含め、検証9の呪文テストが100%合格するように調整します
    spells = [c["id"] for c in cards if c.get("card_type") == "spell"]
    creatures = [c["id"] for c in cards if c.get("card_type") != "spell"]
    
    card_ids = []
    if spells:
        while len(card_ids) < 15:
            card_ids.extend(spells)
    if creatures:
        while len(card_ids) < 40:
            card_ids.extend(creatures)
            
    # それでも40枚に満たない場合は全体のカードプールから補充
    card_pool = [c["id"] for c in cards]
    while len(card_ids) < 40:
        card_ids.extend(card_pool)
        
    card_ids = card_ids[:40]
    random.shuffle(card_ids)
    
    # [新機能検証] スリーブ設定（カスタムスリーブ）を含めて保存
    res = requests.post(f"{BASE_URL}/save_deck", json={
        "token": token,
        "name": f"{name}の検証デッキ",
        "cards": card_ids,
        "sleeve_type": "custom",
        "sleeve_image": "test_sleeve_image.png"
    })
    assert res.status_code == 200, f"デッキ保存失敗: {res.text}"
    deck = res.json()["deck"]
    assert deck.get("sleeve_type") == "custom", "スリーブタイプの保存エラー"
    assert deck.get("sleeve_image") == "test_sleeve_image.png", "スリーブ画像の保存エラー"
    print(f"  デッキ＆カスタムスリーブ保存成功: id={deck['id']}, sleeve={deck['sleeve_image']}")
    return deck["id"]

def setup_room(p1_token, p1_deck_id, p2_token, p2_deck_id):
    print("=== 3. ルームの作成と参加 ===")
    room_id = f"test_{random.randint(1000, 9999)}"
    
    # プレイヤー1がルーム作成
    res_create = requests.post(f"{BASE_URL}/create_room", json={
        "room_id": room_id,
        "deck_id": p1_deck_id,
        "token": p1_token
    })
    assert res_create.status_code == 200, f"ルーム作成失敗: {res_create.text}"
    p1_id = res_create.json()["player_id"]
    print(f"  ルーム作成OK: room_id={room_id}, p1_id={p1_id}")
    
    # プレイヤー2がルーム参加
    res_join = requests.post(f"{BASE_URL}/join_room", json={
        "room_id": room_id,
        "deck_id": p2_deck_id,
        "token": p2_token
    })
    assert res_join.status_code == 200, f"ルーム参加失敗: {res_join.text}"
    p2_id = res_join.json()["player_id"]
    print(f"  ルーム参加OK: p2_id={p2_id}")
    
    return room_id, p1_id, p2_id

async def run_websocket_tests(room_id, p1_id, p2_id):
    print("\n=== 4. WebSocket によるサンドボックス機能検証 ===")
    uri1 = f"{WS_URL}/{room_id}?player_id={p1_id}"
    uri2 = f"{WS_URL}/{room_id}?player_id={p2_id}"
    
    async with websockets.connect(uri1) as ws1, websockets.connect(uri2) as ws2:
        # P1 & P2 状態読み出し
        msg1_wait = json.loads(await ws1.recv())
        msg2_init = json.loads(await ws2.recv())
        msg1_state = json.loads(await ws1.recv())
        msg2_state = json.loads(await ws2.recv())
        
        print("  対戦が開始されました。初期手札とシールド枚数をチェックします。")
        assert msg1_state["phase"] == "playing"
        assert len(msg1_state["you"]["hand"]) == 5
        assert len(msg1_state["you"]["shields"]) == 5

        # [新機能検証] 初期の自分のシールドが裏向きでマスクされていることを確認
        print("  [検証] 自分の初期シールドが裏向きでマスクされているか（ホバー時の漏洩防止）")
        for shield in msg1_state["you"]["shields"]:
            assert shield.get("hidden") is True, "自分の初期シールドが裏向きになっていません"
            assert "name" not in shield, "自分の初期シールドのカード名が見えてしまっています"
            assert "text" not in shield, "自分の初期シールドのテキストが見えてしまっています"
        print("  -> OK! 自分の初期シールドは完全にマスクされています。")
        
        # [新機能検証] スリーブ情報の同期を確認
        print("  [検証] 自分と相手のスリーブ設定が同期されているか")
        assert msg1_state["you"]["sleeve_type"] == "custom"
        assert msg1_state["you"]["sleeve_image"] == "test_sleeve_image.png"
        assert msg1_state["opponent"]["sleeve_type"] == "custom"
        assert msg1_state["opponent"]["sleeve_image"] == "test_sleeve_image.png"
        print("  -> OK! 自分と相手のスリーブ情報が同期されています。")
        
        # ターンプレイヤーに関わらず、P1を主体として検証を行います。
        opponent_hand = msg1_state["opponent"]["hand"]
        opponent_shields = msg1_state["opponent"]["shields"]
        
        print("  [検証] 相手の手札データがマスクされ、UUIDが振られているか")
        assert len(opponent_hand) == 5
        assert all("hidden" in c and "uuid" in c for c in opponent_hand), "相手手札のマスクエラー"
        print("  -> OK! UUID付きでマスクされています。")
        
        # ----------------------------------------------------------------------
        # 検証1: 手動タップ/アンタップ (toggle_tap) のテスト
        # ----------------------------------------------------------------------
        print("\n  --- [検証1] 手動タップ/アンタップ ---")
        p1_hand_card = msg1_state["you"]["hand"][0]
        p1_card_uuid = p1_hand_card["uuid"]
        
        print(f"  手札のカード({p1_hand_card['name']})をバトルゾーンに移動します。")
        await ws1.send(json.dumps({
            "action": "move_card",
            "card_uuid": p1_card_uuid,
            "from_zone": "hand",
            "to_zone": "battle"
        }))
        
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())
        
        # タップ切り替え (toggle_tap)
        print("  バトルゾーンのカードをタップします。")
        await ws1.send(json.dumps({
            "action": "toggle_tap",
            "card_uuid": p1_card_uuid,
            "zone": "battle"
        }))
        
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())
        
        print("  [検証] カードがタップリストに入ったか")
        assert p1_card_uuid in msg1_state["you"]["tapped_creatures"], "タップされていません"
        print("  -> OK! タップ状態になりました。")
        
        # アンタップ
        print("  バトルゾーンのカードをアンタップします。")
        await ws1.send(json.dumps({
            "action": "toggle_tap",
            "card_uuid": p1_card_uuid,
            "zone": "battle"
        }))
        
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())
        
        print("  [検証] カードがタップリストから外れたか")
        assert p1_card_uuid not in msg1_state["you"]["tapped_creatures"], "アンタップされていません"
        print("  -> OK! アンタップ状態に戻りました。")

        # ----------------------------------------------------------------------
        # 検証2: カード効果の宣言 (declare_effect)
        # ----------------------------------------------------------------------
        print("\n  --- [検証2] カード効果の宣言 ---")
        effect_text = "バトルゾーンに出た時、山札の上から1枚をマナに置きます。"
        print(f"  効果を宣言します: 「{effect_text}」")
        await ws1.send(json.dumps({
            "action": "declare_effect",
            "card_uuid": p1_card_uuid,
            "text": effect_text
        }))
        
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())
        
        print("  [検証] ログに効果宣言メッセージが含まれているか")
        latest_log = msg1_state["log"][-1]
        print(f"  最新ログ: {latest_log}")
        assert "効果を宣言:" in latest_log and effect_text in latest_log, "ログへの出力がありません"
        print("  -> OK! 効果の宣言がログにブロードキャストされました。")

        # ----------------------------------------------------------------------
        # 検証3: 山札の任意位置へのカード移動 (move_card with position/index)
        # ----------------------------------------------------------------------
        print("\n  --- [検証3] 山札の指定位置へのインサート ---")
        p1_hand_card2 = msg1_state["you"]["hand"][0]
        p1_card2_uuid = p1_hand_card2["uuid"]
        
        print(f"  手札のカード({p1_hand_card2['name']})を山札の上から2枚目に差し込みます。")
        await ws1.send(json.dumps({
            "action": "move_card",
            "card_uuid": p1_card2_uuid,
            "from_zone": "hand",
            "to_zone": "deck",
            "position": "index",
            "index": 2
        }))
        
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())
        
        deck_cards = msg1_state["you"]["deck"]
        print("  [検証] 山札の上から2枚目（配列の最後から2番目の要素）にカードが挿入されているか")
        assert deck_cards[-2]["uuid"] == p1_card2_uuid, f"山札の挿入位置が違います"
        print("  -> OK! 正しく上から2枚目に挿入されています。")

        # ----------------------------------------------------------------------
        # 検証4: シールドドロップ時の表裏指定 (move_card with face_up)
        # ----------------------------------------------------------------------
        print("\n  --- [検証4] シールドドロップ時の表裏指定 ---")
        p1_hand_card3 = msg1_state["you"]["hand"][0]
        p1_card3_uuid = p1_hand_card3["uuid"]
        
        print(f"  手札のカード({p1_hand_card3['name']})を「表向き」でシールドに置きます。")
        await ws1.send(json.dumps({
            "action": "move_card",
            "card_uuid": p1_card3_uuid,
            "from_zone": "hand",
            "to_zone": "shields",
            "face_up": True
        }))
        
        msg1_state = json.loads(await ws1.recv())
        msg2_state = json.loads(await ws2.recv())
        
        p1_shields = msg1_state["you"]["shields"]
        target_shield_p1 = next((s for s in p1_shields if s["uuid"] == p1_card3_uuid), None)
        assert target_shield_p1 is not None, "シールドが見つかりません"
        assert target_shield_p1["face_up"] is True, "シールドが表向きになっていません"
        
        p2_opp_shields = msg2_state["opponent"]["shields"]
        target_shield_p2 = next((s for s in p2_opp_shields if s.get("uuid") == p1_card3_uuid), None)
        print("  [検証] 相手から見て、表向きシールドの中身（実画像・カード名など）が見えているか")
        assert target_shield_p2 is not None
        assert "hidden" not in target_shield_p2, "表向きシールドなのにマスクされています"
        assert target_shield_p2["name"] == p1_hand_card3["name"], "カード名が一致しません"
        print(f"  -> OK! 相手からもカード名 '{target_shield_p2['name']}' が見えています。")

        # ----------------------------------------------------------------------
        # 検証5: 相手手札（裏向き）を安全にドラッグ操作して墓地へ送るテスト
        # ----------------------------------------------------------------------
        print("\n  --- [検証5] 相手手札のブラインドドラッグ操作 ---")
        p2_card_mask = opponent_hand[0]
        p2_card_uuid = p2_card_mask["uuid"]
        
        print(f"  相手の手札（マスク状態）からカード(UUID: {p2_card_uuid})をドラッグして墓地に送ります。")
        await ws1.send(json.dumps({
            "action": "move_card",
            "card_uuid": p2_card_uuid,
            "from_zone": "opp-hand",
            "to_zone": "graveyard"
        }))
        
        msg1_state = json.loads(await ws1.recv())
        msg2_state = json.loads(await ws2.recv())
        
        assert msg2_state["you"]["hand_count"] == 4, "相手手札の枚数が減っていません"
        p2_graveyard_uuids = [c["uuid"] for c in msg2_state["you"]["graveyard"]]
        print("  [検証] 相手の墓地にドラッグしたカードが届いているか")
        assert p2_card_uuid in p2_graveyard_uuids, "相手の墓地にカードが届いていません"
        print("  -> OK! 相手の手札から相手の墓地へ安全にブラインドドラッグ移動されました。")

        # ----------------------------------------------------------------------
        # 検証6: 相手のターン中であっても自由にドラッグ操作ができるか（ターン制限の撤廃）
        # ----------------------------------------------------------------------
        print("\n  --- [検証6] 相手のターン中でのドラッグ操作の可否 ---")
        is_p1_turn = msg1_state["is_your_turn"]
        if is_p1_turn:
            print("  P1のターンのため、一度ターン終了します。")
            await ws1.send(json.dumps({"action": "end_turn"}))
            msg1_state = json.loads(await ws1.recv())
            _ = json.loads(await ws2.recv())
            
        print("  現在の状態を確認: P1のターンですか？", msg1_state["is_your_turn"])
        assert msg1_state["is_your_turn"] is False, "P1のターンから切り替わっていません"
        
        p1_hand_card_t6 = msg1_state["you"]["hand"][0]
        p1_uuid_t6 = p1_hand_card_t6["uuid"]
        
        print(f"  [相手ターン中] P1が手札のカード({p1_hand_card_t6['name']})をマナゾーンにドラッグ移動します。")
        await ws1.send(json.dumps({
            "action": "move_card",
            "card_uuid": p1_uuid_t6,
            "from_zone": "hand",
            "to_zone": "mana"
        }))
        
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())
        
        print("  [検証] 相手ターン中でもカード移動がエラーにならず成功しているか")
        p1_mana_uuids = [c["uuid"] for c in msg1_state["you"]["mana_zone"]]
        assert p1_uuid_t6 in p1_mana_uuids, "相手ターン中のドラッグ移動に失敗しました"
        print("  -> OK! 相手のターンであっても、自由にカード移動操作（サンドボックス化）が行えました！")

        # ----------------------------------------------------------------------
        # 検証7: クリーチャー以外の自動コスト支払い登場（バリデーション緩和の検証）
        # ----------------------------------------------------------------------
        print("\n  --- [検証7] カード登場のバリデーション緩和検証 ---")
        # P1のターンであることを保証する
        if not msg1_state["is_your_turn"]:
            print("  P2のターンのため、一度ターン終了します。")
            await ws2.send(json.dumps({"action": "end_turn"}))
            msg2_state = json.loads(await ws2.recv())
            msg1_state = json.loads(await ws1.recv())

        # 手札が不足しないよう、またマナが十分貯まるよう、まずは山札から数枚ドロー
        for _ in range(5):
            deck_cards = msg1_state["you"]["deck"]
            if deck_cards:
                c_uuid = deck_cards[-1]["uuid"]
                await ws1.send(json.dumps({
                    "action": "move_card",
                    "card_uuid": c_uuid,
                    "from_zone": "deck",
                    "to_zone": "hand"
                }))
                msg1_state = json.loads(await ws1.recv())
                _ = json.loads(await ws2.recv())

        # 手札からマナへ5枚マニュアル移動（常に先頭のカードを移動し、手札が枯渇しないようにする）
        for _ in range(5):
            if len(msg1_state["you"]["hand"]) > 1:
                c_uuid = msg1_state["you"]["hand"][0]["uuid"]
                await ws1.send(json.dumps({
                    "action": "move_card",
                    "card_uuid": c_uuid,
                    "from_zone": "hand",
                    "to_zone": "mana"
                }))
                msg1_state = json.loads(await ws1.recv())
                _ = json.loads(await ws2.recv())
            
        # 呪文以外のカードを手札から探し、それをsummon検証の対象にする
        p1_hand_card_t7 = None
        for c in msg1_state["you"]["hand"]:
            if c.get("card_type") != "spell":
                p1_hand_card_t7 = c
                break
        if p1_hand_card_t7 is None:
            p1_hand_card_t7 = msg1_state["you"]["hand"][0]

        print(f"  マナを支払って {p1_hand_card_t7['name']}(タイプ: {p1_hand_card_t7.get('card_type')}) をバトルゾーンに登場させます（summonアクション送信）。")
        
        # 呪文以外のどんなカードタイプでもsummonアクションが通ることを検証
        await ws1.send(json.dumps({
            "action": "summon",
            "card_uuid": p1_hand_card_t7["uuid"]
        }))
        
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())
        
        print("  [検証] バトルゾーンにカードが登場しているか")
        battle_uuids = [c["uuid"] for c in msg1_state["you"]["battle_zone"]]
        assert p1_hand_card_t7["uuid"] in battle_uuids, "バリデーションエラーかマナ不足で登場に失敗しました"
        print("  -> OK! クリーチャー以外のカードでも、無事に自動マナ支払いプレイ登場が完了しました（緩和合格）。")

        # ----------------------------------------------------------------------
        # 検証8: 手動バトル解決（攻撃時に破壊されず、battle_trigger受信）のテスト
        # ----------------------------------------------------------------------
        print("\n  --- [検証8] 手動バトル解決とbattle_triggerイベントの検証 ---")
        # P1のターンにする（P2ターンになっている場合はターン終了）
        if not msg1_state["is_your_turn"]:
            print("  P2のターンのため、一度ターン終了します。")
            await ws2.send(json.dumps({"action": "end_turn"}))
            msg2_state = json.loads(await ws2.recv())
            msg1_state = json.loads(await ws1.recv())

        # アタッカーの召喚酔いを解除するため、1往復ターンを回します
        print("  カードの召喚酔いを解除するためにターンを回します。")
        await ws1.send(json.dumps({"action": "end_turn"}))
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())
        
        await ws2.send(json.dumps({"action": "end_turn"}))
        msg2_state = json.loads(await ws2.recv())
        msg1_state = json.loads(await ws1.recv())

        # P2のバトルゾーンに標的クリーチャーを配置（マニュアル移動）
        p2_target_card = msg2_state["you"]["hand"][0]
        print(f"  P2のバトルゾーンに標的カード({p2_target_card['name']})をマニュアル配置します。")
        await ws2.send(json.dumps({
            "action": "move_card",
            "card_uuid": p2_target_card["uuid"],
            "from_zone": "hand",
            "to_zone": "battle"
        }))
        msg2_state = json.loads(await ws2.recv())
        msg1_state = json.loads(await ws1.recv())

        # P1の攻撃可能なアタッカーを特定
        p1_attacker = msg1_state["you"]["battle_zone"][0]
        
        # 攻撃アクション送信
        print(f"  アタッカー({p1_attacker['name']}) で 標的({p2_target_card['name']}) を攻撃します。")
        await ws1.send(json.dumps({
            "action": "attack_creature",
            "attacker_uuid": p1_attacker["uuid"],
            "target_uuid": p2_target_card["uuid"]
        }))
        
        # アクション成功時のブロードキャスト（game_state）を受信
        msg1_state = json.loads(await ws1.recv())
        msg2_state = json.loads(await ws2.recv())

        print("  [検証] 相手側のゲームステートに攻撃警告（current_attack）が含まれているか")
        assert msg2_state["current_attack"] is not None, "攻撃警告情報がありません"
        assert msg2_state["current_attack"]["attacker_uuid"] == p1_attacker["uuid"], "攻撃元クリーチャーのUUID不一致"
        assert msg2_state["current_attack"]["target_uuid"] == p2_target_card["uuid"], "攻撃対象のUUID不一致"
        assert "効果を使ってください" in msg2_state["current_attack"]["message"], "警告メッセージが違います"
        print("  -> OK! 相手側に対しても正確な攻撃警告情報が送信されています。")
        
        # 次に、バトル解決開始による "battle_trigger" ブロードキャストメッセージを受信します！
        trigger1 = json.loads(await ws1.recv())
        trigger2 = json.loads(await ws2.recv())
        
        print("  [検証] battle_trigger イベントメッセージが届いたか")
        assert trigger1["type"] == "battle_trigger", "battle_triggerメッセージがありません"
        assert trigger1["attacker"]["uuid"] == p1_attacker["uuid"], "アタッカーのUUID不一致"
        assert trigger1["target"]["uuid"] == p2_target_card["uuid"], "ターゲットのUUID不一致"
        print(f"  -> OK! 勝敗結果 '{trigger1['result']}' を含んだ battle_trigger メッセージが届きました。")
        
        print("  [検証] 敗北したクリーチャーが自動で墓地に送られず、バトルゾーンに残っているか")
        p2_battle_uuids = [c["uuid"] for c in msg2_state["you"]["battle_zone"]]
        assert p2_target_card["uuid"] in p2_battle_uuids, "自動で墓地に送られてしまっています"
        print("  -> OK! 自動破壊されず、手動解決のためにバトルゾーンに留まっています（手動解決合格）。")

        # ----------------------------------------------------------------------
        # 検証9: 呪文のバトルゾーンからの手動墓地送りと墓地回収の検証
        # ----------------------------------------------------------------------
        print("\n  --- [検証9] 呪文の手動墓地送りと墓地からの回収検証 ---")
        # 前提：手札にある呪文カード（例：邪侵入）をバトルゾーンに手動移動（move_card）
        p1_spell_card = None
        for c in msg1_state["you"]["hand"]:
            if c.get("card_type") == "spell":
                p1_spell_card = c
                break
        
        # 呪文が手札になければ、山札からドローして探す
        if not p1_spell_card:
            # 探索用に山札からドロー
            for _ in range(5):
                deck_cards = msg1_state["you"]["deck"]
                if deck_cards:
                    c_uuid = deck_cards[-1]["uuid"]
                    await ws1.send(json.dumps({
                        "action": "move_card",
                        "card_uuid": c_uuid,
                        "from_zone": "deck",
                        "to_zone": "hand"
                    }))
                    msg1_state = json.loads(await ws1.recv())
                    _ = json.loads(await ws2.recv())
            for c in msg1_state["you"]["hand"]:
                if c.get("card_type") == "spell":
                    p1_spell_card = c
                    break

        assert p1_spell_card is not None, "検証に必要な呪文カードが手札に見つかりませんでした"
        print(f"  呪文カード({p1_spell_card['name']}) をバトルゾーンに手動移動（フリープレイ）します。")
        
        # 手動でバトルゾーンへ移動
        await ws1.send(json.dumps({
            "action": "move_card",
            "card_uuid": p1_spell_card["uuid"],
            "from_zone": "hand",
            "to_zone": "battle"
        }))
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())
        
        # バトルゾーンに入ったことを検証
        p1_battle_uuids = [c["uuid"] for c in msg1_state["you"]["battle_zone"]]
        assert p1_spell_card["uuid"] in p1_battle_uuids, "手動でバトルゾーンに置くことに失敗しました"

        # [バグ修正の検証] バトルゾーンにある呪文カードを手動で墓地に移動させる（move_card）
        print(f"  バトルゾーンにある呪文({p1_spell_card['name']}) を墓地へドラッグ移動（move_card）します。")
        await ws1.send(json.dumps({
            "action": "move_card",
            "card_uuid": p1_spell_card["uuid"],
            "from_zone": "my-battle", # フロントエンドから送られてくる my-battle を指定
            "to_zone": "graveyard"
        }))
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())

        # 墓地に入ったことを検証
        p1_grave_uuids = [c["uuid"] for c in msg1_state["you"]["graveyard"]]
        assert p1_spell_card["uuid"] in p1_grave_uuids, "バトルゾーンからの墓地送りでエラーが発生したか失敗しました"
        print("  -> OK! バトルゾーンに置かれた呪文カードでも、エラーなく無事に墓地へドラッグ移動できました（バグ修正合格）。")

        # [墓地から任意のゾーンへの移動の検証] 墓地にある呪文カードを手札へ回収（move_card）
        print(f"  墓地にあるカード({p1_spell_card['name']}) を手札へドラッグ回収（move_card）します。")
        await ws1.send(json.dumps({
            "action": "move_card",
            "card_uuid": p1_spell_card["uuid"],
            "from_zone": "graveyard",
            "to_zone": "hand"
        }))
        msg1_state = json.loads(await ws1.recv())
        _ = json.loads(await ws2.recv())

        # 手札に戻ったことを検証
        p1_hand_uuids = [c["uuid"] for c in msg1_state["you"]["hand"]]
        assert p1_spell_card["uuid"] in p1_hand_uuids, "墓地から手札への回収に失敗しました"
        print("  -> OK! 墓地から手札へのマニュアル回収ドラッグ移動も正常に機能しました（墓地回収合格）。")

    print("\n=== 全てのサンドボックス機能拡張・検証テストに合格しました！ ===")

if __name__ == "__main__":
    p1_token, p2_token = get_auth_tokens()
    p1_deck_id = create_and_save_deck(p1_token, "testp1")
    p2_deck_id = create_and_save_deck(p2_token, "testp2")
    room_id, p1_id, p2_id = setup_room(p1_token, p1_deck_id, p2_token, p2_deck_id)
    
    asyncio.run(run_websocket_tests(room_id, p1_id, p2_id))
