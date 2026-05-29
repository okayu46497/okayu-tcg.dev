"""P2接続スクリプト"""
import requests
import asyncio
import websockets
import json
import sys

ROOM_ID = sys.argv[1] if len(sys.argv) > 1 else "6b075da8"

# Join room
r = requests.post(f"http://localhost:8000/join_room", json={"room_id": ROOM_ID, "player_name": "CPU"})
data = r.json()
p2_id = data["player_id"]
print(f"P2 joined: {p2_id}")


async def p2_connect():
    uri = f"ws://localhost:8000/ws/{ROOM_ID}?player_id={p2_id}"
    async with websockets.connect(uri) as ws:
        msg = json.loads(await ws.recv())
        print("Game phase:", msg.get("phase", msg.get("type")))
        # Keep alive for 60 seconds
        await asyncio.sleep(60)
        print("P2 disconnecting")


asyncio.run(p2_connect())
