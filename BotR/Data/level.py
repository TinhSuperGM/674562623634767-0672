from __future__ import annotations

import asyncio([github.com](https://github.com/TinhSuperGM/674562623634767-0672/tree/main/BotR/Data))ct, Optional

from BotR import api_client

# =========================================================
# level.py (API mode)
# - Replaces direct JSON file access
# - Keeps old function names for compatibility
# - Uses /inventory and /data/level through the API
# =========================================================

LEVEL_DIV = 100
LEVEL_CACHE: Optional[Dict[str, Dict[str, int]]] = None
LOCK = asyncio.Lock()


def calc_level(love: int) -> int:
    return int(love) // LEVEL_DIV


async def load_inventory() -> Dict[str, Any]:
    data = await api_client.get_inventory()
    return data if isinstance(data, dict) else {}


async def load_level_data() -> Dict[str, Any]:
    data = await api_client.get_data("level")
    return data if isinstance(data, dict) else {}


async def save_level_data(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    return await api_client.set_data("level", data)


async def get_love_from_inv(user_id: str, waifu_id: str) -> int:
    inv = await load_inventory()
    user = inv.get(str(user_id), {})
    waifus = user.get("waifus", {}) if isinstance(user, dict) else {}
    val = waifus.get(str(waifu_id))

    if isinstance(val, int):
        return val
    if isinstance(val, dict):
        return int(val.get("love", 0))
    return 0


async def get_level(user_id: str, waifu_id: str) -> int:
    love = await get_love_from_inv(user_id, waifu_id)
    return calc_level(love)


async def sync_all() -> Dict[str, Dict[str, int]]:
    """
    Rebuild LEVEL_CACHE from current inventory data.
    """
    global LEVEL_CACHE

    async with LOCK:
        inv = await load_inventory()
        new_cache: Dict[str, Dict[str, int]] = {}

        if not isinstance(inv, dict):
            inv = {}

        for user_id, user_info in inv.items():
            if not isinstance(user_info, dict):
                continue

            waifus = user_info.get("waifus", {})
            if not isinstance(waifus, dict):
                waifus = {}

            new_cache[user_id] = {}
            for w_id, w_val in waifus.items():
                if isinstance(w_val, int):
                    love = w_val
                elif isinstance(w_val, dict):
                    love = int(w_val.get("love", 0))
                else:
                    love = 0
                new_cache[user_id][str(w_id)] = calc_level(love)

        LEVEL_CACHE = new_cache
        await save_level_data(LEVEL_CACHE)
        return LEVEL_CACHE


async def get_level_cached(user_id: str, waifu_id: str) -> int:
    global LEVEL_CACHE

    if LEVEL_CACHE is None:
        return await get_level(user_id, waifu_id)

    return int(LEVEL_CACHE.get(str(user_id), {}).get(str(waifu_id), 0))


async def save_all_levels() -> Dict[str, Dict[str, int]]:
    global LEVEL_CACHE

    async with LOCK:
        if LEVEL_CACHE is None:
            return {}
        await save_level_data(LEVEL_CACHE)
        return LEVEL_CACHE


# =========================================================
# Compatibility sync helpers
# =========================================================
# These are intentionally not real sync file I/O.
# They exist only so old imports do not break immediately.

def load_json(path: str):
    raise RuntimeError("load_json() is disabled in API mode. Use await load_inventory() / await load_level_data().")


def save_json(path: str, data: Any):
    raise RuntimeError("save_json() is disabled in API mode. Use await save_level_data(data).")


print("Loaded level (API mode) success")
