# ══════════════════════════════════════════════════════
#  cogs/seasons.py  —  CP Season and Hall of Fame System
# ══════════════════════════════════════════════════════

import discord
from discord.ext import commands, tasks
import database as db
import calendar
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


class Seasons(commands.Cog):
    """Cog to manage monthly Competitive Programming seasons, resets, and Hall of Fame."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.season_checker.start()

    def cog_unload(self) -> None:
        self.season_checker.cancel()

    # ── Background Month Transition Task ────────────────

    @tasks.loop(hours=6)
    async def season_checker(self) -> None:
        """Checks for month transitions and wraps up the season."""
        try:
            now = datetime.now(IST)
            current_month = now.month
            current_year = now.year

            # Get last checked month/year from DB metadata or a settings check
            # For simplicity, we can store it in a local key or look at the latest hall_of_fame record
            with db._connect() as con:
                latest_hof = con.execute(
                    "SELECT season_number FROM hall_of_fame ORDER BY ended_at DESC LIMIT 1"
                ).fetchone()

            last_resolved_season = 0
            if latest_hof:
                # Let's say season number was stored as month
                last_resolved_season = latest_hof["season_number"]

            # Calculate target season (previous month)
            # If current month is different from the last resolved season (allowing for a fresh reset)
            # Wait, if last_resolved_season == 0, it means no seasons have ended yet. Let's record the current month as active
            if last_resolved_season == 0:
                # Let's save a dummy entry or just wait till month ends
                # We want to resolve the previous month if it has not been resolved yet.
                # E.g. if today is June 1st and we haven't resolved May (5), we resolve May.
                # Let's find previous month
                prev_month = 12 if current_month == 1 else current_month - 1
                prev_year = current_year - 1 if current_month == 1 else current_year
                
                # If we transition, let's check if there is any season data for prev_month that needs resolution
                # If there is no HOF record for prev_month, resolve it!
                # Let's check:
                with db._connect() as con:
                    exists = con.execute(
                        "SELECT * FROM hall_of_fame WHERE season_number = ?",
                        (prev_month,)
                    ).fetchone()

                if not exists:
                    # We need to resolve prev_month season!
                    await self.resolve_season(prev_month, prev_year)

            elif last_resolved_season != current_month:
                # Check if previous month needs resolution
                prev_month = 12 if current_month == 1 else current_month - 1
                prev_year = current_year - 1 if current_month == 1 else current_year
                
                if last_resolved_season != prev_month:
                    # We haven't resolved the previous month yet!
                    await self.resolve_season(prev_month, prev_year)

            # ── Last day of month countdown alert ────────────────
            # On the last day of the month (e.g. after 6 PM), announce top 3 with countdown
            last_day = calendar.monthrange(current_year, current_month)[1]
            if now.day == last_day and now.hour >= 18:
                # Only announce once per day (between 6 PM and 10 PM)
                # Let's see: we can check if already announced today using a local variable or DB.
                # Let's make it alert every 6 hours on the last day! That's fine and acts as a nice hype countdown.
                await self.announce_countdown(current_month, last_day)
        except Exception as e:
            print(f"[Season Checker Task] Main Loop Error: {e}")

    @season_checker.before_loop
    async def before_checker(self) -> None:
        await self.bot.wait_until_ready()

    async def announce_countdown(self, season_num: int, last_day: int) -> None:
        """Announce top 3 contenders and countdown on the last day of the month."""
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.channels, name="cf-activity")
            if not channel:
                continue

            with db._connect() as con:
                rows = con.execute(
                    "SELECT user_id, points FROM seasons WHERE guild_id = ? AND season_number = ? ORDER BY points DESC LIMIT 3",
                    (guild.id, season_num)
                ).fetchall()

            if not rows:
                continue

            podium = []
            medals = ["🥇", "🥈", "🥉"]
            for idx, r in enumerate(rows):
                member = guild.get_member(r["user_id"])
                name = member.mention if member else f"User {r['user_id']}"
                podium.append(f"{medals[idx]} **{name}** — `{r['points']} season points`")

            embed = discord.Embed(
                title="⏳ SEASON FINALE COUNTDOWN! 🏁",
                description=(
                    f"Grinders, the current season ends **TONIGHT**! ⚔️\n"
                    f"Only a few hours remain to claim your spot in the permanent **Hall of Fame**!\n\n"
                    f"⚡ **TOP CONTENDERS (Current Podium):**\n" +
                    "\n".join(podium) +
                    "\n\nKeep grinding Codeforces solves and duels until midnight! Every point counts! 🔥"
                ),
                color=0xE67E22
            )
            await channel.send(embed=embed)

    async def resolve_season(self, season_num: int, year: int) -> None:
        """End a season, record champion in HOF, assign championship roles, reset points."""
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.channels, name="cf-activity")
            if not channel:
                continue

            # Find winner of that season
            with db._connect() as con:
                winner_row = con.execute(
                    "SELECT user_id, points FROM seasons WHERE guild_id = ? AND season_number = ? ORDER BY points DESC LIMIT 1",
                    (guild.id, season_num)
                ).fetchone()

            if not winner_row or winner_row["points"] <= 0:
                # No activity in this season, skip
                continue

            winner_id = winner_row["user_id"]
            winner_points = winner_row["points"]
            
            member = guild.get_member(winner_id)
            winner_name = member.display_name if member else f"User {winner_id}"

            # 1. Save to Hall of Fame
            now_ist = datetime.now(IST).isoformat()
            with db._connect() as con:
                con.execute(
                    """
                    INSERT OR REPLACE INTO hall_of_fame (season_number, guild_id, winner_id, winner_name, points, ended_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (season_num, guild.id, winner_id, winner_name, winner_points, now_ist)
                )

            # 2. Give permanent Champion Role
            # Role name format: "Season X Champion"
            role_name = f"Season {season_num} Champion"
            
            try:
                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    # Create with unique color
                    import random
                    color = discord.Color(random.randint(0, 0xFFFFFF))
                    role = await guild.create_role(
                        name=role_name,
                        color=color,
                        hoist=True,
                        reason=f"Season {season_num} Championship winner role"
                    )
                
                if member and role not in member.roles:
                    await member.add_roles(role)
            except discord.Forbidden:
                print(f"[Seasons] Missing role management permissions on server {guild.name}")

            # 3. Trigger achievements check for Season King
            try:
                ach_cog = self.bot.get_cog("Achievements")
                if ach_cog:
                    await ach_cog.check_achievements(guild, winner_id)
            except Exception as e:
                print(f"[Season End Achievements] Error checking: {e}")

            # 4. Hype announcement
            embed = discord.Embed(
                title=f"👑 SEASON {season_num} CHAMPION CROWNED! 🏆",
                description=(
                    f"🎉 **Let's hear it for our Season Champion!** 🎉\n\n"
                    f"⚡ {member.mention if member else winner_name} has won **Season {season_num}** with a spectacular **{winner_points} points**! 🥇\n\n"
                    f"> 🏷️ Awarded the permanent role: **`{role_name}`**\n"
                    f"> 🏆 Permanently inducted into the server **Hall of Fame**!\n\n"
                    f"A brand new month has begun! **Season {datetime.now(IST).month}** is now officially **LIVE**! Let the grind resume! 💻⚔️"
                ),
                color=0xF1C40F
            )
            if member:
                embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)

    # ── Commands ───────────────────────────────────────

    @commands.command(name="season")
    @commands.guild_only()
    async def view_season(self, ctx: commands.Context) -> None:
        """Show current season number, days remaining, and your personal ranking."""
        now = datetime.now(IST)
        season_num = now.month
        season_name = now.strftime("%B %Y")
        
        # Days remaining in current month
        last_day = calendar.monthrange(now.year, now.month)[1]
        days_remaining = last_day - now.day

        # Get rankings
        with db._connect() as con:
            rows = con.execute(
                "SELECT user_id, points FROM seasons WHERE guild_id = ? AND season_number = ? ORDER BY points DESC",
                (ctx.guild.id, season_num)
            ).fetchall()

        rank = "N/A"
        points = 0
        for idx, row in enumerate(rows):
            if row["user_id"] == ctx.author.id:
                rank = idx + 1
                points = row["points"]
                break

        embed = discord.Embed(
            title=f"🏆 CP Season: {season_name}",
            description=(
                f"💪 **Active Season:** `Season {season_num}`\n"
                f"⌛ **Days Remaining:** `{days_remaining} day(s)`\n\n"
                f"👤 **Your Stats:**\n"
                f"> ⭐ **Season Points:** `{points} pts`\n"
                f"> 🏅 **Rank:** `#{rank}` of `{len(rows)}` players"
            ),
            color=0x3498DB
        )
        embed.set_footer(text="AGNoobies Season Tracker • Earn points by solves, days, and duels")
        await ctx.reply(embed=embed)

    @commands.command(name="seasonleaderboard", aliases=["slb", "seasonlb"])
    @commands.guild_only()
    async def season_leaderboard(self, ctx: commands.Context) -> None:
        """Show top 10 players for the current season."""
        now = datetime.now(IST)
        season_num = now.month

        with db._connect() as con:
            rows = con.execute(
                "SELECT user_id, points FROM seasons WHERE guild_id = ? AND season_number = ? ORDER BY points DESC LIMIT 10",
                (ctx.guild.id, season_num)
            ).fetchall()

        if not rows:
            await ctx.reply("No season activity recorded yet. Get grinding to claim #1! ⚔️")
            return

        embed = discord.Embed(
            title=f"🏆 SEASON {season_num} LEADERBOARD",
            description=f"Active Season: **{now.strftime('%B %Y')}**\n" + "```\n#   Name                 Points\n" + "─" * 31 + "```",
            color=0xF1C40F
        )

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for idx, row in enumerate(rows):
            medal = medals[idx] if idx < 3 else f"`{idx + 1:2d}.`"
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name[:18] if member else f"User {row['user_id']}"
            lines.append(f"{medal}  **{name:<18}** — **{row['points']}** pts")

        embed.add_field(name="\u200b", value="\n".join(lines), inline=False)
        embed.set_footer(text="AGNoobies Season System")
        await ctx.reply(embed=embed)

    @commands.command(name="halloffame", aliases=["hof"])
    @commands.guild_only()
    async def hall_of_fame(self, ctx: commands.Context) -> None:
        """Display all past season champions."""
        with db._connect() as con:
            rows = con.execute(
                "SELECT * FROM hall_of_fame WHERE guild_id = ? ORDER BY season_number DESC",
                (ctx.guild.id,)
            ).fetchall()

        if not rows:
            await ctx.reply("🏛️ **The Hall of Fame is currently empty!** Win this month's season to be permanently inducted! 🥇")
            return

        embed = discord.Embed(
            title="🏛️ Server Hall of Fame",
            description="The legendary champions of past AGNoobies Competitive Programming seasons: ✨",
            color=0xF1C40F
        )

        for row in rows:
            ended_dt = datetime.fromisoformat(row["ended_at"])
            date_str = ended_dt.strftime("%B %Y")
            embed.add_field(
                name=f"🏆 Season {row['season_number']} Champion ({date_str})",
                value=(
                    f"👤 **Champion:** <@{row['winner_id']}> (`{row['winner_name']}`)\n"
                    f"⚡ **Winning Score:** `{row['points']} points`"
                ),
                inline=False
            )

        embed.set_footer(text="AGNoobies CP Legend Archive")
        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Seasons(bot))
