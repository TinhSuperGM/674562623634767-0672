from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Dict, Union

import discord
from discord.ext import commands

from api_client import get, post
from Commands.prayer import get_luck

# ===== SIDE =====
choices = ["ngua", "sap"]

# ===== EMOJI =====
CUSTOM_EMOJI = {}
UNICODE_EMOJI = {
    "ngua": "<:ngua:1490580499582681088>",
    "sap": "<:sap:1490580475172098178>",
}


def get_emoji(x):
    return CUSTOM_EMOJI.get(x) or UNICODE_EMOJI.get(x, "❔")


def pretty_side(x: str):
    x = str(x).lower()
    if x == "ngua":
        return "Ngửa"
    if x == "sap":
        return "Sấp"
    return x


def _safe_int(v):
    try:
        return int(v)
    except Exception:
        return 0


def _get_user(ctx):
    return ctx.user if isinstance(ctx, discord.Interaction) else ctx.author


# ===== ANTI SPAM =====
_LAST_PLAY: Dict[int, float] = {}
_SPAM_COUNT: Dict[int, int] = {}


def spam_control(uid):
    now = time.time()
    last = _LAST_PLAY.get(uid, 0)
    diff = now - last

    if diff < 2:
        _SPAM_COUNT[uid] = _SPAM_COUNT.get(uid, 0) + 1
    else:
        _SPAM_COUNT[uid] = 0

    _LAST_PLAY[uid] = now
    spam = _SPAM_COUNT[uid]
    delay = min(spam * 0.5, 2)
    scale = max(1 - spam * 0.1, 0.5)
    return delay, scale, spam


async def _defer_if_needed(ctx, *, ephemeral: bool = False):
    if isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
        try:
            await ctx.response.defer(ephemeral=ephemeral)
        except Exception:
            pass


# ===== SEND SAFE =====
async def _send(
    ctx: Union[commands.Context, discord.Interaction],
    content=None,
    embed=None,
    ephemeral: bool = False,
):
    try:
        if isinstance(ctx, discord.Interaction):
            try:
                if not ctx.response.is_done():
                    await ctx.response.send_message(
                        content=content,
                        embed=embed,
                        ephemeral=ephemeral,
                    )
                    return await ctx.original_response()
                return await ctx.followup.send(
                    content=content,
                    embed=embed,
                    ephemeral=ephemeral,
                )
            except discord.InteractionResponded:
                return await ctx.followup.send(
                    content=content,
                    embed=embed,
                    ephemeral=ephemeral,
                )

        return await ctx.send(content=content, embed=embed)

    except Exception as e:
        print("[SEND ERROR]", e)
        return None


# ===== API HELPERS =====
async def remove_gold(user_id: int, amount: int) -> bool:
    res = await post(f"/users/{user_id}/gold/remove", {"amount": amount})
    return isinstance(res, dict) and res.get("success", False)


async def add_gold(user_id: int, amount: int):
    await post(f"/users/{user_id}/gold/add", {"amount": amount})


async def get_gold(user_id: int) -> int:
    user = await get(f"/users/{user_id}")
    if isinstance(user, dict):
        return _safe_int(user.get("gold"))
    return 0


# ===== EMBED CHỜ =====
def build_wait_embed(user):
    embed = discord.Embed(description="", color=0xF1C40F)
    embed.set_author(name="Tung đồng xu")
    return embed


# ===== EMBED KẾT QUẢ =====
def build_result_embed(user, choice, result, amount, reward, win, gold, spam, scale, luck):
    embed = discord.Embed()
    embed.set_author(name="Tung đồng xu")

    result_line = f"Kết quả: {get_emoji(result)} {pretty_side(result)}"

    if win:
        embed.color = 0x2ECC71
        embed.description = (
            f"{result_line}\n\n"
            f"Bạn đã trúng {pretty_side(choice)}\n"
            f"Đã cộng thêm {reward} gold"
        )
        if spam >= 2:
            embed.description += f"\n⚠️ Spam → giảm thưởng x{scale:.2f}"
    else:
        embed.color = 0xE74C3C
        embed.description = (
            f"{result_line}\n\n"
            f"Bạn không trúng mặt nào.\n"
            f"Đã trừ đi {amount} gold"
        )

    embed.set_footer(text=f"Số dư hiện tại: {gold}")
    return embed


# ===== MAIN =====
async def coinflip_logic(ctx, choice: str, amount: Any):
    await _defer_if_needed(ctx, ephemeral=isinstance(ctx, discord.Interaction))

    user = _get_user(ctx)
    uid = user.id
    choice = str(choice).strip().lower()
    amount = _safe_int(amount)
    is_slash = isinstance(ctx, discord.Interaction)

    if choice not in choices:
        return await _send(ctx, "❌ Chỉ được nhập: Ngua hoặc Sap!", ephemeral=is_slash)

    if amount <= 0:
        return await _send(ctx, "❌ Gold phải > 0!", ephemeral=is_slash)

    if not await remove_gold(uid, amount):
        return await _send(ctx, "❌ Không đủ gold!", ephemeral=is_slash)

    delay, scale, spam = spam_control(uid)

    wait_msg = await _send(ctx, embed=build_wait_embed(user))
    if wait_msg is None:
        return

    wait_time = random.uniform(3, 5) + delay
    await asyncio.sleep(wait_time)

    luck = _safe_int(get_luck(uid))

    weights = {"ngua": 1.0, "sap": 1.0}
    weights[choice] *= (1 + max(0, (luck - 1) / 100) * 5)

    result = random.choices(
        ["ngua", "sap"],
        weights=[weights["ngua"], weights["sap"]],
        k=1,
    )[0]

    if choice == result:
        reward = int(amount * 1.7)
        reward = int(reward * scale)
        await add_gold(uid, reward)
        win = True
    else:
        reward = 0
        win = False

    gold = await get_gold(uid)
    embed = build_result_embed(
        user=user,
        choice=choice,
        result=result,
        amount=amount,
        reward=reward,
        win=win,
        gold=gold,
        spam=spam,
        scale=scale,
        luck=luck,
    )

    try:
        if wait_msg:
            await wait_msg.edit(embed=embed)
    except Exception:
        pass

    print("Loaded coinflip (API mode) has success")


def _normalize_side(text: str) -> str:
    text = str(text).strip().lower()
    if text in {"ngửa", "ngua", "u", "heads"}:
        return "ngua"
    if text in {"sấp", "sap", "x", "tails"}:
        return "sap"
    return text


async def coinflip_prefix(ctx, choice: str, amount: Any):
    return await coinflip_logic(ctx, _normalize_side(choice), amount)


async def coinflip_slash(interaction, choice: str, amount: Any):
    return await coinflip_logic(interaction, _normalize_side(choice), amount)


print("Loaded coinflip (API mode) has success")
