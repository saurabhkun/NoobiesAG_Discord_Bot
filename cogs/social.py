# ══════════════════════════════════════════════════════
#  cogs/social.py  —  Find partner, study groups, and private VC system
# ══════════════════════════════════════════════════════

import asyncio
from datetime import datetime, timezone, timedelta
import aiohttp
import discord
from discord.ext import commands, tasks

import database as db
from config import PROGRESS_CHANNEL, SETUP_CATEGORY

IST = timezone(timedelta(hours=5, minutes=30))


class Social(commands.Cog):
    """Cog for social features: matching partners, study groups, and temporary private VCs."""

    CF_BASE = "https://codeforces.com/api"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession()
        self.vc_monitor_task.start()
        self.weekly_group_leaderboard.start()

    async def cog_unload(self) -> None:
        self.vc_monitor_task.cancel()
        self.weekly_group_leaderboard.cancel()
        if self._session:
            await self._session.close()

    # ── CF API Helpers ──────────────────────────────────

    async def _fetch_json(self, url: str) -> dict | None:
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"[Social API] Error: {e}")
        return None

    async def _get_user_rating(self, cf_handle: str) -> int:
        data = await self._fetch_json(f"{self.CF_BASE}/user.info?handles={cf_handle}")
        if data and data.get("status") == "OK":
            return data["result"][0].get("rating", 800)
        return 800

    async def _get_cf_solves(self, cf_handle: str) -> int:
        data = await self._fetch_json(f"{self.CF_BASE}/user.status?handle={cf_handle}")
        solves = set()
        if data and data.get("status") == "OK":
            for sub in data["result"]:
                if sub.get("verdict") == "OK":
                    prob = sub.get("problem", {})
                    c_id = prob.get("contestId")
                    idx = prob.get("index")
                    if c_id and idx:
                        solves.add(f"{c_id}{idx}")
        return len(solves)

    # ── Commands ───────────────────────────────────────

    @commands.command(name="findpartner")
    async def find_partner(self, ctx: commands.Context, target_rating: int = None) -> None:
        """Find practice partners whose CF rating is within 200 of target rating."""
        if target_rating is None:
            await ctx.reply("❌ Usage: `!findpartner <target_rating>` (e.g. `!findpartner 1400`)")
            return

        async with ctx.typing():
            users = db.get_all_cf_users()
            partners = []

            for row in users:
                user_id = row["user_id"]
                cf_handle = row["cf_handle"]
                if user_id == ctx.author.id:
                    continue

                rating = await self._get_user_rating(cf_handle)
                if abs(rating - target_rating) <= 200:
                    partners.append((cf_handle, rating, user_id))

            if not partners:
                await ctx.reply("❌ No partners found at this rating range (+/- 200). Try a different range!")
                return

            embed = discord.Embed(
                title=f"🤝 Practice Partners Found (Rating: ~{target_rating})",
                color=0x3498DB
            )
            lines = []
            for handle, rating, uid in partners:
                member = ctx.guild.get_member(uid)
                mention = member.mention if member else f"User {uid}"
                profile_url = f"https://codeforces.com/profile/{handle}"
                lines.append(f"• {mention} — **[{handle}]({profile_url})** (Rating: `{rating}`)")

            embed.description = "\n".join(lines)
            embed.set_footer(text="AGNoobies Partner Finder")
            await ctx.reply(embed=embed)

    # ── Study Group System ─────────────────────────────

    @commands.command(name="creategroup")
    @commands.guild_only()
    async def create_group_cmd(self, ctx: commands.Context, group_name: str = None) -> None:
        """Create a study group of up to 5 members."""
        if group_name is None:
            await ctx.reply("❌ Usage: `!creategroup <group_name>`")
            return

        # Check if user already in group
        if db.get_user_group(ctx.author.id):
            await ctx.reply("❌ You are already in a study group! Leave it before creating a new one.")
            return

        # Check if group exists
        if db.get_group(group_name):
            await ctx.reply("❌ A study group with that name already exists. Choose a unique name.")
            return

        db.create_group(group_name, ctx.author.id)
        await ctx.reply(
            f"✅ Study Group **{group_name}** has been successfully created!\n"
            f"Other members can join using `!joingroup {group_name}`. (Max 5 members)"
        )

    @commands.command(name="joingroup")
    @commands.guild_only()
    async def join_group_cmd(self, ctx: commands.Context, group_name: str = None) -> None:
        """Join an existing study group."""
        if group_name is None:
            await ctx.reply("❌ Usage: `!joingroup <group_name>`")
            return

        # Check if user already in group
        if db.get_user_group(ctx.author.id):
            await ctx.reply("❌ You are already in a study group! Leave it first.")
            return

        # Check group existence
        group = db.get_group(group_name)
        if not group:
            await ctx.reply(f"❌ Study group **{group_name}** does not exist.")
            return

        # Check group size limit
        members = db.get_group_members(group_name)
        if len(members) >= 5:
            await ctx.reply(f"❌ Group **{group_name}** is already full (max 5 members).")
            return

        db.join_group(group_name, ctx.author.id)
        await ctx.reply(f"✅ Welcome to the crew! You have successfully joined study group **{group_name}**! 🚀")

    @commands.command(name="leavegroup")
    @commands.guild_only()
    async def leave_group_cmd(self, ctx: commands.Context) -> None:
        """Leave your current study group."""
        user_grp = db.get_user_group(ctx.author.id)
        if not user_grp:
            await ctx.reply("❌ You are not in any study group.")
            return

        g_name = user_grp["group_name"]
        db.leave_group(g_name, ctx.author.id)
        await ctx.reply(f"✅ You have successfully left study group **{g_name}**.")

    @commands.command(name="groupstats")
    @commands.guild_only()
    async def group_stats(self, ctx: commands.Context) -> None:
        """See combined stats and progress of your study group."""
        user_grp = db.get_user_group(ctx.author.id)
        if not user_grp:
            await ctx.reply("❌ You are not in any study group. Create one with `!creategroup`!")
            return

        async with ctx.typing():
            g_name = user_grp["group_name"]
            members = db.get_group_members(g_name)

            total_days = 0
            total_solves = 0
            member_lines = []

            for m in members:
                uid = m["user_id"]
                days = m["current_day"] or 0
                total_days += days
                cf_handle = m["cf_handle"] or "N/A"

                cf_solves = 0
                if cf_handle != "N/A":
                    cf_solves = await self._get_cf_solves(cf_handle)
                    total_solves += cf_solves

                member = ctx.guild.get_member(uid)
                mention = member.mention if member else f"User {uid}"
                member_lines.append(f"• {mention} | Day `{days}` | CF: **{cf_handle}** (Solves: `{cf_solves}`)")

            avg_days = total_days / len(members) if members else 0

            embed = discord.Embed(
                title=f"📊 Study Group Stats — {g_name}",
                color=0x2ECC71
            )
            embed.add_field(name="👥 Members", value="\n".join(member_lines), inline=False)
            embed.add_field(name="📅 Total Days Completed", value=f"`{total_days}`", inline=True)
            embed.add_field(name="📈 Average Day", value=f"`{avg_days:.1f}`", inline=True)
            embed.add_field(name="💻 Combined CF Solves", value=f"`{total_solves}`", inline=True)
            embed.set_footer(text="AGNoobies Study Group Analytics")

            await ctx.reply(embed=embed)

    # ── Private VC System ──────────────────────────────

    @commands.command(name="createvc")
    @commands.guild_only()
    async def create_vc_cmd(self, ctx: commands.Context, opponent: discord.Member = None) -> None:
        """Create a temporary private voice channel for practicing with @user."""
        if opponent is None or opponent.bot or opponent == ctx.author:
            await ctx.reply("❌ Usage: `!createvc @user` to open a private practice room.")
            return

        # Check existing active VC
        if db.get_active_vc(ctx.author.id):
            await ctx.reply("❌ You already have an active private VC channel! Use it or let it close.")
            return
        if db.get_active_vc(opponent.id):
            await ctx.reply(f"❌ {opponent.display_name} is already in another private VC.")
            return

        guild = ctx.guild
        category = discord.utils.get(guild.categories, name=SETUP_CATEGORY)

        # Set overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
            ctx.author: discord.PermissionOverwrite(connect=True, speak=True, view_channel=True),
            opponent: discord.PermissionOverwrite(connect=True, speak=True, view_channel=True),
            guild.me: discord.PermissionOverwrite(connect=True, speak=True, view_channel=True, manage_channels=True)
        }

        channel_name = f"🎯 {ctx.author.display_name} x {opponent.display_name}"

        try:
            vc_channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason="Temporary private practicing voice channel"
            )
        except discord.Forbidden:
            await ctx.reply("❌ I do not have permissions to manage channels. Ask server admin to fix my roles.")
            return

        db.create_vc(vc_channel.id, ctx.author.id, opponent.id)

        await ctx.reply(
            f"✅ Temporary private VC room **{vc_channel.mention}** has been created!\n"
            f"Only {ctx.author.mention} and {opponent.mention} can view and connect to it.\n"
            f"⚠️ **Note:** If left empty for 5 minutes, it will automatically delete itself!"
        )

    @create_vc_cmd.error
    async def create_vc_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, (commands.MemberNotFound, commands.BadArgument)):
            await ctx.reply("❌ Please mention a valid server member")

    # ── Tasks ──────────────────────────────────────────

    @tasks.loop(minutes=2)
    async def vc_monitor_task(self) -> None:
        """Monitor temporary private VCs, auto-delete if empty for 5 minutes."""
        try:
            vcs = db.get_all_vcs()
            if not vcs:
                return

            for vc_row in vcs:
                channel_id = vc_row["channel_id"]
                u1_id = vc_row["user1_id"]
                u2_id = vc_row["user2_id"]
                empty_since_str = vc_row["empty_since"]

                channel = self.bot.get_channel(channel_id)
                if not channel:
                    # If deleted manually
                    db.delete_vc(channel_id)
                    continue

                member_count = len(channel.members)

                if member_count == 0:
                    if not empty_since_str:
                        # Mark empty since now
                        now_str = datetime.now(timezone.utc).isoformat()
                        db.update_vc_empty_since(channel_id, now_str)
                    else:
                        # Calculate duration
                        empty_since = datetime.fromisoformat(empty_since_str)
                        elapsed = (datetime.now(timezone.utc) - empty_since).total_seconds()
                        if elapsed >= 300:  # 5 minutes
                            try:
                                await channel.delete(reason="Temporary private VC empty for 5 minutes")
                                db.delete_vc(channel_id)

                                # Send notification in progress updates
                                progress_chan = discord.utils.get(channel.guild.channels, name=PROGRESS_CHANNEL)
                                if progress_chan:
                                    u1 = channel.guild.get_member(u1_id)
                                    u2 = channel.guild.get_member(u2_id)
                                    name1 = u1.mention if u1 else f"User {u1_id}"
                                    name2 = u2.mention if u2 else f"User {u2_id}"
                                    await progress_chan.send(f"Session between {name1} and {name2} has ended 👋")
                            except Exception as e:
                                print(f"[VC Monitor Task] Error deleting VC: {e}")
                else:
                    if empty_since_str:
                        # Clear empty since status
                        db.update_vc_empty_since(channel_id, None)
        except Exception as e:
            print(f"[VC Monitor Task] Main Loop Error: {e}")

    @vc_monitor_task.before_loop
    async def before_vc_monitor(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=30)
    async def weekly_group_leaderboard(self) -> None:
        """Every Sunday at 8 PM IST, announce group leaderboard in progress-updates."""
        try:
            now = datetime.now(IST)
            if now.weekday() == 6 and now.hour == 20 and now.minute < 30:
                # Compile weekly leaderboard
                groups = db.get_all_groups()
                if not groups:
                    return

                leaderboard_data = []

                for g in groups:
                    g_name = g["group_name"]
                    members = db.get_group_members(g_name)

                    total_days = 0
                    for m in members:
                        total_days += m["current_day"] or 0

                    avg_days = total_days / len(members) if members else 0
                    leaderboard_data.append((g_name, total_days, avg_days, len(members)))

                # Sort by total days descending
                leaderboard_data = sorted(leaderboard_data, key=lambda x: x[1], reverse=True)

                for guild in self.bot.guilds:
                    channel = discord.utils.get(guild.channels, name=PROGRESS_CHANNEL)
                    if not channel:
                        continue

                    lines = []
                    for idx, (name, total, avg, count) in enumerate(leaderboard_data[:10]):
                        medal = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else "🔹"
                        lines.append(f"{medal} **{name}** — Total Days: `{total}` | Avg Day: `{avg:.1f}` | Members: `{count}/5`")

                    embed = discord.Embed(
                        title="🏆 Weekly Study Group Leaderboard",
                        description=(
                            "Here are the top performing study groups for this week:\n\n" +
                            "\n".join(lines)
                        ),
                        color=0x9B59B6
                    )
                    embed.set_footer(text="AGNoobies Study Group Arena")
                    await channel.send(embed=embed)
        except Exception as e:
            print(f"[Weekly Group Leaderboard] Main Loop Error: {e}")

    @weekly_group_leaderboard.before_loop
    async def before_weekly_leaderboard(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Social(bot))
