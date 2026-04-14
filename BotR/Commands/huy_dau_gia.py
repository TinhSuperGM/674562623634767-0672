async def huy_dau_gia_logic(interaction, auction_id: str):
    await interaction.response.defer(ephemeral=True)

    auctions = await get_auctions()
    auction = auctions.get(auction_id)

    if not auction:
        return await interaction.followup.send("❌ Auction không tồn tại!")

    uid = str(interaction.user.id)
    seller = str(auction.get("seller"))

    is_admin = uid in list(map(str, data_admin.ADMINS))

    if not is_admin and uid != seller:
        return await interaction.followup.send("❌ Không có quyền hủy!")

    # 🔒 LOCK THEO AUCTION
    async with dau_gia.get_auction_lock(auction_id):

        # reload tránh stale
        auctions = await get_auctions()
        auction = auctions.get(auction_id)

        if not auction:
            return await interaction.followup.send("❌ Auction đã bị xử lý trước đó!")

        waifu_id = auction["waifu_id"]
        love = auction.get("love", 1)

        # ===== TRẢ WAIFU =====
        async with dau_gia.GLOBAL_LOCK:
            inv = await get_inventory(seller)

            inv.setdefault("waifus", {})
            inv.setdefault("bag", {})

            inv["waifus"][waifu_id] = love

            await update_inventory(seller, inv)

        # ===== HOÀN GOLD =====
        highest = auction.get("highest_bidder")
        current = int(auction.get("current_bid", 0))

        if highest and current > 0:
            try:
                await add_gold(highest, current)
            except Exception as e:
                print("[REFUND ERROR]", e)

        # ===== XÓA MESSAGE =====
        channels = await get_auction_channels()

        for gid, ch_data in channels.items():

            ch_id = ch_data.get("auction_channel_id") if isinstance(ch_data, dict) else ch_data
            msg_id = auction.get(f"message_id_{gid}")

            if not ch_id or not msg_id:
                continue

            try:
                ch = interaction.client.get_channel(int(ch_id)) or await interaction.client.fetch_channel(int(ch_id))
                msg = ch.get_partial_message(int(msg_id))
                await msg.delete()
            except Exception as e:
                print("[DELETE MSG ERROR]", e)

        # ===== XÓA DATA =====
        auctions.pop(auction_id, None)
        dau_gia.auction_locks.pop(auction_id, None)

        await update_auctions(auctions)

    await interaction.followup.send("✅ Đã hủy đấu giá thành công!")