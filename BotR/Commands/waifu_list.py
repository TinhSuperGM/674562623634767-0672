import discord
import math
import asyncio
from typing import Any, Dict, List, Optional, Union

from api_client import get  # 🔥 dùng API

# =====================
# CONFIG
# =====================
RANK_ORDER = {
    "limited": 0,
    "toi_thuong": 1,
    "truyen_thuyet": 2,
    "huyen_thoai": 3,
    "anh_hung": 4,
    "thuong": 5,
}

VIEW_TIMEOUT = 600
PER_PAGE = 10
PAGE_SELECT_LIMIT = 25

# =====================
# LOAD API (THAY JSON)
# =====================
async def load_inv():
    data = await get("/inventory")
    return data if isinstance(data, dict) else {}


async def load_waifu_data():
    data = await get("/waifu")
    return data if isinstance(data, dict) else {}


# =====================
# NORMALIZE / SORT
# =====================
def _clean_text(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def _get_target_display_name(user: Union[discord.User, discord.Member]) -> str:
    return getattr(user, "display_name", None) or getattr(user, "name", "Unknown")


def normalize_collection(collection: Any, waifu_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    if isinstance(collection, dict):
        for waifu_id, raw in collection.items():
            waifu_id = str(waifu_id)

            # ❗ QUAN TRỌNG: skip count = 0
            if int(raw) <= 0:
                continue

            base = waifu_data.get(waifu_id, {})

            merged: Dict[str, Any] = {}
            if isinstance(base, dict):
                merged.update(base)

            merged["id"] = waifu_id
            merged["name"] = base.get("name", waifu_id)
            merged["rank"] = base.get("rank", "")

            items.append(merged)

    return items


def sort_waifus(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def sort_key(item: Dict[str, Any]):
        rank_raw = _clean_text(item.get("rank"))
        rank_index = RANK_ORDER.get(rank_raw, 999)
        name = _clean_text(item.get("name"))
        return (rank_index, name)

    return sorted(items, key=sort_key)


def filter_waifus(items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    q = _clean_text(query)
    if not q:
        return items

    return [
        item for item in items
        if q in _clean_text(item.get("id")) or q in _clean_text(item.get("name"))
    ]


def _rank_label(rank: Any) -> str:
    return str(rank).strip() or "không xác định"


# =====================
# VIEW
# =====================
class WaifuListView(discord.ui.View):
    def __init__(self, author, target_user, waifu_items):
        super().__init__(timeout=VIEW_TIMEOUT)

        self.author = author
        self.target_user = target_user
        self.items = waifu_items

        self.page = 0
        self.per_page = PER_PAGE
        self.search = None

    def get_current_items(self):
        start = self.page * self.per_page
        return self.items[start:start + self.per_page]

    def get_embed(self):
        current = self.get_current_items()

        lines = []
        for i, w in enumerate(current, start=1):
            lines.append(
                f"{i}. 🩷 **{w['name']}** (`{w['id']}`) | 🎖️ `{_rank_label(w.get('rank'))}`"
            )

        if not lines:
            lines = ["Không có waifu"]

        embed = discord.Embed(
            title=f"🗂️ Waifu của {self.target_user.display_name}",
            description="\n".join(lines),
            color=0xFF66CC
        )

        embed.set_footer(text=f"Trang {self.page+1}")
        return embed


# =====================
# MAIN
# =====================
async def waifu_list_run(ctx_or_interaction, target_user=None):
    inv = await load_inv()
    waifu_data = await load_waifu_data()

    invoker = ctx_or_interaction.user if hasattr(ctx_or_interaction, "user") else ctx_or_interaction.author
    target = target_user or invoker

    uid = str(target.id)

    raw_collection = inv.get(uid, {}).get("waifus", {})

    waifu_items = normalize_collection(raw_collection, waifu_data)
    waifu_items = sort_waifus(waifu_items)

    if not waifu_items:
        msg = f"📦 {target.display_name} chưa có waifu nào."

        if hasattr(ctx_or_interaction, "response"):
            await ctx_or_interaction.response.send_message(msg, ephemeral=True)
        else:
            await ctx_or_interaction.send(msg)
        return

    view = WaifuListView(invoker, target, waifu_items)
    embed = view.get_embed()

    if hasattr(ctx_or_interaction, "response"):
        await ctx_or_interaction.response.send_message(embed=embed, view=view)
    else:
        await ctx_or_interaction.send(embed=embed, view=view)


print("✅ Loaded waifu list (API mode)")