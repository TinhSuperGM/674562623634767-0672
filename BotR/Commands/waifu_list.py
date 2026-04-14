from __future__ import annotations

import discord
from typing import Any, Dict, List, Optional, Union

from BotR import api_client

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

async def load_inv() -> Dict[str, Any]:
    data = await api_client.get("/inventory")
    return data if isinstance(data, dict) else {}


async def load_waifu_data() -> Dict[str, Any]:
    data = await api_client.get("/waifu")
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

            try:
                count = int(raw)
            except Exception:
                continue

            # skip count = 0
            if count <= 0:
                continue

            base = waifu_data.get(waifu_id, {})
            merged: Dict[str, Any] = {}

            if isinstance(base, dict):
                merged.update(base)

            merged["id"] = waifu_id
            merged["name"] = base.get("name", waifu_id) if isinstance(base, dict) else waifu_id
            merged["rank"] = base.get("rank", "") if isinstance(base, dict) else ""
            merged["count"] = count

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
        self.search: Optional[str] = None

    def get_current_items(self):
        start = self.page * self.per_page
        return self.items[start:start + self.per_page]

    def get_embed(self):
        current = self.get_current_items()
        lines = []

        for i, w in enumerate(current, start=1):
            lines.append(
                f"{i}. **{w['name']}** (`{w['id']}`) | `{_rank_label(w.get('rank'))}`"
            )

        if not lines:
            lines = ["Không có waifu"]

        embed = discord.Embed(
            title=f"Waifu của {_get_target_display_name(self.target_user)}",
            description="\n".join(lines),
            color=0xFF66CC
        )
        total_pages = max(1, (len(self.items) + self.per_page - 1) // self.per_page)
        embed.set_footer(text=f"Trang {self.page + 1}/{total_pages}")
        return embed

    def _can_go_prev(self) -> bool:
        return self.page > 0

    def _can_go_next(self) -> bool:
        return (self.page + 1) * self.per_page < len(self.items)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("❌ Bạn không phải người xem danh sách này.", ephemeral=True)

        if not self._can_go_prev():
            return await interaction.response.defer()

        self.page -= 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("❌ Bạn không phải người xem danh sách này.", ephemeral=True)

        if not self._can_go_next():
            return await interaction.response.defer()

        self.page += 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


# =====================
# MAIN
# =====================

async def _send_result(ctx_or_interaction, *, content: Optional[str] = None, embed: Optional[discord.Embed] = None, view: Optional[discord.ui.View] = None):
    if hasattr(ctx_or_interaction, "response"):
        if ctx_or_interaction.response.is_done():
            return await ctx_or_interaction.followup.send(content=content, embed=embed, view=view, ephemeral=bool(content))
        return await ctx_or_interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=bool(content))
    return await ctx_or_interaction.send(content=content, embed=embed, view=view)


async def waifu_list_run(ctx_or_interaction, target_user=None):
    inv = await load_inv()
    waifu_data = await load_waifu_data()

    invoker = ctx_or_interaction.user if hasattr(ctx_or_interaction, "user") else ctx_or_interaction.author
    target = target_user or invoker
    uid = str(target.id)

    raw_collection = {}
    target_bucket = inv.get(uid, {}) if isinstance(inv, dict) else {}

    if isinstance(target_bucket, dict):
        raw_collection = target_bucket.get("waifus", {}) or {}

    waifu_items = normalize_collection(raw_collection, waifu_data)
    waifu_items = sort_waifus(waifu_items)

    if not waifu_items:
        msg = f"{_get_target_display_name(target)} chưa có waifu nào."
        return await _send_result(ctx_or_interaction, content=msg)

    view = WaifuListView(invoker, target, waifu_items)
    embed = view.get_embed()

    await _send_result(ctx_or_interaction, embed=embed, view=view)


print("✅ Loaded waifu list (API mode)")
