# ══════════════════════════════════════════════════════
#  cogs/progress.py  —  Progress tracking cog
# ══════════════════════════════════════════════════════

import re
import discord
from discord.ext import commands

import database as db
from config import PROGRESS_CHANNEL, DAY_ROLES, PHASE_ROLES, TIER_ROLES
from utils.helpers import (
    congrats_message, get_phase_role_for_day, levelup_message,
    get_tier_progress, TIER_EMOJI, motivation,
)

_DAY_RE = re.compile(
    r"(?:completed\s+day[\s\-_]*(\d+)|day[\s\-_]*(\d+)[\s\-_]*(?:lecture[\s\-_]*)?(?:done|complete))",
    re.IGNORECASE
)
_TIER_NAMES: set[str] = {t["name"] for t in TIER_ROLES}


def _get_tier_for_day(day: int) -> dict | None:
    info = get_tier_progress(day)
    return info["current_tier"] if info else None


class Progress(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    def _parse_day(content: str) -> int | None:
        m = _DAY_RE.search(content)
        if m:
            val = m.group(1) or m.group(2)
            if val:
                return int(val)
        return None

    @staticmethod
    async def _get_or_create_role(guild: discord.Guild, name: str) -> discord.Role:
        role = discord.utils.get(guild.roles, name=name)
        if role is None:
            print(f"[Roles] '{name}' not found, creating...")
            role = await guild.create_role(name=name, reason="Auto-created by tracker")
        return role

    async def _apply_day_and_phase_roles(self, member: discord.Member, day: int) -> None:
        old = [r for r in member.roles if r.name in DAY_ROLES.values()]
        if old:
            try:
                await member.remove_roles(*old, reason="Progress: swap day role")
                print(f"[Roles] Removed old day roles from {member}: {[r.name for r in old]}")
            except discord.Forbidden:
                print(f"[Roles] [ERROR] FORBIDDEN removing day roles from {member}. Fix bot hierarchy.")
                return

        if day in DAY_ROLES:
            r = await self._get_or_create_role(member.guild, DAY_ROLES[day])
            try:
                print(f"[Roles] [OK] Assigned '{r.name}' to {member}")
            except discord.Forbidden:
                print(f"[Roles] [ERROR] FORBIDDEN assigning '{r.name}' - move bot role ABOVE it.")

        phase = get_phase_role_for_day(day, PHASE_ROLES)
        if phase:
            pr = await self._get_or_create_role(member.guild, phase)
            try:
                await member.add_roles(pr, reason=f"Phase milestone: {phase}")
                print(f"[Roles] [OK] Awarded phase '{phase}' to {member}")
            except discord.Forbidden:
                print(f"[Roles] [ERROR] FORBIDDEN assigning phase '{phase}'.")

    async def _apply_tier_role(
        self, member: discord.Member, day: int, channel: discord.TextChannel
    ) -> None:
        info = get_tier_progress(day)
        if not info:
            return
        new_tier = info["current_tier"]
        new_name = new_tier["name"]
        print(f"[Roles] {member} day={day} → tier='{new_name}'")

        cur_tier_roles = [r for r in member.roles if r.name in _TIER_NAMES]
        old_name = cur_tier_roles[0].name if cur_tier_roles else None
        if old_name == new_name:
            print(f"[Roles] {member} already '{new_name}', no change.")
            return

        if cur_tier_roles:
            try:
                await member.remove_roles(*cur_tier_roles, reason="Tier update")
                print(f"[Roles] [OK] Removed old tier {[r.name for r in cur_tier_roles]} from {member}")
            except discord.Forbidden:
                print(f"[Roles] [ERROR] FORBIDDEN removing tier roles from {member}.")

        new_role = discord.utils.get(member.guild.roles, name=new_name)
        if new_role is None:
            print(f"[Roles] '{new_name}' missing - auto-creating. Run !setup first.")
            try:
                new_role = await member.guild.create_role(
                    name=new_name,
                    color=discord.Color(new_tier["color"]),
                    permissions=discord.Permissions(**new_tier["perms"]),
                    hoist=True, mentionable=True,
                    reason="Auto-created by tracker",
                )
            except discord.Forbidden:
                print(f"[Roles] [ERROR] FORBIDDEN creating '{new_name}'.")
                return

        try:
            await member.add_roles(new_role, reason=f"Tier: {new_name}")
            print(f"[Roles] [OK] Assigned tier '{new_name}' to {member}")
        except discord.Forbidden:
            print(f"[Roles] [ERROR] FORBIDDEN assigning '{new_name}' - move bot role ABOVE it.")
            return

        await channel.send(levelup_message(member.mention, new_name, day))

    # ── Message listener ───────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        # Ensure other commands are not blocked
        await self.bot.process_commands(message)

        if message.guild is None:
            return
        if message.channel.name != PROGRESS_CHANNEL:
            return

        day = self._parse_day(message.content)
        if day is None or day <= 0:
            return

        member = message.guild.get_member(message.author.id)
        if member is None:
            return

        # ── Day validation ─────────────────────────────
        row = db.get_progress(member.id)
        current_day  = row["current_day"] if row else 0
        expected_day = current_day + 1

        from datetime import datetime, timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        today_ist = datetime.now(ist_tz).strftime("%Y-%m-%d")

        if row and row.get("last_updated"):
            last_date_ist = row["last_updated"][:10]
            if last_date_ist == today_ist:
                await message.reply("❌ You already logged your progress today! Come back tomorrow grinder 💪")
                return

        if day == current_day:
            await message.reply(
                f"⛔ **WA** — Duplicate submission! Day **{day}** already **AC** ✅\n"
                f"Submit `day {expected_day} done` next."
            )
            return

        if day < current_day:
            await message.reply(
                f"⛔ **WA** — You've already passed Day **{day}** "
                f"(currently on Day {current_day}). Submit `day {expected_day} done`."
            )
            return

        if day > expected_day:
            if current_day == 0:
                await message.reply(
                    "⛔ **WA** — First submission must be `day 1 done`. "
                    "Your journey starts at Day 1! 🚀"
                )
            else:
                await message.reply(
                    f"⛔ **WA** — You are on Day **{current_day}**, "
                    f"cannot skip to Day **{day}**!\n"
                    f"**Penalty:** submit `day {expected_day} done` first. 💪"
                )
            return

        # ── Valid submission ────────────────────────────

        # 1. Tier role (most visible)
        await self._apply_tier_role(member, day, message.channel)
        # 2. Day / Phase roles
        await self._apply_day_and_phase_roles(member, day)
        # 3. Persist
        db.save_progress(message.author.id, str(message.author), day)
        # 3b. Award XP and Coins (+30 XP, +15 coins)
        from cogs.economy import award_xp_and_coins
        try:
            await award_xp_and_coins(self.bot, message.guild, message.author.id, 30, 15, reason="day_completed")
        except Exception as e:
            print(f"[Progress XP Award] Error: {e}")
        # 3c. Trigger achievements check
        try:
            ach_cog = self.bot.get_cog("Achievements")
            if ach_cog:
                await ach_cog.check_achievements(message.guild, message.author.id)
        except Exception as e:
            print(f"[Progress Achievements] Error: {e}")
        # 4. Congrats reply
        text = congrats_message(message.author.mention, day)
        phase = get_phase_role_for_day(day, PHASE_ROLES)
        if phase:
            text += f"\n🏅 Milestone reached — **{phase}** role awarded!"
        await message.reply(text)

    # ── Commands ───────────────────────────────────────

    @commands.command(name="progress", aliases=["myprogress", "rank", "stats"])
    async def my_progress(self, ctx: commands.Context) -> None:
        """Show your personal CP-style progress stats card."""
        row = db.get_progress(ctx.author.id)

        if not row:
            embed = discord.Embed(
                title="🖥️ Progress Report",
                description=(
                    "```\n"
                    "STATUS   : NOT STARTED\n"
                    "Day      : 0\n"
                    "Tier     : None\n"
                    "```\n"
                    f"Submit `day 1 done` in **#{PROGRESS_CHANNEL}** to begin!"
                ),
                color=0x2C2F33,
            )
            await ctx.reply(embed=embed)
            return

        current_day = row["current_day"]
        info        = get_tier_progress(current_day)
        tier        = info["current_tier"]
        tier_name   = tier["name"]
        tier_emoji  = TIER_EMOJI.get(tier_name, "")
        next_name   = info["next_tier"]["name"] if info["next_tier"] else "MAX"
        bar         = info["bar"]
        days_left   = info["days_to_next"]
        motiv       = motivation(tier_name, days_left)

        cf_row    = db.get_cf_user(ctx.author.id)
        cf_handle = cf_row["cf_handle"] if cf_row else "Not linked"
        cf_url    = f"https://codeforces.com/profile/{cf_handle}" if cf_row else None
        cf_str    = f"[{cf_handle}]({cf_url})" if cf_row else "`Not linked — use !setcf`"

        embed = discord.Embed(
            title=f"🖥️ Progress Report — {ctx.author.display_name}",
            color=discord.Color(tier["color"]),
        )
        embed.add_field(
            name="📊 STATUS",
            value=(
                f"```\n"
                f"Day      : {current_day}\n"
                f"Tier     : {tier_emoji} {tier_name}\n"
                f"Next     : {next_name}\n"
                f"```"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"⚡ PROGRESS TO {next_name.upper()}",
            value=f"`{bar}`",
            inline=False,
        )
        embed.add_field(name="💻 CODEFORCES", value=cf_str, inline=True)
        embed.add_field(
            name="📅 LAST SUBMISSION",
            value=f"`{row['updated_at'][:10]}`",
            inline=True,
        )
        embed.add_field(name="💬 MOTIVATION", value=motiv, inline=False)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="AGNoobies • Competitive Programming Tracker")
        await ctx.reply(embed=embed)

    @commands.command(name="leaderboard", aliases=["lb", "standings"])
    async def leaderboard(self, ctx: commands.Context) -> None:
        """Show contest standings for this server (top 10)."""
        rows = db.get_all_progress()
        if not rows:
            await ctx.reply("No progress data yet. Be the first! 🚀")
            return

        sorted_rows = sorted(rows, key=lambda r: r["current_day"], reverse=True)[:10]
        medals      = ["🥇", "🥈", "🥉"]

        embed = discord.Embed(
            title="🏆 CONTEST STANDINGS",
            description="```\n#    Name                 Day   Tier\n" + "─" * 44 + "```",
            color=0x2C2F33,
        )

        lines: list[str] = []
        for i, row in enumerate(sorted_rows):
            medal    = medals[i] if i < 3 else f"`{i + 1:2d}.`"
            tier     = _get_tier_for_day(row["current_day"])
            emoji    = TIER_EMOJI.get(tier["name"], "  ") if tier else "  "
            tier_name = tier["name"] if tier else "—"
            # Trim name to 18 chars for alignment
            name     = row["username"].split("#")[0][:18]
            lines.append(
                f"{medal}  **{name}** — Day **{row['current_day']}**  {emoji} {tier_name}"
            )

        embed.add_field(name="\u200b", value="\n".join(lines), inline=False)
        embed.set_footer(
            text=f"Showing top {len(sorted_rows)} of {len(rows)} participants"
        )
        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Progress(bot))
