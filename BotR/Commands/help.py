from __future__ import annotations

import discord


def build_help_embed(prefix: str = "/") -> discord.Embed:
    embed = discord.Embed(
        title="Danh sách các lệnh",
        description=f"Dùng `{prefix}` để sử dụng lệnh",
        color=discord.Color.blue(),
    )

    embed.add_field(
        name="Kinh tế",
        value=f"""
{prefix}gold : Xem số dư hiện tại.
{prefix}daily: Điểm danh và nhận thưởng mỗi ngày.
{prefix}cf: Quay đồng xu (Cú pháp: .cf <sap/ngua> <tiền cược>)
{prefix}bc: Chơi Bầu cua (Cú pháp: .bc <nai/bau/ga/ca/cua/tom> <tiền cược>)
{prefix}work: Đưa waifu của bạn đi làm và nhận gold
{prefix}code: Nhập code (Cú pháp: {prefix}code <mã>)
""".strip(),
        inline=False,
    )

    embed.add_field(
        name="Waifu",
        value=f"""
{prefix}rw: Roll waifu
{prefix}wl: Xem bộ sưu tập
{prefix}ws: Chọn waifu mặc định
{prefix}sell: Bán waifu
{prefix}bag: Xem waifu và vật phẩm trong kho
""".strip(),
        inline=False,
    )

    embed.add_field(
        name="Couple",
        value=f"""
{prefix}cp: Tỏ tình ai đó
{prefix}cpr: Gửi lời đề nghị chia tay
{prefix}cpc: Hủy lời đề nghị chia tay
{prefix}cpi: Xem thông tin cặp đôi
{prefix}cpg: Tặng quà cho nửa kia
""".strip(),
        inline=False,
    )

    embed.add_field(
        name="Đấu giá",
        value=f"""
{prefix}dg: Tạo bài đấu giá
{prefix}hdg: Hủy bài đấu giá
""".strip(),
        inline=False,
    )

    embed.add_field(
        name="Khác",
        value=f"""
{prefix}h: Lệnh hướng dẫn member
{prefix}me: Xem profile của bản thân hoặc người khác
{prefix}gift: Tặng quà cho người khác ({prefix}gift <waifu/gold> <waifu_id/amount> <user_name>)
""".strip(),
        inline=False,
    )

    embed.add_field(
        name="Battle Waifu",
        value=f"""
{prefix}fight: Chọn ai đó đấu với bạn ({prefix}fight <user_name>)
{prefix}team: Cài đặt team đấu của bạn ({prefix}team [set/show/remove/clear] <waifu_id>)
""".strip(),
        inline=False,
    )

    embed.set_footer(text="Slash: / | Prefix: .")
    return embed


async def help_slash(interaction: discord.Interaction):
    embed = build_help_embed("/")
    await interaction.response.send_message(embed=embed)


async def help_prefix(message):
    embed = build_help_embed(".")
    await message.channel.send(embed=embed)


print("Loaded help has successs")
