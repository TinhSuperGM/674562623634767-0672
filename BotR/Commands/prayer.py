import time
import random

MAX_LUCK = 5.0
DEFAULT_LUCK = 1.0


# ===== HELPER SEND =====
async def _send(ctx, msg):
    try:
        if hasattr(ctx, "response"):
            if not ctx.response.is_done():
                return await ctx.response.send_message(content=msg)
            return await ctx.followup.send(content=msg)
        return await ctx.send(msg)
    except Exception as e:
        print(f"[prayer._send] {e}")
        return None


# ===== GET LUCK =====
async def get_luck(user_id: int) -> float:
    from Data.api_client import (
    get_user_data,
    update_user,
    add_gold
    )
    user = await get_user_data(str(user_id))
    return round(user.get("luck", DEFAULT_LUCK), 2)


# ===== MAIN =====
async def prayer_logic(ctx):
    # Defer sớm cho slash command để tránh timeout nếu API chậm
    if hasattr(ctx, "response") and not ctx.response.is_done():
        try:
            await ctx.response.defer(thinking=False)
        except Exception as e:
            print(f"[prayer_logic.defer] {e}")

    user_obj = ctx.user if hasattr(ctx, "user") else ctx.author
    uid = str(user_obj.id)
    now = int(time.time())

    # ===== LOAD USER (API) =====
    user = await get_user_data(uid)

    # ensure fields (KHÔNG phá schema)
    user.setdefault("gold", 0)
    user.setdefault("luck", DEFAULT_LUCK)
    user.setdefault("last_pray", 0)

    last = int(user["last_pray"])

    # ===== COOLDOWN =====
    if now - last < 86400:
        remain = 86400 - (now - last)
        hours = remain // 3600
        minutes = (remain % 3600) // 60
        return await _send(ctx, f"🛐 Bạn cần chờ {hours}h {minutes}m để cầu nguyện tiếp.")

    # ===== SET COOLDOWN =====
    user["last_pray"] = now
    try:
        await update_user(uid, {"last_pray": now})
    except Exception as e:
        print(f"[prayer_logic.update_user] {e}")
        return await _send(ctx, "❌ Có lỗi khi lưu dữ liệu, vui lòng thử lại.")

    roll = random.random()

    # ===== +GOLD =====
    if roll < 0.4:
        gold = random.randint(300, 1000)

        try:
            await add_gold(uid, gold)
        except Exception as e:
            print(f"[prayer_logic.add_gold+] {e}")
            return await _send(ctx, "❌ Có lỗi khi cộng gold, vui lòng thử lại.")

        return await _send(
            ctx,
            "😐 Thật không may, lần này thần linh đã không xuất hiện.\n"
            f"💰 Nhưng bù lại, bạn lại tìm thấy **{gold} 🪙**"
        )

    # ===== -GOLD =====
    elif roll < 0.8:
        gold = random.randint(300, 1000)

        try:
            await add_gold(uid, -gold)
        except Exception as e:
            print(f"[prayer_logic.add_gold-] {e}")
            return await _send(ctx, "❌ Có lỗi khi trừ gold, vui lòng thử lại.")

        return await _send(
            ctx,
            "💀 Bạn thật đen đủi, thần linh lần này lại ngó lơ bạn.\n"
            f"💸 Đã vậy còn bị mất **{gold} 🪙** nữa chứ, xui quá đi mất"
        )

    # ===== +LUCK =====
    else:
        current_luck = float(user.get("luck", DEFAULT_LUCK))

        if current_luck < MAX_LUCK:
            current_luck = round(min(MAX_LUCK, current_luck + 0.1), 2)

            try:
                await update_user(uid, {"luck": current_luck})
            except Exception as e:
                print(f"[prayer_logic.save_luck] {e}")
                return await _send(ctx, "❌ Có lỗi khi lưu luck, vui lòng thử lại.")

            return await _send(
                ctx,
                "🛐 Thần linh đã hiển linh và hoàn thành tâm nguyện của bạn!\n"
                f"✨ Bạn đang rất may mắn đấy"
            )

        return await _send(
            ctx,
            "🛐 Thần linh đã hiển linh và hoàn thành tâm nguyện của bạn!\n"
            "✨ Bạn đang rất may mắn đấy"
        )


print("Loaded prayer (API) has success")