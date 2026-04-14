import random
import asyncio

from Commands.prayer import get_luck
from Data.level import sync_all

from api_client import get, post  # 🔥 dùng API

# ===== LOCKS =====
_user_locks = {}
_inventory_lock = asyncio.Lock()  # 🔥 giữ nguyên logic lock


def get_lock(uid: str):
    if uid not in _user_locks:
        _user_locks[uid] = asyncio.Lock()
    return _user_locks[uid]


# ===== MAIN =====
async def use_logic(user, send, waifu_id=None, item_id=None, qty=1):
    uid = str(user.id)

    if qty <= 0:
        return await send("❌ Số lượng phải lớn hơn 0.")

    async with get_lock(uid):
        async with _inventory_lock:

            # ===== LOAD INVENTORY TỪ API =====
            inv = await get(f"/inventory/{uid}") or {}

            # đảm bảo structure giống JSON (KHÔNG phá schema)
            inv.setdefault("waifus", {})
            inv.setdefault("bag", {})
            inv.setdefault("bag_item", {})
            inv.setdefault("default_waifu", None)

            # ===== USE WAIFU =====
            if waifu_id:
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

                # ===== SAVE API =====
                await post(f"/inventory/{uid}/update", {
                    "data": inv
                })

                return await send(f"✨ Đã mở khóa waifu **{waifu_id}**!")

            # ===== USE ITEM =====
            if item_id:
                item_id = item_id.lower()

                if item_id not in inv["bag_item"]:
                    return await send(f"❌ Bạn không có `{item_id}`.")

                if inv["bag_item"][item_id] < qty:
                    return await send(f"❌ Không đủ `{item_id}`.")

                default_w = inv.get("default_waifu")

                if not default_w or default_w not in inv["waifus"]:
                    return await send("❌ Default waifu lỗi.")

                luck = get_luck(user.id)
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

                # APPLY
                inv["waifus"][default_w] += total_point
                inv["bag_item"][item_id] -= qty

                if inv["bag_item"][item_id] <= 0:
                    del inv["bag_item"][item_id]

                # ===== SAVE API =====
                await post(f"/inventory/{uid}/update", {
                    "data": inv
                })

                # SYNC SAU
                try:
                    if asyncio.iscoroutinefunction(sync_all):
                        asyncio.create_task(sync_all())
                    else:
                        sync_all()
                except:
                    pass

                return await send(
                    f"✅ Dùng **{qty} {item_id}** → **{default_w}** +{total_point} ❤️"
                )

            return await send("❌ Bạn phải nhập waifu_id hoặc item_id.")


print("Loaded use has success (API)")