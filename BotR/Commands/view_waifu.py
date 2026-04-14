from __future__ import annotations

from typing import Any, Dict

from api_client import get_waifu, get_inventory, get_data, post


# ===== SAFE CONVERTERS =====
def to_int(value, default=0):
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


# ===== LEVEL =====
def get_level(level_data, user_id, waifu_id):
    try:
        if not isinstance(level_data, dict):
            return 1

        user_lv = level_data.get(str(user_id), {})
        if not isinstance(user_lv, dict):
            return 1

        data = user_lv.get(str(waifu_id))
        if isinstance(data, dict):
            return max(1, to_int(data.get("level", 1), 1))
        if isinstance(data, int):
            return max(1, data)
        return 1
    except Exception:
        return 1


# ===== INVENTORY NORMALIZER =====
def normalize_waifus_field(user_data):
    changed = False

    if not isinstance(user_data, dict):
        return {}, True

    waifus = user_data.get("waifus", {})

    # list -> dict
    if isinstance(waifus, list):
        new_waifus = {}
        for item in waifus:
            if isinstance(item, str):
                new_waifus[str(item)] = 0
            elif isinstance(item, dict):
                w_id = item.get("id") or item.get("waifu_id") or item.get("name")
                if w_id is not None:
                    new_waifus[str(w_id)] = max(
                        0, to_int(item.get("love", item.get("amount", 0)), 0)
                    )
        user_data["waifus"] = new_waifus
        waifus = new_waifus
        changed = True

    elif not isinstance(waifus, dict):
        user_data["waifus"] = {}
        waifus = {}
        changed = True

    # ép key + fix value
    fixed = {}
    for k, v in waifus.items():
        k = str(k)
        if isinstance(v, dict):
            v["love"] = max(0, to_int(v.get("love", v.get("amount", 0)), 0))
            fixed[k] = v
        else:
            fixed[k] = max(0, to_int(v, 0))

    if fixed != waifus:
        user_data["waifus"] = fixed
        waifus = fixed
        changed = True

    # fix default
    default = user_data.get("default_waifu")
    if default is not None and str(default) not in waifus:
        user_data["default_waifu"] = None
        changed = True

    return waifus, changed


# ===== CLEANUP =====
def cleanup_missing_waifu(inventory, user_id, user_data, waifu_id):
    changed = False
    waifus = user_data.get("waifus", {})
    waifu_id = str(waifu_id)

    if isinstance(waifus, dict) and waifu_id in waifus:
        waifus.pop(waifu_id, None)
        changed = True

    if str(user_data.get("default_waifu")) == waifu_id:
        user_data["default_waifu"] = None
        changed = True

    if changed:
        inventory[user_id] = user_data

    return changed


async def save_inventory_user(user_id: str, user_data: Dict[str, Any]):
    return await post(f"/inventory/{user_id}/update", user_data)


# ===== CORE =====
async def view_waifu_logic(user, send, send_embed, waifu_id: str):
    waifu_id = str(waifu_id)

    try:
        user_id = str(user.id)

        # ===== LOAD FROM API =====
        waifu_data = await get_waifu()
        inventory = await get_inventory(user_id)
        level_data = await get_data("level")

        if not isinstance(waifu_data, dict):
            waifu_data = {}

        if not isinstance(inventory, dict):
            inventory = {}

        if user_id not in inventory or not isinstance(inventory.get(user_id), dict):
            return await send("❌ Bạn chưa có waifu nào!")

        user_data = inventory[user_id]

        # ===== NORMALIZE INVENTORY =====
        waifus, changed = normalize_waifus_field(user_data)
        if changed:
            inventory[user_id] = user_data
            await save_inventory_user(user_id, user_data)

        if waifu_id not in waifus:
            return await send("❌ Bạn không sở hữu waifu này!")

        if waifu_id not in waifu_data or not isinstance(waifu_data.get(waifu_id), dict):
            if cleanup_missing_waifu(inventory, user_id, user_data, waifu_id):
                await save_inventory_user(user_id, user_data)
            return await send("❌ Waifu này không tồn tại!")

        waifu = waifu_data[waifu_id]
        waifu_inv = waifus.get(waifu_id, 0)

        name = waifu.get("name") or waifu_id
        rank = waifu.get("rank") or "Unknown"
        bio = waifu.get("Bio") or "Không có tiểu sử."
        image = waifu.get("image") or ""

        if isinstance(waifu_inv, dict):
            love_point = waifu_inv.get("love", waifu_inv.get("amount", 0))
        else:
            love_point = waifu_inv

        love_point = max(0, to_int(love_point, 0))
        level = get_level(level_data, user_id, waifu_id)

        embed_data = {
            "title": " Waifu của bạn ",
            "description": (
                f" Tên waifu: **{name}** (id: `{waifu_id}`)\n"
                f"️ Level: **{level}**\n"
                f"️ Rank: **{rank}** | ❤️ Love: **{love_point}**\n"
                f" Tiểu sử: {bio}"
            ),
            "footer": f"Waifu thuộc sở hữu của {getattr(user, 'name', 'bạn')}",
        }

        if isinstance(image, str) and image.startswith(("http://", "https://")):
            embed_data["image"] = image

        return await send_embed(embed_data)

    except Exception as e:
        print(f"[view_waifu_logic] ERROR: {e}")
        return await send("❌ Đã xảy ra lỗi khi đọc dữ liệu waifu!")


print("Loaded view waifu (API) success")
