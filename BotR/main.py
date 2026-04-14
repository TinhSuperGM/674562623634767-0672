from __future__ import annotations

import asyncio
import inspect
import os
import time
from typing import Any, Dict, Optional
\([github.com](https://github.com/TinhSuperGM/674562623634767-0672/blob/main/BotR/main.py))d.ext import commands
from dotenv import load_dotenv

from BotR import api_client
from Commands.work import init_work
from Data.level import sync_all

load_dotenv()


async def maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


# =========================================================
# BotR main.py (API mode)
# - No direct JSON file access
# - Uses BotR/api_client.py for all runtime data
# - Fixes await issues in auction loop and sync tasks
# =========================================================


class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=".", intents=intents, help_command=None)

    async def setup_hook(self):
        from Commands.slash import setup as slash_setup
        from Commands.prefix import setup as prefix_setup
        from Other.ranking import setup as ranking_setup
        from Other.phe_duyet import setup as phe_duyet_setup
        from bot_queue import start_workers
        from Data import data_user

        # ===== LOAD MODULE =====
        await ranking_setup(self)
        await slash_setup(self)
        await prefix_setup(self)
        await phe_duyet_setup(self)

        # ===== START WORKERS =====
        start_workers(self, 5)

        # ===== BACKGROUND TASKS =====
        self.loop.create_task(self.auto_sync_level())
        self.loop.create_task(self.auction_loop())
        self.loop.create_task(data_user.auto_save_loop())

        # ===== SYNC SLASH =====
        await self.tree.sync()

    async def auto_sync_level(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await sync_all()
            except Exception as e:
                print(f"❌ Sync lỗi: {e}")
            await asyncio.sleep(30)

    async def auction_loop(self):
        from Commands.dau_gia import get_channels as load_channels
        from Data import data_user

        await self.wait_until_ready()
        while not self.is_closed():
            await asyncio.sleep(30)

            try:
                auctions = await api_client.get_auction()
                inv = await api_client.get_inventory()
            except Exception as e:
                print(f"[AUCTION LOAD ERROR] {e}")
                continue

            if not isinstance(auctions, dict):
                auctions = {}
            if not isinstance(inv, dict):
                inv = {}

            try:
                channels = await maybe_await(load_channels())
            except Exception as e:
                print(f"[AUCTION CHANNEL ERROR] {e}")
                channels = {}

            if not isinstance(channels, dict):
                channels = {}

            now = time.time()
            remove_list = []

            for aid, a in list(auctions.items()):
                if not isinstance(a, dict):
                    continue

                if now < a.get("end_time", 0):
                    continue

                seller = str(a.get("seller", ""))
                winner = a.get("highest_bidder")
                waifu = str(a.get("waifu_id", ""))
                love = int(a.get("love", 0))
                price = int(a.get("current_bid", 0))

                if not seller or not waifu:
                    remove_list.append(aid)
                    continue

                # ===== RESULT =====
                if winner:
                    winner = str(winner)
                    user = inv.setdefault(winner, {})
                    if not isinstance(user, dict):
                        user = {}
                        inv[winner] = user

                    waifus = user.setdefault("waifus", {})
                    bag = user.setdefault("bag", {})
                    if not isinstance(waifus, dict):
                        waifus = {}
                        user["waifus"] = waifus
                    if not isinstance(bag, dict):
                        bag = {}
                        user["bag"] = bag

                    if waifu in waifus:
                        bag[waifu] = bag.get(waifu, 0) + 1
                    else:
                        waifus[waifu] = love

                    # FIX ASYNC
                    try:
                        await data_user.add_gold(seller, price)
                    except Exception as e:
                        print(f"[AUCTION ADD GOLD ERROR] {e}")

                    result_text = f"<@{winner}> thắng đấu giá **{waifu}** ({price})"
                else:
                    user = inv.setdefault(seller, {})
                    if not isinstance(user, dict):
                        user = {}
                        inv[seller] = user

                    waifus = user.setdefault("waifus", {})
                    if not isinstance(waifus, dict):
                        waifus = {}
                        user["waifus"] = waifus

                    waifus[waifu] = love
                    result_text = f"❌ Không ai mua **{waifu}** → trả lại <@{seller}>"

                # ===== DELETE MESSAGES =====
                for msg_info in a.get("messages", []):
                    if not isinstance(msg_info, dict):
                        continue
                    ch = self.get_channel(int(msg_info.get("channel_id", 0)))
                    if ch:
                        try:
                            msg = await ch.fetch_message(int(msg_info.get("message_id", 0)))
                            await msg.delete()
                        except Exception:
                            pass

                # ===== SEND RESULT =====
                for gid, ch_data in channels.items():
                    ch_id = ch_data.get("channel_id") if isinstance(ch_data, dict) else ch_data
                    if not ch_id:
                        continue
                    ch = self.get_channel(int(ch_id))
                    if ch:
                        try:
                            await ch.send(result_text)
                        except Exception:
                            pass

                remove_list.append(aid)

            # ===== SAVE =====
            for aid in remove_list:
                auctions.pop(aid, None)

            try:
                await api_client.set_auction(auctions)
                await api_client.set_data("inventory", inv)
            except Exception as e:
                print(f"[AUCTION SAVE ERROR] {e}")


bot = MyBot()


@bot.event
async def on_ready():
    # FIX QUAN TRỌNG NHẤT
    init_work(bot)
    print(f"✅ Bot online: {bot.user}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error


TOKEN = os.getenv("DISCORD_TOKEN")
print("Token OK:", bool(TOKEN))
bot.run(TOKEN)
