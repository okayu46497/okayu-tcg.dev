"""
デュエル・マスターズ風カードゲーム バックエンド
FastAPI + WebSocket によるリアルタイム2人対戦サーバー
"""

import json
import uuid
import random
import asyncio
import shutil
import hashlib
from typing import Optional
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    File,
    UploadFile,
    Form,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ============================================================
# アプリケーション初期化
# ============================================================

app = FastAPI(title="でぃうえま", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# カードデータ読み込み
# ============================================================

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CARDS_PATH = DATA_DIR / "cards.json"
DECKS_PATH = DATA_DIR / "decks.json"
USERS_PATH = DATA_DIR / "users.json"
STATIC_DIR = BASE_DIR / "static"
CARD_IMAGES_DIR = STATIC_DIR / "cards"
SLEEVES_DIR = STATIC_DIR / "sleeves"
AVATARS_DIR = STATIC_DIR / "avatars"

# ディレクトリが無ければ作成
DATA_DIR.mkdir(exist_ok=True)
CARD_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
SLEEVES_DIR.mkdir(parents=True, exist_ok=True)
AVATARS_DIR.mkdir(parents=True, exist_ok=True)

# 通常裏面画像.jpgをstaticディレクトリにコピー
NORMAL_BACK_SRC = BASE_DIR / "通常裏面画像.jpg"
NORMAL_BACK_DST = STATIC_DIR / "通常裏面画像.jpg"
if NORMAL_BACK_SRC.exists():
    shutil.copy(NORMAL_BACK_SRC, NORMAL_BACK_DST)


import os
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://pvwiojdoiheamfhshgvx.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

def get_supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

def load_cards() -> list[dict]:
    """Supabase もしくは cards.json から手動登録カード一覧を読み込む"""
    if not SUPABASE_KEY:
        if not CARDS_PATH.exists():
            return []
        with open(CARDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        url = f"{SUPABASE_URL}/rest/v1/user_cards?select=*&order=id.asc"
        resp = requests.get(url, headers=get_supabase_headers(), timeout=5)
        if resp.status_code == 200:
            raw_cards = resp.json()
            cards = []
            for c in raw_cards:
                cards.append({
                    "id": c["id"],
                    "name": c["name"],
                    "civilization": c.get("civilization"),
                    "card_type": c.get("card_type"),
                    "cost": c.get("cost"),
                    "power": c.get("power"),
                    "text": c.get("text", ""),
                    "race": c.get("race"),
                    "image": c.get("image")
                })
            return cards
        else:
            print(f"Supabase load_cards failed (status={resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"Error loading cards from Supabase: {e}")
    
    # 接続エラー時の最後のローカルフォールバック
    if CARDS_PATH.exists():
        with open(CARDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_cards(cards: list[dict]):
    """Supabase および cards.json に手動登録カード一覧を保存する"""
    global ALL_CARDS, CARD_MAP
    ALL_CARDS = cards
    CARD_MAP = {card["id"]: card for card in ALL_CARDS}
    
    # 常にローカルにも保存して耐障害性を高める
    try:
        with open(CARDS_PATH, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Local cards.json write error: {e}")
        
    if SUPABASE_KEY:
        try:
            # 1. 一旦全削除して同期ズレを防ぐ
            del_url = f"{SUPABASE_URL}/rest/v1/user_cards?id=gt.0"
            requests.delete(del_url, headers=get_supabase_headers(), timeout=5)
            
            # 2. バルクインサート用のデータ整形
            db_cards = []
            for c in cards:
                db_cards.append({
                    "id": c["id"],
                    "name": c["name"],
                    "civilization": c.get("civilization"),
                    "card_type": c.get("card_type"),
                    "cost": c.get("cost"),
                    "power": str(c.get("power")) if c.get("power") is not None else None,
                    "text": c.get("text", ""),
                    "race": c.get("race"),
                    "image": c.get("image")
                })
                
            if db_cards:
                ins_url = f"{SUPABASE_URL}/rest/v1/user_cards"
                resp = requests.post(ins_url, json=db_cards, headers=get_supabase_headers(), timeout=5)
                if resp.status_code not in (200, 201):
                    print(f"Supabase save_cards insert failed (status={resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"Error saving cards to Supabase: {e}")
            
    # ハイブリッド統合インデックスを再ビルド
    rebuild_combined_cards()


def next_card_id(cards: list[dict]) -> int:
    """次のカードIDを自動生成"""
    if not cards:
        return 1
    return max(c["id"] for c in cards) + 1


def load_decks() -> list[dict]:
    """Supabase もしくは decks.json からデッキ一覧を読み込む"""
    raw_decks = []
    from_supabase = False

    if SUPABASE_KEY:
        try:
            url = f"{SUPABASE_URL}/rest/v1/user_decks?select=*&order=id.asc"
            resp = requests.get(url, headers=get_supabase_headers(), timeout=5)
            if resp.status_code == 200:
                raw_decks = resp.json()
                from_supabase = True
            else:
                print(f"Supabase load_decks failed (status={resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"Error loading decks from Supabase: {e}")

    if not from_supabase:
        if not DECKS_PATH.exists():
            return []
        try:
            with open(DECKS_PATH, "r", encoding="utf-8") as f:
                raw_decks = json.load(f)
        except Exception as e:
            print(f"Error loading local decks.json: {e}")
            return []

    # デッキ内の古い手動IDを公式IDへマイグレーション
    decks = []
    migration_needed = False

    for d in raw_decks:
        original_cards = d.get("cards", [])
        new_cards = []
        replaced_any = False

        for cid in original_cards:
            resolved_cid = cid
            try:
                # cid が数値、もしくは数値の文字列の場合に MIGRATION_MAP を参照
                int_cid = int(cid)
                if int_cid in MIGRATION_MAP:
                    resolved_cid = MIGRATION_MAP[int_cid]
                    replaced_any = True
                    migration_needed = True
            except (ValueError, TypeError):
                pass
            new_cards.append(resolved_cid)

        deck_data = {
            "id": d["id"],
            "name": d["name"],
            "owner": d["owner"],
            "cards": new_cards,
            "card_count": len(new_cards),
            "sleeve_type": d.get("sleeve_type", "normal"),
            "sleeve_image": d.get("sleeve_image"),
            "created_at": d.get("created_at")
        }
        decks.append(deck_data)

        if replaced_any:
            print(f"Migrated deck '{d['name']}' (ID: {d['id']}, Owner: {d['owner']}): Replaced manual card IDs with official string IDs.")

    # マイグレーションが行われた場合は即時保存
    if migration_needed:
        print("Saving migrated decks back to DB/file...")
        try:
            save_decks(decks)
        except Exception as e:
            print(f"Error saving migrated decks: {e}")

    return decks



def save_decks(decks: list[dict]):
    """Supabase および decks.json にデッキ一覧を保存する"""
    try:
        with open(DECKS_PATH, "w", encoding="utf-8") as f:
            json.dump(decks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Local decks.json write error: {e}")
        
    if SUPABASE_KEY:
        try:
            # 1. 一旦全削除して同期ズレを防ぐ
            del_url = f"{SUPABASE_URL}/rest/v1/user_decks?id=gt.0"
            requests.delete(del_url, headers=get_supabase_headers(), timeout=5)
            
            # 2. バルクインサート用のデータ整形
            db_decks = []
            for d in decks:
                db_decks.append({
                    "id": d["id"],
                    "name": d["name"],
                    "owner": d["owner"],
                    "cards": d["cards"],
                    "card_count": d["card_count"],
                    "sleeve_type": d.get("sleeve_type", "normal"),
                    "sleeve_image": d.get("sleeve_image"),
                    "created_at": d.get("created_at")
                })
                
            if db_decks:
                ins_url = f"{SUPABASE_URL}/rest/v1/user_decks"
                resp = requests.post(ins_url, json=db_decks, headers=get_supabase_headers(), timeout=5)
                if resp.status_code not in (200, 201):
                    print(f"Supabase save_decks insert failed (status={resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"Error saving decks to Supabase: {e}")


def next_deck_id(decks: list[dict]) -> int:
    """次のデッキIDを自動生成"""
    if not decks:
        return 1
    return max(d["id"] for d in decks) + 1


def load_users() -> list[dict]:
    """users.json を読み込む"""
    if not USERS_PATH.exists():
        return []
    with open(USERS_PATH, "r", encoding="utf-8") as f:
        try:
            users = json.load(f)
        except Exception:
            return []
    # デフォルトのプロフィール項目を補填
    updated = False
    for u in users:
        if "avatar" not in u:
            u["avatar"] = "👤"
            updated = True
        if "bio" not in u:
            u["bio"] = ""
            updated = True
        if "email" not in u:
            u["email"] = ""
            updated = True
        if "password" not in u:
            u["password"] = "password123"
            updated = True
    if updated:
        save_users(users)
    return users


def save_users(users: list[dict]):
    """users.json に保存する"""
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def hash_password(password: str) -> str:
    """パスワードをハッシュ化"""
    return hashlib.sha256(password.encode()).hexdigest()


def find_user_by_token(token: str) -> Optional[dict]:
    """トークンからユーザーを検索"""
    users = load_users()
    for u in users:
        if u.get("token") == token:
            return u
    return None


ALL_CARDS: list[dict] = load_cards()
CARD_MAP: dict[int, dict] = {card["id"]: card for card in ALL_CARDS}

# ============================================================
# SQLite カードデータベース (cards_v2.db) オンメモリロード
# ============================================================
import sqlite3

ALL_CARDS_V2: list[dict] = []
CARD_MAP_V2: dict[str, dict] = {}

# ハイブリッド統合インデックス用のグローバル変数
ALL_CARDS_COMBINED: list[dict] = []
CARD_MAP_COMBINED: dict[str | int, dict] = {}
MIGRATION_MAP: dict[int, str] = {}  # 古い手動IDから公式IDへのマイグレーションマップ

def rebuild_combined_cards():
    """
    公式DB (cards_v2.db) とユーザー手動登録 (cards.json) を統合し、高速検索インデックスを再構築する。
    同名カードがある場合、公式データを優先して重複（手動側）を非表示にするマスク処理を自動で行う。
    """
    global ALL_CARDS_COMBINED, CARD_MAP_COMBINED, MIGRATION_MAP
    combined_list = []
    combined_map = {}
    migration_map = {}

    # 1. 公式マスタデータをロード
    for card in ALL_CARDS_V2:
        card_copy = dict(card)
        card_copy["is_official"] = True
        # game.htmlで効果を宣言する際に、text属性から効果を引っ張ってくるためのマッピング
        card_copy["text"] = card_copy.get("ability_text", "")
        combined_list.append(card_copy)
        combined_map[card_copy["card_id"]] = card_copy

    # 2. ユーザー登録カードをロード (公式と重複する同名カードはマスク)
    # 表記揺れ（全角・半角スペース、英数字全角・半角）を考慮した正規化
    def normalize_name(name):
        if not name:
            return ""
        name = name.replace("　", "").replace(" ", "")
        name = name.translate(str.maketrans(
            '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ',
            '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        ))
        return name.lower().strip()

    official_by_norm_name = {}
    for c in ALL_CARDS_V2:
        norm_name = normalize_name(c["card_name"])
        if norm_name not in official_by_norm_name:
            official_by_norm_name[norm_name] = c

    for card in ALL_CARDS:
        card_name = card.get("name", "").strip()
        norm_mname = normalize_name(card_name)

        # 同名カードが公式マスタにある場合はマスク（非表示）
        if norm_mname in official_by_norm_name:
            off_card = official_by_norm_name[norm_mname]
            # 既存デッキが古い手動IDで参照している場合のためにエイリアスを登録
            card_copy = dict(off_card)
            card_copy["is_official"] = True
            card_copy["text"] = card_copy.get("ability_text", "")
            combined_map[card["id"]] = card_copy
            combined_map[str(card["id"])] = card_copy
            # 古い手動IDから公式IDへのマッピングを記録
            migration_map[card["id"]] = off_card["card_id"]
            continue

        # v2 のデータ構造に合わせてフォーマット
        card_copy = {
            "card_id": str(card["id"]),
            "id": card["id"],
            "card_name": card_name,
            "civilization": card.get("civilization"),
            "card_type": card.get("card_type"),
            "cost": card.get("cost"),
            "power": card.get("power"),
            "race": card.get("race"),
            "text": card.get("text", ""),
            "ability_text": card.get("text", ""),
            "image_url": f"/static/cards/{card.get('image')}" if card.get("image") else "/static/通常裏面画像.jpg",
            "is_official": False
        }
        combined_list.append(card_copy)
        combined_map[card["id"]] = card_copy
        combined_map[str(card["id"])] = card_copy

    ALL_CARDS_COMBINED = combined_list
    CARD_MAP_COMBINED = combined_map
    MIGRATION_MAP = migration_map
    print(f"Rebuilt hybrid card database: {len(ALL_CARDS_COMBINED)} cards loaded (Official: {len(ALL_CARDS_V2)}, Manual: {len(ALL_CARDS_COMBINED) - len(ALL_CARDS_V2)})")
    print(f"Migration map created with {len(MIGRATION_MAP)} items.")


def load_cards_v2():
    global ALL_CARDS_V2, CARD_MAP_V2
    
    # 1. Supabase からのロードを試みる (本番用・環境変数設定時)
    if SUPABASE_KEY:
        try:
            print("Loading official master cards from Supabase official_cards...")
            raw_cards = []
            limit = 1000
            offset = 0
            while True:
                url = f"{SUPABASE_URL}/rest/v1/official_cards?select=*&order=id.asc&limit={limit}&offset={offset}"
                resp = requests.get(url, headers=get_supabase_headers(), timeout=15)
                if resp.status_code == 200:
                    chunk = resp.json()
                    if not chunk:
                        break
                    raw_cards.extend(chunk)
                    if len(chunk) < limit:
                        break
                    offset += limit
                else:
                    print(f"Failed to load chunk from Supabase official_cards (status={resp.status_code}): {resp.text}")
                    break
                    
            if raw_cards:
                ALL_CARDS_V2 = []
                for c in raw_cards:
                    ALL_CARDS_V2.append({
                        "card_id": c["id"],
                        "card_name": c["name"],
                        "civilization": c.get("civilization"),
                        "card_type": c.get("card_type"),
                        "cost": c.get("cost"),
                        "power": c.get("power"),
                        "ability_text": c.get("text", ""),
                        "race": c.get("race"),
                        "image_url": c.get("image"),
                        "detail_url": f"https://dm.takaratomy.co.jp/card/detail/?id={c['id']}"
                    })
                CARD_MAP_V2 = {c["card_id"]: c for c in ALL_CARDS_V2}
                print(f"Successfully loaded {len(ALL_CARDS_V2)} cards from Supabase official_cards into memory.")
                rebuild_combined_cards()
                return
            else:
                print("No cards loaded from Supabase official_cards.")
        except Exception as e:
            print(f"Error loading official cards from Supabase: {e}")
            
    # 2. ローカル SQLite (cards_v2.db) からのロード (開発用・フォールバック)
    db_path = BASE_DIR / "cards_v2.db"
    if not db_path.exists():
        print("Warning: cards_v2.db does not exist yet. Please run collect_cards.py script to crawl data.")
        ALL_CARDS_V2 = []
        CARD_MAP_V2 = {}
        rebuild_combined_cards()
        return
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cards")
        rows = cursor.fetchall()
        ALL_CARDS_V2 = [dict(r) for r in rows]
        CARD_MAP_V2 = {c["card_id"]: c for c in ALL_CARDS_V2}
        conn.close()
        print(f"Successfully loaded {len(ALL_CARDS_V2)} cards from local cards_v2.db into memory.")
    except Exception as e:
        print(f"Error loading cards from SQLite: {e}")
        ALL_CARDS_V2 = []
        CARD_MAP_V2 = {}
    
    # 統合インデックスをビルド
    rebuild_combined_cards()

# サーバー起動時に SQLite の情報をキャッシュにロード
load_cards_v2()

# 静的ファイル配信（カード画像用）
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ============================================================
# 定数
# ============================================================

DECK_SIZE = 40  # デッキ枚数
INITIAL_HAND = 5  # 初期手札枚数
INITIAL_SHIELDS = 5  # 初期シールド枚数
MAX_PLAYERS = 2  # 1ルームあたりのプレイヤー数

# ============================================================
# ユーティリティ
# ============================================================


def build_deck() -> list[dict]:
    """カードプールからランダムにデッキを構築する"""
    deck = []
    for _ in range(DECK_SIZE):
        card = random.choice(ALL_CARDS).copy()
        card["uuid"] = str(uuid.uuid4())
        deck.append(card)
    random.shuffle(deck)
    return deck


def build_deck_from_ids(card_ids: list) -> list[dict]:
    """指定されたカードIDリストからデッキを構築する (手動 & 公式)"""
    deck = []
    for cid in card_ids:
        # cid can be int or str. We look it up in CARD_MAP_COMBINED.
        card = CARD_MAP_COMBINED.get(cid)
        if not card:
            # Try converting to int if it's a string representing a number
            try:
                card = CARD_MAP_COMBINED.get(int(cid))
            except (ValueError, TypeError):
                pass
        
        if card:
            card_copy = {}
            # Copy all fields from combined card and map to both old and new schemas
            card_copy["id"] = card.get("id") if card.get("id") is not None else card.get("card_id")
            card_copy["card_id"] = card.get("card_id")
            card_copy["name"] = card.get("card_name")
            card_copy["card_name"] = card.get("card_name")
            card_copy["text"] = card.get("ability_text", "")
            card_copy["ability_text"] = card.get("ability_text", "")
            card_copy["civilization"] = card.get("civilization")
            card_copy["card_type"] = card.get("card_type")
            card_copy["cost"] = card.get("cost")
            card_copy["power"] = card.get("power")
            card_copy["race"] = card.get("race")
            
            # Image mapping
            if card.get("is_official"):
                # Use proxy or direct image url
                card_copy["image"] = f"/api/v2/cards/image/{card.get('card_id')}"
                card_copy["image_url"] = card.get("image_url")
            else:
                # Manual cards
                img_url = card.get("image_url", "")
                if "/static/cards/" in img_url:
                    card_copy["image"] = img_url.replace("/static/cards/", "")
                else:
                    card_copy["image"] = img_url.replace("/static/", "")
                card_copy["image_url"] = card.get("image_url")
                
            card_copy["is_official"] = card.get("is_official", False)
            card_copy["uuid"] = str(uuid.uuid4())
            deck.append(card_copy)
            
    random.shuffle(deck)
    return deck


# ============================================================
# プレイヤー状態
# ============================================================


class PlayerState:
    """1人のプレイヤーのゲーム内状態を管理する"""

    def __init__(self, player_id: str, name: str, deck_card_ids: list[int] = None, sleeve_type: str = 'normal', sleeve_image: Optional[str] = None):
        self.player_id = player_id
        self.name = name
        self.deck_card_ids = deck_card_ids or []  # デッキのカードIDリスト
        self.deck: list[dict] = []
        self.hand: list[dict] = []
        self.shields: list[dict] = []
        self.mana_zone: list[dict] = []
        self.battle_zone: list[dict] = []
        self.graveyard: list[dict] = []
        self.tapped_mana: list[str] = []  # タップ済みマナのuuidリスト
        self.tapped_creatures: list[str] = []  # タップ済みクリーチャーのuuidリスト
        self.can_attack: bool = False
        self.has_charged_mana: bool = False  # 今ターンにマナチャージしたか
        self.sleeve_type = sleeve_type
        self.sleeve_image = sleeve_image

    def setup(self):
        """ゲーム開始時のセットアップ"""
        if self.deck_card_ids:
            self.deck = build_deck_from_ids(self.deck_card_ids)
        else:
            self.deck = build_deck()
        self.hand = [self.deck.pop() for _ in range(INITIAL_HAND)]
        self.shields = [self.deck.pop() for _ in range(INITIAL_SHIELDS)]
        for card in self.shields:
            card["face_up"] = False

    def draw(self, count: int = 1) -> list[dict]:
        """山札からカードを引く"""
        drawn = []
        for _ in range(count):
            if not self.deck:
                return drawn  # デッキ切れ
            drawn.append(self.deck.pop())
        self.hand.extend(drawn)
        return drawn

    def available_mana(self) -> int:
        """使用可能マナ数（アンタップ状態のマナ）"""
        return len(self.mana_zone) - len(self.tapped_mana)

    def total_mana(self) -> int:
        """マナゾーンのカード枚数"""
        return len(self.mana_zone)

    def untap_all(self):
        """ターン開始時に全てアンタップ"""
        self.tapped_mana.clear()
        self.tapped_creatures.clear()
        self.has_charged_mana = False

    def to_dict(self, is_owner: bool = True) -> dict:
        """状態を辞書に変換（相手には手札の中身を隠す）"""
        # シールドの表裏に応じたマスク処理（裏向きシールドは自分にとっても相手にとっても中身を隠す）
        shields_data = []
        for card in self.shields:
            c = card.copy()
            if not c.get("face_up", False):
                # 自分にとっても相手にとっても裏向きシールドは中身を完全に隠す（UUIDのみ含めてドラッグ可能に）
                shields_data.append({"hidden": True, "uuid": c["uuid"], "face_up": False})
            else:
                shields_data.append(c)

        return {
            "player_id": self.player_id,
            "name": self.name,
            "hand": self.hand if is_owner else [{"hidden": True, "uuid": c["uuid"]} for c in self.hand],
            "hand_count": len(self.hand),
            "deck": self.deck if is_owner else [],  # デバッグ用: 自分の山札のみ
            "deck_count": len(self.deck),
            "shields": shields_data,
            "shield_count": len(self.shields),
            "mana_zone": self.mana_zone,
            "mana_available": self.available_mana(),
            "mana_total": self.total_mana(),
            "tapped_mana": self.tapped_mana,
            "battle_zone": self.battle_zone,
            "tapped_creatures": self.tapped_creatures,
            "graveyard": self.graveyard,
            "has_charged_mana": self.has_charged_mana,
            "sleeve_type": self.sleeve_type,
            "sleeve_image": self.sleeve_image,
        }


# ============================================================
# ゲームルーム
# ============================================================


class GameRoom:
    """1つの対戦ルームを管理する"""

    def __init__(self, room_id: str):
        self.room_id = room_id
        self.players: dict[str, PlayerState] = {}
        self.connections: dict[str, WebSocket] = {}
        self.turn_player_id: Optional[str] = None
        self.turn_number: int = 0
        self.phase: str = "waiting"  # waiting / ready / playing / finished
        self.winner: Optional[str] = None
        self.player_order: list[str] = []
        self.log: list[str] = []
        self.current_attack = None

    @property
    def is_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS

    def add_player(
        self, player_id: str, name: str, deck_card_ids: list[int] = None, sleeve_type: str = 'normal', sleeve_image: Optional[str] = None
    ) -> PlayerState:
        """プレイヤーをルームに追加"""
        if self.is_full:
            raise ValueError("ルームが満員です")
        player = PlayerState(player_id, name, deck_card_ids, sleeve_type=sleeve_type, sleeve_image=sleeve_image)
        self.players[player_id] = player
        self.player_order.append(player_id)
        return player

    def get_opponent_id(self, player_id: str) -> Optional[str]:
        """相手プレイヤーのIDを取得"""
        for pid in self.player_order:
            if pid != player_id:
                return pid
        return None

    def _get_break_count(self, card: dict) -> int:
        """カードの効果テキストからブレイク能力を判定して枚数を返す"""
        ability_text = card.get("ability_text") or card.get("text") or ""

        # ワールド・ブレイカー、G・ブレイカー、ドラゴン・ワールド・ブレイカー (全ブレイク)
        if any(x in ability_text for x in ["ワールド・ブレイカー", "G・ブレイカー", "ドラゴン・ワールド・ブレイカー"]):
            return 99

        # Q・ブレイカー (4枚)
        if "Q・ブレイカー" in ability_text or "Q・" in ability_text:
            return 4

        # T・ブレイカー (3枚)
        if any(x in ability_text for x in ["T・ブレイカー", "マスター・T・ブレイカー", "ドラゴン・T・ブレイカー"]):
            return 3

        # W・ブレイカー (2枚)
        if any(x in ability_text for x in ["W・ブレイカー", "Ｗ・ブレイカー", "Wダブル・ブレイカー", "マスター・W・ブレイカー", "ドラゴン・W・ブレイカー"]):
            return 2

        # パワード・ブレイカー (パワー6000ごとに+1枚)
        if "パワード・ブレイカー" in ability_text:
            power_val = 0
            p = card.get("power", 0)
            if p is not None:
                if isinstance(p, int):
                    power_val = p
                elif isinstance(p, str):
                    import re
                    m = re.search(r'\d+', p)
                    if m:
                        power_val = int(m.group(0))
            return max(1, 1 + power_val // 6000)

        return 1

    def _has_shield_trigger(self, card: dict) -> bool:
        """カードがシールドトリガー能力（または関連能力）を持つか判定する"""
        ability_text = card.get("ability_text") or card.get("text") or ""
        keywords = ["シールド・トリガー", "S・トリガー", "Ｓ・トリガー", "S・バック", "サバキZ", "裁きの紋章"]
        return any(kw in ability_text for kw in keywords)

    def _automate_card_effect(self, player_id: str, card: dict) -> list[str]:
        """出た時などの単純なカード効果を自動で解決する"""
        player = self.players[player_id]
        opponent_id = self.get_opponent_id(player_id)
        opponent = self.players[opponent_id] if opponent_id else None
        
        ability_text = card.get("ability_text") or card.get("text") or ""
        if not ability_text:
            return []
            
        logs = []
        
        # 1. ドロー効果 (カードをN枚引く)
        import re
        draw_match = re.search(r'(?:カードを|山札の上から)?([１２３４５1-5])枚(?:まで)?引く', ability_text)
        if draw_match:
            num_map = {'１': 1, '２': 2, '３': 3, '４': 4, '５': 5, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5}
            num_str = draw_match.group(1)
            num_draw = num_map.get(num_str, 1)
            
            drawn_cards = []
            for _ in range(num_draw):
                if player.deck:
                    c = player.deck.pop()
                    player.hand.append(c)
                    drawn_cards.append(c["name"])
            if drawn_cards:
                logs.append(f"🔮 {card['name']} の効果により、{player.name} はカードを {len(drawn_cards)} 枚引きました")
                
        # 2. マナ加速効果 (山札の上からN枚目をマナゾーンに置く)
        mana_match = re.search(r'山札の上から([１２1-2])枚(?:目)?を(?:、)?マナゾーンに置く', ability_text)
        if mana_match:
            num_map = {'１': 1, '２': 2, '1': 1, '2': 2}
            num_mana = num_map.get(mana_match.group(1), 1)
            
            boosted = []
            for _ in range(num_mana):
                if player.deck:
                    c = player.deck.pop()
                    player.mana_zone.append(c)
                    boosted.append(c["name"])
            if boosted:
                logs.append(f"🔮 {card['name']} の効果により、{player.name} は山札の上から {len(boosted)} 枚をマナゾーンに置きました")
                
        # 3. シールド化効果 (山札の上からN枚目をシールドゾーンに置く / シールド化する)
        shield_match = re.search(r'山札の上から([１1])枚(?:目)?を(?:、)?(?:新しいシールドとして)?シールドゾーンに置く|シールド化する', ability_text)
        if shield_match:
            if player.deck:
                c = player.deck.pop()
                c["face_up"] = False
                player.shields.append(c)
                logs.append(f"🔮 {card['name']} の効果により、{player.name} は山札の上から 1 枚をシールド化しました")
                
        # 4. ハンデス効果 (相手は手札を1枚捨てる)
        discard_match = re.search(r'相手は(?:自身|自分)の手札を([１1])枚(?:選んで)?捨てる|相手の手札を1枚(?:見ないで選び、)?捨てさせる', ability_text)
        if discard_match and opponent and opponent.hand:
            import random
            discarded_card = opponent.hand.pop(random.randint(0, len(opponent.hand) - 1))
            opponent.graveyard.append(discarded_card)
            logs.append(f"🔮 {card['name']} の効果により、{opponent.name} は手札から {discarded_card['name']} を墓地に捨てました")
            
        for log in logs:
            self._add_log(log)
            
        return logs

    def action_stack_card(self, player_id: str, card_uuid: str, target_uuid: str, stack_type: str) -> dict:
        """指定されたカードを、バトルゾーンにある別のカード（target）の上に重ねる（進化）か、下に敷く"""
        current_player = self.players[player_id]
        
        # 1. 重ね先のターゲットカードをバトルゾーンから探す
        target_card = None
        target_zone = None
        target_owner = None
        
        for p in self.players.values():
            target_card = self._find_card(p.battle_zone, target_uuid)
            if target_card:
                target_zone = p.battle_zone
                target_owner = p
                break
                
        if not target_card:
            return {"error": "重ね先のカードがバトルゾーンに見つかりません"}
            
        # 2. 重ねるカードをすべてのゾーンから探し出して取り出す
        card = None
        from_zone_name = ""
        
        for p in self.players.values():
            for z_name, zone_list in [('hand', p.hand), ('battle', p.battle_zone), ('mana', p.mana_zone), ('graveyard', p.graveyard), ('deck', p.deck), ('shields', p.shields)]:
                card = self._find_and_remove(zone_list, card_uuid)
                if card:
                    from_zone_name = z_name
                    # 各種クリーンアップ
                    if z_name == 'mana' and card_uuid in p.tapped_mana:
                        p.tapped_mana.remove(card_uuid)
                    if z_name == 'battle' and card_uuid in p.tapped_creatures:
                        p.tapped_creatures.remove(card_uuid)
                    break
            if card:
                break
                
        if not card:
            return {"error": "重ねるカードが見つかりません"}
            
        # 表裏・非表示状態のクリーンアップ
        card.pop("face_up", None)
        card.pop("hidden", None)
        
        # 3. 重ね処理
        if stack_type == 'top':
            # 上に重ねる（進化）
            # 新しい一番上のカードに、古い一番上のカードとその下層カードをマージする
            old_under = target_card.pop("under_cards", [])
            card["under_cards"] = [target_card] + old_under
            
            # バトルゾーンにおける target_card のインデックスを取得し、そこに card を挿入
            try:
                idx = target_zone.index(target_card)
                target_zone[idx] = card
            except ValueError:
                target_zone.append(card)
                
            self._add_log(f"📁 {current_player.name} が {target_card['name']} の上に {card['name']} を重ねました（進化）")
            
        elif stack_type == 'bottom':
            # 下に敷く
            target_card["under_cards"] = target_card.get("under_cards", []) + [card]
            self._add_log(f"📁 {current_player.name} が {target_card['name']} の下に {card['name']} を敷きました")
            
        else:
            # エラーの場合は元に戻す
            current_player.hand.append(card)
            return {"error": f"無効な重ね合わせタイプです: {stack_type}"}
            
        return {"success": True}

    def action_break_shields(self, player_id: str, card_uuids: list[str], to_zone: str) -> dict:
        """指定されたシールドカードを複数選択してブレイク（移動）する"""
        current_atk = self.current_attack
        self.current_attack = None  # 攻撃解決したのでクリア
        
        if not current_atk:
            return {"error": "無効なシールドブレイク要求です（攻撃中のクリーチャーがいません）"}
            
        defender_id = current_atk.get("attacked_player_id")
        if not defender_id:
            return {"error": "無効なシールドブレイク要求です（防御側プレイヤーが特定できません）"}
            
        defender = self.players[defender_id]
        
        if to_zone == 'hand':
            dst_list = defender.hand
        elif to_zone == 'graveyard':
            dst_list = defender.graveyard
        else:
            return {"error": f"不明な移動先です: {to_zone}"}
            
        # 攻撃側と防御側の両方のバトルゾーンから攻撃クリーチャーを検索する
        attacker_card = None
        for p in self.players.values():
            attacker_card = self._find_card(p.battle_zone, current_atk.get("attacker_uuid"))
            if attacker_card:
                break
            
        broken_cards = []
        for uuid in card_uuids:
            card = self._find_and_remove(defender.shields, uuid)
            if card:
                card.pop("face_up", None)
                card.pop("hidden", None)
                
                # S-トリガー判定
                if to_zone == 'hand' and self._has_shield_trigger(card):
                    card["trigger_prompt"] = True
                    
                dst_list.append(card)
                broken_cards.append(card)
                
        if not broken_cards:
            return {"error": "対象のシールドが見つかりませんでした"}
            
        attacker_name = attacker_card["name"] if attacker_card else "クリーチャー"
        to_name = "手札" if to_zone == 'hand' else "墓地"
        card_names = ", ".join([c["name"] for c in broken_cards])
        self._add_log(f"💥 {attacker_name} の攻撃により、{defender.name} のシールド ({card_names}) がブレイクされ、{to_name} に送られました")
        
        return {"success": True}

    def action_resolve_trigger(self, player_id: str, card_uuid: str, use: bool) -> dict:
        """シールドトリガーの使用・見送りを解決する"""
        player = self.players[player_id]
        card = self._find_card(player.hand, card_uuid)
        if not card:
            return {"error": "カードが手札に見つかりません"}
            
        card.pop("trigger_prompt", None)
        
        if use:
            self._add_log(f"⚡ {player.name} が {card['name']} の S・トリガー/効果 を宣言しました！")
            
            if card.get("card_type") == "creature":
                self._find_and_remove(player.hand, card_uuid)
                player.battle_zone.append(card)
                self._add_log(f"⚔️ {card['name']} がバトルゾーンに出ました")
                self._automate_card_effect(player_id, card)
                
            elif card.get("card_type") == "spell":
                self._find_and_remove(player.hand, card_uuid)
                player.graveyard.append(card)
                self._add_log(f"📜 {card['name']} を唱えて墓地に置きました")
                self._automate_card_effect(player_id, card)
        else:
            self._add_log(f"{player.name} は {card['name']} の S・トリガー/効果 の使用を見送りました")
            
        return {"success": True}

    def start_game(self):
        """ゲーム開始"""
        self.phase = "playing"
        random.shuffle(self.player_order)
        self.turn_player_id = self.player_order[0]
        self.turn_number = 1
        for player in self.players.values():
            player.setup()
        self._add_log("ゲーム開始！")
        self._add_log(f"{self.players[self.turn_player_id].name} の先攻です")

    def next_turn(self):
        """ターンを次のプレイヤーに移す"""
        self.current_attack = None  # ターンが切り替わったら攻撃表示をクリア
        current_idx = self.player_order.index(self.turn_player_id)
        next_idx = (current_idx + 1) % MAX_PLAYERS
        self.turn_player_id = self.player_order[next_idx]
        self.turn_number += 1

        # 新しいターンのプレイヤーのアンタップ＆ドロー
        current_player = self.players[self.turn_player_id]
        current_player.untap_all()

        # 最初のターンはドローなし（先攻1ターン目はturn_numberが1）
        if self.turn_number > 1:
            drawn = current_player.draw(1)
            if not drawn and not current_player.deck:
                # デッキ切れ → 敗北
                opponent_id = self.get_opponent_id(self.turn_player_id)
                self.winner = opponent_id
                self.phase = "finished"
                self._add_log(
                    f"{current_player.name} はデッキが切れました。{self.players[opponent_id].name} の勝利！"
                )
                return

        self._add_log(f"ターン{self.turn_number}: {current_player.name} のターン")

    def _add_log(self, message: str):
        self.log.append(message)
        if len(self.log) > 100:
            self.log = self.log[-50:]

    def get_game_state(self, for_player_id: str) -> dict:
        """特定プレイヤー視点のゲーム状態を返す"""
        opponent_id = self.get_opponent_id(for_player_id)
        return {
            "room_id": self.room_id,
            "phase": self.phase,
            "turn_number": self.turn_number,
            "turn_player_id": self.turn_player_id,
            "is_your_turn": self.turn_player_id == for_player_id,
            "you": self.players[for_player_id].to_dict(is_owner=True),
            "opponent": (
                self.players[opponent_id].to_dict(is_owner=False)
                if opponent_id
                else None
            ),
            "winner": self.winner,
            "log": self.log[-10:],
            "current_attack": self.current_attack,
        }

    # ----------------------------------------------------------
    # ゲームアクション
    # ----------------------------------------------------------

    def action_move_card(self, player_id: str, card_uuid: str, from_zone: str, to_zone: str, position: str = 'top', index: Optional[int] = None, face_up: Optional[bool] = None, allow_trigger: bool = True) -> dict:
        """任意のゾーンから任意のゾーンへカードを直接移動する"""
        current_atk = self.current_attack
        self.current_attack = None  # アクションが起きたら攻撃中表示をクリア
        player = self.players[player_id]
        opponent_id = self.get_opponent_id(player_id)
        opponent = self.players[opponent_id] if opponent_id else None

        # フロントエンドのゾーン名をバックエンドの標準ゾーン名に正規化
        # 自分
        if from_zone == 'my-battle': from_zone = 'battle'
        # 相手
        if from_zone == 'opp-battle': from_zone = 'opp-battle'
        if from_zone == 'opp-mana': from_zone = 'opp-mana'
        if from_zone == 'opp-graveyard': from_zone = 'opp-graveyard'
        if from_zone == 'opp-deck': from_zone = 'opp-deck'

        if to_zone == 'my-battle': to_zone = 'battle'
        if to_zone == 'opp-battle': to_zone = 'opp-battle'
        if to_zone == 'opp-mana': to_zone = 'opp-mana'
        if to_zone == 'opp-graveyard': to_zone = 'opp-graveyard'
        if to_zone == 'opp-deck': to_zone = 'opp-deck'

        # 1. 移動元のリストと対象オーナーの特定
        src_list = None
        src_owner = player # カードの本来の持ち主

        if from_zone == 'hand':
            src_list = player.hand
            src_owner = player
        elif from_zone == 'battle':
            src_list = player.battle_zone
            src_owner = player
        elif from_zone == 'mana':
            src_list = player.mana_zone
            src_owner = player
        elif from_zone == 'graveyard':
            src_list = player.graveyard
            src_owner = player
        elif from_zone == 'deck':
            src_list = player.deck
            src_owner = player
        elif from_zone == 'shields':
            src_list = player.shields
            src_owner = player
        elif from_zone == 'opp-hand' and opponent:
            src_list = opponent.hand
            src_owner = opponent
        elif from_zone == 'opp-battle' and opponent:
            src_list = opponent.battle_zone
            src_owner = opponent
        elif from_zone == 'opp-mana' and opponent:
            src_list = opponent.mana_zone
            src_owner = opponent
        elif from_zone == 'opp-graveyard' and opponent:
            src_list = opponent.graveyard
            src_owner = opponent
        elif from_zone == 'opp-deck' and opponent:
            src_list = opponent.deck
            src_owner = opponent
        elif from_zone == 'opp-shields' and opponent:
            src_list = opponent.shields
            src_owner = opponent
        else:
            return {"error": f"不明な移動元ゾーンです: {from_zone}"}

        # 移動元からカードを探して削除
        card = self._find_and_remove(src_list, card_uuid)
        if not card:
            return {"error": "移動元のゾーンに指定されたカードが見つかりません"}

        # バトルゾーンからカードが離れる場合、下に重ねられていたカードがあればすべて持ち主の墓地へ送る
        if from_zone in ('battle', 'opp-battle') and card.get("under_cards"):
            under_list = card.pop("under_cards", [])
            for uc in under_list:
                src_owner.graveyard.append(uc)
            under_names = ", ".join([c["name"] for c in under_list])
            self._add_log(f"📁 {card['name']} がバトルゾーンを離れたため、下に敷かれていたカード ({under_names}) は墓地へ送られました")

        # 2. 移動先リストの決定（カードの本来の持ち主のゾーンに送るルール）
        dst_player = src_owner
        dst_list = None

        # もし移動先が明示的に対戦相手のゾーンを指している場合はそちらにする
        if to_zone == 'opp-hand' and opponent:
            dst_player = opponent
            to_zone = 'hand'
        elif to_zone == 'opp-battle' and opponent:
            dst_player = opponent
            to_zone = 'battle'
        elif to_zone == 'opp-mana' and opponent:
            dst_player = opponent
            to_zone = 'mana'
        elif to_zone == 'opp-graveyard' and opponent:
            dst_player = opponent
            to_zone = 'graveyard'
        elif to_zone == 'opp-deck' and opponent:
            dst_player = opponent
            to_zone = 'deck'
        elif to_zone == 'opp-shields' and opponent:
            dst_player = opponent
            to_zone = 'shields'

        # 本来の持ち主（または明示されたプレイヤー）のゾーンを選択
        if to_zone == 'hand':
            dst_list = dst_player.hand
        elif to_zone == 'battle':
            dst_list = dst_player.battle_zone
        elif to_zone == 'mana':
            dst_list = dst_player.mana_zone
        elif to_zone == 'graveyard':
            dst_list = dst_player.graveyard
        elif to_zone == 'deck':
            dst_list = dst_player.deck
        elif to_zone == 'shields':
            dst_list = dst_player.shields
        else:
            # エラーの場合は元に戻す
            src_list.append(card)
            return {"error": f"不明な移動先ゾーンです: {to_zone}"}

        # 3. タップ状態や召喚酔い、シールド表裏のクリーンアップ＆設定
        if from_zone == 'mana' and card_uuid in player.tapped_mana:
            player.tapped_mana.remove(card_uuid)
        if from_zone == 'mana' and opponent and card_uuid in opponent.tapped_mana:
            opponent.tapped_mana.remove(card_uuid)

        if from_zone == 'battle' and card_uuid in player.tapped_creatures:
            player.tapped_creatures.remove(card_uuid)
        if from_zone == 'battle' and opponent and card_uuid in opponent.tapped_creatures:
            opponent.tapped_creatures.remove(card_uuid)

        # 召喚酔い解除
        # if to_zone == 'battle':
        #     card["summoning_sickness"] = True
        # else:
        #     card.pop("summoning_sickness", None)

        # シールドの表裏設定
        if to_zone == 'shields':
            if face_up is not None:
                card["face_up"] = face_up
            else:
                card["face_up"] = card.get("face_up", False)
        else:
            card.pop("face_up", None)
            card.pop("hidden", None)  # シールドから他ゾーンへの移動時は裏向き状態を確実にクリーンアップして表向きにする
            
            # S・トリガーの処理
            if to_zone == 'hand' and from_zone in ('shields', 'opp-shields') and allow_trigger and self._has_shield_trigger(card):
                card["trigger_prompt"] = True

        # 4. 移動先にカードを追加
        pos_text = ""
        if to_zone == 'deck':
            # 山札への追加位置の処理
            if position == 'bottom':
                dst_list.insert(0, card)  # リストの先頭（一番下）に挿入
                pos_text = "山札の一番下"
            elif position == 'index' and index is not None:
                # 1-indexed 上からN枚目にインサート
                insert_idx = max(0, min(len(dst_list) - index + 1, len(dst_list)))
                dst_list.insert(insert_idx, card)
                pos_text = f"山札の上から {index} 枚目"
            else:
                dst_list.append(card)  # リストの末尾（一番上）に挿入
                pos_text = "山札の一番上"
        else:
            dst_list.append(card)

        # ログメッセージ
        zone_names = {
            'hand': '手札',
            'battle': 'バトルゾーン',
            'mana': 'マナゾーン',
            'graveyard': '墓地',
            'deck': '山札',
            'shields': 'シールドゾーン'
        }

        from_name = zone_names.get(from_zone, from_zone)
        if from_zone == 'opp-hand': from_name = "相手の手札"
        if from_zone == 'opp-shields': from_name = "相手のシールド"

        to_name = zone_names.get(to_zone, to_zone)
        if to_zone == 'deck':
            to_name = pos_text
        if to_zone == 'shields':
            to_name = f"{'表向き' if card.get('face_up') else '裏向き'}シールド"

        # シールド移動ログ
        self._add_log(f"{player.name} が {card['name']} を {from_name} から {dst_player.name} の {to_name} へ移動しました")

        return {"success": True}

    def action_toggle_tap(self, player_id: str, card_uuid: str, zone: str) -> dict:
        """指定されたカードのタップ/アンタップ状態を手動で切り替える"""
        self.current_attack = None  # アクションが起きたら攻撃中表示をクリア
        player = self.players[player_id]

        # 対象のリストとタップUUIDリストを取得
        tapped_list = None
        target_list = None

        if zone == 'mana':
            tapped_list = player.tapped_mana
            target_list = player.mana_zone
        elif zone == 'battle':
            tapped_list = player.tapped_creatures
            target_list = player.battle_zone
        else:
            return {"error": f"手動タップ非対応のゾーンです: {zone}"}

        card = self._find_card(target_list, card_uuid)
        if not card:
            return {"error": "カードが見つかりません"}

        # タップトグル
        if card_uuid in tapped_list:
            tapped_list.remove(card_uuid)
            self._add_log(f"{player.name} が {card['name']} をアンタップしました")
        else:
            tapped_list.append(card_uuid)
            self._add_log(f"{player.name} が {card['name']} をタップしました")

        return {"success": True}

    def action_declare_effect(self, player_id: str, card_uuid: str, text: str) -> dict:
        """プレイヤーがカードの効果の使用を宣言する"""
        self.current_attack = None  # アクションが起きたら攻撃中表示をクリア
        player = self.players[player_id]

        # すべてのプレイヤーの全ゾーンからカードを探す
        card = None
        for p in self.players.values():
            for zone in (p.hand, p.battle_zone, p.mana_zone, p.graveyard, p.shields):
                card = self._find_card(zone, card_uuid)
                if card:
                    break
            if card:
                break

        if not card:
            return {"error": "効果を宣言するカードが見つかりません"}

        text = text.strip()
        if not text:
            return {"error": "効果宣言のテキストが空です"}

        self._add_log(f"📣 {player.name} が {card['name']} の効果を宣言: 「{text}」")
        return {"success": True}

    def action_charge_mana(self, player_id: str, card_uuid: str) -> dict:
        """手札のカードをマナゾーンに置く（1ターンに1回）"""
        self.current_attack = None  # アクションが起きたら攻撃中表示をクリア
        player = self.players[player_id]

        if self.turn_player_id != player_id:
            return {"error": "あなたのターンではありません"}
        if player.has_charged_mana:
            return {"error": "このターンは既にマナチャージしています"}

        card = self._find_and_remove(player.hand, card_uuid)
        if not card:
            return {"error": "手札にそのカードがありません"}

        player.mana_zone.append(card)
        player.has_charged_mana = True
        self._add_log(f"{player.name} が {card['name']} をマナチャージ")
        return {"success": True}

    def action_summon(self, player_id: str, card_uuid: str) -> dict:
        """クリーチャーなどを召喚・登場させる"""
        self.current_attack = None  # アクションが起きたら攻撃中表示をクリア
        player = self.players[player_id]

        if self.turn_player_id != player_id:
            return {"error": "あなたのターンではありません"}

        card = self._find_card(player.hand, card_uuid)
        if not card:
            return {"error": "手札にそのカードがありません"}
        # if player.available_mana() < card["cost"]:
        #     return {
        #         "error": f"マナが足りません（必要: {card['cost']}, 使用可能: {player.available_mana()}）"
        #     }

        # # マナをタップ
        # self._tap_mana(player, card["cost"])

        # 手札から除去し、バトルゾーンに出す
        self._find_and_remove(player.hand, card_uuid)
        # card["summoning_sickness"] = True  # 召喚酔い
        player.battle_zone.append(card)
        self._add_log(f"{player.name} が {card['name']} を登場させました（コスト{card['cost']}）")
        
        # 自動効果解決
        self._automate_card_effect(player_id, card)
        
        return {"success": True}

    def action_cast_spell(
        self, player_id: str, card_uuid: str, target_uuid: Optional[str] = None
    ) -> dict:
        """呪文を唱える"""
        self.current_attack = None  # アクションが起きたら攻撃中表示をクリア
        player = self.players[player_id]
        opponent_id = self.get_opponent_id(player_id)
        opponent = self.players[opponent_id]

        if self.turn_player_id != player_id:
            return {"error": "あなたのターンではありません"}

        card = self._find_card(player.hand, card_uuid)
        if not card:
            return {"error": "手札にそのカードがありません"}
        if card["card_type"] != "spell":
            return {"error": "呪文カードではありません"}
        # if player.available_mana() < card["cost"]:
        #     return {
        #         "error": f"マナが足りません（必要: {card['cost']}, 使用可能: {player.available_mana()}）"
        #     }

        # # マナをタップ
        # self._tap_mana(player, card["cost"])

        # 手札から除去
        self._find_and_remove(player.hand, card_uuid)

        # 呪文効果の簡易処理
        effect_msg = self._resolve_spell(card, player, opponent, target_uuid)

        # 呪文は使用後墓地へ
        player.graveyard.append(card)
        self._add_log(f"{player.name} が {card['name']} を唱えた。{effect_msg}")
        
        # 自動効果解決
        self._automate_card_effect(player_id, card)
        
        return {"success": True}

    def action_attack_creature(
        self, player_id: str, attacker_uuid: str, target_uuid: str
    ) -> dict:
        """クリーチャーで相手クリーチャーを攻撃"""
        player = self.players[player_id]
        opponent_id = self.get_opponent_id(player_id)
        opponent = self.players[opponent_id]

        if self.turn_player_id != player_id:
            return {"error": "あなたのターンではありません"}

        attacker = self._find_card(player.battle_zone, attacker_uuid)
        if not attacker:
            return {"error": "攻撃クリーチャーが見つかりません"}
        # if attacker.get("summoning_sickness"):
        #     return {"error": "召喚酔いのクリーチャーは攻撃できません"}
        if attacker_uuid in player.tapped_creatures:
            return {"error": "タップ済みのクリーチャーは攻撃できません"}

        target = self._find_card(opponent.battle_zone, target_uuid)
        if not target:
            return {"error": "攻撃対象のクリーチャーが見つかりません"}

        # 攻撃クリーチャーをタップ
        player.tapped_creatures.append(attacker_uuid)

        # バトル処理（パワーを安全に整数にパースして比較）
        def _parse_power(p) -> int:
            if p is None: return 0
            if isinstance(p, int): return p
            if isinstance(p, str):
                import re
                m = re.search(r'\d+', p)
                if m: return int(m.group(0))
            return 0

        atk_power = _parse_power(attacker.get("power", 0))
        tgt_power = _parse_power(target.get("power", 0))

        self._add_log(
            f"{player.name} の {attacker['name']}(P{atk_power}) が {opponent.name} の {target['name']}(P{tgt_power}) を攻撃"
        )

        battle_result = "draw"
        if atk_power > tgt_power:
            battle_result = "attacker_win"
            self._add_log(f"バトル解決: {attacker['name']} の勝利。{target['name']} は破壊される対象になりました")
        elif atk_power < tgt_power:
            battle_result = "target_win"
            self._add_log(f"バトル解決: {target['name']} の勝利。{attacker['name']} は破壊される対象になりました")
        else:
            battle_result = "draw"
            self._add_log(f"バトル解決: 相打ち。両者は破壊される対象になりました")

        self.current_attack = {
            "attacker_uuid": attacker_uuid,
            "target_uuid": target_uuid,
            "target_zone": "battle",
            "attacked_player_id": opponent_id,
            "message": "クリーチャーが攻撃されました！シールドか効果を使ってください。"
        }

        return {
            "success": True,
            "battle_trigger": {
                "attacker": {
                    "uuid": attacker_uuid,
                    "name": attacker["name"],
                    "power": atk_power,
                    "owner_id": player_id
                },
                "target": {
                    "uuid": target_uuid,
                    "name": target["name"],
                    "power": tgt_power,
                    "owner_id": opponent_id
                },
                "result": battle_result
            }
        }

    def action_attack_player(self, player_id: str, attacker_uuid: str) -> dict:
        """クリーチャーで相手プレイヤーを直接攻撃（シールドブレイクまたはダイレクトアタックの宣言）"""
        player = self.players[player_id]
        opponent_id = self.get_opponent_id(player_id)
        opponent = self.players[opponent_id]

        if self.turn_player_id != player_id:
            return {"error": "あなたのターンではありません"}

        attacker = self._find_card(player.battle_zone, attacker_uuid)
        if not attacker:
            return {"error": "攻撃クリーチャーが見つかりません"}
        # if attacker.get("summoning_sickness"):
        #     return {"error": "召喚酔いのクリーチャーは攻撃できません"}
        if attacker_uuid in player.tapped_creatures:
            return {"error": "タップ済みのクリーチャーは攻撃できません"}

        # 攻撃クリーチャーをタップ
        player.tapped_creatures.append(attacker_uuid)

        # ブレイク対象のシールドがあるかチェック
        target_shield_uuid = None
        if opponent.shields:
            # 先頭のシールドを攻撃対象として選択
            target_shield = opponent.shields[0]
            target_shield_uuid = target_shield["uuid"]
            self._add_log(f"💥 {attacker['name']} が {opponent.name} のシールドへ攻撃を宣言！")

            break_count = self._get_break_count(attacker)
            self.current_attack = {
                "attacker_uuid": attacker_uuid,
                "target_uuid": target_shield_uuid,
                "target_zone": "shields",
                "attacked_player_id": opponent_id,
                "message": "シールドが攻撃されました！シールドか効果を使ってください。",
                "break_count": break_count
            }
        else:
            # シールドがない場合：ダイレクトアタック宣言
            self.current_attack = {
                "attacker_uuid": attacker_uuid,
                "target_uuid": "player",
                "target_zone": "player",
                "attacked_player_id": opponent_id,
                "message": "ダイレクトアタックされました！効果を使って防いでください。"
            }
            self._add_log(f"⚡ {attacker['name']} が {opponent.name} へダイレクトアタックを宣言！")

            # 即時ゲーム終了（勝利確定）
            self.winner = player_id
            self.phase = "finished"

        return {"success": True}

    def action_end_turn(self, player_id: str) -> dict:
        """ターン終了"""
        if self.turn_player_id != player_id:
            return {"error": "あなたのターンではありません"}

        # 召喚酔い解除（バトルゾーンのクリーチャー）
        player = self.players[player_id]
        for creature in player.battle_zone:
            creature["summoning_sickness"] = False

        self._add_log(f"{player.name} がターン終了")
        self.next_turn()
        return {"success": True}

    # ----------------------------------------------------------
    # 内部ヘルパー
    # ----------------------------------------------------------

    @staticmethod
    def _find_card(zone: list[dict], card_uuid: str) -> Optional[dict]:
        for card in zone:
            if card.get("uuid") == card_uuid:
                return card
            under = card.get("under_cards", [])
            found = GameRoom._find_card(under, card_uuid)
            if found:
                return found
        return None

    @staticmethod
    def _find_and_remove(zone: list[dict], card_uuid: str) -> Optional[dict]:
        for i, card in enumerate(zone):
            if card.get("uuid") == card_uuid:
                return zone.pop(i)
            under = card.get("under_cards", [])
            found = GameRoom._find_and_remove(under, card_uuid)
            if found:
                if not under:
                    card.pop("under_cards", None)
                return found
        return None

    @staticmethod
    def _tap_mana(player: PlayerState, cost: int):
        """マナを指定コスト分タップする"""
        untapped = [c for c in player.mana_zone if c["uuid"] not in player.tapped_mana]
        for i in range(min(cost, len(untapped))):
            player.tapped_mana.append(untapped[i]["uuid"])

    def _resolve_spell(
        self,
        card: dict,
        caster: PlayerState,
        opponent: PlayerState,
        target_uuid: Optional[str] = None,
    ) -> str:
        """呪文効果を解決する（簡易版）"""
        name = card["name"]

        # デーモン・ハンド: 相手クリーチャー1体破壊
        if name == "デーモン・ハンド" and target_uuid:
            target = self._find_and_remove(opponent.battle_zone, target_uuid)
            if target:
                opponent.graveyard.append(target)
                return f"{target['name']} を破壊した"

        # ナチュラル・トラップ: 相手クリーチャー1体をマナゾーンに
        elif name == "ナチュラル・トラップ" and target_uuid:
            target = self._find_and_remove(opponent.battle_zone, target_uuid)
            if target:
                opponent.mana_zone.append(target)
                return f"{target['name']} をマナゾーンに送った"

        # 火炎流星弾: 相手のパワー5000以下のクリーチャーを全て破壊
        elif name == "火炎流星弾":
            destroyed = [c for c in opponent.battle_zone if c.get("power", 0) <= 5000]
            for c in destroyed:
                self._find_and_remove(opponent.battle_zone, c["uuid"])
                opponent.graveyard.append(c)
            return f"{len(destroyed)}体のクリーチャーを破壊した"

        # ホーリー・スパーク: 相手クリーチャーを全てタップ
        elif name == "ホーリー・スパーク":
            for c in opponent.battle_zone:
                if c["uuid"] not in opponent.tapped_creatures:
                    opponent.tapped_creatures.append(c["uuid"])
            return "相手クリーチャーを全てタップした"

        # ダーク・リバース: 墓地からクリーチャー1体を手札に
        elif name == "ダーク・リバース" and target_uuid:
            target = self._find_and_remove(caster.graveyard, target_uuid)
            if target:
                caster.hand.append(target)
                return f"{target['name']} を墓地から手札に戻した"

        # 地獄スクラッパー: パワー合計5000以下まで選んで破壊
        elif name == "地獄スクラッパー":
            total = 0
            destroyed = []
            sorted_creatures = sorted(
                opponent.battle_zone, key=lambda c: c.get("power", 0)
            )
            for c in sorted_creatures:
                if total + c.get("power", 0) <= 5000:
                    total += c.get("power", 0)
                    destroyed.append(c)
            for c in destroyed:
                self._find_and_remove(opponent.battle_zone, c["uuid"])
                opponent.graveyard.append(c)
            return f"{len(destroyed)}体を破壊した（パワー合計{total}）"

        return ""


# ============================================================
# ルーム管理
# ============================================================

rooms: dict[str, GameRoom] = {}

# ============================================================
# 認証API
# ============================================================


class RegisterRequest(BaseModel):
    name: str
    password: str
    email: str = ""


class LoginRequest(BaseModel):
    name: str
    password: str


def validate_credentials(s: str) -> bool:
    """英数字、全角日本語、および許可された演算記号・一部記号のみを許可するバリデーション"""
    allowed_symbols = set("+-*/=%@!\"#$&'<>{}{}[]~")
    for char in s:
        if char.isalnum():
            continue
        if char in allowed_symbols:
            continue
        return False
    return True


@app.post("/register")
async def register(req: RegisterRequest):
    """新規ユーザー登録"""
    name = req.name.strip()
    password = req.password.strip()
    email = req.email.strip() if req.email else ""

    if not name or len(name) < 1 or len(name) > 20:
        return JSONResponse(
            status_code=400,
            content={"error": "プレイヤー名は1～20文字で入力してください"},
        )
    if not password or len(password) < 4 or len(password) > 20:
        return JSONResponse(
            status_code=400,
            content={"error": "パスワードは4～20文字で入力してください"},
        )
    if not email or "@" not in email:
        return JSONResponse(
            status_code=400,
            content={"error": "有効なメールアドレスを入力してください"},
        )

    if not validate_credentials(name):
        return JSONResponse(
            status_code=400,
            content={"error": "プレイヤー名に使用できない特殊文字が含まれています"},
        )

    if not validate_credentials(password):
        return JSONResponse(
            status_code=400,
            content={"error": "パスワードに使用できない特殊文字が含まれています"},
        )

    users = load_users()
    # 名前重複チェック
    if any(u["name"] == name for u in users):
        return JSONResponse(
            status_code=400, content={"error": "そのプレイヤー名は既に使われています"}
        )

    # メールアドレス重複チェック
    if any(u.get("email") == email for u in users):
        return JSONResponse(
            status_code=400, content={"error": "そのメールアドレスは既に登録されています"}
        )

    token = str(uuid.uuid4())
    user = {
        "name": name,
        "password_hash": hash_password(password),
        "password": password,
        "email": email,
        "token": token,
        "created_at": datetime.now().isoformat(),
        "avatar": "👤",
        "bio": "",
    }
    users.append(user)
    save_users(users)
    return JSONResponse(content={"success": True, "token": token, "name": name})


@app.post("/login")
async def login(req: LoginRequest):
    """ログイン"""
    name = req.name.strip()
    password = req.password.strip()
    if not name or not password:
        return JSONResponse(
            status_code=400,
            content={"error": "プレイヤー名とパスワードを入力してください"},
        )

    users = load_users()
    user = None
    for u in users:
        if u["name"] == name:
            user = u
            break

    if not user:
        return JSONResponse(
            status_code=400, content={"error": "プレイヤー名が見つかりません"}
        )
    if user["password_hash"] != hash_password(password):
        return JSONResponse(
            status_code=400, content={"error": "パスワードが正しくありません"}
        )

    # 新しいトークンを発行
    new_token = str(uuid.uuid4())
    user["token"] = new_token
    save_users(users)
    return JSONResponse(content={"success": True, "token": new_token, "name": name, "avatar": user.get("avatar", "👤"), "email": user.get("email", "")})


@app.post("/verify_token")
async def verify_token(body: dict):
    """トークン検証"""
    token = body.get("token", "")
    user = find_user_by_token(token)
    if not user:
        return JSONResponse(status_code=401, content={"error": "無効なトークンです"})
    return JSONResponse(content={"valid": True, "name": user["name"], "avatar": user.get("avatar", "👤"), "email": user.get("email", "")})


class SaveProfileRequest(BaseModel):
    token: str
    name: str
    avatar: str
    bio: str


@app.get("/get_profile/{username}")
async def get_profile(username: str):
    """ユーザーのプロフィールを取得"""
    users = load_users()
    for u in users:
        if u["name"].lower() == username.lower():
            return {
                "name": u["name"],
                "avatar": u.get("avatar", "👤"),
                "bio": u.get("bio", ""),
            }
    raise HTTPException(status_code=404, detail="ユーザーが見つかりません")


@app.post("/save_profile")
async def save_profile(req: SaveProfileRequest):
    """自分のプロフィールを編集・保存"""
    user = find_user_by_token(req.token)
    if not user:
        raise HTTPException(status_code=401, detail="無効なトークンです")

    new_name = req.name.strip()
    new_avatar = req.avatar.strip()
    new_bio = req.bio.strip()

    # バリデーション
    if not new_name or len(new_name) < 1 or len(new_name) > 20:
        raise HTTPException(status_code=400, detail="名前は1～20文字で入力してください")
    if not validate_credentials(new_name):
        raise HTTPException(status_code=400, detail="名前に使用できない特殊文字が含まれています")
    if len(new_bio) > 100:
        raise HTTPException(status_code=400, detail="ひとことは100文字以下で入力してください")

    users = load_users()
    
    # 名前変更がある場合の重複チェックとデッキのオーナー名一括更新
    old_name = user["name"]
    if new_name != old_name:
        if any(u["name"] == new_name for u in users):
            raise HTTPException(status_code=400, detail="その名前は既に使われています")
        
        # 所有するすべてのデッキの owner 名を新しい名前に一括更新
        decks = load_decks()
        updated_any = False
        for d in decks:
            if d.get("owner") == old_name:
                d["owner"] = new_name
                updated_any = True
        if updated_any:
            save_decks(decks)

    # ユーザー情報を更新
    for u in users:
        if u["token"] == req.token:
            u["name"] = new_name
            u["avatar"] = new_avatar
            u["bio"] = new_bio
            break

    save_users(users)
    return {"success": True, "name": new_name}


@app.post("/upload_avatar")
async def upload_avatar(
    token: str = Form(...),
    image: UploadFile = File(...),
):
    """アバター画像をアップロードして設定する"""
    user = find_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="無効なトークンです")

    ext = Path(image.filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        raise HTTPException(
            status_code=400,
            detail="画像形式が不正です（png, jpg, jpeg, gif, webp のみ）"
        )
    
    content = await image.read()
    
    # 1. ファイルサイズ上限の検証 (2MB = 2 * 1024 * 1024 バイト)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="画像サイズは2MB以下にしてください"
        )
    
    # 安全なファイル名を生成
    import re
    safe_username = re.sub(r'[^a-zA-Z0-9]', '', user["name"])
    if not safe_username:
        safe_username = "user"
    filename = f"avatar_{safe_username}_{uuid.uuid4().hex[:8]}{ext}"
    
    # 2. 画像の中央を正方形（正円のベース）に切り抜いてリサイズ保存
    from PIL import Image
    import io
    
    try:
        img = Image.open(io.BytesIO(content))
        width, height = img.size
        min_dim = min(width, height)
        left = (width - min_dim) / 2
        top = (height - min_dim) / 2
        right = (width + min_dim) / 2
        bottom = (height + min_dim) / 2
        
        img_cropped = img.crop((left, top, right, bottom))
        
        # アバター表示に最適なサイズ（512x512）に高品質リサイズ
        img_resized = img_cropped.resize((512, 512), Image.Resampling.LANCZOS)
        
        # 保存
        image_path = AVATARS_DIR / filename
        save_format = img.format if img.format else "PNG"
        img_resized.save(image_path, format=save_format)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="画像処理に失敗しました。破損したファイルか非対応の形式です"
        )
        
    # 前のアバター画像が存在する場合は、ファイルシステムから削除してストレージを節約する
    old_avatar = user.get("avatar", "👤")
    if old_avatar and old_avatar.startswith("image:"):
        old_filename = old_avatar.replace("image:", "")
        old_path = AVATARS_DIR / old_filename
        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass
                
    # データベース（json）更新
    users = load_users()
    for u in users:
        if u["token"] == token:
            u["avatar"] = f"image:{filename}"
            break
    save_users(users)
    
    return {"success": True, "avatar": f"image:{filename}"}


@app.post("/delete_account")
async def delete_account(req: dict):
    """ユーザーのアカウントを削除（退会）"""
    token = req.get("token", "")
    user = find_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="無効なトークンです")

    # ユーザーを削除
    users = load_users()
    users = [u for u in users if u["token"] != token]
    save_users(users)

    # 関連するデッキも削除
    decks = load_decks()
    decks = [d for d in decks if d.get("owner") != user["name"]]
    save_decks(decks)

    # 関連するアバター画像の削除
    old_avatar = user.get("avatar", "👤")
    if old_avatar and old_avatar.startswith("image:"):
        old_filename = old_avatar.replace("image:", "")
        old_path = AVATARS_DIR / old_filename
        if old_path.exists():
            try:
                old_path.unlink()
            except Exception:
                pass

    return {"success": True}


# パスワードリセット用トークンストア（メモリ内）
password_resets: dict[str, dict] = {}


@app.post("/get_personal_info")
async def get_personal_info(req: dict):
    """ユーザーの個人情報（メール、パスワード）を取得（要認証）"""
    token = req.get("token", "")
    user = find_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="無効なトークンです")

    return {
        "name": user["name"],
        "email": user.get("email", ""),
        "password": user.get("password", "password123"),  # プレーンテキスト
    }


@app.post("/save_personal_info")
async def save_personal_info(req: dict):
    """ユーザーの個人情報を保存・更新（要認証）"""
    token = req.get("token", "")
    user = find_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="無効なトークンです")

    email = req.get("email", "").strip()
    password = req.get("password", "").strip()

    if not email or "@" not in email:
        raise HTTPException(
            status_code=400, detail="有効なメールアドレスを入力してください"
        )
    if not password or len(password) < 4 or len(password) > 20:
        raise HTTPException(
            status_code=400, detail="パスワードは4～20文字で入力してください"
        )
    if not validate_credentials(password):
        raise HTTPException(
            status_code=400, detail="パスワードに使用できない特殊文字が含まれています"
        )

    users = load_users()

    # メールアドレス重複チェック
    for u in users:
        if u.get("email") == email and u["token"] != token:
            raise HTTPException(
                status_code=400, detail="そのメールアドレスは既に登録されています"
            )

    # 個人情報を更新
    for u in users:
        if u["token"] == token:
            u["email"] = email
            u["password"] = password
            u["password_hash"] = hash_password(password)
            break

    save_users(users)
    return {"success": True}


@app.post("/forgot_password")
async def forgot_password(req: dict):
    """パスワード再設定URLの発行と模擬メール送信"""
    email = req.get("email", "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="メールアドレスを入力してください")

    users = load_users()
    target_user = None
    for u in users:
        if u.get("email") == email:
            target_user = u
            break

    if not target_user:
        raise HTTPException(
            status_code=404, detail="登録されていないメールアドレスです"
        )

    # 再設定トークン生成
    reset_token = str(uuid.uuid4())
    password_resets[reset_token] = {
        "name": target_user["name"],
        "expires_at": datetime.now() + timedelta(hours=1),
    }

    # 再設定URL
    reset_url = f"http://localhost:8000/reset_password?token={reset_token}"

    # コンソールへの印刷および data/sent_emails.log へのログ出力（メール送信のシミュレート）
    log_msg = (
        f"----------------------------------------\n"
        f"【自動メール送信シミュレータ】\n"
        f"送信先: {email}\n"
        f"件名: パスワードの再設定\n"
        f"本文:\n"
        f"  {target_user['name']} 様、\n"
        f"  パスワードの再設定リクエストを承りました。以下のURLから新しいパスワードを登録してください。\n"
        f"  再設定URL: {reset_url}\n"
        f"  (有効期限: 1時間)\n"
        f"----------------------------------------\n"
      )
    print(log_msg)

    # ログファイル書き出し
    LOG_DIR = BASE_DIR / "data"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / "sent_emails.log", "a", encoding="utf-8") as f:
        f.write(log_msg)

    return {"success": True}


@app.get("/reset_password", response_class=HTMLResponse)
async def serve_reset_password():
    """パスワード再設定画面を配信"""
    html_path = BASE_DIR / "reset_password.html"
    if not html_path.exists():
        # もし作成されていなければエラー
        raise HTTPException(status_code=404, detail="再設定ページが見つかりません")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/api/reset_password")
async def api_reset_password(req: dict):
    """パスワードを再設定（トークンベース）"""
    token = req.get("token", "")
    password = req.get("password", "").strip()

    if not token or token not in password_resets:
        raise HTTPException(status_code=400, detail="無効または期限切れのトークンです")

    reset_info = password_resets[token]
    if datetime.now() > reset_info["expires_at"]:
        password_resets.pop(token, None)
        raise HTTPException(status_code=400, detail="トークンの有効期限が切れています")

    if not password or len(password) < 4 or len(password) > 20:
        raise HTTPException(
            status_code=400, detail="パスワードは4～20文字で入力してください"
        )
    if not validate_credentials(password):
        raise HTTPException(
            status_code=400, detail="パスワードに使用できない特殊文字が含まれています"
        )

    users = load_users()
    user_updated = False
    for u in users:
        if u["name"] == reset_info["name"]:
            u["password"] = password
            u["password_hash"] = hash_password(password)
            user_updated = True
            break

    if not user_updated:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")

    # トークンを無効化
    password_resets.pop(token, None)
    save_users(users)

    return {"success": True}


# ============================================================
# REST API エンドポイント
# ============================================================


class CreateRoomRequest(BaseModel):
    room_id: str
    deck_id: int
    token: str


class CreateRoomResponse(BaseModel):
    room_id: str
    player_id: str


class JoinRoomRequest(BaseModel):
    room_id: str
    deck_id: int
    token: str


class JoinRoomResponse(BaseModel):
    room_id: str
    player_id: str


@app.post("/create_room", response_model=CreateRoomResponse)
async def create_room(req: CreateRoomRequest):
    """新しいルームを作成し、プレイヤー1として参加する"""
    # トークン検証
    user = find_user_by_token(req.token)
    if not user:
        raise HTTPException(status_code=401, detail="ログインしてください")

    room_id = req.room_id.strip()
    if not room_id or len(room_id) < 1 or len(room_id) > 20:
        raise HTTPException(
            status_code=400, detail="ルームIDは1～20文字で入力してください"
        )
    if room_id in rooms:
        raise HTTPException(status_code=400, detail="そのルームIDは既に使われています")

    # デッキ検証
    decks = load_decks()
    deck_data = None
    for d in decks:
        if d["id"] == req.deck_id:
            deck_data = d
            break
    if not deck_data:
        raise HTTPException(status_code=400, detail="デッキが見つかりません")

    room = GameRoom(room_id)
    player_id = str(uuid.uuid4())[:8]
    sleeve_type = deck_data.get("sleeve_type", "normal")
    sleeve_image = deck_data.get("sleeve_image", None)
    room.add_player(player_id, user["name"], deck_data["cards"], sleeve_type=sleeve_type, sleeve_image=sleeve_image)
    rooms[room_id] = room
    return CreateRoomResponse(room_id=room_id, player_id=player_id)


@app.post("/join_room", response_model=JoinRoomResponse)
async def join_room(req: JoinRoomRequest):
    """既存のルームにプレイヤー2として参加する"""
    # トークン検証
    user = find_user_by_token(req.token)
    if not user:
        raise HTTPException(status_code=401, detail="ログインしてください")

    room = rooms.get(req.room_id)
    if not room:
        raise HTTPException(status_code=404, detail="ルームが見つかりません")
    if room.is_full:
        raise HTTPException(status_code=400, detail="ルームが満員です")

    # デッキ検証
    decks = load_decks()
    deck_data = None
    for d in decks:
        if d["id"] == req.deck_id:
            deck_data = d
            break
    if not deck_data:
        raise HTTPException(status_code=400, detail="デッキが見つかりません")

    player_id = str(uuid.uuid4())[:8]
    sleeve_type = deck_data.get("sleeve_type", "normal")
    sleeve_image = deck_data.get("sleeve_image", None)
    room.add_player(player_id, user["name"], deck_data["cards"], sleeve_type=sleeve_type, sleeve_image=sleeve_image)
    return JoinRoomResponse(room_id=req.room_id, player_id=player_id)


@app.get("/rooms")
async def list_rooms():
    """ルーム一覧を取得"""
    users = load_users()
    # ユーザー名からアバターをマッピングするための辞書
    avatar_map = {u["name"]: u.get("avatar", "👤") for u in users}
    return [
        {
            "room_id": room.room_id,
            "players": len(room.players),
            "player_info": [
                {
                    "name": p.name,
                    "avatar": avatar_map.get(p.name, "👤")
                }
                for p in room.players.values()
            ],
            "phase": room.phase,
        }
        for room in rooms.values()
        if room.phase in ("waiting", "ready")
    ]


# ============================================================
# WebSocket エンドポイント
# ============================================================


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    """WebSocket 接続で対戦を行う"""

    # クエリパラメータから player_id を取得
    player_id = websocket.query_params.get("player_id")
    if not player_id:
        await websocket.close(code=4001, reason="player_id が必要です")
        return

    room = rooms.get(room_id)
    if not room:
        await websocket.close(code=4004, reason="ルームが見つかりません")
        return

    if player_id not in room.players:
        await websocket.close(code=4003, reason="このルームのプレイヤーではありません")
        return

    await websocket.accept()
    room.connections[player_id] = websocket

    try:
        # 全員揃ったらゲーム開始
        if len(room.connections) == MAX_PLAYERS and room.phase == "waiting":
            room.start_game()
            await broadcast_game_state(room)

        # 接続時に現在の状態を送信
        await send_game_state(room, player_id)

        # メッセージ受信ループ
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if room.phase == "finished":
                await send_to_player(
                    room,
                    player_id,
                    {
                        "type": "error",
                        "message": "ゲームは既に終了しています",
                    },
                )
                continue

            if room.phase != "playing":
                await send_to_player(
                    room,
                    player_id,
                    {
                        "type": "info",
                        "message": "対戦相手を待っています...",
                    },
                )
                continue

            # アクションのディスパッチ
            result = {}
            if action == "charge_mana":
                result = room.action_charge_mana(player_id, data.get("card_uuid"))
            elif action == "summon":
                result = room.action_summon(player_id, data.get("card_uuid"))
            elif action == "cast_spell":
                result = room.action_cast_spell(
                    player_id, data.get("card_uuid"), data.get("target_uuid")
                )
            elif action == "attack_creature":
                result = room.action_attack_creature(
                    player_id, data.get("attacker_uuid"), data.get("target_uuid")
                )
            elif action == "attack_player":
                result = room.action_attack_player(player_id, data.get("attacker_uuid"))
            elif action == "end_turn":
                result = room.action_end_turn(player_id)
            elif action == "move_card":
                result = room.action_move_card(
                    player_id,
                    data.get("card_uuid"),
                    data.get("from_zone"),
                    data.get("to_zone"),
                    position=data.get("position", "top"),
                    index=data.get("index"),
                    face_up=data.get("face_up"),
                    allow_trigger=data.get("allow_trigger", True)
                )
            elif action == "break_shields":
                result = room.action_break_shields(
                    player_id,
                    data.get("card_uuids", []),
                    data.get("to_zone")
                )
            elif action == "stack_card":
                result = room.action_stack_card(
                    player_id,
                    data.get("card_uuid"),
                    data.get("target_uuid"),
                    data.get("stack_type")
                )
            elif action == "resolve_trigger":
                result = room.action_resolve_trigger(
                    player_id,
                    data.get("card_uuid"),
                    data.get("use")
                )
            elif action == "toggle_tap":
                result = room.action_toggle_tap(
                    player_id,
                    data.get("card_uuid"),
                    data.get("zone")
                )
            elif action == "declare_effect":
                result = room.action_declare_effect(
                    player_id,
                    data.get("card_uuid"),
                    data.get("text")
                )
            else:
                result = {"error": f"不明なアクション: {action}"}

            # エラーの場合は本人にのみ通知
            if "error" in result:
                await send_to_player(
                    room,
                    player_id,
                    {
                        "type": "error",
                        "message": result["error"],
                    },
                )
            else:
                # 成功 → 全員にゲーム状態を配信
                await broadcast_game_state(room)
                if "battle_trigger" in result:
                    trigger_data = result["battle_trigger"]
                    for conn_ws in list(room.connections.values()):
                        try:
                            await conn_ws.send_json({
                                "type": "battle_trigger",
                                "attacker": trigger_data["attacker"],
                                "target": trigger_data["target"],
                                "result": trigger_data["result"]
                            })
                        except Exception:
                            pass

    except WebSocketDisconnect:
        room.connections.pop(player_id, None)
        opponent_id = room.get_opponent_id(player_id)
        if opponent_id and opponent_id in room.connections:
            opp_ws = room.connections.get(opponent_id)
            if opp_ws:
                try:
                    await opp_ws.send_json({
                        "type": "error",
                        "message": "対戦相手が退室したため、強制終了します。",
                    })
                    await opp_ws.close()
                except Exception:
                    pass
        rooms.pop(room_id, None)
    except Exception as e:
        room.connections.pop(player_id, None)
        opponent_id = room.get_opponent_id(player_id)
        if opponent_id and opponent_id in room.connections:
            opp_ws = room.connections.get(opponent_id)
            if opp_ws:
                try:
                    await opp_ws.send_json({
                        "type": "error",
                        "message": "対戦相手との通信エラーが発生したため、強制終了します。",
                    })
                    await opp_ws.close()
                except Exception:
                    pass
        rooms.pop(room_id, None)
        print(f"WebSocket error: {e}")


# ============================================================
# メッセージ送信ヘルパー
# ============================================================


async def send_to_player(room: GameRoom, player_id: str, message: dict):
    """特定プレイヤーにメッセージを送る"""
    ws = room.connections.get(player_id)
    if ws:
        try:
            await ws.send_json(message)
        except Exception:
            room.connections.pop(player_id, None)


async def send_game_state(room: GameRoom, player_id: str):
    """特定プレイヤーにゲーム状態を送る"""
    if room.phase == "waiting":
        await send_to_player(
            room,
            player_id,
            {
                "type": "info",
                "message": "対戦相手を待っています...",
            },
        )
        return
    state = room.get_game_state(player_id)
    await send_to_player(room, player_id, {"type": "game_state", **state})


async def broadcast_game_state(room: GameRoom):
    """全プレイヤーにそれぞれの視点でゲーム状態を配信する"""
    for pid in list(room.connections.keys()):
        state = room.get_game_state(pid)
        await send_to_player(room, pid, {"type": "game_state", **state})


# ============================================================
# HTML配信エンドポイント
# ============================================================


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """ロビー画面を配信"""
    html_path = BASE_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/profile", response_class=HTMLResponse)
async def serve_profile():
    """プロフィール画面を配信"""
    html_path = BASE_DIR / "profile.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/game", response_class=HTMLResponse)
async def serve_game():
    """ゲーム画面を配信"""
    html_path = BASE_DIR / "game.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/card_editor", response_class=HTMLResponse)
async def serve_card_editor():
    """カード追加画面を配信"""
    html_path = BASE_DIR / "card_editor.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/deck_builder", response_class=HTMLResponse)
async def serve_deck_builder():
    """デッキ作成画面を配信"""
    html_path = BASE_DIR / "deck_builder.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ============================================================
# カード追加API
# ============================================================


@app.post("/add_card")
async def add_card(
    name: str = Form(...),
    cost: int = Form(...),
    power: str = Form("0"),
    civilization: str = Form("fire"),
    card_type: str = Form("creature"),
    text: str = Form(""),
    race: str = Form(""),
    image: UploadFile = File(...),
):
    """新しいカードを追加する"""
    global ALL_CARDS, CARD_MAP

    # バリデーション
    if not name or not name.strip():
        return JSONResponse(status_code=400, content={"error": "カード名は必須です"})
    if cost < 0:
        return JSONResponse(
            status_code=400, content={"error": "コストは0以上の数値を指定してください"}
        )
    # パワーバリデーション（数値または 数値/数値 形式）
    import re

    power = power.strip()
    if power and not re.match(r"^\d+(/\d+)*$", power):
        return JSONResponse(
            status_code=400,
            content={"error": "パワーは数値または 1000/3000 形式で入力してください"},
        )
    VALID_CIVS = ("fire", "water", "light", "darkness", "nature", "zero")
    civ_list = [c.strip() for c in civilization.split(",") if c.strip()]
    if not civ_list:
        return JSONResponse(
            status_code=400, content={"error": "文明を少なくとも1つ選択してください"}
        )
    for civ in civ_list:
        if civ not in VALID_CIVS:
            return JSONResponse(
                status_code=400, content={"error": f"不正な文明です: {civ}"}
            )
    # 正規化して保存（重複除去・ソート）
    civilization = ",".join(dict.fromkeys(civ_list))
    VALID_CARD_TYPES = (
        "creature",
        "tamaseed",
        "tamaseed_creature",
        "spell",
        "cross_gear",
        "castle",
        "field",
        "dragheart",
        "aura",
        "twinpact",
    )
    if card_type not in VALID_CARD_TYPES:
        return JSONResponse(
            status_code=400, content={"error": "不正なカードタイプです"}
        )

    # 画像必須チェック
    if not image or not image.filename:
        return JSONResponse(status_code=400, content={"error": "カード画像は必須です"})

    # カードデータ再読み込み（他プロセスの変更を反映）
    ALL_CARDS = load_cards()
    new_id = next_card_id(ALL_CARDS)

    # 画像保存
    image_filename = None
    if image and image.filename:
        ext = Path(image.filename).suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            return JSONResponse(
                status_code=400,
                content={"error": "画像形式が不正です（png, jpg, gif, webp のみ）"},
            )
        image_filename = f"{new_id}{ext}"
        image_path = CARD_IMAGES_DIR / image_filename
        with open(image_path, "wb") as f:
            content = await image.read()
            f.write(content)

    # カードデータ作成
    new_card = {
        "id": new_id,
        "name": name.strip(),
        "civilization": civilization,
        "card_type": card_type,
        "cost": cost,
        "power": (
            power
            if card_type
            in ("creature", "tamaseed_creature", "twinpact", "dragheart", "aura")
            and power
            else None
        ),
        "text": text.strip(),
        "race": race.strip() if race else None,
        "image": image_filename,
    }

    ALL_CARDS.append(new_card)
    CARD_MAP[new_id] = new_card
    save_cards(ALL_CARDS)

    return JSONResponse(content={"success": True, "card": new_card})


@app.get("/api/cards")
async def get_all_cards():
    """登録済みカード一覧を返す"""
    return load_cards()


# ============================================================
# 新カードデータベース (cards_v2.db) API エンドポイント
# ============================================================
from fastapi.responses import StreamingResponse
import requests

@app.get("/api/v2/cards/search")
async def search_cards_v2(
    q: Optional[str] = None,
    civilization: Optional[str] = None,
    card_type: Optional[str] = None,
    cost: Optional[int] = None,
):
    """
    メモリ上のハイブリッド統合カードデータベースから高速にあいまい検索を行う
    """
    results = ALL_CARDS_COMBINED
    
    if q and q.strip():
        search_query = q.strip().lower()
        results = [
            c for c in results
            if search_query in c["card_name"].lower()
        ]
        
    if civilization and civilization.strip():
        civil_query = civilization.strip()
        results = [
            c for c in results
            if c["civilization"] and civil_query in c["civilization"]
        ]
        
    if card_type and card_type.strip():
        type_query = card_type.strip()
        results = [
            c for c in results
            if c["card_type"] and type_query in c["card_type"]
        ]
        
    if cost is not None:
        results = [
            c for c in results
            if c["cost"] == cost
        ]
        
    # パフォーマンスとUIのロード負荷を考慮し、無条件の場合は最大100件までに制限する
    if not q and not civilization and not card_type and cost is None:
        return results[:100]
        
    return results

@app.get("/api/v2/cards/reload")
@app.post("/api/v2/cards/reload")
async def reload_cards_v2_api():
    """
    キャッシュされている公式・手動ハイブリッドデータベースをメモリ上に再ロードする
    """
    try:
        load_cards_v2()
        return {
            "success": True,
            "message": "Database reloaded successfully",
            "official_count": len(ALL_CARDS_V2),
            "combined_count": len(ALL_CARDS_COMBINED)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload: {e}")

@app.get("/api/v2/cards/{card_id}")
async def get_card_v2(card_id: str):
    """
    指定された card_id のカード情報を O(1) で高速に取得する (公式・手動ハイブリッド)
    """
    card = CARD_MAP_COMBINED.get(card_id)
    # 文字列と数値の両方で検索を試みる
    if not card:
        try:
            card = CARD_MAP_COMBINED.get(int(card_id))
        except ValueError:
            pass
            
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card

@app.get("/api/v2/cards/image/{card_id}")
async def proxy_card_image(card_id: str):
    """
    公式の画像URLをプロキシ中継して返す (CORS や Referer ポリシー対策)
    手動登録カードの場合は、ローカルに保存されている静的画像を返す
    """
    card = CARD_MAP_COMBINED.get(card_id)
    if not card:
        try:
            card = CARD_MAP_COMBINED.get(int(card_id))
        except ValueError:
            pass
            
    if not card or not card.get("image_url"):
        raise HTTPException(status_code=404, detail="Card or image URL not found")
        
    image_url = card["image_url"]
    
    # ユーザー登録（手動）カードの場合はローカルから読み出して返却する
    if not card.get("is_official", True):
        if image_url.startswith("/static/"):
            rel_path = image_url[len("/static/"):]
            local_path = STATIC_DIR / rel_path
            if local_path.exists():
                from fastapi.responses import FileResponse
                return FileResponse(str(local_path))
        raise HTTPException(status_code=404, detail="Local manual image not found")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://dm.takaratomy.co.jp/"
    }
    
    try:
        resp = requests.get(image_url, headers=headers, stream=True, timeout=5)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Failed to fetch image from official site")
            
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        
        def image_generator():
            for chunk in resp.iter_content(chunk_size=4096):
                yield chunk
                
        headers_response = {
            "Cache-Control": "public, max-age=86400"
        }
        
        return StreamingResponse(image_generator(), media_type=content_type, headers=headers_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image proxy error: {str(e)}")



@app.post("/api/upload_sleeve")
async def upload_sleeve_api(image: UploadFile = File(...)):
    """カスタムスリーブ画像をアップロードする"""
    ext = Path(image.filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        return JSONResponse(
            status_code=400,
            content={"error": "画像形式が不正です（png, jpg, jpeg, webp のみ）"},
        )
    filename = f"{uuid.uuid4()}{ext}"
    path = SLEEVES_DIR / filename
    with open(path, "wb") as f:
        content = await image.read()
        f.write(content)
    return JSONResponse(content={"success": True, "sleeve_image": filename})


@app.post("/update_card")
async def update_card(
    card_id: int = Form(...),
    name: str = Form(...),
    cost: int = Form(...),
    power: str = Form("0"),
    civilization: str = Form("fire"),
    card_type: str = Form("creature"),
    text: str = Form(""),
    race: str = Form(""),
    image: Optional[UploadFile] = File(None),
):
    """既存のカードを更新する"""
    global ALL_CARDS, CARD_MAP
    import re

    # バリデーション
    if not name or not name.strip():
        return JSONResponse(status_code=400, content={"error": "カード名は必須です"})
    if cost < 0:
        return JSONResponse(
            status_code=400, content={"error": "コストは0以上の数値を指定してください"}
        )
    power = power.strip()
    if power and not re.match(r"^\d+(/\d+)*$", power):
        return JSONResponse(
            status_code=400,
            content={"error": "パワーは数値または 1000/3000 形式で入力してください"},
        )
    VALID_CIVS = ("fire", "water", "light", "darkness", "nature", "zero")
    civ_list = [c.strip() for c in civilization.split(",") if c.strip()]
    if not civ_list:
        return JSONResponse(
            status_code=400, content={"error": "文明を少なくとも1つ選択してください"}
        )
    for civ in civ_list:
        if civ not in VALID_CIVS:
            return JSONResponse(
                status_code=400, content={"error": f"不正な文明です: {civ}"}
            )
    civilization = ",".join(dict.fromkeys(civ_list))
    VALID_CARD_TYPES = (
        "creature",
        "tamaseed",
        "tamaseed_creature",
        "spell",
        "cross_gear",
        "castle",
        "field",
        "dragheart",
        "aura",
        "twinpact",
    )
    if card_type not in VALID_CARD_TYPES:
        return JSONResponse(
            status_code=400, content={"error": "不正なカードタイプです"}
        )

    # カード検索
    ALL_CARDS = load_cards()
    target = None
    for c in ALL_CARDS:
        if c["id"] == card_id:
            target = c
            break
    if not target:
        return JSONResponse(
            status_code=404, content={"error": "カードが見つかりません"}
        )

    # 画像更新（新しい画像がアップロードされた場合）
    if image and image.filename:
        ext = Path(image.filename).suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            return JSONResponse(
                status_code=400, content={"error": "画像形式が不正です"}
            )
        image_filename = f"{card_id}{ext}"
        # 旧画像削除
        if target.get("image"):
            old_path = CARD_IMAGES_DIR / target["image"]
            if old_path.exists():
                old_path.unlink()
        image_path = CARD_IMAGES_DIR / image_filename
        with open(image_path, "wb") as f:
            content = await image.read()
            f.write(content)
        target["image"] = image_filename

    # データ更新
    target["name"] = name.strip()
    target["civilization"] = civilization
    target["card_type"] = card_type
    target["cost"] = cost
    target["power"] = (
        power
        if card_type
        in ("creature", "tamaseed_creature", "twinpact", "dragheart", "aura")
        and power
        else None
    )
    target["text"] = text.strip()
    target["race"] = race.strip() if race else None

    CARD_MAP[card_id] = target
    save_cards(ALL_CARDS)

    return JSONResponse(content={"success": True, "card": target})


# ============================================================
# デッキAPI
# ============================================================


@app.post("/save_deck")
async def save_deck_api(request_body: dict):
    """デッキを保存する"""
    token = request_body.get("token", "")
    user = find_user_by_token(token)
    if not user:
        return JSONResponse(status_code=401, content={"error": "ログインしてください"})

    deck_name = request_body.get("name", "").strip()
    card_ids = request_body.get("cards", [])
    sleeve_type = request_body.get("sleeve_type", "normal")
    sleeve_image = request_body.get("sleeve_image", None)

    # バリデーション
    if not deck_name:
        return JSONResponse(status_code=400, content={"error": "デッキ名は必須です"})
    if not isinstance(card_ids, list):
        return JSONResponse(
            status_code=400, content={"error": "カードリストが不正です"}
        )
    if len(card_ids) < 40:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"デッキには40枚以上のカードが必要です（現在: {len(card_ids)}枚）"
            },
        )

    # カードIDの存在チェック (手動 & 公式)
    for cid in card_ids:
        if cid not in CARD_MAP_COMBINED:
            return JSONResponse(
                status_code=400, content={"error": f"不正なカードIDです: {cid}"}
            )

    # デッキ保存
    decks = load_decks()
    new_deck = {
        "id": next_deck_id(decks),
        "name": deck_name,
        "owner": user["name"],
        "cards": card_ids,
        "card_count": len(card_ids),
        "sleeve_type": sleeve_type,
        "sleeve_image": sleeve_image,
        "created_at": datetime.now().isoformat(),
    }
    decks.append(new_deck)
    save_decks(decks)

    return JSONResponse(content={"success": True, "deck": new_deck})


@app.post("/update_deck")
async def update_deck_api(request_body: dict):
    """デッキを更新する"""
    token = request_body.get("token", "")
    user = find_user_by_token(token)
    if not user:
        return JSONResponse(status_code=401, content={"error": "ログインしてください"})

    deck_id = request_body.get("deck_id")
    deck_name = request_body.get("name", "").strip()
    card_ids = request_body.get("cards", [])

    if not deck_name:
        return JSONResponse(status_code=400, content={"error": "デッキ名は必須です"})
    if not isinstance(card_ids, list) or len(card_ids) < 40:
        return JSONResponse(
            status_code=400, content={"error": "デッキには40枚以上のカードが必要です"}
        )

    # カードIDの存在チェック (手動 & 公式)
    for cid in card_ids:
        if cid not in CARD_MAP_COMBINED:
            return JSONResponse(
                status_code=400, content={"error": f"不正なカードIDです: {cid}"}
            )

    decks = load_decks()
    target = None
    for d in decks:
        if d["id"] == deck_id:
            target = d
            break
    if not target:
        return JSONResponse(
            status_code=404, content={"error": "デッキが見つかりません"}
        )
    if target.get("owner") != user["name"]:
        return JSONResponse(
            status_code=403, content={"error": "他のユーザーのデッキは編集できません"}
        )

    target["name"] = deck_name
    target["cards"] = card_ids
    target["card_count"] = len(card_ids)
    target["sleeve_type"] = request_body.get("sleeve_type", "normal")
    target["sleeve_image"] = request_body.get("sleeve_image", None)
    save_decks(decks)

    return JSONResponse(content={"success": True, "deck": target})


@app.post("/copy_deck")
async def copy_deck_api(request_body: dict):
    """他ユーザーのデッキをコピーする"""
    token = request_body.get("token", "")
    user = find_user_by_token(token)
    if not user:
        return JSONResponse(status_code=401, content={"error": "ログインしてください"})

    deck_id = request_body.get("deck_id")
    decks = load_decks()
    source = None
    for d in decks:
        if d["id"] == deck_id:
            source = d
            break
    if not source:
        return JSONResponse(
            status_code=404, content={"error": "デッキが見つかりません"}
        )

    new_deck = {
        "id": next_deck_id(decks),
        "name": source["name"] + "（コピー）",
        "owner": user["name"],
        "cards": source["cards"][:],
        "card_count": source["card_count"],
        "sleeve_type": source.get("sleeve_type", "normal"),
        "sleeve_image": source.get("sleeve_image", None),
        "created_at": datetime.now().isoformat(),
    }
    decks.append(new_deck)
    save_decks(decks)

    return JSONResponse(content={"success": True, "deck": new_deck})


@app.post("/delete_deck")
async def delete_deck_api(request_body: dict):
    """デッキを削除する"""
    token = request_body.get("token", "")
    user = find_user_by_token(token)
    if not user:
        return JSONResponse(status_code=401, content={"error": "ログインしてください"})

    deck_id = request_body.get("deck_id")
    if deck_id is None:
        return JSONResponse(status_code=400, content={"error": "デッキIDが指定されていません"})

    try:
        deck_id = int(deck_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "不正なデッキIDです"})

    decks = load_decks()
    target = None
    for d in decks:
        if d["id"] == deck_id:
            target = d
            break

    if not target:
        return JSONResponse(
            status_code=404, content={"error": "デッキが見つかりません"}
        )

    if target.get("owner") != user["name"]:
        return JSONResponse(
            status_code=403, content={"error": "他のユーザーのデッキは削除できません"}
        )

    # デッキの削除（decks.jsonから該当要素を取り除くのみ。cards.jsonには一切手を付けない）
    decks = [d for d in decks if d["id"] != deck_id]
    save_decks(decks)

    return JSONResponse(content={"success": True})


@app.get("/api/decks")
async def get_all_decks():
    """登録済みデッキ一覧を返す"""
    return load_decks()


@app.post("/api/my_decks")
async def get_my_decks(body: dict):
    """自分のデッキ一覧を返す"""
    token = body.get("token", "")
    user = find_user_by_token(token)
    if not user:
        return JSONResponse(status_code=401, content={"error": "ログインしてください"})
    decks = load_decks()
    my = [d for d in decks if d.get("owner") == user["name"]]
    return my


@app.post("/api/other_decks")
async def get_other_decks(body: dict):
    """他ユーザーのデッキ一覧を返す"""
    token = body.get("token", "")
    user = find_user_by_token(token)
    if not user:
        return JSONResponse(status_code=401, content={"error": "ログインしてください"})
    decks = load_decks()
    others = [d for d in decks if d.get("owner") != user["name"]]
    return others


# ============================================================
# エントリーポイント
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
