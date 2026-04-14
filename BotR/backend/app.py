from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, request

# =========================================================
# BotR Full JSON API
# - Load all JSON files from BotR/Data into memory
# - Expose REST endpoints for the Discord bot client
# - Fix common 405/NoneType issues by always returning JSON
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
BOTR_DIR = BASE_DIR.parent if (BASE_DIR / "Data").exists() is False else BASE_DIR
DATA_DIR = BOTR_DIR / "Data"

if not DATA_DIR.exists():
    # Fallback for running this file outside /BotR
    alt = Path(__file__).resolve().parent / "BotR" / "Data"
    if alt.exists():
        BOTR_DIR = alt.parent
        DATA_DIR = alt

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

DATA_LOCK = threading.RLock()
CACHE: Dict[str, Any] = {}

# Only serve these files by default. Add more if you want them exported.
JSON_FILES = {
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

# Aliases used by your bot logs/client code
ALIASES = {
    "reward-state": "reward_state",
    "top-state": "top_state",
    "auction-channels": "auction_channels",
    "phe-duyet-channels": "phe_duyet_channels",
    "used-code": "used_code",
}


def _resolve_key(name: str) -> str:
    return ALIASES.get(name, name)


def _json_path(key: str) -> Path:
    file_name = JSON_FILES.get(key, f"{key}.json")
    return DATA_DIR / file_name


def _ensure_file(path: Path, default: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=4), encoding="utf-8")


def _read_json_file(path: Path, default: Any) -> Any:
    _ensure_file(path, default)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if data is not None else default
    except Exception:
        return default


def _write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp, path)


def _default_for_key(key: str) -> Any:
    if key in {"users", "inventory", "waifu", "couple", "team", "code", "used_code", "auction", "auction_channels", "level", "cooldown", "reward_state", "top", "top_state", "phe_duyet_channels", "reaction_record", "data_admin"}:
        return {}
    return {}


def load_all_json() -> Dict[str, Any]:
    loaded: Dict[str, Any] = {}
    for key in JSON_FILES:
        loaded[key] = _read_json_file(_json_path(key), _default_for_key(key))
    return loaded


def save_all_json() -> None:
    for key, value in CACHE.items():
        _write_json_file(_json_path(key), value)


def get_store(name: str) -> Any:
    key = _resolve_key(name)
    with DATA_LOCK:
        if key not in CACHE:
            CACHE[key] = _read_json_file(_json_path(key), _default_for_key(key))
        return CACHE[key]


def set_store(name: str, value: Any) -> Any:
    key = _resolve_key(name)
    with DATA_LOCK:
        CACHE[key] = value if value is not None else _default_for_key(key)
        _write_json_file(_json_path(key), CACHE[key])
        return CACHE[key]


def get_user_bucket(user_id: str) -> Dict[str, Any]:
    users = get_store("users")
    if not isinstance(users, dict):
        users = {}
        set_store("users", users)
    uid = str(user_id)
    if uid not in users or not isinstance(users[uid], dict):
        users[uid] = {
            "gold": 0,
            "last_free": 0,
        }
        set_store("users", users)
    return users[uid]


def get_inventory_bucket(user_id: str) -> Dict[str, Any]:
    inventory = get_store("inventory")
    if not isinstance(inventory, dict):
        inventory = {}
        set_store("inventory", inventory)
    uid = str(user_id)
    if uid not in inventory or not isinstance(inventory[uid], dict):
        inventory[uid] = {
            "bag": {},
            "bag_item": {},
        }
        set_store("inventory", inventory)
    return inventory[uid]


def _success(payload: Any, status: int = 200):
    return jsonify(payload), status


def _fail(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


# =========================================================
# Bootstrap: import full json on startup
# =========================================================
with DATA_LOCK:
    CACHE.update(load_all_json())


@app.get("/")
def home():
    return _success(
        {
            "success": True,
            "message": "BotR JSON API is running",
            "loaded": list(CACHE.keys()),
        }
    )


@app.get("/health")
def health():
    return _success({"success": True, "status": "ok", "time": int(time.time())})


# =========================================================
# Generic JSON endpoints
# =========================================================
@app.get("/users")
def api_users():
    return _success(get_store("users") or {})


@app.get("/users/<user_id>")
def api_user(user_id: str):
    return _success(get_user_bucket(user_id))


@app.post("/users/<user_id>/update")
def api_user_update(user_id: str):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    users = get_store("users")
    if not isinstance(users, dict):
        users = {}
    users[str(user_id)] = data
    set_store("users", users)
    return _success({"success": True, "user_id": str(user_id), "data": data})


@app.post("/users/<user_id>/gold/add")
def api_user_gold_add(user_id: str):
    data = request.get_json(silent=True) or {}
    amount = int(data.get("amount", 0))
    if amount < 0:
        return _fail("amount must be >= 0")
    users = get_store("users")
    if not isinstance(users, dict):
        users = {}
    bucket = get_user_bucket(user_id)
    bucket["gold"] = int(bucket.get("gold", 0)) + amount
    users[str(user_id)] = bucket
    set_store("users", users)
    return _success({"success": True, "user_id": str(user_id), "gold": bucket["gold"]})


@app.post("/users/<user_id>/gold/remove")
def api_user_gold_remove(user_id: str):
    data = request.get_json(silent=True) or {}
    amount = int(data.get("amount", 0))
    if amount < 0:
        return _fail("amount must be >= 0")
    users = get_store("users")
    if not isinstance(users, dict):
        users = {}
    bucket = get_user_bucket(user_id)
    current = int(bucket.get("gold", 0))
    if current < amount:
        return _success({"success": False, "reason": "not_enough_gold", "gold": current}, 200)
    bucket["gold"] = current - amount
    users[str(user_id)] = bucket
    set_store("users", users)
    return _success({"success": True, "user_id": str(user_id), "gold": bucket["gold"]})


@app.get("/inventory")
def api_inventory():
    return _success(get_store("inventory") or {})


@app.get("/inventory/<user_id>")
def api_inventory_user(user_id: str):
    return _success(get_inventory_bucket(user_id))


@app.post("/inventory/<user_id>/update")
def api_inventory_update(user_id: str):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    inventory = get_store("inventory")
    if not isinstance(inventory, dict):
        inventory = {}
    inventory[str(user_id)] = data
    set_store("inventory", inventory)
    return _success({"success": True, "user_id": str(user_id), "data": data})


@app.post("/inventory/<user_id>/item/add")
def api_inventory_item_add(user_id: str):
    data = request.get_json(silent=True) or {}
    item = str(data.get("item", "")).strip()
    amount = int(data.get("amount", 1))
    if not item:
        return _fail("item is required")
    if amount <= 0:
        return _fail("amount must be > 0")

    bucket = get_inventory_bucket(user_id)
    bag_item = bucket.setdefault("bag_item", {})
    bag_item[item] = int(bag_item.get(item, 0)) + amount

    inventory = get_store("inventory")
    inventory[str(user_id)] = bucket
    set_store("inventory", inventory)
    return _success({"success": True, "user_id": str(user_id), "item": item, "amount": bag_item[item]})


@app.post("/inventory/<user_id>/item/remove")
def api_inventory_item_remove(user_id: str):
    data = request.get_json(silent=True) or {}
    item = str(data.get("item", "")).strip()
    amount = int(data.get("amount", 1))
    if not item:
        return _fail("item is required")
    if amount <= 0:
        return _fail("amount must be > 0")

    bucket = get_inventory_bucket(user_id)
    bag_item = bucket.setdefault("bag_item", {})
    current = int(bag_item.get(item, 0))
    if current < amount:
        return _success({"success": False, "reason": "not_enough_item", "amount": current}, 200)

    new_amount = current - amount
    if new_amount <= 0:
        bag_item.pop(item, None)
    else:
        bag_item[item] = new_amount

    inventory = get_store("inventory")
    inventory[str(user_id)] = bucket
    set_store("inventory", inventory)
    return _success({"success": True, "user_id": str(user_id), "item": item, "amount": bag_item.get(item, 0)})


@app.get("/reward-state")
def api_reward_state():
    return _success(get_store("reward_state") or {})


@app.post("/reward-state/update")
def api_reward_state_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("reward_state", data)})


@app.get("/top")
def api_top():
    return _success(get_store("top") or {})


@app.post("/top/update")
def api_top_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("top", data)})


@app.get("/top-state")
def api_top_state():
    return _success(get_store("top_state") or {})


@app.post("/top-state/update")
def api_top_state_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("top_state", data)})


@app.get("/auction")
def api_auction():
    return _success(get_store("auction") or {})


@app.post("/auction/update")
def api_auction_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("auction", data)})


@app.get("/auction-channels")
def api_auction_channels():
    return _success(get_store("auction_channels") or {})


@app.get("/auction-channels/<channel_id>")
def api_auction_channel(channel_id: str):
    data = get_store("auction_channels")
    if not isinstance(data, dict):
        data = {}
    return _success(data.get(str(channel_id), {}))


@app.post("/auction-channels/<channel_id>/update")
def api_auction_channel_update(channel_id: str):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    current = get_store("auction_channels")
    if not isinstance(current, dict):
        current = {}
    current[str(channel_id)] = data
    set_store("auction_channels", current)
    return _success({"success": True, "channel_id": str(channel_id), "data": data})


@app.get("/waifu")
def api_waifu():
    return _success(get_store("waifu") or {})


@app.post("/waifu/update")
def api_waifu_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("waifu", data)})


@app.get("/couple")
def api_couple():
    return _success(get_store("couple") or {})


@app.post("/couple/update")
def api_couple_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("couple", data)})


@app.get("/team")
def api_team():
    return _success(get_store("team") or {})


@app.post("/team/update")
def api_team_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("team", data)})


@app.get("/code")
def api_code():
    return _success(get_store("code") or {})


@app.post("/code/update")
def api_code_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("code", data)})


@app.get("/used-code")
def api_used_code():
    return _success(get_store("used_code") or {})


@app.post("/used-code/update")
def api_used_code_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("used_code", data)})


@app.get("/cooldown")
def api_cooldown():
    return _success(get_store("cooldown") or {})


@app.post("/cooldown/update")
def api_cooldown_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("cooldown", data)})


@app.get("/phe-duyet-channels")
def api_phe_duyet_channels():
    return _success(get_store("phe_duyet_channels") or {})


@app.post("/phe-duyet-channels/update")
def api_phe_duyet_channels_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("phe_duyet_channels", data)})


@app.get("/reaction-record")
def api_reaction_record():
    return _success(get_store("reaction_record") or {})


@app.post("/reaction-record/update")
def api_reaction_record_update():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _fail("Invalid JSON body")
    return _success({"success": True, "data": set_store("reaction_record", data)})


@app.get("/data/<name>")
def api_generic_get(name: str):
    key = _resolve_key(name)
    if key not in JSON_FILES:
        # Still serve unknown JSON names if the file exists on disk.
        return _success(_read_json_file(_json_path(key), {}))
    return _success(get_store(key) or {})


@app.post("/data/<name>/update")
def api_generic_update(name: str):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, (dict, list)):
        return _fail("Invalid JSON body")
    return _success({"success": True, "name": name, "data": set_store(name, data)})


@app.post("/import-json")
def api_import_json():
    """
    Reload every JSON file from disk into memory.
    Useful after manual edits in the Data folder.
    """
    with DATA_LOCK:
        CACHE.clear()
        CACHE.update(load_all_json())
    return _success({"success": True, "loaded": list(CACHE.keys())})


@app.post("/save-json")
def api_save_json():
    with DATA_LOCK:
        save_all_json()
    return _success({"success": True})


@app.errorhandler(404)
def not_found(_):
    return _fail("Not found", 404)


@app.errorhandler(405)
def method_not_allowed(_):
    return _fail("Method not allowed", 405)


if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "5000"))
    debug = os.getenv("API_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
