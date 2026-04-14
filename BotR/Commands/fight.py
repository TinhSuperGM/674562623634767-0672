from __future__ import annotations

import asyncio
import copy
import random
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import discord
from discord.ext import commands

import api_client
from Data import data_user

# =========================================================
# fight.py (API mode)
# - No direct JSON access
# - Uses BotR/api_client.py for inventory/waifu/team/cooldown
# - Keeps public entrypoint: fight_logic(ctx, opponent)
# =========================================================

INV_LOCK = asyncio.Lock()
BATTLE_STATE_LOCK = asyncio.Lock()
COOLDOWN_LOCK = threading.RLock()

ACTIVE_BATTLE_USERS: Set[str] = set()
COOLDOWNS: Dict[str, float] = {}
COOLDOWNS_LOADED = False

COOLDOWN_HOURS = 6
MAX_ROUNDS = 20
ACTION_DELAY = 1.5
LOVE_DROP_RATE = 0.20

RANK_STATS = {
    "thuong": (100, 10, 5),
    "anh_hung": (130, 12, 6),
    "huyen_thoai": (160, 14, 7),
    "truyen_thuyet": (190, 16, 8),
    "toi_thuong": (230, 18, 9),
    "limited": (270, 20, 10),
}

CRIT_BASE = {
    "thuong": 0.04,
    "anh_hung": 0.05,
    "huyen_thoai": 0.06,
    "truyen_thuyet": 0.07,
    "toi_thuong": 0.08,
    "limited": 0.10,
}

LIFESTEAL_BASE = {
    "thuong": 0.02,
    "anh_hung": 0.03,
    "huyen_thoai": 0.04,
    "truyen_thuyet": 0.05,
    "toi_thuong": 0.06,
    "limited": 0.08,
}


# =========================================================
# API wrappers
# =========================================================
async def api_get(path: str) -> Dict[str, Any]:
    data = await api_client.get(path)
    return data if isinstance(data, dict) else {}


async def api_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = await api_client.post(path, payload)
    return data if isinstance(data, dict) else {}


async def load_inventory_db() -> Dict[str, Any]:
    data = await api_get("/inventory")
    return data if isinstance(data, dict) else {}


async def load_waifu_db() -> Dict[str, Any]:
    data = await api_get("/waifu")
    return data if isinstance(data, dict) else {}


async def load_team_db() -> Dict[str, Any]:
    data = await api_get("/team")
    return data if isinstance(data, dict) else {}


async def ensure_cooldowns_loaded():
    global COOLDOWNS_LOADED, COOLDOWNS

    if COOLDOWNS_LOADED:
        return

    raw = await api_get("/cooldown")
    out: Dict[str, float] = {}
    now = time.time()

    if isinstance(raw, dict):
        for key, value in raw.items():
            try:
                expiry = float(value)
            except Exception:
                continue
            if expiry > now:
                out[str(key)] = expiry

    with COOLDOWN_LOCK:
        COOLDOWNS = out
        COOLDOWNS_LOADED = True


async def save_cooldowns_to_api():
    with COOLDOWN_LOCK:
        snapshot = dict(COOLDOWNS)
    await api_client.set_cooldown(snapshot)


def get_user_obj(ctx):
    return getattr(ctx, "user", None) or getattr(ctx, "author", None)


async def _defer_if_interaction(ctx, ephemeral: bool = False):
    if isinstance(ctx, discord.Interaction) and not ctx.response.is_done():
        try:
            await ctx.response.defer(ephemeral=ephemeral)
        except Exception:
            pass


async def send_like(ctx, content=None, embed=None, view=None):
    kwargs = {}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view

    if isinstance(ctx, discord.Interaction):
        if not ctx.response.is_done():
            await ctx.response.send_message(**kwargs)
            try:
                return await ctx.original_response()
            except Exception:
                return None
        return await ctx.followup.send(**kwargs)

    if hasattr(ctx, "channel") and ctx.channel is not None:
        return await ctx.channel.send(**kwargs)

    return None


async def edit_like(msg, content=None, embed=None, view=None):
    try:
        kwargs = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if view is not None:
            kwargs["view"] = view
        return await msg.edit(**kwargs)
    except Exception:
        return None


# =========================================================
# Inventory / team helpers
# =========================================================
def _ensure_waifus_dict(user_inv: Dict[str, Any]) -> Dict[str, Any]:
    waifus = user_inv.get("waifus")
    if isinstance(waifus, dict):
        return waifus
    if isinstance(waifus, list):
        converted = {str(w): 0 for w in waifus}
        user_inv["waifus"] = converted
        return converted
    user_inv["waifus"] = {}
    return user_inv["waifus"]


def get_love(inv: Dict[str, Any], uid: str, wid: str) -> int:
    uid = str(uid)
    wid = str(wid)
    user = inv.setdefault(uid, {})
    waifus = _ensure_waifus_dict(user)
    val = waifus.get(wid, 0)

    if isinstance(val, dict):
        val = val.get("love", val.get("amount", 0))

    try:
        return max(0, int(val))
    except Exception:
        return 0


def set_love(inv: Dict[str, Any], uid: str, wid: str, val: int):
    uid = str(uid)
    wid = str(wid)
    user = inv.setdefault(uid, {})
    waifus = _ensure_waifus_dict(user)
    current = waifus.get(wid)

    new_val = max(0, int(val))
    if isinstance(current, dict):
        current["love"] = new_val
        if "amount" in current:
            current["amount"] = new_val
    else:
        waifus[wid] = new_val


def drop_love(inv: Dict[str, Any], uid: str, wid: str):
    old = get_love(inv, uid, wid)
    new = max(0, int(old * (1 - LOVE_DROP_RATE)))
    set_love(inv, uid, wid, new)
    return new


def normalize_team_ids(inv: Dict[str, Any], uid: str, team_db: Dict[str, Any]) -> List[str]:
    uid = str(uid)
    user_inv = inv.get(uid, {})
    if not isinstance(user_inv, dict):
        return []

    candidates = user_inv.get("team")
    if not candidates:
        candidates = user_inv.get("selected_team")
    if not candidates:
        candidates = user_inv.get("battle_team")
    if not candidates:
        candidates = team_db.get(uid)

    out: List[str] = []

    if isinstance(candidates, list):
        for x in candidates:
            if x is None:
                continue
            out.append(str(x))
    elif isinstance(candidates, dict):
        for k, v in candidates.items():
            if isinstance(v, (str, int)):
                out.append(str(v))
            elif isinstance(k, (str, int)):
                out.append(str(k))

    if not out:
        waifus = user_inv.get("waifus", {})
        if isinstance(waifus, dict):
            out = [str(k) for k in list(waifus.keys())[:3]]

    seen = set()
    uniq: List[str] = []
    for wid in out:
        if wid not in seen:
            uniq.append(wid)
            seen.add(wid)

    return uniq[:3]


def build_char(uid: str, wid: str, inv: Dict[str, Any], waifu_db: Dict[str, Any]) -> Dict[str, Any]:
    uid = str(uid)
    wid = str(wid)
    record = waifu_db.get(wid, {})
    if not isinstance(record, dict):
        record = {}

    rank = str(record.get("rank", "thuong")).lower().strip()
    base_hp, base_damage, base_speed = RANK_STATS.get(rank, RANK_STATS["thuong"])
    love = get_love(inv, uid, wid)

    hp_bonus = min(120, love // 4)
    dmg_bonus = min(40, love // 10)
    spd_bonus = min(15, love // 25)

    max_hp = max(1, base_hp + hp_bonus)
    damage = max(1, base_damage + dmg_bonus)
    speed = max(1, base_speed + spd_bonus)

    crit = min(0.40, CRIT_BASE.get(rank, 0.04) + (love / 2000))
    lifesteal = min(0.25, LIFESTEAL_BASE.get(rank, 0.02) + (love / 3000))

    name = record.get("name") or record.get("Name") or f"Waifu {wid}"
    image = record.get("image") or record.get("Image") or ""
    bio = record.get("Bio") or record.get("bio") or ""

    return {
        "uid": uid,
        "wid": wid,
        "name": str(name),
        "rank": rank,
        "love": love,
        "max_hp": max_hp,
        "hp": max_hp,
        "damage": damage,
        "speed": speed,
        "crit_chance": crit,
        "lifesteal": lifesteal,
        "alive": True,
        "image": image,
        "bio": bio,
    }


def hp_bar(current, max_hp, length=10):
    max_hp = max(1, int(max_hp))
    current = max(0, min(int(current), max_hp))
    ratio = current / max_hp
    filled = int(ratio * length)
    return "█" * filled + "░" * (length - filled)


def fmt_pct(value: float) -> str:
    try:
        return f"{max(0.0, float(value)) * 100:.0f}%"
    except Exception:
        return "0%"


def get_dodge_chance(attacker_speed: int, defender_speed: int) -> float:
    diff = max(-20, min(20, int(defender_speed) - int(attacker_speed)))
    return max(0.03, min(0.30, 0.10 + diff * 0.01))


def get_crit_damage(base_damage: int, is_combo: bool) -> int:
    return int(base_damage * (2.0 if is_combo else 1.5))


def get_crit_heal_amount(max_hp: int, is_combo: bool) -> int:
    return int(max_hp * (0.20 if is_combo else 0.12))


def get_gold_rate_by_turn(t: int) -> float:
    if t <= 3:
        return 0.10
    if t <= 6:
        return 0.12
    if t <= 10:
        return 0.15
    if t <= 15:
        return 0.18
    return 0.20


# =========================================================
# Cooldown helpers
# =========================================================
def _battle_key(uid1: str, uid2: str) -> str:
    return "|".join(sorted((str(uid1), str(uid2))))


def cleanup_cooldowns():
    with COOLDOWN_LOCK:
        now = time.time()
        expired = [k for k, expiry in COOLDOWNS.items() if expiry <= now]
        for k in expired:
            COOLDOWNS.pop(k, None)


def is_on_cooldown(uid1: str, uid2: str) -> Tuple[bool, int]:
    with COOLDOWN_LOCK:
        now = time.time()
        key = _battle_key(uid1, uid2)
        expiry = COOLDOWNS.get(key)
        if not expiry:
            return False, 0

        remain = int(expiry - now)
        if remain <= 0:
            COOLDOWNS.pop(key, None)
            return False, 0

        return True, remain


async def set_cooldown(uid1: str, uid2: str, hours: int = COOLDOWN_HOURS):
    with COOLDOWN_LOCK:
        COOLDOWNS[_battle_key(uid1, uid2)] = time.time() + hours * 3600
    await save_cooldowns_to_api()


# =========================================================
# View
# =========================================================
class SpeedView(discord.ui.View):
    def __init__(self, session, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.session = session
        self.message = None
        self.last_click_by_user: Dict[str, float] = {}

        self.btn_x1 = discord.ui.Button(label="x1", style=discord.ButtonStyle.gray)
        self.btn_x2 = discord.ui.Button(label="x2", style=discord.ButtonStyle.gray)

        self.btn_x1.callback = self.set_x1
        self.btn_x2.callback = self.set_x2

        self.add_item(self.btn_x1)
        self.add_item(self.btn_x2)

    def refresh_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = False

        self.btn_x1.label = "x1"
        self.btn_x2.label = "x2"

        if self.session.delay <= 1:
            self.btn_x2.disabled = True
        else:
            self.btn_x1.disabled = False
            self.btn_x2.disabled = False

    def disable_all(self):
        for item in self.children:
            item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if getattr(self.session, "finished", False):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Trận đã kết thúc.", ephemeral=True)
            except Exception:
                pass
            return False

        uid = str(getattr(interaction.user, "id", ""))
        if uid not in {self.session.uid1, self.session.uid2}:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Chỉ 2 người đang đấu mới bấm được nút này.",
                        ephemeral=True,
                    )
            except Exception:
                pass
            return False

        now = time.time()
        last = self.last_click_by_user.get(uid, 0.0)
        if now - last < 0.5:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("⏳ Bấm chậm lại một chút.", ephemeral=True)
            except Exception:
                pass
            return False

        self.last_click_by_user[uid] = now
        return True

    async def set_x1(self, interaction: discord.Interaction):
        self.session.delay = 2
        self.refresh_buttons()
        try:
            await interaction.response.edit_message(embed=self.session.render(), view=self)
        except Exception as e:
            print(f"[fight.py] set_x1 error: {e}")

    async def set_x2(self, interaction: discord.Interaction):
        self.session.delay = 1
        self.refresh_buttons()
        try:
            await interaction.response.edit_message(embed=self.session.render(), view=self)
        except Exception as e:
            print(f"[fight.py] set_x2 error: {e}")

    async def on_timeout(self):
        self.disable_all()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception as e:
                print(f"[fight.py] view timeout edit error: {e}")


# =========================================================
# Fight session
# =========================================================
class FightSession:
    def __init__(self, ctx, uid1, uid2, ta, tb, inv, waifu, na, nb):
        self.ctx = ctx
        self.uid1 = str(uid1)
        self.uid2 = str(uid2)
        self.na = na
        self.nb = nb
        self.inv = inv
        self.waifu = waifu

        self.ta = [c for c in (build_char(self.uid1, w, inv, waifu) for w in ta) if isinstance(c, dict)]
        self.tb = [c for c in (build_char(self.uid2, w, inv, waifu) for w in tb) if isinstance(c, dict)]

        self.turn = 1
        self.delay = ACTION_DELAY
        self.finished = False
        self.sudden_death_applied = False
        self.love_drop_targets: Set[Tuple[str, str]] = set()
        self.logs: List[str] = []

        # Simple nickname cleanup for display only
        for c in self.ta + self.tb:
            c["hp"] = int(c["max_hp"])
            c["alive"] = True

    def log(self, text: str):
        self.logs.append(str(text))
        if len(self.logs) > 12:
            self.logs = self.logs[-12:]

    def mark_love_drop(self, uid: str, wid: str):
        self.love_drop_targets.add((str(uid), str(wid)))

    def alive(self, team: List[dict]) -> List[dict]:
        return [c for c in team if c.get("alive", True) and int(c.get("hp", 0)) > 0]

    def is_over(self):
        return not (self.alive(self.ta) and self.alive(self.tb))

    def choose_attacker(self, side: str) -> Optional[dict]:
        team = self.ta if side == "a" else self.tb
        alive = self.alive(team)
        if not alive:
            return None
        return random.choice(alive)

    def choose_defender(self, side: str) -> Optional[dict]:
        enemy = self.tb if side == "a" else self.ta
        alive = self.alive(enemy)
        if not alive:
            return None
        return random.choice(alive)

    def get_side_name(self, side: str) -> str:
        return self.na if side == "a" else self.nb

    def get_side_id(self, side: str) -> str:
        return self.uid1 if side == "a" else self.uid2

    def winner(self):
        a = self.alive(self.ta)
        b = self.alive(self.tb)
        if a and not b:
            return "a"
        if b and not a:
            return "b"
        return None

    def apply_sudden_death(self):
        if self.sudden_death_applied:
            return
        self.sudden_death_applied = True
        for c in self.alive(self.ta) + self.alive(self.tb):
            cut = max(1, int(c["max_hp"] * 0.15))
            c["hp"] = max(1, int(c["hp"]) - cut)
        self.log("⚡ SUDDEN DEATH kích hoạt!")

    def render(self):
        emb = discord.Embed(
            title="⚔️ Fight",
            description=f"**{self.na}** vs **{self.nb}**\nTurn: **{self.turn}/{MAX_ROUNDS}**",
            color=discord.Color.red(),
        )

        def team_block(team: List[dict]) -> str:
            if not team:
                return "Không có waifu."
            rows = []
            for c in team:
                rows.append(
                    f"**{c['name']}** [{c['rank']}] | HP `{int(c['hp'])}/{int(c['max_hp'])}` `{hp_bar(c['hp'], c['max_hp'])}`"
                )
            return "\n".join(rows)

        emb.add_field(name=self.na, value=team_block(self.ta), inline=False)
        emb.add_field(name=self.nb, value=team_block(self.tb), inline=False)

        if self.logs:
            emb.add_field(name="Log", value="\n".join(self.logs[-8:]), inline=False)

        emb.set_footer(text=f"Delay x{2 if self.delay >= 2 else 1} | Cooldown {COOLDOWN_HOURS}h")
        return emb

    async def attack(self, msg, attacker: dict, defender: dict, view: SpeedView):
        if not attacker or not defender:
            return

        if attacker["hp"] <= 0 or defender["hp"] <= 0:
            return

        dodge_chance = get_dodge_chance(attacker["speed"], defender["speed"])
        if random.random() < dodge_chance:
            self.log(f"🌀 {defender['name']} né đòn của {attacker['name']}!")
            await edit_like(msg, embed=self.render(), view=view)
            await asyncio.sleep(self.delay)
            return

        base_damage = int(attacker["damage"] * random.uniform(0.90, 1.10))
        base_damage = max(1, base_damage)

        is_crit = random.random() < attacker["crit_chance"]
        is_combo = is_crit and random.random() < 0.25

        if is_crit and random.random() < 0.20:
            heal = get_crit_heal_amount(attacker["max_hp"], is_combo)
            start_hp = attacker["hp"]
            attacker["hp"] = min(attacker["max_hp"], attacker["hp"] + heal)
            actual = attacker["hp"] - start_hp
            if actual > 0:
                if is_combo:
                    self.log(f"✨ {attacker['name']} COMBO HEAL hồi {actual} HP!")
                else:
                    self.log(f"✨ {attacker['name']} hồi {actual} HP nhờ chí mạng!")
            else:
                self.log(f"✨ {attacker['name']} kích hoạt hồi máu nhưng HP đã đầy.")
            await edit_like(msg, embed=self.render(), view=view)
            await asyncio.sleep(self.delay)
            return

        damage = get_crit_damage(base_damage, is_combo) if is_crit else base_damage
        damage = max(1, damage)

        defender["hp"] = max(0, defender["hp"] - damage)

        if is_crit and is_combo:
            self.log(f"💥 {attacker['name']} COMBO CRIT {defender['name']} gây {damage} dame!")
        elif is_crit:
            self.log(f"💥 {attacker['name']} CRIT {defender['name']} gây {damage} dame!")
        else:
            self.log(f"⚔️ {attacker['name']} đánh {defender['name']} gây {damage} dame!")

        if defender["hp"] <= 0 and defender["alive"]:
            defender["alive"] = False
            old_love = get_love(self.inv, defender["uid"], defender["wid"])
            new_love = drop_love(self.inv, defender["uid"], defender["wid"])
            self.mark_love_drop(defender["uid"], defender["wid"])
            self.log(f"☠️ {defender['name']} đã bị hạ gục. Love giảm từ {old_love} còn {new_love}.")

        heal = min(
            int(attacker["max_hp"] * 0.25),
            int(damage * attacker.get("lifesteal", 0)),
        )
        if heal > 0 and attacker["hp"] > 0 and attacker["hp"] < attacker["max_hp"]:
            start_hp = attacker["hp"]
            attacker["hp"] = min(attacker["max_hp"], attacker["hp"] + heal)
            actual = attacker["hp"] - start_hp
            if actual > 0:
                self.log(f"🩸 {attacker['name']} hút {actual} HP.")

        await edit_like(msg, embed=self.render(), view=view)
        await asyncio.sleep(self.delay)

    async def play_round(self, msg, view: SpeedView):
        if self.is_over():
            return

        if self.turn == MAX_ROUNDS and not self.sudden_death_applied:
            self.apply_sudden_death()
            if self.is_over():
                return

        speed_a = sum(c["speed"] for c in self.alive(self.ta))
        speed_b = sum(c["speed"] for c in self.alive(self.tb))

        roll_a = speed_a + random.randint(0, max(1, speed_a // 5 + 1))
        roll_b = speed_b + random.randint(0, max(1, speed_b // 5 + 1))
        order = ("a", "b") if roll_a >= roll_b else ("b", "a")

        for side in order:
            if self.is_over():
                break
            attacker = self.choose_attacker(side)
            defender = self.choose_defender(side)
            if not attacker or not defender:
                continue
            await self.attack(msg, attacker, defender, view)

    async def play(self, msg):
        view = SpeedView(self, timeout=max(300, MAX_ROUNDS * (ACTION_DELAY + 5)))
        view.message = msg
        await edit_like(msg, embed=self.render(), view=view)

        while not self.is_over() and self.turn <= MAX_ROUNDS:
            await self.play_round(msg, view)
            self.turn += 1

        self.finished = True
        view.disable_all()
        await edit_like(msg, embed=self.render(), view=view)
        return view

    async def commit(self):
        if not self.love_drop_targets:
            return

        grouped: Dict[str, Set[str]] = {}
        for uid, wid in self.love_drop_targets:
            grouped.setdefault(str(uid), set()).add(str(wid))

        async with INV_LOCK:
            latest_all = await load_inventory_db()
            if not isinstance(latest_all, dict):
                latest_all = {}

            for uid, wids in grouped.items():
                user_inv = latest_all.get(uid, {})
                if not isinstance(user_inv, dict):
                    user_inv = {}

                waifus = user_inv.get("waifus", {})
                if isinstance(waifus, list):
                    waifus = {str(w): 0 for w in waifus}
                elif not isinstance(waifus, dict):
                    waifus = {}

                for wid in wids:
                    current = waifus.get(wid, 0)
                    if isinstance(current, dict):
                        current_love = current.get("love", current.get("amount", 0))
                    else:
                        current_love = current

                    try:
                        current_love = max(0, int(current_love))
                    except Exception:
                        current_love = 0

                    new_love = max(0, int(current_love * (1 - LOVE_DROP_RATE)))
                    if isinstance(waifus.get(wid), dict):
                        waifus[wid]["love"] = new_love
                        if "amount" in waifus[wid]:
                            waifus[wid]["amount"] = new_love
                    else:
                        waifus[wid] = new_love

                user_inv["waifus"] = waifus
                latest_all[uid] = user_inv
                await api_client.post(f"/inventory/{uid}/update", user_inv)

            self.inv = latest_all


# =========================================================
# Public entrypoint
# =========================================================
def _resolve_opponent(opponent):
    if opponent is None:
        return None, None

    if hasattr(opponent, "id"):
        uid = str(opponent.id)
        name = getattr(opponent, "display_name", getattr(opponent, "name", f"<@{uid}>"))
        return uid, name

    if isinstance(opponent, (str, int)):
        raw = str(opponent).strip()
        digits = re.sub(r"\D", "", raw)
        uid = digits if digits else raw
        name = f"<@{uid}>" if digits else raw
        return uid, name

    return None, None


async def transfer_gold_safely(winner: str, loser: str, amount: int) -> bool:
    amount = max(0, int(amount))
    if amount <= 0:
        return True

    ok_remove = await data_user.remove_gold(str(loser), amount)
    if not ok_remove:
        return False

    ok_add = await data_user.add_gold(str(winner), amount)
    if not ok_add:
        await data_user.add_gold(str(loser), amount)
        return False

    return True


async def fight_logic(ctx, opponent):
    await _defer_if_interaction(ctx)
    await ensure_cooldowns_loaded()

    user = get_user_obj(ctx)
    if not user:
        return await send_like(ctx, content="❌ Không xác định user")

    uid1 = str(user.id)
    user_name = getattr(user, "display_name", getattr(user, "name", f"<@{uid1}>"))

    uid2, opponent_name = _resolve_opponent(opponent)
    if not uid2:
        return await send_like(ctx, content="❌ Chọn đối thủ hợp lệ")

    if uid1 == uid2:
        return await send_like(ctx, content="❌ Không thể tự đánh")

    on_cd, remain = is_on_cooldown(uid1, uid2)
    if on_cd:
        hrs = remain // 3600
        mins = (remain % 3600) // 60
        return await send_like(ctx, content=f"⏳ Hai người đã đấu gần đây. Còn cooldown {hrs}h {mins}p.")

    async with BATTLE_STATE_LOCK:
        if uid1 in ACTIVE_BATTLE_USERS or uid2 in ACTIVE_BATTLE_USERS:
            return await send_like(ctx, content="⏳ Đang trong trận khác")

        ACTIVE_BATTLE_USERS.add(uid1)
        ACTIVE_BATTLE_USERS.add(uid2)

    try:
        async with INV_LOCK:
            inv = await load_inventory_db()
            waifu = await load_waifu_db()
            team = await load_team_db()

        if str(uid1) not in inv or str(uid2) not in inv:
            return await send_like(ctx, content="❌ Một trong hai người chưa có inventory.")

        ta = normalize_team_ids(inv, uid1, team)
        tb = normalize_team_ids(inv, uid2, team)

        if not ta:
            return await send_like(ctx, content="❌ Bạn không có team")
        if not tb:
            return await send_like(ctx, content="❌ Đối thủ không có team")

        session = FightSession(
            ctx=ctx,
            uid1=uid1,
            uid2=uid2,
            ta=ta,
            tb=tb,
            inv=copy.deepcopy(inv),
            waifu=waifu,
            na=user_name,
            nb=opponent_name,
        )

        if not session.ta:
            return await send_like(ctx, content="❌ Team bạn lỗi hoặc rỗng")
        if not session.tb:
            return await send_like(ctx, content="❌ Team đối thủ lỗi hoặc rỗng")

        msg = await send_like(ctx, content="⚔️ Fight!", embed=session.render())
        if not msg:
            return

        await session.play(msg)

        win = session.winner()
        t = max(1, session.turn - 1)
        rate = get_gold_rate_by_turn(t)

        if not win:
            await session.commit()
            await set_cooldown(uid1, uid2)

            result_embed = discord.Embed(
                title="Kết quả",
                description=f"Trận chiến giữa {user_name} và {opponent_name} đã kết thúc với tỉ số hòa.",
                color=discord.Color.gold(),
            )
            result_embed.add_field(name="Phần thưởng", value="Không có gold.", inline=False)
            result_embed.set_footer(text=f"Turn hoàn thành: {t} | Cooldown {COOLDOWN_HOURS}h")

            await edit_like(msg, content=None, embed=result_embed, view=None)
            return

        winner = uid1 if win == "a" else uid2
        loser = uid2 if win == "a" else uid1

        try:
            loser_data = await api_client.get_user_data(loser)
            loser_gold = int((loser_data or {}).get("gold", 0))
        except Exception:
            loser_gold = 0

        bonus = max(0, min(loser_gold, int(loser_gold * rate)))
        transferred = await transfer_gold_safely(winner, loser, bonus)

        await session.commit()
        await set_cooldown(uid1, uid2)

        win_name = session.get_side_name(win)
        lose_name = session.get_side_name("b" if win == "a" else "a")

        result_embed = discord.Embed(
            title="Kết quả",
            description=f"🏆 **{win_name}** đã chiến thắng **{lose_name}**.",
            color=discord.Color.green(),
        )
        reward_text = f"{bonus} gold"
        if bonus > 0:
            reward_text += " (đã chuyển)"
        if not transferred:
            reward_text += " — chuyển thất bại, nhưng trận đấu vẫn hoàn tất."
        result_embed.add_field(name="Phần thưởng", value=reward_text, inline=False)
        result_embed.set_footer(text=f"Turn hoàn thành: {t} | Cooldown {COOLDOWN_HOURS}h")

        await edit_like(msg, content=None, embed=result_embed, view=None)

    finally:
        async with BATTLE_STATE_LOCK:
            ACTIVE_BATTLE_USERS.discard(uid1)
            ACTIVE_BATTLE_USERS.discard(uid2)


# =========================================================
# Cog / command
# =========================================================
class FightCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="fight", aliases=["f", "chien"])
    async def fight_cmd(self, ctx, *, opponent=None):
        if not opponent:
            return await send_like(ctx, content="❌ Dùng: `.fight @user`")

        await fight_logic(ctx, opponent)


async def setup(bot):
    await bot.add_cog(FightCog(bot))
    print("Loaded fight has success")
