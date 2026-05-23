# ══════════════════════════════════════════════════════
#  cogs/scheduler.py  —  Daily announcements and streak management
# ══════════════════════════════════════════════════════

import asyncio
import random
from datetime import datetime, timezone, timedelta
import discord
from discord.ext import commands, tasks

import database as db
from config import PROGRESS_CHANNEL, TIER_ROLES

IST = timezone(timedelta(hours=5, minutes=30))

CP_QUOTES = [
    "Every expert was once a beginner. 💪",
    "Consistency is the difference between failure and success. 🚀",
    "First, solve the problem. Then, write the code. 🎯",
    "Talk is cheap. Show me the code. 💻",
    "The only way to learn is by doing. Keep grinding! 🔥",
    "You don't have to be great to start, but you have to start to be great. 🌟",
    "Clean code always looks like it was written by someone who cares. 💎",
    "Slow and steady wins the race. AC is the goal! 🐢",
    "If it was easy, everyone would do it. Push your limits! 🦾",
    "Every red coder was once an unrated newbie. Keep climbing! 👑",
]


class Scheduler(commands.Cog):
    """Cog for managing daily announcements and checking streak resets."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.daily_morning_task.start()
        self.streak_reset_checker.start()

    async def cog_unload(self) -> None:
        self.daily_morning_task.cancel()
        self.streak_reset_checker.cancel()

    # ── Commands ───────────────────────────────────────

    @commands.command(name="freeze")
    @commands.guild_only()
    async def streak_freeze(self, ctx: commands.Context) -> None:
        """Activate a streak freeze to protect your streak for 1 day (1 per week limit)."""
        now = datetime.now(IST)
        current_week_str = now.strftime("%Y-%U") # Year and Week number

        freeze_row = db.get_freeze(ctx.author.id)
        if freeze_row:
            last_used_str = freeze_row["last_freeze_used"]
            # Check if last used date belongs to the same week
            try:
                last_used = datetime.fromisoformat(last_used_str)
                last_week_str = last_used.strftime("%Y-%U")
                if current_week_str == last_week_str:
                    await ctx.reply(
                        "❌ You have already used your free streak freeze for this week!\n"
                        "Your weekly limit resets every Sunday midnight. 🛡️"
                    )
                    return
            except ValueError:
                pass

        # Activate freeze
        today_iso = now.date().isoformat()
        db.use_freeze(ctx.author.id, today_iso)

        embed = discord.Embed(
            title="❄️ Streak Freeze Activated!",
            description=(
                f"**{ctx.author.mention}**, your streak has been frozen for today!\n\n"
                f"> 🛡️ **Status:** Protected\n"
                f"> 📅 **Date:** `{today_iso}`\n"
                f"> ⏳ **Weekly Limit:** `1/1 Used` (Resets Sunday midnight)\n\n"
                f"You have 1 extra day to submit your next `day done` update without resetting!"
            ),
            color=0x3498DB
        )
        embed.set_footer(text="AGNoobies Streak Protection")
        await ctx.reply(embed=embed)

    # ── Tasks ──────────────────────────────────────────

    @tasks.loop(hours=24)
    async def daily_morning_task(self) -> None:
        """Sends a beautiful daily morning motivation card at 8 AM IST."""
        try:
            now = datetime.now(IST)
            target = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            delay = (target - now).total_seconds()
            print(f"[Scheduler Morning] Waiting {delay} seconds until next 8 AM IST.")
            await asyncio.sleep(delay)

            # Get top grinder
            progress_rows = db.get_all_progress()
            top_user = "None"
            top_day = 0

            if progress_rows:
                best_row = max(progress_rows, key=lambda r: r["current_day"])
                top_user = best_row["username"].split("#")[0]
                top_day = best_row["current_day"]

            quote = random.choice(CP_QUOTES)

            for guild in self.bot.guilds:
                channel = discord.utils.get(guild.channels, name=PROGRESS_CHANNEL)
                if not channel:
                    continue

                embed = discord.Embed(
                    title="☀️ Good Morning, Coders!",
                    description=(
                        f"**Today's Goal:** Stay consistent, solve at least 1 problem! 🎯\n\n"
                        f"🏆 **Current Top Grinder:** `{top_user}` at Day **{top_day}**\n"
                        f"💬 **Remember:** *\"{quote}\"*"
                    ),
                    color=0xF1C40F
                )
                embed.set_footer(text="AGNoobies Daily Grind")
                await channel.send(embed=embed)
        except Exception as e:
            print(f"[Scheduler Daily Morning Task] Loop Error: {e}")

    @daily_morning_task.before_loop
    async def before_morning(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def streak_reset_checker(self) -> None:
        """Every day at midnight IST, checks active streaks and applies warning/resets."""
        try:
            now = datetime.now(IST)
            target = now.replace(hour=0, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            delay = (target - now).total_seconds()
            print(f"[Scheduler Midnight] Waiting {delay} seconds until next midnight IST.")
            await asyncio.sleep(delay)

            # Run streak checks
            progress_rows = db.get_all_progress()
            if not progress_rows:
                return

            utc_now = datetime.now(timezone.utc)
            beginner_tier = TIER_ROLES[0] # Beginner

            for row in progress_rows:
                user_id = row["user_id"]
                username = row["username"]
                current_day = row["current_day"]
                updated_at_str = row["updated_at"]

                if current_day == 0:
                    continue

                try:
                    last_update = datetime.fromisoformat(updated_at_str)
                    delta_days = (utc_now - last_update).days

                    # Check if they have an active freeze used in the last 2 days
                    has_active_freeze = False
                    freeze_row = db.get_freeze(user_id)
                    if freeze_row:
                        last_used_str = freeze_row["last_freeze_used"]
                        last_used_date = datetime.fromisoformat(last_used_str).date()
                        # If freeze used yesterday or today
                        if (utc_now.date() - last_used_date).days <= 2:
                            has_active_freeze = True

                    # If they have an active freeze, give them 1 day extension
                    effective_delta = delta_days - 1 if has_active_freeze else delta_days

                    if effective_delta == 2:
                        # DM Warning
                        for guild in self.bot.guilds:
                            member = guild.get_member(user_id)
                            if member:
                                try:
                                    await member.send(
                                        f"⚠️ **Hey {member.display_name}!** You haven't updated your progress in **2 days**.\n"
                                        f"Submit your next update in #{PROGRESS_CHANNEL} today, or your streak will **reset tomorrow**! 📉"
                                    )
                                    print(f"[Scheduler Reset] Sent warning DM to {username}")
                                except discord.Forbidden:
                                    print(f"[Scheduler Reset] Failed to DM warning to {username} (DMs closed)")
                                break

                    elif effective_delta >= 3:
                        # Reset Streak
                        db.reset_progress(user_id)
                        print(f"[Scheduler Reset] Streak reset for {username} (Day {current_day} → 0)")

                        # Strip roles and assign Beginner
                        for guild in self.bot.guilds:
                            member = guild.get_member(user_id)
                            if member:
                                # Strip all day/tier roles
                                tier_names = {t["name"] for t in TIER_ROLES}
                                roles_to_remove = [r for r in member.roles if r.name in tier_names or r.name.startswith("Day ")]
                                try:
                                    if roles_to_remove:
                                        await member.remove_roles(*roles_to_remove, reason="Streak reset: inactive for 3 days")
                                    
                                    # Assign Beginner
                                    beginner_role = discord.utils.get(guild.roles, name=beginner_tier["name"])
                                    if beginner_role:
                                        await member.add_roles(beginner_role, reason="Streak reset: set to Beginner")
                                except discord.Forbidden:
                                    print(f"[Scheduler Reset] [ERROR] FORBIDDEN resetting roles for {username}")

                                # Notify via DM
                                try:
                                    await member.send(
                                        f"❌ **Streak Reset!** You haven't updated your progress in **3 days**.\n"
                                        f"Your progress has been reset to **Day 0** and your rank has been set back to **Beginner**.\n"
                                        f"Grind again to regain your consistency! 💪"
                                    )
                                except discord.Forbidden:
                                    pass
                                break
                except Exception as e:
                    print(f"[Scheduler Reset] Error checking {username}: {e}")
        except Exception as e:
            print(f"[Scheduler Streak Reset Checker] Loop Error: {e}")

    @streak_reset_checker.before_loop
    async def before_reset(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Scheduler(bot))
