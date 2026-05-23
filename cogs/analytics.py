# ══════════════════════════════════════════════════════
#  cogs/analytics.py  —  CP Performance Analytics Cog
# ══════════════════════════════════════════════════════

import discord
from discord.ext import commands, tasks
import database as db
import aiohttp
import math
import io
import collections
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw

IST = timezone(timedelta(hours=5, minutes=30))


class Analytics(commands.Cog):
    """Cog for advanced Codeforces performance analytics, heatmaps, rating prediction, and upsolving."""

    CF_BASE = "https://codeforces.com/api"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None
        self.sunday_reminder.start()

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession()

    async def cog_unload(self) -> None:
        self.sunday_reminder.cancel()
        if self._session:
            await self._session.close()

    # ── CF API Helpers ──────────────────────────────────

    async def _fetch_json(self, url: str) -> dict | None:
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"[Analytics API] Error: {e}")
        return None

    # ── Sunday Upsolve Reminder Task ────────────────────

    @tasks.loop(hours=24)
    async def sunday_reminder(self) -> None:
        """Every Sunday morning at 10 AM IST, reminds users of their pending upsolves."""
        try:
            now = datetime.now(IST)
            # Check if today is Sunday
            if now.weekday() != 6: # Sunday = 6
                return

            # Target time 10:00 AM IST
            target = now.replace(hour=10, minute=0, second=0, microsecond=0)
            # Let's say if we are within 30 minutes of 10 AM
            time_diff = abs((now - target).total_seconds())
            if time_diff > 1800: # 30 mins
                return

            # Compile upsolve counts for all active users
            for guild in self.bot.guilds:
                channel = discord.utils.get(guild.channels, name="cf-activity")
                if not channel:
                    continue

                with db._connect() as con:
                    rows = con.execute(
                        "SELECT user_id, COUNT(*) as count FROM upsolves WHERE guild_id = ? AND solved = 0 GROUP BY user_id",
                        (guild.id,)
                    ).fetchall()

                if not rows:
                    continue

                lines = []
                for row in rows:
                    member = guild.get_member(row["user_id"])
                    if member and row["count"] > 0:
                        lines.append(f"• {member.mention} has **{row['count']}** pending upsolve(s)!")

                if lines:
                    embed = discord.Embed(
                        title="📅 Weekly Upsolve Reminder!",
                        description=(
                            "Sunday is upsolving day, grinders! 🦾 Clean up your backlog and learn from your contest mistakes!\n\n"
                            "**Pending Backlog Summary:**\n" +
                            "\n".join(lines) +
                            "\n\nUse `!myupsolves` to view your personal list and get solving! 🚀"
                        ),
                        color=0x9B59B6
                    )
                    embed.set_footer(text="AGNoobies Upsolve Automation")
                    await channel.send(embed=embed)
        except Exception as e:
            print(f"[Analytics Sunday Reminder Task] Loop Error: {e}")

    @sunday_reminder.before_loop
    async def before_reminder(self) -> None:
        await self.bot.wait_until_ready()

    # ── Commands ───────────────────────────────────────

    @commands.command(name="predict")
    @commands.guild_only()
    async def predict_contest(self, ctx: commands.Context, contest_id: int) -> None:
        """Estimate your Codeforces rating change for a recently concluded contest."""
        row = db.get_cf_user(ctx.author.id)
        if not row:
            await ctx.reply("❌ No Codeforces handle linked! Use `!setcf <handle>` first.")
            return

        handle = row["cf_handle"]
        
        async with ctx.typing():
            # 1. Fetch user standings
            standings_url = f"{self.CF_BASE}/contest.standings?contestId={contest_id}&handles={handle}"
            standings_data = await self._fetch_json(standings_url)

            if not standings_data or standings_data.get("status") != "OK":
                await ctx.reply(f"❌ Could not fetch standings. Did you participate in Contest `{contest_id}`?")
                return

            results = standings_data["result"]["rows"]
            if not results:
                await ctx.reply(f"❌ You did not participate in Contest `{contest_id}`!")
                return

            participant = results[0]
            rank = participant["rank"]

            # 2. Fetch current user rating
            user_url = f"{self.CF_BASE}/user.info?handles={handle}"
            user_data = await self._fetch_json(user_url)

            if not user_data or user_data.get("status") != "OK":
                await ctx.reply("❌ Failed to fetch user info from Codeforces.")
                return

            user_info = user_data["result"][0]
            current_rating = user_info.get("rating", 1500)

            # 3. Predict Rating change using our smart expected rank log-formula
            # expected rank = 3000 * 10^((1600 - rating) / 1000)
            expected_rank = 3000 * (10 ** ((1600 - current_rating) / 1000))
            expected_rank = max(100, min(15000, expected_rank))
            
            perf_ratio = expected_rank / rank
            delta = int(200 * math.log10(perf_ratio))
            # Cap deltas
            delta = max(-150, min(250, delta))

            predicted_rating = max(0, current_rating + delta)
            delta_str = f"+{delta}" if delta >= 0 else str(delta)
            color = 0x2ECC71 if delta >= 0 else 0xE74C3C

            embed = discord.Embed(
                title=f"📈 Rating Predictor — Contest {contest_id}",
                color=color
            )
            embed.description = (
                f"**User:** {ctx.author.mention} (`{handle}`)\n"
                f"**Final Rank:** `{rank}`\n\n"
                f"📊 **CURRENT RATING:** `{current_rating}`\n"
                f"🔮 **PREDICTED DELTA :** **{delta_str}**\n"
                f"🏁 **ESTIMATED NEW RATING:** **{predicted_rating}**\n\n"
                f"> *Note: This delta is a custom mathematical approximation. Real delta will vary slightly based on actual contest pool.*"
            )
            embed.set_footer(text="AGNoobies Rating Predictor")
            await ctx.reply(embed=embed)

    @commands.command(name="heatmap")
    @commands.guild_only()
    async def user_heatmap(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Generate a premium GitHub-style Codeforces solve heatmap for a user."""
        target = member or ctx.author
        row = db.get_cf_user(target.id)
        if not row:
            await ctx.reply(f"❌ {target.display_name} has not linked their Codeforces handle!")
            return

        handle = row["cf_handle"]
        
        async with ctx.typing():
            # Fetch submissions
            sub_url = f"{self.CF_BASE}/user.status?handle={handle}"
            sub_data = await self._fetch_json(sub_url)

            if not sub_data or sub_data.get("status") != "OK":
                await ctx.reply(f"❌ Could not fetch submissions for `{handle}`.")
                return

            # Group OK solves by calendar date in IST
            solves_by_date = collections.Counter()
            seen_problems = set()

            for sub in sub_data["result"]:
                if sub.get("verdict") == "OK":
                    prob = sub.get("problem", {})
                    c_id = prob.get("contestId")
                    idx = prob.get("index")
                    if c_id and idx:
                        p_key = f"{c_id}{idx}"
                        if p_key not in seen_problems:
                            seen_problems.add(p_key)
                            creation_ts = sub["creationTimeSeconds"]
                            # convert to IST date
                            dt = datetime.fromtimestamp(creation_ts, tz=IST)
                            solves_by_date[dt.date()] += 1

            # Define graph ranges (last 24 weeks)
            now = datetime.now(IST)
            today_weekday = now.weekday() # Monday = 0
            # Align to start on Sunday of 24 weeks ago
            days_to_subtract = (today_weekday + 1) % 7 + 24 * 7
            start_date = (now - timedelta(days=days_to_subtract)).date()
            today_date = now.date()

            # Generate Pillow Image
            try:
                buf = self._draw_heatmap(solves_by_date, start_date, today_date)
                file = discord.File(buf, filename="heatmap.png")

                embed = discord.Embed(
                    title=f"🟢 solve Heatmap — {handle}",
                    url=f"https://codeforces.com/profile/{handle}",
                    color=0x2ECC71
                )
                embed.set_image(url="attachment://heatmap.png")
                embed.set_footer(text="AGNoobies Solve Heatmap Generator")

                await ctx.reply(embed=embed, file=file)
            except Exception as e:
                import traceback
                traceback.print_exc()
                await ctx.reply(f"❌ Failed to generate heatmap image: {e}")

    def _draw_heatmap(self, count_by_date: dict, start_date, today_date) -> io.BytesIO:
        """Helper to draw heatmap contributions graph using PIL."""
        total_days = (today_date - start_date).days + 1
        num_weeks = (total_days + 6) // 7

        box_size = 14
        padding = 3
        label_width = 35
        top_padding = 25
        bottom_padding = 25
        right_padding = 20

        width = label_width + num_weeks * (box_size + padding) + right_padding
        height = top_padding + 7 * (box_size + padding) + bottom_padding

        # Create base canvas
        img = Image.new("RGB", (width, height), "#0d1117")
        draw = ImageDraw.Draw(img)

        # Contribution colors (GitHub green scheme)
        c_empty = "#161b22"
        c_level1 = "#0e4429"
        c_level2 = "#006d32"
        c_level3 = "#26a641"
        c_level4 = "#39d353"

        def get_color(count: int) -> str:
            if count == 0: return c_empty
            if count <= 1: return c_level1
            if count <= 3: return c_level2
            if count <= 5: return c_level3
            return c_level4

        # Draw weekday markers on the left
        weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        for idx, day_lbl in enumerate(weekdays):
            if idx in [1, 3, 5]: # Mon, Wed, Fri
                y = top_padding + idx * (box_size + padding) - 1
                draw.text((6, y), day_lbl, fill="#8b949e")

        # Draw boxes and months
        curr = start_date
        while curr <= today_date:
            days_diff = (curr - start_date).days
            w = days_diff // 7
            d = (curr.weekday() + 1) % 7 # Sunday = 0

            count = count_by_date[curr]
            color = get_color(count)

            x = label_width + w * (box_size + padding)
            y = top_padding + d * (box_size + padding)

            # Draw cell
            draw.rectangle(
                [x, y, x + box_size, y + box_size],
                fill=color,
                outline="#30363d",
                width=1
            )

            # Draw Month Label at start of month
            if d == 0 and curr.day <= 7:
                month_lbl = curr.strftime("%b")
                draw.text((x, 5), month_lbl, fill="#8b949e")

            curr += timedelta(days=1)

        # Draw legend at bottom
        legend_x = width - 110
        legend_y = height - 16
        draw.text((legend_x - 30, legend_y - 2), "Less", fill="#8b949e")
        
        legend_colors = [c_empty, c_level1, c_level2, c_level3, c_level4]
        for idx, col in enumerate(legend_colors):
            lx = legend_x + idx * (box_size + 2)
            draw.rectangle(
                [lx, legend_y, lx + box_size - 4, legend_y + box_size - 4],
                fill=col,
                outline="#30363d"
            )
        draw.text((legend_x + 5 * (box_size + 2) - 3, legend_y - 2), "More", fill="#8b949e")

        # Save buffer
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    @commands.command(name="weakness")
    @commands.guild_only()
    async def analyze_weakness(self, ctx: commands.Context) -> None:
        """Find your weakest and strongest CP categories based on your last 200 submissions."""
        row = db.get_cf_user(ctx.author.id)
        if not row:
            await ctx.reply("❌ No Codeforces handle linked! Use `!setcf <handle>` first.")
            return

        handle = row["cf_handle"]
        
        async with ctx.typing():
            # Fetch last 200 submissions
            url = f"{self.CF_BASE}/user.status?handle={handle}&from=1&count=200"
            data = await self._fetch_json(url)

            if not data or data.get("status") != "OK":
                await ctx.reply("❌ Failed to fetch Codeforces submission history.")
                return

            submissions = data["result"]
            if not submissions:
                await ctx.reply("ℹ️ No submissions found to analyze! Go solve some problems first!")
                return

            tag_total = collections.defaultdict(int)
            tag_wa = collections.defaultdict(int)

            for sub in submissions:
                prob = sub.get("problem", {})
                tags = prob.get("tags", [])
                verdict = sub.get("verdict")

                for t in tags:
                    tag_total[t] += 1
                    if verdict != "OK":
                        tag_wa[t] += 1

            # Filter tags with at least 5 submissions to get reliable stats
            valid_tags = [t for t, count in tag_total.items() if count >= 5]

            if not valid_tags:
                await ctx.reply("ℹ️ Not enough data! You need at least 5 submissions in any single category to analyze weaknesses.")
                return

            tag_stats = []
            for t in valid_tags:
                total = tag_total[t]
                wa = tag_wa[t]
                wa_rate = (wa / total) * 100
                tag_stats.append({
                    "tag": t,
                    "wa_rate": wa_rate,
                    "total": total,
                    "wa": wa
                })

            # Sort by WA rate descending
            tag_stats.sort(key=lambda x: x["wa_rate"], reverse=True)

            # Top 5 Weakest
            weakest = tag_stats[:5]
            # Top 3 Strongest (lowest WA rate)
            strongest = sorted(tag_stats, key=lambda x: x["wa_rate"])[:3]

            embed = discord.Embed(
                title=f"🧠 CP Strengths & Weaknesses — {handle}",
                description="Analysis based on your last 200 Codeforces submissions:",
                color=0x9B59B6
            )

            weak_lines = []
            for w in weakest:
                weak_lines.append(f"🔴 **{w['tag'].title()}**: `{w['wa_rate']:.1f}%` WA rate ({w['wa']}/{w['total']} failed)")
            
            embed.add_field(
                name="⚠️ TOP 5 WEAKEST TOPICS (High WA rate)",
                value="\n".join(weak_lines) if weak_lines else "None detected",
                inline=False
            )

            strong_lines = []
            for s in strongest:
                success_rate = 100 - s["wa_rate"]
                strong_lines.append(f"🟢 **{s['tag'].title()}**: `{success_rate:.1f}%` AC rate ({s['total'] - s['wa']}/{s['total']} passed)")
            
            embed.add_field(
                name="💪 TOP 3 STRONGEST TOPICS (High AC rate)",
                value="\n".join(strong_lines) if strong_lines else "None detected",
                inline=False
            )

            embed.set_footer(text="AGNoobies CP Analytics Desk")
            await ctx.reply(embed=embed)

    @commands.command(name="upsolve")
    @commands.guild_only()
    async def upsolve_contest(self, ctx: commands.Context, contest_id: int) -> None:
        """Scan a contest, finding unsolved problems and adding them to your backlog."""
        row = db.get_cf_user(ctx.author.id)
        if not row:
            await ctx.reply("❌ No Codeforces handle linked! Use `!setcf <handle>` first.")
            return

        handle = row["cf_handle"]
        
        async with ctx.typing():
            # 1. Fetch contest problems
            contest_url = f"{self.CF_BASE}/contest.standings?contestId={contest_id}&showUnofficial=false"
            contest_data = await self._fetch_json(contest_url)

            if not contest_data or contest_data.get("status") != "OK":
                await ctx.reply(f"❌ Failed to fetch contest data for Contest `{contest_id}`.")
                return

            problems = contest_data["result"]["problems"]

            # 2. Fetch user solves
            sub_url = f"{self.CF_BASE}/user.status?handle={handle}"
            sub_data = await self._fetch_json(sub_url)

            if not sub_data or sub_data.get("status") != "OK":
                await ctx.reply("❌ Failed to fetch user solves from Codeforces API.")
                return

            solved_problems = set()
            for sub in sub_data["result"]:
                if sub.get("verdict") == "OK":
                    prob = sub.get("problem", {})
                    c_id = prob.get("contestId")
                    idx = prob.get("index")
                    if c_id and idx:
                        solved_problems.add(f"{c_id}{idx}")

            # 3. Cross check and add unsolved ones
            added_count = 0
            with db._connect() as con:
                for p in problems:
                    p_id = f"{p['contestId']}{p['index']}"
                    if p_id not in solved_problems:
                        # Check if already added
                        exists = con.execute(
                            "SELECT * FROM upsolves WHERE user_id = ? AND guild_id = ? AND problem_id = ?",
                            (ctx.author.id, ctx.guild.id, p_id)
                        ).fetchone()

                        if not exists:
                            p_url = f"https://codeforces.com/contest/{p['contestId']}/problem/{p['index']}"
                            rating = p.get("rating")
                            con.execute(
                                """
                                INSERT INTO upsolves (user_id, guild_id, problem_id, contest_id, problem_name, rating, link, solved)
                                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                                """,
                                (ctx.author.id, ctx.guild.id, p_id, contest_id, p["name"], rating, p_url)
                            )
                            added_count += 1

            await ctx.reply(f"🎯 Contest `{contest_id}` scanned! Added **{added_count}** unsolved problem(s) to your backlog list. Use `!myupsolves` to solve them! 🦾")

    @commands.command(name="myupsolves")
    @commands.guild_only()
    async def view_my_upsolves(self, ctx: commands.Context) -> None:
        """Display all pending upsolve problems in your database backlog."""
        user_id = ctx.author.id
        guild_id = ctx.guild.id

        with db._connect() as con:
            rows = con.execute(
                "SELECT * FROM upsolves WHERE user_id = ? AND guild_id = ? AND solved = 0 ORDER BY rating ASC",
                (user_id, guild_id)
            ).fetchall()

        if not rows:
            await ctx.reply("🎉 **Zero pending upsolves!** You have perfectly upsolved all targeted problems! 🥇")
            return

        embed = discord.Embed(
            title="🎯 Your Upsolve Backlog List",
            description="Here are the contest problems you need to upsolve to improve your ratings! ⚔️",
            color=0x9B59B6
        )

        for row in rows[:15]: # Show top 15
            rating_str = f"⭐ {row['rating']}" if row['rating'] else "Unrated"
            embed.add_field(
                name=f"💻 {row['problem_name']} ({row['problem_id']})",
                value=(
                    f"🏟️ **Contest:** `{row['contest_id']}`\n"
                    f"📊 **Difficulty:** `{rating_str}`\n"
                    f"🔗 **Link:** [Problem URL]({row['link']})\n"
                    f"💡 To complete: `!solvedupsolve {row['problem_id']}`"
                ),
                inline=False
            )

        embed.set_footer(text=f"Showing {min(len(rows), 15)} of {len(rows)} pending upsolves")
        await ctx.reply(embed=embed)

    @commands.command(name="solvedupsolve")
    @commands.guild_only()
    async def mark_upsolve_done(self, ctx: commands.Context, problem_id: str) -> None:
        """Mark a pending upsolve problem as resolved in your backlog."""
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        p_id = problem_id.strip().upper()

        with db._connect() as con:
            existing = con.execute(
                "SELECT * FROM upsolves WHERE user_id = ? AND guild_id = ? AND problem_id = ? AND solved = 0",
                (user_id, guild_id, p_id)
            ).fetchone()

        if not existing:
            await ctx.reply(f"❌ Problem **{p_id}** is not in your pending upsolve list!")
            return

        with db._connect() as con:
            con.execute(
                "UPDATE upsolves SET solved = 1 WHERE user_id = ? AND guild_id = ? AND problem_id = ?",
                (user_id, guild_id, p_id)
            )

        # Reward solved upsolve! Let's give +20 XP and +10 coins (similar to solving a CF problem)
        from cogs.economy import award_xp_and_coins
        await award_xp_and_coins(self.bot, ctx.guild, user_id, 20, 10, reason="cf_solve")

        await ctx.reply(f"✅ **Problem {p_id} solved!** Removed from your upsolve backlog list. Earned **+20 XP** and **+10 coins**! 🚀")

        # Trigger achievements check
        try:
            ach_cog = self.bot.get_cog("Achievements")
            if ach_cog:
                await ach_cog.check_achievements(ctx.guild, user_id)
        except Exception as e:
            print(f"[Upsolve Achievements] Error: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Analytics(bot))
