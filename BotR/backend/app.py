from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, request

# =========================================================
# BotR Backend API
# - Reads/writes JSON in BotR/Data
# - Exposes endpoints for the async Discord bot client
# - Returns JSON on every failure to avoid NoneType crashes
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
BOTR_DIR = BASE_DIR.parent
DATA_DIR = BOTR_DIR / "Data"

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

LOCK = threading.RLock()
CACHE: Dict[str, Any] = {}

# File mapping used by the bot
JSON_FILES: Dict[str, str] = {
    "users": "user.json",
    "inventory": "inventory.json",
    "waifu": "waifu_data.json",
    "couple": "couple.json",
    "team": "team.json",
    "code": "code.json",
    "used_code": "used_code.json",
    "auction": "auction.json",
    "auction_channels": "auction_channels.json",
    "level": "level.json",
    "cooldown": "cooldown.json",
    "reward_state": "reward_state.json",
    "top": "top.json",
    "top_state": "top_state.json",
    "phe_duyet_channels": "phe_duyet_channels.json",
    "reaction_record": "reaction_record.json",
    "data_admin": "data_admin.json",
}

ALIASES: Dict[str, str] = {
    "reward-state": "reward_state",
    "top-state": "top_state",
    "auction-channels": "auction_channels",
    "phe-duyet-channels": "phe_duyet_channels",
    "used-code": "used_code",
}


def resolve_key(name: str) -> str:
    return ALIASES.get(name, name)


def json_path(key: str) -> Path:
    return DATA_DIR / JSON_FILES.get(key, f"{key}.json")


def default_value(key: str) -> Any:
    # Runtime data buckets are all dicts in this project
    return {}


def ensure_file(path: Path, default: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=4), encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    ensure_file(path, default)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return default if data is None else data
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp, path)


def load_all_json() -> Dict[str, Any]:
    loaded: Dict[str, Any] = {}
    for key in JSON_FILES:
        loaded[key] = read_json(json_path(key), default_value(key))
    return loaded


def save_all_json() -> None:
    for key, value in CACHE.items():
        write_json(json_path(key), value)


def get_store(name: str) -> Any:
    key = resolve_key(name)
    with LOCK:
        if key not in CACHE:
            CACHE[key] = read_json(json_path(key), default_value(key))
        return CACHE[key]


def set_store(name: str, value: Any) -> Any:
    key = resolve_key(name)
    with LOCK:
        CACHE[key] = value if value is not None else default_value(key)
        write_json(json_path(key), CACHE[key])
        return CACHE[key]


def get_dict_bucket(store_name: str, bucket_id: str, base: Dict[str, Any]) -> Dict[str, Any]:
    store = get_store(store_name)
    if not isinstance(store, dict):
        store = {}
    bid = str(bucket_id)
    if bid not in store or not isinstance(store[bid], dict):
        store[bid] = base.copy()
        set_store(store_name, store)
    return store[bid]


# Load everything on startup
with LOCK:
    CACHE.update(load_all_json())


# =========================================================
# Helpers
# =========================================================
def success(payload: Any, status: int = 200):
    return jsonify(payload), status


def fail(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


# =========================================================
# Health
# =========================================================
@app.get("/")
def home():
    return success({"success": True, "message": "BotR JSON API is running"})


@app.get("/health")
def health():
    return success({"success": True, "time": int(time.time())})


# =========================================================
# Users
# =========================================================
@app.get("/users")
def api_users():
    users = get_store("users")
    return success(users if isinstance(users, dict) else {})


@app.get("/users/<user_id>")
def api_user(user_id: str):
    users = get_store("users")
    if not isinstance(users, dict):
        users = {}
    uid = str(user_id)
    if uid not in users or not isinstance(users[uid], dict):
        users[uid] = {"gold": 0, "last_free": 0}
        set_store("users", users)
    return success(users[uid])


@app.post("/users/<user_id>/update")
def api_user_update(user_id: str):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    users = get_store("users")
    if not isinstance(users, dict):
        users = {}
    users[str(user_id)] = data
    set_store("users", users)
    return success({"success": True, "user_id": str(user_id), "data": data})


@app.post("/users/<user_id>/gold/add")
def api_user_gold_add(user_id: str):
    data = request.get_json(silent=True) or {}
    amount = int(data.get("amount", 0))
    if amount < 0:
        return fail("amount must be >= 0")

    users = get_store("users")
    if not isinstance(users, dict):
        users = {}

    uid = str(user_id)
    if uid not in users or not isinstance(users[uid], dict):
        users[uid] = {"gold": 0, "last_free": 0}

    users[uid]["gold"] = int(users[uid].get("gold", 0)) + amount
    set_store("users", users)
    return success({"success": True, "user_id": uid, "gold": users[uid]["gold"]})


@app.post("/users/<user_id>/gold/remove")
def api_user_gold_remove(user_id: str):
    data = request.get_json(silent=True) or {}
    amount = int(data.get("amount", 0))
    if amount < 0:
        return fail("amount must be >= 0")

    users = get_store("users")
    if not isinstance(users, dict):
        users = {}

    uid = str(user_id)
    if uid not in users or not isinstance(users[uid], dict):
        users[uid] = {"gold": 0, "last_free": 0}

    current = int(users[uid].get("gold", 0))
    if current < amount:
        return success({"success": False, "reason": "not_enough_gold", "gold": current})

    users[uid]["gold"] = current - amount
    set_store("users", users)
    return success({"success": True, "user_id": uid, "gold": users[uid]["gold"]})


# =========================================================
# Inventory
# =========================================================
@app.get("/inventory")
def api_inventory():
    inv = get_store("inventory")
    return success(inv if isinstance(inv, dict) else {})


@app.get("/inventory/<user_id>")
def api_inventory_user(user_id: str):
    inv = get_store("inventory")
    if not isinstance(inv, dict):
        inv = {}
    uid = str(user_id)
    if uid not in inv or not isinstance(inv[uid], dict):
        inv[uid] = {"bag": {}, "bag_item": {}}
        set_store("inventory", inv)
    return success(inv[uid])


@app.post("/inventory/<user_id>/update")
def api_inventory_update(user_id: str):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    inv = get_store("inventory")
    if not isinstance(inv, dict):
        inv = {}
    inv[str(user_id)] = data
    set_store("inventory", inv)
    return success({"success": True, "user_id": str(user_id), "data": data})


@app.post("/inventory/<user_id>/item/add")
def api_inventory_item_add(user_id: str):
    data = request.get_json(silent=True) or {}
    item = str(data.get("item", "")).strip()
    amount = int(data.get("amount", 1))
    if not item:
        return fail("item is required")
    if amount <= 0:
        return fail("amount must be > 0")

    inv = get_store("inventory")
    if not isinstance(inv, dict):
        inv = {}

    uid = str(user_id)
    if uid not in inv or not isinstance(inv[uid], dict):
        inv[uid] = {"bag": {}, "bag_item": {}}

    bag_item = inv[uid].setdefault("bag_item", {})
    bag_item[item] = int(bag_item.get(item, 0)) + amount
    set_store("inventory", inv)
    return success({"success": True, "user_id": uid, "item": item, "amount": bag_item[item]})


@app.post("/inventory/<user_id>/item/remove")
def api_inventory_item_remove(user_id: str):
    data = request.get_json(silent=True) or {}
    item = str(data.get("item", "")).strip()
    amount = int(data.get("amount", 1))
    if not item:
        return fail("item is required")
    if amount <= 0:
        return fail("amount must be > 0")

    inv = get_store("inventory")
    if not isinstance(inv, dict):
        inv = {}

    uid = str(user_id)
    if uid not in inv or not isinstance(inv[uid], dict):
        inv[uid] = {"bag": {}, "bag_item": {}}

    bag_item = inv[uid].setdefault("bag_item", {})
    current = int(bag_item.get(item, 0))
    if current < amount:
        return success({"success": False, "reason": "not_enough_item", "amount": current})

    new_amount = current - amount
    if new_amount <= 0:
        bag_item.pop(item, None)
    else:
        bag_item[item] = new_amount

    set_store("inventory", inv)
    return success({"success": True, "user_id": uid, "item": item, "amount": bag_item.get(item, 0)})


# =========================================================
# Shared buckets
# =========================================================
@app.get("/reward-state")
def api_reward_state():
    data = get_store("reward_state")
    return success(data if isinstance(data, dict) else {})


@app.post("/reward-state/update")
def api_reward_state_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("reward_state", data)})


@app.get("/top")
def api_top():
    data = get_store("top")
    return success(data if isinstance(data, dict) else {})


@app.post("/top/update")
def api_top_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("top", data)})


@app.get("/top-state")
def api_top_state():
    data = get_store("top_state")
    return success(data if isinstance(data, dict) else {})


@app.post("/top-state/update")
def api_top_state_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("top_state", data)})


@app.get("/auction")
def api_auction():
    data = get_store("auction")
    return success(data if isinstance(data, dict) else {})


@app.post("/auction/update")
def api_auction_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("auction", data)})


@app.get("/auction-channels")
def api_auction_channels():
    data = get_store("auction_channels")
    return success(data if isinstance(data, dict) else {})


@app.get("/auction-channels/<channel_id>")
def api_auction_channel(channel_id: str):
    data = get_store("auction_channels")
    if not isinstance(data, dict):
        data = {}
    return success(data.get(str(channel_id), {}))


@app.post("/auction-channels/<channel_id>/update")
def api_auction_channel_update(channel_id: str):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    current = get_store("auction_channels")
    if not isinstance(current, dict):
        current = {}
    current[str(channel_id)] = data
    set_store("auction_channels", current)
    return success({"success": True, "channel_id": str(channel_id), "data": data})


@app.get("/waifu")
def api_waifu():
    data = get_store("waifu")
    return success(data if isinstance(data, dict) else {})


@app.post("/waifu/update")
def api_waifu_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("waifu", data)})


@app.get("/couple")
def api_couple():
    data = get_store("couple")
    return success(data if isinstance(data, dict) else {})


@app.post("/couple/update")
def api_couple_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("couple", data)})


@app.get("/team")
def api_team():
    data = get_store("team")
    return success(data if isinstance(data, dict) else {})


@app.post("/team/update")
def api_team_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("team", data)})


@app.get("/code")
def api_code():
    data = get_store("code")
    return success(data if isinstance(data, dict) else {})


@app.post("/code/update")
def api_code_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("code", data)})


@app.get("/used-code")
def api_used_code():
    data = get_store("used_code")
    return success(data if isinstance(data, dict) else {})


@app.post("/used-code/update")
def api_used_code_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("used_code", data)})


@app.get("/cooldown")
def api_cooldown():
    data = get_store("cooldown")
    return success(data if isinstance(data, dict) else {})


@app.post("/cooldown/update")
def api_cooldown_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("cooldown", data)})


@app.get("/phe-duyet-channels")
def api_phe_duyet_channels():
    data = get_store("phe_duyet_channels")
    return success(data if isinstance(data, dict) else {})


@app.post("/phe-duyet-channels/update")
def api_phe_duyet_channels_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("phe_duyet_channels", data)})


@app.get("/reaction-record")
def api_reaction_record():
    data = get_store("reaction_record")
    return success(data if isinstance(data, dict) else {})


@app.post("/reaction-record/update")
def api_reaction_record_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return fail("Invalid JSON body")
    return success({"success": True, "data": set_store("reaction_record", data)})


# =========================================================
# Generic access for any JSON bucket
# =========================================================
@app.get("/data/<name>")
def api_generic_get(name: str):
    key = resolve_key(name)
    if key not in JSON_FILES:
        return success(read_json(json_path(key), {}))
    data = get_store(key)
    return success(data if isinstance(data, dict) else {})


@app.post("/data/<name>/update")
def api_generic_update(name: str):
    data = request.get_json(silent=True)
    if not isinstance(data, (dict, list)):
        return fail("Invalid JSON body")
    return success({"success": True, "name": name, "data": set_store(name, data)})


@app.post("/import-json")
def api_import_json():
    with LOCK:
        CACHE.clear()
        CACHE.update(load_all_json())
    return success({"success": True, "loaded": list(CACHE.keys())})


@app.post("/save-json")
def api_save_json():
    with LOCK:
        save_all_json()
    return success({"success": True})


@app.errorhandler(404)
def handle_404(_):
    return fail("Not found", 404)


@app.errorhandler(405)
def handle_405(_):
    return fail("Method not allowed", 405)


if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "5000"))
    debug = os.getenv("API_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
