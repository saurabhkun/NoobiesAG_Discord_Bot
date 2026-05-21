# ══════════════════════════════════════════════════════
#  cogs/community.py  —  CP Tips, Teams, and Resources
# ══════════════════════════════════════════════════════

import discord
from discord.ext import commands
import database as db
import re
from datetime import datetime, timezone, timedelta
from cogs.economy import award_xp_and_coins

IST = timezone(timedelta(hours=5, minutes=30))


class Community(commands.Cog):
    """Cog for community features: anonymous tips, ICPC team formation, and educational resource sharing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── 1. Anonymous CP Tip Box ────────────────────────

    @commands.command(name="tip")
    @commands.guild_only()
    async def submit_tip(self, ctx: commands.Context, *, tip_content: str) -> None:
        """Submit an anonymous Competitive Programming tip to the tips channel."""
        # Find or create channel 'tips'
        tips_ch = discord.utils.get(ctx.guild.text_channels, name="tips")
        if not tips_ch:
            try:
                from config import SETUP_CATEGORY
                cat = discord.utils.get(ctx.guild.categories, name=SETUP_CATEGORY)
                tips_ch = await ctx.guild.create_text_channel(
                    "tips",
                    category=cat,
                    reason="Auto-created tips channel"
                )
            except Exception:
                try:
                    tips_ch = await ctx.guild.create_text_channel(
                        "tips",
                        reason="Auto-created tips channel"
                    )
                except Exception:
                    await ctx.reply("❌ The `#tips` channel does not exist and I could not create it!")
                    return

        # Delete caller's message to preserve complete anonymity
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        # Fetch tip sequential ID
        now_ist = datetime.now(IST).isoformat()
        with db._connect() as con:
            con.execute(
                "INSERT INTO tips (guild_id, tip_content, message_id, created_at) VALUES (?, ?, 0, ?)",
                (ctx.guild.id, tip_content, now_ist)
            )
            row = con.execute("SELECT last_insert_rowid() as id").fetchone()
            tip_num = row["id"] if row else 1

        # Post tip embed
        embed = discord.Embed(
            title=f"💡 Anonymous CP Tip #{tip_num}",
            description=tip_content,
            color=0x34495E
        )
        embed.set_footer(text="AGNoobies Tip Box • React with 👍 to upvote | 📌 to request pinning (5 required)")
        
        posted_msg = await tips_ch.send(embed=embed)

        # Save actual message id
        with db._connect() as con:
            con.execute("UPDATE tips SET message_id = ? WHERE tip_id = ?", (posted_msg.id, tip_num))

        # Add initial reactions
        await posted_msg.add_reaction("👍")
        await posted_msg.add_reaction("📌")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Auto-pins a tip if it receives 5 or more 📌 reactions."""
        if payload.emoji.name == "📌":
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return
            channel = guild.get_channel(payload.channel_id)
            if not channel or channel.name != "tips":
                return

            try:
                message = await channel.fetch_message(payload.message_id)
                pin_reaction = discord.utils.get(message.reactions, emoji="📌")
                if pin_reaction and pin_reaction.count >= 5:
                    if not message.pinned:
                        await message.pin(reason="Tip reached 5+ 📌 upvotes from community!")
            except Exception as e:
                print(f"[Community Tips Pin] Error: {e}")

    # ── 2. ICPC Team Formation ─────────────────────────

    @commands.command(name="lookingforteam", aliases=["lfpool"])
    @commands.guild_only()
    async def looking_for_team(self, ctx: commands.Context) -> None:
        """Add yourself to the ICPC team formation pool."""
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        now_ist = datetime.now(IST).isoformat()

        with db._connect() as con:
            exists = con.execute(
                "SELECT * FROM lft_pool WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            ).fetchone()

        if exists:
            await ctx.reply("ℹ️ You are already in the team formation pool! Link up with other grinders!")
            return

        with db._connect() as con:
            con.execute("INSERT INTO lft_pool (user_id, guild_id, joined_at) VALUES (?, ?, ?)", (user_id, guild_id, now_ist))

        # Fetch active pool size
        with db._connect() as con:
            pool = con.execute("SELECT user_id FROM lft_pool WHERE guild_id = ?", (guild_id,)).fetchall()

        pool_mentions = []
        for r in pool:
            member = ctx.guild.get_member(r["user_id"])
            if member:
                pool_mentions.append(member.mention)

        embed = discord.Embed(
            title="🤝 ICPC Team Formation Pool",
            description=(
                f"✅ {ctx.author.mention} has joined the team formation pool!\n\n"
                f"👥 **ACTIVE LFT POOL ({len(pool_mentions)} grinders):**\n" +
                ", ".join(pool_mentions) +
                "\n\nFind two partners and run `!formteam @user1 @user2` to set up private workspace channels! 🚀"
            ),
            color=0x2ECC71
        )
        embed.set_footer(text="AGNoobies Team Building Desk")
        await ctx.send(embed=embed)

    @commands.command(name="formteam")
    @commands.guild_only()
    async def form_team(self, ctx: commands.Context, u1: discord.Member, u2: discord.Member) -> None:
        """Form a team with 2 partners, creating custom private text and voice channels."""
        if u1.bot or u2.bot:
            await ctx.reply("❌ You cannot form an ICPC team with bots!")
            return
        if u1 == ctx.author or u2 == ctx.author or u1 == u2:
            await ctx.reply("❌ You must specify two *distinct* team partners other than yourself!")
            return

        team_name = f"team-{ctx.author.name}"
        guild = ctx.guild

        # Setup private channel permissions
        overrides = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
            ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True),
            u1: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True),
            u2: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True)
        }

        # Try to find target Category (e.g. SETUP_CATEGORY)
        category = None
        try:
            from config import SETUP_CATEGORY
            category = discord.utils.get(guild.categories, name=SETUP_CATEGORY)
        except Exception:
            pass

        try:
            text_ch = await guild.create_text_channel(
                name=team_name,
                category=category,
                overwrites=overrides,
                reason=f"ICPC Team formed by {ctx.author}"
            )
            voice_ch = await guild.create_voice_channel(
                name=team_name,
                category=category,
                overwrites=overrides,
                reason=f"ICPC Team formed by {ctx.author}"
            )

            # Persist Team inside DB
            now_ist = datetime.now(IST).isoformat()
            with db._connect() as con:
                con.execute(
                    "INSERT INTO teams (team_name, guild_id, leader_id, text_channel_id, voice_channel_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (team_name, guild.id, ctx.author.id, text_ch.id, voice_ch.id, now_ist)
                )
                row = con.execute("SELECT last_insert_rowid() as id").fetchone()
                team_id = row["id"] if row else 1
                con.execute("INSERT INTO team_members (team_id, user_id) VALUES (?, ?)", (team_id, ctx.author.id))
                con.execute("INSERT INTO team_members (team_id, user_id) VALUES (?, ?)", (team_id, u1.id))
                con.execute("INSERT INTO team_members (team_id, user_id) VALUES (?, ?)", (team_id, u2.id))

                # Remove from LFT pool
                con.execute("DELETE FROM lft_pool WHERE user_id IN (?, ?, ?) AND guild_id = ?", (ctx.author.id, u1.id, u2.id, guild.id))

            embed = discord.Embed(
                title="🏆 ICPC Team Formed!",
                description=(
                    f"⚔️ **Team formed successfully!**\n\n"
                    f"👥 **Members:**\n"
                    f"👑 **Leader:** {ctx.author.mention}\n"
                    f"• {u1.mention}\n"
                    f"• {u2.mention}\n\n"
                    f"🔒 **Your Private Workspaces:**\n"
                    f"💬 Text: {text_ch.mention}\n"
                    f"🔊 Voice: {voice_ch.mention}\n\n"
                    f"Grind together, learn together, conquer ICPC together! 🦾"
                ),
                color=0x9B59B6
            )
            await ctx.send(embed=embed)
            await text_ch.send(embed=embed)

        except discord.Forbidden:
            await ctx.reply("❌ Missing permissions to create channels or manage roles!")
        except Exception as e:
            await ctx.reply(f"❌ Failed to form team: {e}")

    # ── 3. Resource Sharing Tracker ─────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Scan messages in resources channel, logging Youtube/CF educational link shares and rewarding XP."""
        if message.author.bot or message.guild is None:
            return

        if message.channel.name != "resources":
            return

        content = message.content
        # Regex to find CF blog posts or Youtube videos
        yt_regex = r"(https?://(?:www\.)?youtube\.com/watch\?v=\S+|https?://(?:www\.)?youtu\.be/\S+)"
        cf_regex = r"(https?://codeforces\.com/blog/entry/\d+)"

        matched_yt = re.search(yt_regex, content)
        matched_cf = re.search(cf_regex, content)

        url = None
        if matched_yt:
            url = matched_yt.group(1)
        elif matched_cf:
            url = matched_cf.group(1)

        if url:
            user_id = message.author.id
            guild_id = message.guild.id
            now_ist = datetime.now(IST).isoformat()

            # Save resource in database
            with db._connect() as con:
                con.execute(
                    "INSERT INTO resources (guild_id, user_id, link, shared_at) VALUES (?, ?, ?, ?)",
                    (guild_id, user_id, url, now_ist)
                )

            # Reward +20 XP and +10 coins
            try:
                await award_xp_and_coins(self.bot, message.guild, user_id, 20, 10, reason="shared_resource")
                await message.reply(
                    f"💡 **Resource logged!** Thank you for contributing to the community! **+20 XP** and **+10 coins** awarded! 🪙"
                )
            except Exception as e:
                print(f"[Resource XP Award] Error: {e}")

            # Trigger achievements check for Guru badge
            try:
                ach_cog = self.bot.get_cog("Achievements")
                if ach_cog:
                    await ach_cog.check_achievements(message.guild, user_id)
            except Exception as e:
                print(f"[Resource Achievements Check] Error: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Community(bot))
