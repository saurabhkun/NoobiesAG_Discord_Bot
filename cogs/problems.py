# ══════════════════════════════════════════════════════
#  cogs/problems.py  —  CP Problem Recommendations & Duels
# ══════════════════════════════════════════════════════

import asyncio
import random
from datetime import datetime, timezone, timedelta
import aiohttp
import discord
from discord.ext import commands, tasks

import database as db
from config import PROGRESS_CHANNEL

# Timezone for IST
IST = timezone(timedelta(hours=5, minutes=30))


class Problems(commands.Cog):
    """Cog for problem recommendations, daily problem challenge, and virtual duels."""

    CF_BASE = "https://codeforces.com/api"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession()
        self.daily_recommendation.start()
        self.duel_checker.start()

    async def cog_unload(self) -> None:
        self.daily_recommendation.cancel()
        self.duel_checker.cancel()
        if self._session:
            await self._session.close()

    # ── CF API Helpers ──────────────────────────────────

    async def _fetch_json(self, url: str) -> dict | None:
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"[Problems API] Error fetching {url}: {e}")
        return None

    async def _get_solved_problems(self, cf_handle: str) -> set[str]:
        """Return set of problem keys (e.g. '123A') solved by the user."""
        url = f"{self.CF_BASE}/user.status?handle={cf_handle}"
        data = await self._fetch_json(url)
        solved = set()
        if data and data.get("status") == "OK":
            for sub in data["result"]:
                if sub.get("verdict") == "OK":
                    prob = sub.get("problem", {})
                    c_id = prob.get("contestId")
                    idx = prob.get("index")
                    if c_id and idx:
                        solved.add(f"{c_id}{idx}")
        return solved

    async def _get_user_rating(self, cf_handle: str) -> int:
        """Fetch current rating, default to 800 if unrated or error."""
        url = f"{self.CF_BASE}/user.info?handles={cf_handle}"
        data = await self._fetch_json(url)
        if data and data.get("status") == "OK":
            info = data["result"][0]
            return info.get("rating", 800)
        return 800

    async def _pick_problem(self, solved_sets: list[set[str]], target_rating: int) -> dict | None:
        """Pick a random problem of target_rating that isn't solved in any of the solved_sets."""
        url = f"{self.CF_BASE}/problemset.problems"
        data = await self._fetch_json(url)
        if not data or data.get("status") != "OK":
            return None

        problems = data["result"]["problems"]
        candidates = []
        for p in problems:
            if p.get("rating") == target_rating:
                c_id = p.get("contestId")
                idx = p.get("index")
                if c_id and idx:
                    key = f"{c_id}{idx}"
                    # Check if solved by any of the sets
                    if not any(key in s for s in solved_sets):
                        candidates.append(p)

        if candidates:
            return random.choice(candidates)
        return None

    # ── Commands ───────────────────────────────────────

    @commands.command(name="giveproblem")
    async def give_problem(self, ctx: commands.Context, rating: int = None) -> None:
        """Get a random unsolved problem of a specific rating."""
        if rating is None:
            await ctx.reply("❌ Usage: `!giveproblem <rating>` (e.g. `!giveproblem 1200`)")
            return

        cf_row = db.get_cf_user(ctx.author.id)
        if not cf_row:
            await ctx.reply("❌ Link your CF account first with `!setcf <handle>`")
            return

        cf_handle = cf_row["cf_handle"]
        async with ctx.typing():
            solved = await self._get_solved_problems(cf_handle)
            prob = await self._pick_problem([solved], rating)

            if not prob:
                await ctx.reply(f"❌ No unsolved problems found with rating `{rating}`.")
                return

            c_id = prob["contestId"]
            idx = prob["index"]
            name = prob["name"]
            tags = ", ".join(prob.get("tags", []))
            url = f"https://codeforces.com/contest/{c_id}/problem/{idx}"

            embed = discord.Embed(
                title=f"🎯 Suggested Problem (Rating: {rating})",
                description=(
                    f"**[{name}]({url})**\n\n"
                    f"> 🏷️ **Tags:** `{tags}`\n"
                    f"> 🏟️ **Contest:** `{c_id}{idx}`"
                ),
                color=0x2C2F33
            )
            embed.set_footer(text=f"Codeforces • {cf_handle}", icon_url="https://codeforces.com/favicon.ico")
            await ctx.reply(embed=embed)

    @commands.command(name="virtualduel", aliases=["vd", "duel"])
    @commands.guild_only()
    async def virtual_duel(self, ctx: commands.Context, opponent: discord.Member = None) -> None:
        """Challenge another user to a virtual duel on a random suitable problem."""
        if opponent is None or opponent.bot or opponent == ctx.author:
            await ctx.reply("❌ Usage: `!virtualduel @user` to challenge a practice partner.")
            return

        # Check handles
        challenger_row = db.get_cf_user(ctx.author.id)
        opponent_row = db.get_cf_user(opponent.id)

        if not challenger_row:
            await ctx.reply("❌ You must link your Codeforces handle first with `!setcf`")
            return
        if not opponent_row:
            await ctx.reply(f"❌ {opponent.display_name} has not linked their Codeforces handle yet!")
            return

        # Check if either is already in an active duel
        if db.get_active_duel(ctx.author.id):
            await ctx.reply("❌ You are already in an active duel! Finish or let it expire first.")
            return
        if db.get_active_duel(opponent.id):
            await ctx.reply(f"❌ {opponent.display_name} is currently in another active duel.")
            return

        await ctx.reply(
            f"⚔️ **{ctx.author.display_name}** has challenged **{opponent.display_name}** to a Virtual Duel!\n"
            f"Fetching a suitable unsolved problem. Standby..."
        )

        async with ctx.typing():
            c_handle = challenger_row["cf_handle"]
            o_handle = opponent_row["cf_handle"]

            c_rating = await self._get_user_rating(c_handle)
            o_rating = await self._get_user_rating(o_handle)
            avg_rating = round((c_rating + o_rating) / 2 / 100) * 100
            if avg_rating < 800:
                avg_rating = 800

            c_solved = await self._get_solved_problems(c_handle)
            o_solved = await self._get_solved_problems(o_handle)

            prob = await self._pick_problem([c_solved, o_solved], avg_rating)
            if not prob:
                # Fallback to +/- 100 rating
                prob = await self._pick_problem([c_solved, o_solved], avg_rating + 100)
                if not prob:
                    prob = await self._pick_problem([c_solved, o_solved], avg_rating - 100)

            if not prob:
                await ctx.reply("❌ Could not find a suitable unsolved problem for both participants.")
                return

            c_id = prob["contestId"]
            idx = prob["index"]
            name = prob["name"]
            url = f"https://codeforces.com/contest/{c_id}/problem/{idx}"

            start_time = datetime.now(timezone.utc).isoformat()
            duration = 7200  # 2 hours in seconds

            db.create_duel(ctx.author.id, opponent.id, name, url, avg_rating, start_time, duration)

            embed = discord.Embed(
                title="⚔️ Virtual Duel Started!",
                description=(
                    f"**{ctx.author.mention}** vs **{opponent.mention}**\n\n"
                    f"🏆 **Target Problem:** **[{name}]({url})**\n"
                    f"📊 **Problem Rating:** `{avg_rating}`\n"
                    f"⏱️ **Time Limit:** 2 Hours (120 minutes)\n\n"
                    f"Both users must submit their solutions on Codeforces. "
                    f"The bot will check submissions every 5 minutes and crown the first to get **AC**!"
                ),
                color=0xE74C3C
            )
            embed.set_footer(text="AGNoobies Duel Arena")
            await ctx.send(embed=embed)

    # ── Tasks ──────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def duel_checker(self) -> None:
        """Check all active duels for AC submissions or expiration."""
        try:
            active_duels = db.get_all_active_duels()
            if not active_duels:
                return

            for duel in active_duels:
                c_id = duel["challenger_id"]
                o_id = duel["challenged_id"]
                start_str = duel["start_time"]
                duration = duel["duration"]
                prob_name = duel["problem_name"]
                prob_url = duel["problem_url"]

                c_row = db.get_cf_user(c_id)
                o_row = db.get_cf_user(o_id)

                if not c_row or not o_row:
                    continue

                c_handle = c_row["cf_handle"]
                o_handle = o_row["cf_handle"]

                start_time = datetime.fromisoformat(start_str)
                now = datetime.now(timezone.utc)
                elapsed = (now - start_time).total_seconds()

                # Fetch recent status
                c_subs = await self._fetch_json(f"{self.CF_BASE}/user.status?handle={c_handle}&count=10")
                o_subs = await self._fetch_json(f"{self.CF_BASE}/user.status?handle={o_handle}&count=10")

                c_ac_time = None
                o_ac_time = None

                def get_ac_time(subs_data):
                    if not subs_data or subs_data.get("status") != "OK":
                        return None
                    for sub in subs_data["result"]:
                        if sub.get("verdict") == "OK":
                            prob = sub.get("problem", {})
                            p_name = prob.get("name")
                            if p_name == prob_name:
                                sub_time = datetime.fromtimestamp(sub["creationTimeSeconds"], tz=timezone.utc)
                                if sub_time >= start_time:
                                    return sub_time
                    return None

                c_ac_time = get_ac_time(c_subs)
                o_ac_time = get_ac_time(o_subs)

                winner_id = None
                status = "active"

                if c_ac_time and o_ac_time:
                    if c_ac_time < o_ac_time:
                        winner_id = c_id
                        status = "challenger_won"
                    elif o_ac_time < c_ac_time:
                        winner_id = o_id
                        status = "challenged_won"
                    else:
                        status = "draw"
                elif c_ac_time:
                    winner_id = c_id
                    status = "challenger_won"
                elif o_ac_time:
                    winner_id = o_id
                    status = "challenged_won"
                elif elapsed >= duration:
                    status = "expired"

                if status != "active":
                    db.update_duel_status(c_id, o_id, start_str, status, winner_id)

                    # Announce in a suitable channel
                    for guild in self.bot.guilds:
                        channel = discord.utils.get(guild.channels, name=PROGRESS_CHANNEL)
                        if not channel:
                            continue

                        c_member = guild.get_member(c_id)
                        o_member = guild.get_member(o_id)
                        if not c_member or not o_member:
                            continue

                        if status in ["challenger_won", "challenged_won"]:
                            w_member = c_member if winner_id == c_id else o_member
                            l_member = o_member if winner_id == c_id else c_member
                            w_handle = c_handle if winner_id == c_id else o_handle
                            l_handle = o_handle if winner_id == c_id else c_handle

                            # Award XP & Coins (+100 XP, +50 coins)
                            from cogs.economy import award_xp_and_coins
                            try:
                                await award_xp_and_coins(self.bot, guild, winner_id, 100, 50, reason="duel_won")
                            except Exception as e:
                                print(f"[Duel XP Award] Error: {e}")

                            # Trigger achievements check
                            try:
                                ach_cog = self.bot.get_cog("Achievements")
                                if ach_cog:
                                    await ach_cog.check_achievements(guild, winner_id)
                            except Exception as e:
                                print(f"[Duel Achievements] Error: {e}")

                            embed = discord.Embed(
                                title="⚔️ Virtual Duel Ended!",
                                description=(
                                    f"🏆 **Winner:** {w_member.mention} (**{w_handle}**) got **AC** first! 🎉\n"
                                    f"💀 **Defeated:** {l_member.mention} (**{l_handle}**)\n\n"
                                    f"**Problem:** [{prob_name}]({prob_url})\n\n"
                                    f"🔼 {w_member.mention} earned **+100 XP** and **+50 coins**! 🪙"
                                ),
                                color=0x2ECC71
                            )
                            await channel.send(embed=embed)
                        elif status == "draw":
                            embed = discord.Embed(
                                title="⚔️ Virtual Duel Ended in a Draw!",
                                description=(
                                    f"🤝 Both {c_member.mention} and {o_member.mention} solved it simultaneously!\n\n"
                                    f"**Problem:** [{prob_name}]({prob_url})"
                                ),
                                color=0x3498DB
                            )
                            await channel.send(embed=embed)
                        elif status == "expired":
                            embed = discord.Embed(
                                title="⏱️ Virtual Duel Expired!",
                                description=(
                                    f"⌛ Time limit of 2 hours has expired!\n"
                                    f"Neither {c_member.mention} nor {o_member.mention} solved the problem.\n\n"
                                    f"**Verdict:** **No AC** (Draw/Expired)"
                                ),
                                color=0x7F8C8D
                            )
                            await channel.send(embed=embed)
        except Exception as e:
            print(f"[Problems Duel Checker Task] Loop Error: {e}")

    @duel_checker.before_loop
    async def before_duel_checker(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def daily_recommendation(self) -> None:
        """Every day at 9 AM IST post recommended problem in progress-updates."""
        try:
            # We need to run specifically at 9:00 AM IST.
            # Check current time in IST
            now = datetime.now(IST)
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            # Wait until next 9 AM IST
            delay = (target - now).total_seconds()
            print(f"[Problems Task] Waiting {delay} seconds until next 9 AM IST.")
            await asyncio.sleep(delay)

            # Run recommendation
            users = db.get_all_cf_users()
            if not users:
                return

            for guild in self.bot.guilds:
                channel = discord.utils.get(guild.channels, name=PROGRESS_CHANNEL)
                if not channel:
                    continue

                for user_row in users:
                    user_id = user_row["user_id"]
                    cf_handle = user_row["cf_handle"]
                    member = guild.get_member(user_id)
                    if not member:
                        continue

                    try:
                        rating = await self._get_user_rating(cf_handle)
                        target_rating = rating + 100  # Challenge slightly above
                        # Round to nearest 100
                        target_rating = round(target_rating / 100) * 100
                        if target_rating < 800:
                            target_rating = 800

                        solved = await self._get_solved_problems(cf_handle)
                        prob = await self._pick_problem([solved], target_rating)

                        if prob:
                            c_id = prob["contestId"]
                            idx = prob["index"]
                            p_name = prob["name"]
                            url = f"https://codeforces.com/contest/{c_id}/problem/{idx}"

                            embed = discord.Embed(
                                title=f"☀️ Daily Problem Recommendation",
                                description=(
                                    f"Good morning {member.mention}! Here is your daily CP challenge:\n\n"
                                    f"🎯 **[{p_name}]({url})** (Rating: `{target_rating}`)\n"
                                    f"🏷️ **Tags:** `{', '.join(prob.get('tags', []))}`"
                                ),
                                color=0xF1C40F
                            )
                            await channel.send(embed=embed)
                    except Exception as e:
                        print(f"[Problems Task] Error suggesting for {cf_handle}: {e}")
        except Exception as e:
            print(f"[Problems Daily Recommendation Task] Loop Error: {e}")

    @daily_recommendation.before_loop
    async def before_daily(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Problems(bot))
