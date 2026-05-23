# ══════════════════════════════════════════════════════
#  cogs/contests.py  —  Weekly mini-contests and contest alerts
# ══════════════════════════════════════════════════════

import asyncio
import random
from datetime import datetime, timezone, timedelta
import aiohttp
import discord
from discord.ext import commands, tasks

import database as db
from config import CF_ACTIVITY_CHANNEL

IST = timezone(timedelta(hours=5, minutes=30))


class Contests(commands.Cog):
    """Cog for managing Codeforces weekly mini-contests and upcoming contest notifications."""

    CF_BASE = "https://codeforces.com/api"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None
        self.notified_contests = set()

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession()
        # Initialize tables for contests cog if they don't exist
        with db._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS weekly_contest (
                    week_id  TEXT PRIMARY KEY, -- YYYY-WW
                    p1       TEXT NOT NULL,
                    p2       TEXT NOT NULL,
                    p3       TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS weekly_solves (
                    user_id  INTEGER NOT NULL,
                    week_id  TEXT NOT NULL,
                    p_key    TEXT NOT NULL,
                    PRIMARY KEY (user_id, week_id, p_key)
                );
            """)
        self.contest_alert_task.start()
        self.weekly_contest_manager.start()

    async def cog_unload(self) -> None:
        self.contest_alert_task.cancel()
        self.weekly_contest_manager.cancel()
        if self._session:
            await self._session.close()

    # ── CF API Helpers ──────────────────────────────────

    async def _fetch_json(self, url: str) -> dict | None:
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"[Contests API] Error: {e}")
        return None

    async def _get_random_problem(self, rating: int) -> str | None:
        data = await self._fetch_json(f"{self.CF_BASE}/problemset.problems")
        if not data or data.get("status") != "OK":
            return None
        problems = [
            p for p in data["result"]["problems"]
            if p.get("rating") == rating and p.get("contestId") and p.get("index")
        ]
        if problems:
            p = random.choice(problems)
            return f"{p['contestId']}_{p['index']}_{p['name']}"
        return None

    # ── Commands ───────────────────────────────────────

    @commands.command(name="contests", aliases=["upcoming"])
    async def upcoming_contests(self, ctx: commands.Context) -> None:
        """Display the next 5 upcoming Codeforces contests."""
        async with ctx.typing():
            data = await self._fetch_json(f"{self.CF_BASE}/contest.list?gym=false")
            if not data or data.get("status") != "OK":
                await ctx.reply("❌ Failed to fetch contest list from Codeforces.")
                return

            contests = [c for c in data["result"] if c.get("phase") == "BEFORE"]
            # Sort by start time (relativeTimeSeconds is negative, meaning seconds until contest starts)
            contests.sort(key=lambda c: -c.get("relativeTimeSeconds", 0))

            upcoming = contests[:5]
            if not upcoming:
                await ctx.reply("ℹ️ No upcoming Codeforces contests found.")
                return

            embed = discord.Embed(
                title="🖥️ Upcoming Codeforces Contests",
                color=0x2C2F33
            )

            for c in upcoming:
                name = c.get("name", "Unnamed Contest")
                c_id = c.get("id")
                duration_sec = c.get("durationSeconds", 0)
                duration_hr = duration_sec // 3600
                duration_min = (duration_sec % 3600) // 60
                rel_sec = -c.get("relativeTimeSeconds", 0)

                # Start time calculation
                start_ts = int(datetime.now(timezone.utc).timestamp() + rel_sec)
                start_time_ist = datetime.fromtimestamp(start_ts, tz=IST)
                start_str = start_time_ist.strftime("%d %b %Y, %I:%M %p IST")

                embed.add_field(
                    name=f"🏆 {name}",
                    value=(
                        f"📅 **Start:** `{start_str}`\n"
                        f"⏱️ **Duration:** `{duration_hr}h {duration_min}m`\n"
                        f"🔗 [Contest Link](https://codeforces.com/contests/{c_id})"
                    ),
                    inline=False
                )

            embed.set_footer(text="AGNoobies Contest Notifier")
            await ctx.reply(embed=embed)

    # ── Tasks ──────────────────────────────────────────

    @tasks.loop(hours=1)
    async def contest_alert_task(self) -> None:
        """Checks for upcoming contests and notifies if starting within 1 hour."""
        try:
            data = await self._fetch_json(f"{self.CF_BASE}/contest.list?gym=false")
            if not data or data.get("status") != "OK":
                return

            contests = [c for c in data["result"] if c.get("phase") == "BEFORE"]
            for c in contests:
                rel_sec = -c.get("relativeTimeSeconds", 0)
                c_id = c.get("id")

                # If contest starts in less than 1 hour (3600 seconds) and not yet notified
                if 0 < rel_sec <= 3600 and c_id not in self.notified_contests:
                    self.notified_contests.add(c_id)

                    duration_sec = c.get("durationSeconds", 0)
                    duration_hr = duration_sec // 3600
                    duration_min = (duration_sec % 3600) // 60
                    mins_left = rel_sec // 60

                    for guild in self.bot.guilds:
                        channel = discord.utils.get(guild.channels, name=CF_ACTIVITY_CHANNEL)
                        if not channel:
                            continue

                        embed = discord.Embed(
                            title="🚨 Contest Alert!",
                            description=(
                                f"🏆 **{c.get('name')}** is starting in **{mins_left} minutes**!\n\n"
                                f"> ⏱️ **Duration:** `{duration_hr}h {duration_min}m`\n"
                                f"> 🔗 **Register now:** [Codeforces Contests](https://codeforces.com/contest/{c_id})"
                            ),
                            color=0xE74C3C
                        )
                        await channel.send(embed=embed)
        except Exception as e:
            print(f"[Contests Alert Task] Loop Error: {e}")

    @contest_alert_task.before_loop
    async def before_contest_alert(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=10)
    async def weekly_contest_manager(self) -> None:
        """Manages weekly mini-contest: start on Monday 9 AM, end/leaderboard on Sunday 9 PM IST."""
        try:
            now = datetime.now(IST)
            week_id = now.strftime("%Y-%U") # Current year and week number

            # Get or create the weekly champion role
            # We need a temporary "Weekly Champion" role with yellow color
            async def get_champion_role(guild: discord.Guild) -> discord.Role:
                role = discord.utils.get(guild.roles, name="Weekly Champion")
                if not role:
                    role = await guild.create_role(
                        name="Weekly Champion",
                        color=discord.Color.from_rgb(241, 196, 15), # yellow
                        hoist=True,
                        reason="Weekly Contest reward role"
                    )
                return role

            # Monday 9 AM start check
            # We only announce if this week has not been announced yet
            with db._connect() as con:
                active_week = con.execute("SELECT * FROM weekly_contest WHERE week_id = ?", (week_id,)).fetchone()

            if not active_week and now.weekday() == 0 and now.hour >= 9:
                # Generate 3 problems: 1000, 1300, 1600 rating
                p1_str = await self._get_random_problem(1000) or "1200_A_fallback"
                p2_str = await self._get_random_problem(1300) or "1300_A_fallback"
                p3_str = await self._get_random_problem(1600) or "1600_A_fallback"

                with db._connect() as con:
                    con.execute(
                        "INSERT OR IGNORE INTO weekly_contest (week_id, p1, p2, p3) VALUES (?, ?, ?, ?)",
                        (week_id, p1_str, p2_str, p3_str)
                    )

                # Announce in cf-activity
                for guild in self.bot.guilds:
                    channel = discord.utils.get(guild.channels, name=CF_ACTIVITY_CHANNEL)
                    if not channel:
                        continue

                    def make_url(p_str):
                        parts = p_str.split("_")
                        return f"https://codeforces.com/contest/{parts[0]}/problem/{parts[1]}"

                    embed = discord.Embed(
                        title="🏆 Weekly Mini-Contest is LIVE!",
                        description=(
                            f"Grinders, a new week has started! Solve these 3 problems before Sunday 9 PM to win the **Weekly Champion** title!\n\n"
                            f"1️⃣ **Div3 Easy (Rating 1000):** [{p1_str.split('_')[2]}]({make_url(p1_str)})\n"
                            f"2️⃣ **Div2 Medium (Rating 1300):** [{p2_str.split('_')[2]}]({make_url(p2_str)})\n"
                            f"3️⃣ **Div1 Easy / Div2 Hard (Rating 1600):** [{p3_str.split('_')[2]}]({make_url(p3_str)})\n\n"
                            f"Bot will track your submissions automatically. Good luck! **AC** is the goal! 🚀"
                        ),
                        color=0xF1C40F
                    )
                    await channel.send(embed=embed)

            # Sync solves via CF API for all active week problems
            if active_week:
                users = db.get_all_cf_users()
                p1, p2, p3 = active_week["p1"], active_week["p2"], active_week["p3"]
                p_keys = {p1.split("_")[0] + p1.split("_")[1], p2.split("_")[0] + p2.split("_")[1], p3.split("_")[0] + p3.split("_")[1]}

                for user_row in users:
                    user_id = user_row["user_id"]
                    cf_handle = user_row["cf_handle"]

                    try:
                        url = f"{self.CF_BASE}/user.status?handle={cf_handle}&count=15"
                        sub_data = await self._fetch_json(url)
                        if sub_data and sub_data.get("status") == "OK":
                            for sub in sub_data["result"]:
                                if sub.get("verdict") == "OK":
                                    prob = sub.get("problem", {})
                                    c_id = prob.get("contestId")
                                    idx = prob.get("index")
                                    if c_id and idx:
                                        key = f"{c_id}{idx}"
                                        if key in p_keys:
                                            # Record solve
                                            with db._connect() as con:
                                                con.execute(
                                                    "INSERT OR IGNORE INTO weekly_solves (user_id, week_id, p_key) VALUES (?, ?, ?)",
                                                    (user_id, week_id, key)
                                                )
                    except Exception as e:
                        print(f"[Contests Weekly Sync] Error syncing {cf_handle}: {e}")

            # Sunday 9 PM end check
            # We only compile leaderboard once. Let's make sure we do it on Sunday 9 PM IST.
            # We can write a flag in DB or check if we already announced the results for this week_id.
            if now.weekday() == 6 and now.hour == 21 and now.minute < 15:
                # Check if leaderboard already posted
                with db._connect() as con:
                    leaderboard_posted = con.execute(
                        "SELECT COUNT(*) as count FROM weekly_solves WHERE week_id = ? AND p_key = 'LEADERBOARD_POSTED'",
                        (week_id,)
                    ).fetchone()

                if leaderboard_posted["count"] == 0 and active_week:
                    # Mark as posted
                    with db._connect() as con:
                        con.execute(
                            "INSERT OR IGNORE INTO weekly_solves (user_id, week_id, p_key) VALUES (0, ?, 'LEADERBOARD_POSTED')",
                            (week_id,)
                        )

                    # Get all solves for this week
                    with db._connect() as con:
                        solves = con.execute(
                            "SELECT user_id, COUNT(*) as count FROM weekly_solves WHERE week_id = ? AND user_id != 0 GROUP BY user_id",
                            (week_id,)
                        ).fetchall()

                    # Sort by count descending
                    solves = sorted(solves, key=lambda s: s["count"], reverse=True)

                    for guild in self.bot.guilds:
                        channel = discord.utils.get(guild.channels, name=CF_ACTIVITY_CHANNEL)
                        if not channel:
                            continue

                        # Compile leaderboard
                        leaderboard_lines = []
                        winner_id = None
                        max_solves = 0

                        for idx, row in enumerate(solves):
                            m_id = row["user_id"]
                            cnt = row["count"]
                            member = guild.get_member(m_id)
                            name = member.display_name if member else f"User {m_id}"

                            if idx == 0 and cnt > 0:
                                winner_id = m_id
                                max_solves = cnt

                            medal = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else "🔹"
                            leaderboard_lines.append(f"{medal} **{name}** solved `{cnt}/3` problems")

                        if not leaderboard_lines:
                            leaderboard_lines.append("No solves recorded this week! Come on grinders! 😤")

                        # Handle Weekly Champion role reassignment
                        champ_role = await get_champion_role(guild)
                        # Remove from all current members holding it
                        for m in champ_role.members:
                            try:
                                await m.remove_roles(champ_role, reason="Weekly mini-contest end: stripping old champ")
                            except discord.Forbidden:
                                print(f"[Contests Weekly End] [ERROR] FORBIDDEN stripping role from {m}")

                        winner_announce = ""
                        if winner_id:
                            winner_member = guild.get_member(winner_id)
                            if winner_member:
                                try:
                                    await winner_member.add_roles(champ_role, reason="Weekly mini-contest winner!")
                                except discord.Forbidden:
                                    print(f"[Contests Weekly End] [ERROR] FORBIDDEN adding role to {winner_member}")
                                winner_announce = f"\n👑 **Congratulations to our Weekly Champion:** {winner_member.mention}! They solved `{max_solves}` problems! 🏆"
                                
                                # Award XP and Coins (+200 XP, +100 coins)
                                from cogs.economy import award_xp_and_coins
                                try:
                                    await award_xp_and_coins(self.bot, guild, winner_id, 200, 100, reason="contest_won")
                                except Exception as e:
                                    print(f"[Weekly Contest XP Award] Error: {e}")

                                # Trigger achievements check
                                try:
                                    ach_cog = self.bot.get_cog("Achievements")
                                    if ach_cog:
                                        await ach_cog.check_achievements(guild, winner_id)
                                except Exception as e:
                                    print(f"[Weekly Contest Achievements] Error: {e}")

                        embed = discord.Embed(
                            title="🏆 Weekly Mini-Contest Standings!",
                            description=(
                                "Here is the final standings table for this week's mini-contest:\n\n" +
                                "\n".join(leaderboard_lines) +
                                winner_announce
                            ),
                            color=0xF1C40F
                        )
                        await channel.send(embed=embed)
        except Exception as e:
            print(f"[Contests Weekly Manager Task] Loop Error: {e}")

    @commands.command(name="weeklyresults", aliases=["weekly_results", "weekly", "mini_contest"])
    @commands.guild_only()
    async def weekly_results_cmd(self, ctx: commands.Context) -> None:
        """Display the active weekly mini-contest problems and live standings."""
        async with ctx.typing():
            now = datetime.now(IST)
            week_id = now.strftime("%Y-%U")

            with db._connect() as con:
                active_week = con.execute("SELECT * FROM weekly_contest WHERE week_id = ?", (week_id,)).fetchone()

            if not active_week:
                await ctx.reply("ℹ️ No active weekly mini-contest has started yet for this week.")
                return

            p1, p2, p3 = active_week["p1"], active_week["p2"], active_week["p3"]

            def make_url(p_str):
                parts = p_str.split("_")
                return f"https://codeforces.com/contest/{parts[0]}/problem/{parts[1]}"

            # Get live standings
            with db._connect() as con:
                solves = con.execute(
                    "SELECT user_id, COUNT(*) as count FROM weekly_solves WHERE week_id = ? AND user_id != 0 GROUP BY user_id",
                    (week_id,)
                ).fetchall()

            solves = sorted(solves, key=lambda s: s["count"], reverse=True)
            standings_lines = []
            for idx, row in enumerate(solves[:10]):
                m_id = row["user_id"]
                cnt = row["count"]
                member = ctx.guild.get_member(m_id)
                name = member.display_name if member else f"User {m_id}"
                medal = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else "🔹"
                standings_lines.append(f"{medal} **{name}** solved `{cnt}/3` problems")

            if not standings_lines:
                standings_lines.append("No solves recorded yet. Be the first! 🚀")

            embed = discord.Embed(
                title=f"🏆 Weekly Mini-Contest — Week {week_id}",
                description=(
                    f"**Problems:**\n"
                    f"1️⃣ **Div3 Easy (Rating 1000):** [{p1.split('_')[2]}]({make_url(p1)})\n"
                    f"2️⃣ **Div2 Medium (Rating 1300):** [{p2.split('_')[2]}]({make_url(p2)})\n"
                    f"3️⃣ **Div1 Easy / Div2 Hard (Rating 1600):** [{p3.split('_')[2]}]({make_url(p3)})\n\n"
                    f"📊 **Live Standings (Top 10):**\n" +
                    "\n".join(standings_lines)
                ),
                color=0xF1C40F
            )
            embed.set_footer(text="AGNoobies Live Weekly Mini-Contest")
            await ctx.reply(embed=embed)

    @weekly_contest_manager.before_loop
    async def before_weekly_manager(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Contests(bot))
