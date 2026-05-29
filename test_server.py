"""サーバー動作確認テスト"""
import requests
import asyncio
import websockets
import json


def test_rest_api():
    print("=== REST API テスト ===")

    # ルーム作成
    r1 = requests.post("http://localhost:8000/create_room", json={"player_name": "Alice"})
    assert r1.status_code == 200
    data1 = r1.json()
    room_id = data1["room_id"]
    p1_id = data1["player_id"]
    print(f"  ルーム作成OK: room={room_id}, p1={p1_id}")

    # ルーム一覧
    r_list = requests.get("http://localhost:8000/rooms")
    assert r_list.status_code == 200
    print(f"  ルーム一覧OK: {len(r_list.json())}件")

    # ルーム参加
    r2 = requests.post("http://localhost:8000/join_room", json={"room_id": room_id, "player_name": "Bob"})
    assert r2.status_code == 200
    data2 = r2.json()
    p2_id = data2["player_id"]
    print(f"  ルーム参加OK: p2={p2_id}")

    # 満員テスト
    r3 = requests.post("http://localhost:8000/join_room", json={"room_id": room_id, "player_name": "Charlie"})
    assert r3.status_code == 400
    print("  満員拒否OK")

    return room_id, p1_id, p2_id


async def test_websocket(room_id, p1_id, p2_id):
    print("\n=== WebSocket テスト ===")
    uri1 = f"ws://localhost:8000/ws/{room_id}?player_id={p1_id}"
    uri2 = f"ws://localhost:8000/ws/{room_id}?player_id={p2_id}"

    async with websockets.connect(uri1) as ws1, websockets.connect(uri2) as ws2:
        # P1: 待機中メッセージを受信
        msg1_wait = json.loads(await ws1.recv())
        print(f"  P1 初回メッセージ: type={msg1_wait['type']}")

        # P2接続後、両者にゲーム状態が配信される
        msg2_info = json.loads(await ws2.recv())
        msg1_state = json.loads(await ws1.recv())
        msg2_state = json.loads(await ws2.recv())

        print(f"  P1 ゲーム状態: phase={msg1_state.get('phase')}")
        print(f"  P2 ゲーム状態: phase={msg2_state.get('phase')}")

        assert msg1_state["phase"] == "playing"
        assert msg2_state["phase"] == "playing"
        print(f"  P1 手札: {msg1_state['you']['hand_count']}枚")
        print(f"  P1 シールド: {msg1_state['you']['shield_count']}枚")
        print(f"  P1 デッキ: {msg1_state['you']['deck_count']}枚")

        # ターンプレイヤーを特定
        if msg1_state["is_your_turn"]:
            turn_ws, other_ws = ws1, ws2
            turn_state = msg1_state
            turn_name = "P1"
        else:
            turn_ws, other_ws = ws2, ws1
            turn_state = msg2_state
            turn_name = "P2"

        print(f"  先攻: {turn_name}")

        # マナチャージ
        hand = turn_state["you"]["hand"]
        card_uuid = hand[0]["uuid"]
        card_name = hand[0]["name"]
        await turn_ws.send(json.dumps({"action": "charge_mana", "card_uuid": card_uuid}))
        resp1 = json.loads(await turn_ws.recv())
        resp2 = json.loads(await other_ws.recv())
        print(f"  マナチャージOK: {card_name}")
        print(f"    マナ数: {resp1['you']['mana_total']}")

        # ターン終了
        await turn_ws.send(json.dumps({"action": "end_turn"}))
        resp1 = json.loads(await turn_ws.recv())
        resp2 = json.loads(await other_ws.recv())
        print(f"  ターン終了OK: ターン{resp2['turn_number']}")

        print("\n=== 全テスト合格！ ===")


if __name__ == "__main__":
    room_id, p1_id, p2_id = test_rest_api()
    asyncio.run(test_websocket(room_id, p1_id, p2_id))
