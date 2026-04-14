from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union

import discord
from discord.ext import commands

from Data import data_user
import api_client

VN_TZ = timezone(timedelta(hours=7))

# =========================================================
# couple.py (API mode)
# - No direct JSON file access
# - Uses api_client.get_couple() / api_client.set_couple()
# - Keeps the original helper names so slash/prefix files
#   can keep calling this module without heavy refactor.
# =========================================================

_COUPLE_LOCK = asyncio.Lock()
_COUPLE_LOOP_STARTED = False


# ===== API LOAD / SAVE =====
async def load_couple_data() -> Dict[str, Any]:
    data = await api_client.get_couple()
    return data if isinstance(data, dict) else {}


async def save_couple_data(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        data = {}
    res = await api_client.set_couple(data)
    return bool(res and res.get("success"))


# ===== TIME =====
def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def iso_now_vn() -> str:
    return now_vn().isoformat()


def parse_iso_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        return dt
    except Exception:
        return None


# ===== CORE =====
def create_couple(data: Dict[str, Any], u1: int, u2: int) -> None:
    now = now_vn().strftime("%Y-%m-%d")
    data[str(u1)] = {
        "partner": str(u2),
        "since": now,
        "points": 0,
        "pending_break": False,
        "break_time": None,
        "break_initiator": None,
    }
    data[str(u2)] = {
        "partner": str(u1),
        "since": now,
        "points": 0,
        "pending_break": False,
        "break_time": None,
        "break_initiator": None,
    }


def remove_couple(data: Dict[str, Any], u1: Any, u2: Any) -> None:
    data.pop(str(u1), None)
    data.pop(str(u2), None)


def is_couple(data: Dict[str, Any], u1: Any, u2: Any) -> bool:
    u1 = str(u1)
    u2 = str(u2)
    return (
        u1 in data
        and u2 in data
        and data[u1].get("partner") == u2
        and data[u2].get("partner") == u1
    )


def check_auto_break(data: Dict[str, Any], u1: str) -> bool:
    info = data.get(str(u1))
    if not isinstance(info, dict):
        return False
    if not info.get("pending_break"):
        return False

    bt_time = parse_iso_dt(info.get("break_time"))
    if not bt_time:
        return False

    if now_vn() - bt_time >= timedelta(days=7):
        partner = info.get("partner")
        if partner:
            remove_couple(data, u1, partner)
        else:
            data.pop(str(u1), None)
        return True
    return False


# ===== UTILS =====
def _get_user(ctx):
    return getattr(ctx, "author", None) or getattr(ctx, "user", None)


def _get_channel(ctx):
    return getattr(ctx, "channel", None)


async def _send(
    ctx: Union[commands.Context, discord.Interaction],
    content=None,
    embed=None,
    ephemeral: bool = False,
):
    try:
        if isinstance(ctx, discord.Interaction):
            if not ctx.response.is_done():
                await ctx.response.send_message(
                    content=content,
                    embed=embed,
                    ephemeral=ephemeral,
                )
                try:
                    return await ctx.original_response()
                except Exception:
                    return None
            return await ctx.followup.send(
                content=content,
                embed=embed,
                ephemeral=ephemeral,
            )
        return await ctx.send(content=content, embed=embed)
    except Exception as e:
        print("[COUPLE SEND ERROR]", e)
        return None


async def safe_send(ctx, content=None, embed=None, ephemeral: bool = False):
    return await _send(ctx, content=content, embed=embed, ephemeral=ephemeral)


def resolve_target_from_ctx(ctx, target: Optional[Any]) -> Optional[Any]:
    if target is not None:
        return target

    message = getattr(ctx, "message", None)
    if message and getattr(message, "mentions", None):
        return message.mentions[0]

    return None


# ===== EMBEDS =====
def build_info_embed(target, info: Dict[str, Any]) -> discord.Embed:
    partner_id = info.get("partner")
    embed = discord.Embed(
        title=f"💞 Couple của {getattr(target, 'display_name', getattr(target, 'name', 'User'))}",
        color=discord.Color.from_rgb(255, 105, 180),
    )
    embed.add_field(name="Partner", value=f"<@{partner_id}>" if partner_id else "Không có", inline=True)
    embed.add_field(name="Từ ngày", value=str(info.get("since", "?")), inline=True)
    embed.add_field(name="Điểm", value=str(info.get("points", 0)), inline=True)
    embed.add_field(name="Chờ chia tay", value=str(bool(info.get("pending_break"))), inline=True)
    if info.get("break_time"):
        embed.add_field(name="Break time", value=str(info.get("break_time")), inline=False)
    return embed


def build_gift_embed(user, partner_id: str, item_name: str, points: int) -> discord.Embed:
    embed = discord.Embed(
        title="🎁 Tặng quà couple",
        description=(
            f"{user.mention} đã tặng **{item_name}** cho <@{partner_id}>.\n"
            f"Cả hai nhận thêm **{points} điểm** tình cảm."
        ),
        color=discord.Color.from_rgb(255, 182, 193),
    )
    return embed


def build_break_request_embed(user, partner_id: str) -> discord.Embed:
    embed = discord.Embed(
        title="💔 Yêu cầu chia tay",
        description=(
            f"{user.mention} muốn chia tay với <@{partner_id}>.\n"
            "Nhắn `yes` để đồng ý hoặc `no` để từ chối."
        ),
        color=discord.Color.red(),
    )
    return embed


def build_cancel_embed(user, partner_id: str) -> discord.Embed:
    embed = discord.Embed(
        title="✅ Hủy yêu cầu chia tay",
        description=f"{user.mention} đã hủy yêu cầu chia tay với <@{partner_id}>.",
        color=discord.Color.green(),
    )
    return embed


def build_propose_embed(user, target) -> discord.Embed:
    embed = discord.Embed(
        title="💘 Tỏ tình",
        description=f"{user.mention} đã tỏ tình với {target.mention}.\n{target.mention} hãy nhắn `yes` để đồng ý hoặc `no` để từ chối.",
        color=discord.Color.from_rgb(255, 105, 180),
    )
    return embed


# ===== LOGIC =====
async def couple_logic(bot, ctx, target: Optional[Any] = None):
    data = await load_couple_data()
    send = _send
    user = _get_user(ctx)
    channel = _get_channel(ctx)
    target = resolve_target_from_ctx(ctx, target)

    if user is None:
        return await send(ctx, "❌ Không xác định được người dùng.", ephemeral=True if hasattr(ctx, "response") else False)

    if target is None:
        return await send(
            ctx,
            "❌ Hãy mention hoặc reply người bạn muốn tỏ tình.",
            ephemeral=True if hasattr(ctx, "response") else False,
        )

    u1 = str(user.id)
    u2 = str(target.id)

    if u1 == u2:
        return await send(ctx, "❌ Bạn không thể tỏ tình với chính mình.")

    if u1 in data and data[u1].get("partner") == u2:
        return await send(ctx, "❌ Hai bạn đã là một cặp rồi.")

    if u1 in data:
        return await send(ctx, "❌ Bạn đang có người yêu rồi.")

    if u2 in data:
        return await send(ctx, "❌ Người này đã có người yêu rồi.")

    await send(ctx, embed=build_propose_embed(user, target))

    def check(m):
        return m.author.id == target.id and m.channel == channel

    try:
        while True:
            msg = await bot.wait_for("message", timeout=60, check=check)
            content = msg.content.lower().strip()

            if content == "yes":
                async with _COUPLE_LOCK:
                    data = await load_couple_data()
                    if u1 in data or u2 in data:
                        return await send(ctx, "❌ Một trong hai người đã có trạng thái couple rồi.")
                    create_couple(data, user.id, target.id)
                    await save_couple_data(data)

                embed = discord.Embed(
                    title="💞 Couple thành công",
                    description=f"{user.mention} và {target.mention} đã chính thức trở thành một cặp đôi.",
                    color=discord.Color.from_rgb(255, 105, 180),
                )
                embed.set_footer(text="Chúc mừng hai bạn!")
                return await send(ctx, embed=embed)

            if content == "no":
                embed = discord.Embed(
                    title="❌ Bị từ chối",
                    description=f"{target.mention} đã từ chối lời tỏ tình của {user.mention}.",
                    color=discord.Color.red(),
                )
                return await send(ctx, embed=embed)

            await send(ctx, f"❌ {target.mention} chỉ cần nhắn `yes` hoặc `no`.")

    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="⌛ Hết thời gian",
            description=f"{target.mention} đã không phản hồi kịp lời tỏ tình của {user.mention}.",
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Đôi khi chờ đợi cũng là một phần của câu chuyện.")
        return await send(ctx, embed=embed)


async def couple_release_logic(bot, ctx):
    data = await load_couple_data()
    send = _send
    user = _get_user(ctx)
    channel = _get_channel(ctx)

    if user is None:
        return await send(ctx, "❌ Không xác định được người dùng.")

    u1 = str(user.id)
    if u1 not in data:
        return await send(ctx, "❌ Bạn chưa có người yêu.")

    if check_auto_break(data, u1):
        await save_couple_data(data)
        return await send(ctx, "💔 Hai bạn đã tự động chia tay.")

    info = data[u1]
    u2 = info.get("partner")
    if not u2 or u2 not in data:
        remove_couple(data, u1, u2 or "")
        await save_couple_data(data)
        return await send(ctx, "❌ Dữ liệu couple bị lỗi và đã được dọn lại.")

    await send(ctx, f"<@{u2}>", embed=build_break_request_embed(user, u2))

    def check(m):
        return m.author.id == int(u2) and m.channel == channel

    try:
        while True:
            msg = await bot.wait_for("message", timeout=60, check=check)
            content = msg.content.lower().strip()

            if content == "yes":
                remove_couple(data, u1, u2)
                await save_couple_data(data)
                embed = discord.Embed(
                    title="💔 Đã chia tay",
                    description=f"{user.mention} và <@{u2}> đã chính thức chia tay.",
                    color=discord.Color.red(),
                )
                return await send(ctx, embed=embed)

            if content == "no":
                now = iso_now_vn()
                for uid in (u1, u2):
                    if uid in data:
                        data[uid]["pending_break"] = True
                        data[uid]["break_time"] = now
                        data[uid]["break_initiator"] = u1
                await save_couple_data(data)

                embed = discord.Embed(
                    title="⌛ Yêu cầu đã được lưu",
                    description=(
                        f"<@{u2}> không đồng ý chia tay ngay.\n"
                        "Yêu cầu đã được lưu, sau **7 ngày** hệ thống sẽ tự động chia tay nếu không được hủy."
                    ),
                    color=discord.Color.blurple(),
                )
                embed.set_footer(text="Còn 7 ngày để suy nghĩ lại.")
                return await send(ctx, embed=embed)

            await send(ctx, f"❌ <@{u2}> chỉ cần nhắn `yes` hoặc `no`.")

    except asyncio.TimeoutError:
        now = iso_now_vn()
        for uid in (u1, u2):
            if uid in data:
                data[uid]["pending_break"] = True
                data[uid]["break_time"] = now
                data[uid]["break_initiator"] = u1
        await save_couple_data(data)

        embed = discord.Embed(
            title="⌛ Hết thời gian phản hồi",
            description=(
                f"<@{u2}> đã không trả lời kịp.\n"
                "Yêu cầu chia tay đã được lưu và sẽ tự động xử lý sau **7 ngày**."
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Thời gian sẽ trả lời thay cho lời nói.")
        return await send(ctx, embed=embed)


async def couple_cancel_logic(ctx):
    data = await load_couple_data()
    send = _send
    user = _get_user(ctx)
    if user is None:
        return await send(ctx, "❌ Không xác định được người dùng.")

    u1 = str(user.id)
    if u1 not in data or not data[u1].get("pending_break"):
        return await send(ctx, "❌ Bạn chưa ở trạng thái chờ chia tay.")

    if data[u1].get("break_initiator") != u1:
        return await send(ctx, "❌ Bạn không phải người khởi tạo yêu cầu chia tay nên không thể hủy.")

    u2 = data[u1].get("partner")
    if not u2 or u2 not in data:
        remove_couple(data, u1, u2 or "")
        await save_couple_data(data)
        return await send(ctx, "❌ Dữ liệu couple bị lỗi và đã được dọn lại.")

    for uid in (u1, u2):
        data[uid]["pending_break"] = False
        data[uid]["break_time"] = None
        data[uid]["break_initiator"] = None

    await save_couple_data(data)
    return await send(ctx, embed=build_cancel_embed(user, u2))


async def couple_info_logic(ctx, target: Optional[Any] = None):
    data = await load_couple_data()
    send = _send
    viewer = _get_user(ctx)
    if viewer is None:
        return await send(ctx, "❌ Không xác định được người dùng.")

    target = resolve_target_from_ctx(ctx, target)
    if target is None:
        target = viewer

    uid = str(target.id)
    if uid not in data:
        if uid == str(viewer.id):
            return await send(ctx, "❌ Bạn chưa có người yêu.")
        return await send(ctx, "❌ Người này chưa có người yêu.")

    if check_auto_break(data, uid):
        await save_couple_data(data)
        return await send(ctx, "💔 Cặp đôi này đã tự động chia tay.")

    info = data[uid]
    partner = info.get("partner")
    if not partner or partner not in data:
        remove_couple(data, uid, partner or "")
        await save_couple_data(data)
        return await send(ctx, "❌ Dữ liệu couple bị lỗi và đã được dọn lại.")

    return await send(ctx, embed=build_info_embed(target, info))


async def couple_gift_logic(ctx, item: str):
    couple_data = await load_couple_data()
    send = _send
    user = _get_user(ctx)
    if user is None:
        return await send(ctx, "❌ Không xác định được người dùng.")

    u1 = str(user.id)
    if u1 not in couple_data:
        return await send(ctx, "❌ Bạn chưa có người yêu.")

    if check_auto_break(couple_data, u1):
        await save_couple_data(couple_data)
        return await send(ctx, "💔 Hai bạn đã tự động chia tay.")

    if couple_data[u1].get("pending_break"):
        return await send(ctx, "❌ Hai bạn đang trong trạng thái chờ chia tay, chưa thể tặng quà.")

    u2 = couple_data[u1].get("partner")
    if not u2 or u2 not in couple_data:
        remove_couple(couple_data, u1, u2 or "")
        await save_couple_data(couple_data)
        return await send(ctx, "❌ Dữ liệu couple bị lỗi và đã được dọn lại.")

    item = str(item).lower().strip()
    if item == "rose":
        price, points, name = 1000, 5, "Hoa hồng"
    elif item == "cake":
        price, points, name = 2000, 10, "Bánh kem"
    else:
        return await send(ctx, "❌ Item không hợp lệ. Chỉ có `rose` hoặc `cake`.")

    success = await data_user.remove_gold(u1, price)
    if not success:
        return await send(ctx, f"❌ Bạn không đủ gold để mua {name}.")

    couple_data[u1]["points"] = int(couple_data[u1].get("points", 0)) + points
    couple_data[u2]["points"] = int(couple_data.get(u2, {}).get("points", 0)) + points
    await save_couple_data(couple_data)
    return await send(ctx, embed=build_gift_embed(user, u2, name, points))


# ===== AUTO BREAK BACKUP =====
async def start_couple_loop(bot):
    global _COUPLE_LOOP_STARTED
    if _COUPLE_LOOP_STARTED:
        return
    _COUPLE_LOOP_STARTED = True

    async def auto_break():
        await bot.wait_until_ready()
        while not bot.is_closed():
            try:
                data = await load_couple_data()
                changed = False
                processed = set()

                for u1, info in list(data.items()):
                    if u1 in processed:
                        continue
                    if not isinstance(info, dict):
                        continue
                    if not info.get("pending_break"):
                        continue

                    u2 = info.get("partner")
                    if not u2:
                        continue

                    bt_time = parse_iso_dt(info.get("break_time"))
                    if not bt_time:
                        continue

                    if now_vn() - bt_time >= timedelta(days=7):
                        remove_couple(data, u1, u2)
                        processed.add(u1)
                        processed.add(str(u2))
                        changed = True

                        try:
                            user1 = bot.get_user(int(u1))
                            user2 = bot.get_user(int(u2))
                            if user1:
                                await user1.send("💔 Mối quan hệ đã tự động kết thúc sau 7 ngày chờ chia tay.")
                            if user2:
                                await user2.send("💔 Mối quan hệ đã tự động kết thúc sau 7 ngày chờ chia tay.")
                        except Exception:
                            pass

                if changed:
                    await save_couple_data(data)

            except Exception as e:
                print("[COUPLE AUTO ERROR]", e)

            await asyncio.sleep(60)

    bot.loop.create_task(auto_break())


print("Loaded couple (API mode) has success")
