from __future__ import annotations

import asyncio
import inspect
import random
from typing import Any, Dict, Optional

# --- imports tương thích repo ---
try:
    from Commands.prayer import get_luck
except Exception:
    from BotR.Commands.prayer import get_luck  # type: ignore

try:
    from Data.level import sync_all
except Exception:
    from BotR.Data.level import sync_all  # type: ignore

try:
    import api_client
except Exception:
    import api_client  # type: ignore


# ===== LOCKS =====
_user_locks: Dict[str, asyncio.Lock] = {}
_inventory_lock = asyncio.Lock()


def get_lock(uid: str) -> asyncio.Lock:
    uid = str(uid)
    if uid not in _user_locks:
        _user_locks[uid] = asyncio.Lock()
    return _user_locks[uid]


async def maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def load_inventory(uid: str) -> Dict[str, Any]:
    data = await api_client.get_inventory(uid)
    return data if isinstance(data, dict) else {}


async def save_inventory(uid: str, inv: Dict[str, Any]) -> bool:
    if not isinstance(inv, dict):
        inv = {}
    res = await api_client.post(f"/inventory/{uid}/update", inv)
    return bool(res and res.get("success", True))


async def trigger_sync_all() -> None:
    try:
        if inspect.iscoroutinefunction(sync_all):
            await sync_all()
        else:
            sync_all()
    except Exception:
        pass


# ===== MAIN =====
async def use_logic(user, send, waifu_id=None, item_id=None, qty=1):
    uid = str(user.id)

    try:
        qty = int(qty)
    except Exception:
        return await send("❌ Số lượng không hợp lệ.")

    if qty <= 0:
        return await send("❌ Số lượng phải lớn hơn 0.")

    async with get_lock(uid):
        async with _inventory_lock:
            inv = await load_inventory(uid)

            # đảm bảo structure giống JSON cũ
            if not isinstance(inv, dict):
                inv = {}

            inv.setdefault("waifus", {})
            inv.setdefault("bag", {})
            inv.setdefault("bag_item", {})
            inv.setdefault("default_waifu", None)

            if not isinstance(inv["waifus"], dict):
                inv["waifus"] = {}
            if not isinstance(inv["bag"], dict):
                inv["bag"] = {}
            if not isinstance(inv["bag_item"], dict):
                inv["bag_item"] = {}

            # ===== USE WAIFU =====
            if waifu_id:
                waifu_id = str(waifu_id)

                if waifu_id not in inv["bag"]:
                    return await send(f"❌ Bạn không có waifu `{waifu_id}`.")

                if waifu_id in inv["waifus"]:
                    return await send(f"❌ Waifu `{waifu_id}` đã có.")

                inv["waifus"][waifu_id] = 0
                inv["bag"][waifu_id] -= 1

                if inv["bag"][waifu_id] <= 0:
                    del inv["bag"][waifu_id]

                if not inv["default_waifu"]:
                    inv["default_waifu"] = waifu_id

                ok = await save_inventory(uid, inv)
                if not ok:
                    return await send("❌ Lưu dữ liệu thất bại.")

                await trigger_sync_all()
                return await send(f"✨ Đã mở khóa waifu **{waifu_id}**!")

            # ===== USE ITEM =====
            if item_id:
                item_id = str(item_id).lower()

                if item_id not in inv["bag_item"]:
                    return await send(f"❌ Bạn không có `{item_id}`.")

                if int(inv["bag_item"][item_id]) < qty:
                    return await send(f"❌ Không đủ `{item_id}`.")

                default_w = inv.get("default_waifu")
                if not default_w or default_w not in inv["waifus"]:
                    return await send("❌ Default waifu lỗi.")

                luck = await maybe_await(get_luck(user.id))
                try:
                    luck = int(luck)
                except Exception:
                    luck = 0

                bonus = min(0.5, max(0, (luck - 1) / 100))
                total_point = 0

                if item_id == "soup":
                    total_point = 5 * qty

                elif item_id in ("pizza", "drug"):
                    base_min, base_max = (10, 30) if item_id == "pizza" else (30, 50)

                    for _ in range(qty):
                        r = random.random()
                        r = r + (1 - r) * bonus
                        total_point += int(base_min + (base_max - base_min) * r)

                else:
                    return await send("❌ Item không hợp lệ.")

                inv["waifus"][default_w] = int(inv["waifus"].get(default_w, 0)) + total_point
                inv["bag_item"][item_id] = int(inv["bag_item"][item_id]) - qty

                if inv["bag_item"][item_id] <= 0:
                    del inv["bag_item"][item_id]

                ok = await save_inventory(uid, inv)
                if not ok:
                    return await send("❌ Lưu dữ liệu thất bại.")

                await trigger_sync_all()
                return await send(
                    f"✅ Dùng **{qty} {item_id}** → **{default_w}** +{total_point} ❤️"
                )

            return await send("❌ Bạn phải nhập waifu_id hoặc item_id.")


print("Loaded use has success (API)")
