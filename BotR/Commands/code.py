from __future__ import annotations

import asyncio
import datetime
import time
from typing import Union

import discord
from discord.ext import commands

import api_client
from Data import data_user

_CODE_LOCK = asyncio.Lock()
_COOLDOWN: dict[str, float] = {}


# ===== UNIVERSAL SEND =====
async def send(ctx: Union[commands.Context, discord.Interaction], msg: str):
    try:
        if isinstance(ctx, discord.Interaction):
            if not ctx.response.is_done():
                await ctx.response.send_message(msg, ephemeral=True)
                return
            return await ctx.followup.send(msg, ephemeral=True)
        return await ctx.send(msg)
    except Exception as e:
        print("[SEND ERROR]", e)
        return None


# ===== FORMAT TIME =====
def format_time(ts):
    if ts is None:
        return "Không có"

    try:
        dt = datetime.datetime.fromtimestamp(float(ts))
    except Exception:
        return "Không có"

    now = datetime.datetime.now()
    diff = dt - now
    if diff.total_seconds() > 0:
        mins = int(diff.total_seconds() // 60)
        return dt.strftime("%d/%m %H:%M") + f" (còn {mins} phút)"
    return dt.strftime("%d/%m %H:%M") + " (đã hết hạn)"


# ===== LOAD CODE MAP =====
async def _load_codes() -> dict:
    data = await api_client.get_code()
    return data if isinstance(data, dict) else {}


async def _load_used_codes() -> dict:
    data = await api_client.get_used_code()
    return data if isinstance(data, dict) else {}


async def _save_codes(data: dict) -> None:
    await api_client.set_code(data if isinstance(data, dict) else {})


async def _save_used_codes(data: dict) -> None:
    await api_client.set_used_code(data if isinstance(data, dict) else {})


# ===== MAIN LOGIC =====
async def code_logic(ctx, code: str):
    user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
    user_id = str(user.id)

    if not code:
        return await send(ctx, "❌ Code không hợp lệ!")

    code_input = str(code).strip()
    code_lower = code_input.lower()

    # ===== COOLDOWN =====
    now = time.time()
    last = _COOLDOWN.get(user_id, 0)
    if now - last < 2:
        return await send(ctx, "⏳ Thg chóa, đừng spam nx!!!")
    _COOLDOWN[user_id] = now

    async with _CODE_LOCK:
        raw_codes = await _load_codes()
        used = await _load_used_codes()

        if not isinstance(raw_codes, dict):
            raw_codes = {}
        if not isinstance(used, dict):
            used = {}

        code_map = {str(k).lower(): k for k in raw_codes.keys()}
        if code_lower not in code_map:
            return await send(ctx, "❌ Code không tồn tại hoặc đã hết hạn!")

        real_code = code_map[code_lower]
        code_data = raw_codes.get(real_code)

        # ===== MIGRATE OLD INT FORMAT =====
        if isinstance(code_data, int):
            code_data = {
                "gold": code_data,
                "used": 0,
                "max_use": None,
                "expires": None,
            }
            raw_codes[real_code] = code_data
            await _save_codes(raw_codes)

        if not isinstance(code_data, dict):
            return await send(ctx, "❌ Code lỗi dữ liệu!")

        # ===== EXPIRE =====
        expires = code_data.get("expires")
        if expires is not None:
            try:
                if time.time() > float(expires):
                    return await send(ctx, "❌ Code đã hết hạn sử dụng!")
            except Exception:
                return await send(ctx, "❌ Code lỗi dữ liệu thời gian!")

        # ===== MAX USE =====
        max_use = code_data.get("max_use")
        used_count = int(code_data.get("used", 0))
        if max_use is not None and used_count >= int(max_use):
            return await send(ctx, "❌ Code đã hết lượt sử dụng!")

        # ===== USER USED =====
        if user_id not in used or not isinstance(used.get(user_id), list):
            used[user_id] = []
        if real_code in used[user_id]:
            return await send(ctx, "❌ Bạn đã dùng code này rồi!")

        # ===== REWARD =====
        gold = int(code_data.get("gold", 0) or 0)
        if gold <= 0:
            return await send(ctx, "❌ Code này không hợp lệ!")

        # ===== GIVE GOLD =====
        ok = await data_user.add_gold(user_id, gold)
        if not ok:
            return await send(ctx, "❌ Không thể cộng gold, thử lại sau!")

        # ===== UPDATE =====
        used[user_id].append(real_code)
        code_data["used"] = used_count + 1
        raw_codes[real_code] = code_data

        await _save_used_codes(used)
        await _save_codes(raw_codes)

        # ===== RESULT =====
        max_use_text = code_data.get("max_use") or "∞"
        expire_text = format_time(expires)
        return await send(
            ctx,
            (
                f"✅ Nhập code thành công!\n"
                f"Code đã dùng: `{real_code}`\n"
                f"Đã cộng thêm {gold} gold\n"
                f"Đã dùng: {code_data['used']}/{max_use_text}\n"
                f"⏰ Hết hạn: {expire_text}"
            ),
        )


class CodeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="code")
    async def code_cmd(self, ctx, *, code: str = None):
        await code_logic(ctx, code)

    @commands.hybrid_command(name="code")
    async def code_slash(self, ctx: commands.Context, code: str):
        await code_logic(ctx, code)


async def setup(bot):
    await bot.add_cog(CodeCog(bot))
    print("Loaded code (API mode) has success")
