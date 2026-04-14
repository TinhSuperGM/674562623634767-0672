from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import api_client

# =========================================================
# data_user.py
# - Compatibility wrapper for old code
# - Keeps old function names so Commands/ and main.py
#   do not need to be rewritten all at once
# - All data is now stored through the API
# =========================================================

USER_LOCKS: Dict[str, asyncio.Lock] = {}


def get_lock(user_id: str) -> asyncio.Lock:
    user_id = str(user_id)
    if user_id not in USER_LOCKS:
        USER_LOCKS[user_id] = asyncio.Lock()
    return USER_LOCKS[user_id]


# ===== LOAD / SAVE =====
async def load_data() -> Dict[str, Any]:
    data = await api_client.get("/users")
    return data if isinstance(data, dict) else {}


async def save_data(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if data is None:
        data = await load_data()
    if not isinstance(data, dict):
        data = {}
    return await api_client.set_data("users", data)


# ===== AUTO SAVE (kept for compatibility, no-op if unused) =====
async def auto_save_loop():
    while True:
        await asyncio.sleep(5)
        await api_client.post("/save-json", {})


# ===== GET USER =====
async def get_user(user_id: str) -> Dict[str, Any]:
    data = await load_data()
    user_id = str(user_id)

    if user_id not in data or not isinstance(data[user_id], dict):
        await api_client.create_user(user_id, {"gold": 0, "last_free": 0})
        data = await load_data()

    return data.get(user_id, {"gold": 0, "last_free": 0})


async def get_gold(user_id: str) -> int:
    user = await get_user(user_id)
    return int(user.get("gold", 0))


# ===== ADD GOLD (LOCKED) =====
async def add_gold(user_id: str, amount: int) -> bool:
    lock = get_lock(user_id)
    async with lock:
        return await api_client.add_gold(str(user_id), int(amount))


# ===== REMOVE GOLD (LOCKED) =====
async def remove_gold(user_id: str, amount: int) -> bool:
    lock = get_lock(user_id)
    async with lock:
        return await api_client.remove_gold(str(user_id), int(amount))


# ===== TRANSFER GOLD =====
async def transfer_gold(from_user: str, to_user: str, amount: int) -> bool:
    from_user = str(from_user)
    to_user = str(to_user)
    amount = int(amount)

    first, second = sorted([from_user, to_user])

    async with get_lock(first):
        async with get_lock(second):
            from_gold = await get_gold(from_user)
            if from_gold < amount:
                return False

            ok1 = await api_client.remove_gold(from_user, amount)
            if not ok1:
                return False

            ok2 = await api_client.add_gold(to_user, amount)
            if not ok2:
                await api_client.add_gold(from_user, amount)
                return False

            return True


# ===== SAVE USER =====
async def save_user(user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(user_data, dict):
        user_data = {"gold": 0, "last_free": 0}

    user_id = str(user_id)
    data = await load_data()
    data[user_id] = user_data
    await api_client.set_data("users", data)
    print("Loaded data user has success")
    return user_data


# ===== SYNC HELPERS FOR OLD CODE =====
def load_data_sync() -> Dict[str, Any]:
    raise RuntimeError("load_data_sync() is not supported in API mode. Use 'await load_data()'.")


def get_user_sync(user_id: str) -> Dict[str, Any]:
    raise RuntimeError("get_user_sync() is not supported in API mode. Use 'await get_user()'.")


print("Loaded data_user (API mode)")
