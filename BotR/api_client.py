from __future__ import annotations

import os
from typing import Any, Dict, Optional

import aiohttp

# ==================([github.com](https://github.com/TinhSuperGM/674562623634767-0672/tree/main/BotR))===========
# BotR API Client
# - Use this file from Commands/ and main.py
# - It talks to BotR/backend/app.py
# - All methods are async and always return dicts
# =========================================================

BASE_URL = os.getenv("BOTR_API_URL", "http://127.0.0.1:5000").rstrip("/")
TIMEOUT = int(os.getenv("BOTR_API_TIMEOUT", "15"))

_session: Optional[aiohttp.ClientSession] = None


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        _session = aiohttp.ClientSession(timeout=timeout)
    return _session


async def close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def get(url: str) -> Dict[str, Any]:
    try:
        session = await _get_session()
        async with session.get(f"{BASE_URL}{url}") as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"[API GET ERROR] {url} {resp.status} | {text[:200]}")
                return {}
            data = await resp.json(content_type=None)
            return data if isinstance(data, dict) else {"data": data}
    except Exception as e:
        print(f"[API GET EXCEPTION] {url} | {e}")
        return {}


async def post(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        session = await _get_session()
        async with session.post(f"{BASE_URL}{url}", json=payload) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                print(f"[API POST ERROR] {url} {resp.status} | {text[:200]}")
                return {}
            data = await resp.json(content_type=None)
            return data if isinstance(data, dict) else {"data": data}
    except Exception as e:
        print(f"[API POST EXCEPTION] {url} | {e}")
        return {}


# =========================================================
# Generic data helpers
# =========================================================
async def get_user_data(user_id: str) -> Dict[str, Any]:
    return await get(f"/users/{user_id}")


async def create_user(user_id: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = data or {}
    payload.setdefault("gold", 0)
    payload.setdefault("last_free", 0)
    return await post(f"/users/{user_id}/update", payload)


async def add_gold(user_id: str, amount: int) -> bool:
    res = await post(f"/users/{user_id}/gold/add", {"amount": int(amount)})
    return bool(res.get("success"))


async def remove_gold(user_id: str, amount: int) -> bool:
    res = await post(f"/users/{user_id}/gold/remove", {"amount": int(amount)})
    return bool(res.get("success"))


async def get_inventory(user_id: Optional[str] = None) -> Dict[str, Any]:
    if user_id is None:
        return await get("/inventory")
    return await get(f"/inventory/{user_id}")


async def add_item(user_id: str, item: str, amount: int = 1) -> bool:
    res = await post(f"/inventory/{user_id}/item/add", {"item": item, "amount": int(amount)})
    return bool(res.get("success"))


async def remove_item(user_id: str, item: str, amount: int = 1) -> bool:
    res = await post(f"/inventory/{user_id}/item/remove", {"item": item, "amount": int(amount)})
    return bool(res.get("success"))


# =========================================================
# Shared JSON buckets used by loops / sync tasks
# =========================================================
async def get_reward_state() -> Dict[str, Any]:
    return await get("/reward-state")


async def set_reward_state(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/reward-state/update", data)


async def get_top() -> Dict[str, Any]:
    return await get("/top")


async def set_top(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/top/update", data)


async def get_top_state() -> Dict[str, Any]:
    return await get("/top-state")


async def set_top_state(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/top-state/update", data)


async def get_auction() -> Dict[str, Any]:
    return await get("/auction")


async def set_auction(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/auction/update", data)


async def get_auction_channels() -> Dict[str, Any]:
    return await get("/auction-channels")


async def set_auction_channel(channel_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return await post(f"/auction-channels/{channel_id}/update", data)


async def get_waifu() -> Dict[str, Any]:
    return await get("/waifu")


async def set_waifu(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/waifu/update", data)


async def get_couple() -> Dict[str, Any]:
    return await get("/couple")


async def set_couple(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/couple/update", data)


async def get_team() -> Dict[str, Any]:
    return await get("/team")


async def set_team(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/team/update", data)


async def get_code() -> Dict[str, Any]:
    return await get("/code")


async def set_code(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/code/update", data)


async def get_used_code() -> Dict[str, Any]:
    return await get("/used-code")


async def set_used_code(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/used-code/update", data)


async def get_cooldown() -> Dict[str, Any]:
    return await get("/cooldown")


async def set_cooldown(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/cooldown/update", data)


async def get_phe_duyet_channels() -> Dict[str, Any]:
    return await get("/phe-duyet-channels")


async def set_phe_duyet_channels(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/phe-duyet-channels/update", data)


async def get_reaction_record() -> Dict[str, Any]:
    return await get("/reaction-record")


async def set_reaction_record(data: Dict[str, Any]) -> Dict[str, Any]:
    return await post("/reaction-record/update", data)


# =========================================================
# Convenience wrappers for generic data files
# =========================================================
async def get_data(name: str) -> Dict[str, Any]:
    return await get(f"/data/{name}")


async def set_data(name: str, data: Any) -> Dict[str, Any]:
    return await post(f"/data/{name}/update", {"data": data})


if __name__ == "__main__":
    # Simple smoke test when run directly
    import asyncio

    async def _main() -> None:
        print("=== API CLIENT FUNCTIONS ===")
        print([name for name in globals().keys() if not name.startswith("__")])
        print("health:", await get("/health"))
        await close_session()

    asyncio.run(_main())
