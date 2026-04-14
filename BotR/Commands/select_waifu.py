import discord
import json
import os
import tempfile
import asyncio
from typing import Any, Dict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "Data")
INV_FILE = os.path.join(DATA_DIR, "inventory.json")

_inv_lock = asyncio.Lock()


def ensure_storage() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(INV_FILE):
        with open(INV_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)


def _load_no_lock() -> Dict[str, Any]:
    try:
        with open(INV_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def _save_no_lock(inv: Dict[str, Any]) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix="inventory_",
        suffix=".json",
        dir=DATA_DIR
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(inv, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, INV_FILE)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


async def _send_response(interaction: discord.Interaction, content: str, ephemeral: bool = False):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
    except (discord.HTTPException, discord.NotFound):
        try:
            if interaction.channel:
                await interaction.channel.send(content)
        except Exception:
            pass


# ===== HELPER FIX DEFAULT =====
def _fix_default_waifu(user_data: Dict[str, Any]) -> None:
    """
    Nếu default_waifu không còn trong waifus hoặc count <= 0 → reset về None
    """
    default = user_data.get("default_waifu")
    waifus = user_data.get("waifus", {})

    if not default:
        return

    count = waifus.get(default, 0)

    try:
        count = int(count)
    except Exception:
        count = 0

    if count <= 0:
        user_data["default_waifu"] = None


# ===== LOGIC =====
async def select_waifu_logic(interaction, waifu_id: str):
    ensure_storage()

    if not interaction or not interaction.user:
        return

    uid = str(interaction.user.id)

    if not waifu_id or not isinstance(waifu_id, str):
        return await _send_response(
            interaction,
            "❌ Bạn không sở hữu waifu ``!",
            ephemeral=True
        )

    waifu_id = waifu_id.lower().strip()

    error_msg = None

    async with _inv_lock:
        inv = await asyncio.to_thread(_load_no_lock)

        user_data = inv.get(uid)
        if not isinstance(user_data, dict):
            error_msg = f"❌ Bạn không sở hữu waifu `{waifu_id}`!"
        else:
            # đảm bảo structure
            if "waifus" not in user_data or not isinstance(user_data["waifus"], dict):
                user_data["waifus"] = {}

            if "default_waifu" not in user_data:
                user_data["default_waifu"] = None

            # 🔥 FIX: đảm bảo default không bị "treo"
            _fix_default_waifu(user_data)

            waifus = user_data["waifus"]

            if waifu_id not in waifus or int(waifus.get(waifu_id, 0)) <= 0:
                error_msg = f"❌ Bạn không sở hữu waifu `{waifu_id}`!"
            else:
                user_data["default_waifu"] = waifu_id
                inv[uid] = user_data

                try:
                    await asyncio.to_thread(_save_no_lock, inv)
                except Exception:
                    error_msg = "❌ Có lỗi khi lưu dữ liệu!"

    if error_msg:
        return await _send_response(interaction, error_msg, ephemeral=True)

    await _send_response(
        interaction,
        f"✅ Đã chọn **{waifu_id}** làm waifu mặc định!"
    )


# ===== OPTIONAL: AUTO CLEAN (GỌI Ở COMMAND KHÁC) =====
async def cleanup_default_waifu(uid: str):
    """
    Gọi hàm này sau khi SELL / REMOVE để auto clear default nếu cần
    """
    async with _inv_lock:
        inv = await asyncio.to_thread(_load_no_lock)

        user_data = inv.get(uid)
        if not isinstance(user_data, dict):
            return

        _fix_default_waifu(user_data)

        inv[uid] = user_data

        try:
            await asyncio.to_thread(_save_no_lock, inv)
        except Exception:
            pass


# ===== SETUP =====
async def setup(bot):
    pass


print("Loaded select waifu has success")