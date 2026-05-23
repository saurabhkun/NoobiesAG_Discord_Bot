# ══════════════════════════════════════════════════════
#  cogs/economy.py  —  XP, Coins, and Shop System
# ══════════════════════════════════════════════════════

import discord
from discord.ext import commands
import database as db
from datetime import datetime, timezone, timedelta
import re

IST = timezone(timedelta(hours=5, minutes=30))

# ── Economy Helpers ────────────────────────────────────

async def award_xp_and_coins(bot: commands.Bot, guild: discord.Guild, user_id: int, xp: int, coins: int, reason: str = None) -> None:
    """Award XP and Coins to a user, handling level ups and XP boosts."""
    # Ensure they exist in database
    with db._connect() as con:
        row = con.execute("SELECT * FROM economy WHERE user_id = ? AND guild_id = ?", (user_id, guild.id)).fetchone()
        
    curr_xp = 0
    curr_coins = 0
    curr_level = 1
    xp_boost_until = None
    
    if row:
        curr_xp = row["xp"]
        curr_coins = row["coins"]
        curr_level = row["level"]
        xp_boost_until = row["xp_boost_until"]

    # Check for XP Boost
    boosted = False
    if xp_boost_until:
        try:
            expire_time = datetime.fromisoformat(xp_boost_until)
            if datetime.now(timezone.utc) < expire_time:
                boosted = True
        except ValueError:
            pass

    actual_xp = xp * 2 if boosted else xp
    actual_coins = coins

    new_xp = curr_xp + actual_xp
    new_coins = curr_coins + actual_coins
    new_level = 1 + (new_xp // 500)

    with db._connect() as con:
        con.execute("""
            INSERT INTO economy (user_id, guild_id, xp, coins, level, xp_boost_until)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
                xp = excluded.xp,
                coins = excluded.coins,
                level = excluded.level
        """, (user_id, guild.id, new_xp, new_coins, new_level, xp_boost_until))

    # Also award season points for CF solves, days completed, duels won
    # points = xp
    if reason in ["cf_solve", "day_completed", "duel_won"]:
        points_to_award = xp
        with db._connect() as con:
            # Get current season number (default to 1)
            # Seasons are per guild
            now = datetime.now(IST)
            season_num = now.month  # Season based on month
            con.execute("""
                INSERT INTO seasons (guild_id, season_number, user_id, points)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, season_number, user_id) DO UPDATE SET
                    points = points + excluded.points
            """, (guild.id, season_num, user_id, points_to_award))

    # Level Up Announcement
    if new_level > curr_level:
        channel = discord.utils.get(guild.channels, name="progress-updates")
        if channel:
            member = guild.get_member(user_id)
            if member:
                embed = discord.Embed(
                    title="🎉 LEVEL UP!",
                    description=(
                        f"🔼 {member.mention} has advanced to **Level {new_level}**! 🚀\n"
                        f"XP: `{new_xp}/{new_level*500}`\n\n"
                        f"Keep grinding, you're absolute legend in the making! 💪"
                    ),
                    color=0x2ECC71
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text="AGNoobies Economy System")
                await channel.send(embed=embed)

        # Trigger achievement check on level up to Legend tier
        try:
            ach_cog = bot.get_cog("Achievements")
            if ach_cog:
                await ach_cog.check_achievements(guild, user_id)
        except Exception as e:
            print(f"[Economy] Error checking achievements on level up: {e}")


class Economy(commands.Cog):
    """Cog to manage CP-themed XP, coins, and the virtual upgrade shop."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Commands ───────────────────────────────────────

    @commands.command(name="xp", aliases=["level", "lvl"])
    @commands.guild_only()
    async def view_xp(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Show current level, XP, and progress bar to next level."""
        target = member or ctx.author
        
        with db._connect() as con:
            row = con.execute("SELECT * FROM economy WHERE user_id = ? AND guild_id = ?", (target.id, ctx.guild.id)).fetchone()

        xp = row["xp"] if row else 0
        coins = row["coins"] if row else 0
        level = row["level"] if row else 1
        xp_boost_until = row["xp_boost_until"] if row else None

        # Level calculation
        base_xp = (level - 1) * 500
        xp_in_level = xp - base_xp
        next_level_xp = 500

        # Progress bar
        from utils.helpers import progress_bar
        bar = progress_bar(xp_in_level, next_level_xp, length=12)

        boost_str = ""
        if xp_boost_until:
            try:
                expire_time = datetime.fromisoformat(xp_boost_until)
                remaining = expire_time - datetime.now(timezone.utc)
                if remaining.total_seconds() > 0:
                    hrs = int(remaining.total_seconds() // 3600)
                    mins = int((remaining.total_seconds() % 3600) // 60)
                    boost_str = f"\n⚡ **XP Boost Active:** `2x XP` for `{hrs}h {mins}m` remaining"
            except ValueError:
                pass

        embed = discord.Embed(
            title=f"📊 CP Profile — {target.display_name}",
            color=0x3498DB
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.description = (
            f"💪 **Level:** `{level}`\n"
            f"⭐ **Total XP:** `{xp}`\n"
            f"🪙 **Coin Balance:** `{coins} coins`\n\n"
            f"**Level Progress:**\n"
            f"`{bar}` `{xp_in_level}/{next_level_xp}`"
            f"{boost_str}"
        )
        embed.set_footer(text="AGNoobies Economy Tracker")
        await ctx.reply(embed=embed)

    @commands.command(name="balance", aliases=["bal", "coins"])
    @commands.guild_only()
    async def view_balance(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Show coin balance."""
        target = member or ctx.author
        with db._connect() as con:
            row = con.execute("SELECT coins FROM economy WHERE user_id = ? AND guild_id = ?", (target.id, ctx.guild.id)).fetchone()
        
        coins = row["coins"] if row else 0
        await ctx.reply(f"🪙 **{target.display_name}** has **{coins}** coins.")

    @commands.command(name="xpleaderboard", aliases=["xplb"])
    @commands.guild_only()
    async def xp_leaderboard(self, ctx: commands.Context) -> None:
        """Show top 10 users ranked by overall XP."""
        with db._connect() as con:
            rows = con.execute(
                "SELECT user_id, xp, level FROM economy WHERE guild_id = ? ORDER BY xp DESC LIMIT 10",
                (ctx.guild.id,)
            ).fetchall()

        if not rows:
            await ctx.reply("No economy records found yet.")
            return

        embed = discord.Embed(
            title="🏆 OVERALL XP LEADERBOARD",
            color=0xF1C40F,
            description="```\n#   Name                 Level   XP\n" + "─" * 38 + "```"
        )
        
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for idx, row in enumerate(rows):
            medal = medals[idx] if idx < 3 else f"`{idx + 1:2d}.`"
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name[:18] if member else f"User {row['user_id']}"
            lines.append(f"{medal}  **{name:<18}** — Lvl **{row['level']}**  (`{row['xp']} XP`)")

        embed.add_field(name="\u200b", value="\n".join(lines), inline=False)
        embed.set_footer(text="AGNoobies Economy System")
        await ctx.reply(embed=embed)

    @commands.command(name="shop")
    @commands.guild_only()
    async def view_shop(self, ctx: commands.Context) -> None:
        """Show available items in the upgrade shop."""
        embed = discord.Embed(
            title="🛒 AGNoobies Upgrade Shop",
            description=(
                "Boost your consistency, customize your tags, and level up faster! Use `!buy <item>` to purchase.\n\n"
                "🧊 **Streak Freeze** — `100 coins`\n"
                "> Protect your consistency streak for 1 day. `!buy streak_freeze`\n\n"
                "🎨 **Custom Role Color** — `500 coins`\n"
                "> Pick any hex color for your tier role (or personal role). `!buy custom_role_color #hex`\n\n"
                "📛 **Nickname Color** — `300 coins`\n"
                "> Colored nickname personal role. `!buy nickname_color #hex`\n\n"
                "⚡ **XP Boost 24h** — `400 coins`\n"
                "> Receive 2x XP for all activities for the next 24 hours. `!buy xp_boost`\n\n"
                "🎯 **Problem Skip** — `200 coins`\n"
                "> Skip one calendar day without your consistency streak resetting. `!buy problem_skip`"
            ),
            color=0xE67E22
        )
        embed.set_footer(text="AGNoobies Shop • Competitive Programming Upgrades")
        await ctx.reply(embed=embed)

    @commands.command(name="buy")
    @commands.guild_only()
    async def buy_item(self, ctx: commands.Context, item_name: str, *, arg: str = None) -> None:
        """Purchase an item from the upgrade shop."""
        user_id = ctx.author.id
        guild_id = ctx.guild.id

        with db._connect() as con:
            row = con.execute("SELECT coins, xp_boost_until FROM economy WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)).fetchone()

        if not row or row["coins"] < 0:
            await ctx.reply("❌ You do not have enough coins! Go solve some Codeforces problems! 💻")
            return

        coins = row["coins"]
        item_key = item_name.lower().strip()

        # Define item prices
        prices = {
            "streak_freeze": 100,
            "freeze": 100,
            "custom_role_color": 500,
            "color": 500,
            "nickname_color": 300,
            "nickname": 300,
            "xp_boost": 400,
            "boost": 400,
            "problem_skip": 200,
            "skip": 200
        }

        # Resolve aliases
        resolved_key = None
        for k in prices:
            if item_key == k:
                resolved_key = k
                break
        
        if not resolved_key:
            await ctx.reply("❌ Invalid item! Check available items in `!shop`.")
            return

        price = prices[resolved_key]
        if coins < price:
            await ctx.reply(f"❌ Insufficient balance! **{item_name}** costs `{price} coins`, but you only have `{coins} coins`.")
            return

        # Handle specific items
        success = False
        message = ""

        if resolved_key in ["streak_freeze", "freeze"]:
            # Give streak freeze
            now = datetime.now(IST)
            today_iso = now.date().isoformat()
            db.use_freeze(user_id, today_iso)
            success = True
            message = "🧊 **Streak Freeze activated!** Your consistency streak is protected for today. 🛡️"

        elif resolved_key in ["custom_role_color", "color", "nickname_color", "nickname"]:
            if not arg:
                await ctx.reply("❌ Hex color required! Example: `!buy custom_role_color #FF5733`")
                return
            
            # Validate hex color
            hex_match = re.search(r"^#?([A-Fa-f0-9]{6})$", arg.strip())
            if not hex_match:
                await ctx.reply("❌ Invalid hex color format! Please use `#RRGGBB` format.")
                return

            color_int = int(hex_match.group(1), 16)
            color_obj = discord.Color(color_int)

            # Create personal custom color role
            role_name = f"Color: {ctx.author.name}"
            # Check if role already exists
            existing_role = discord.utils.get(ctx.guild.roles, name=role_name)
            
            try:
                if existing_role:
                    await existing_role.edit(color=color_obj, reason=f"Shop custom color update by {ctx.author}")
                    role = existing_role
                else:
                    role = await ctx.guild.create_role(
                        name=role_name,
                        color=color_obj,
                        reason=f"Shop custom color role purchase by {ctx.author}"
                    )
                    # Put it above tier roles if possible
                    # Find highest tier role or bot role to position it below bot role
                    bot_member = ctx.guild.get_member(self.bot.user.id)
                    pos = max(1, bot_member.top_role.position - 1)
                    await role.edit(position=pos)
                
                if role not in ctx.author.roles:
                    await ctx.author.add_roles(role)

                success = True
                message = f"🎨 **Custom role color applied successfully!** Your personal color is now set to `{arg}`! ✨"
            except (discord.Forbidden, discord.HTTPException) as e:
                await ctx.reply(f"❌ Failed to manage roles: {e}. Move the bot's role HIGHER in the server settings.")
                return

        elif resolved_key in ["xp_boost", "boost"]:
            current_boost = row["xp_boost_until"]
            now_utc = datetime.now(timezone.utc)
            
            if current_boost:
                try:
                    expire_time = datetime.fromisoformat(current_boost)
                    if now_utc < expire_time:
                        new_expire = expire_time + timedelta(hours=24)
                    else:
                        new_expire = now_utc + timedelta(hours=24)
                except ValueError:
                    new_expire = now_utc + timedelta(hours=24)
            else:
                new_expire = now_utc + timedelta(hours=24)

            new_expire_str = new_expire.isoformat()
            
            with db._connect() as con:
                con.execute("UPDATE economy SET xp_boost_until = ? WHERE user_id = ? AND guild_id = ?", (new_expire_str, user_id, guild_id))
            
            success = True
            message = "⚡ **XP Boost 24h purchased!** You will earn `2x XP` for all achievements and activities for the next 24 hours! 🚀"

        elif resolved_key in ["problem_skip", "skip"]:
            # Set progress last updated to today's date in IST so streak checker is satisfied
            # Also increment day by 1 if they want, but a skip usually keeps them safe without day progress
            # Actually, let's just make their progress last updated to now so they don't break streak
            progress_row = db.get_progress(user_id)
            if not progress_row or progress_row["current_day"] == 0:
                await ctx.reply("❌ You haven't started your consistency journey! Submit `day 1 done` first.")
                return

            # Keep current day, but update 'updated_at' to current timestamp so they have 3 more days
            now_utc = datetime.now(timezone.utc).isoformat()
            now_ist = datetime.now(IST).isoformat()
            with db._connect() as con:
                con.execute(
                    "UPDATE progress SET updated_at = ?, last_updated = ? WHERE user_id = ?",
                    (now_utc, now_ist, user_id)
                )
            
            success = True
            message = "🎯 **Problem Skip applied!** Your streak is protected. You successfully skipped today without resetting! 🛡️"

        if success:
            new_balance = coins - price
            with db._connect() as con:
                con.execute("UPDATE economy SET coins = ? WHERE user_id = ? AND guild_id = ?", (new_balance, user_id, guild_id))
            
            embed = discord.Embed(
                title="🛍️ Purchase Successful!",
                description=f"{message}\n\n🪙 **Remaining Balance:** `{new_balance} coins`",
                color=0x2ECC71
            )
            embed.set_footer(text="AGNoobies Shop")
            await ctx.reply(embed=embed)

    @commands.command(name="give", aliases=["gift", "transfer"])
    @commands.guild_only()
    async def gift_coins(self, ctx: commands.Context, target: discord.Member, amount: int) -> None:
        """Gift a specified amount of coins to another user."""
        if target.bot:
            await ctx.reply("❌ You cannot gift coins to bots!")
            return
        if target.id == ctx.author.id:
            await ctx.reply("❌ You cannot gift coins to yourself!")
            return
        if amount <= 0:
            await ctx.reply("❌ Amount must be positive!")
            return

        with db._connect() as con:
            row = con.execute("SELECT coins FROM economy WHERE user_id = ? AND guild_id = ?", (ctx.author.id, ctx.guild.id)).fetchone()

        if not row or row["coins"] < amount:
            await ctx.reply("❌ Insufficient coin balance for this transfer!")
            return

        sender_new = row["coins"] - amount

        with db._connect() as con:
            # Update sender
            con.execute("UPDATE economy SET coins = ? WHERE user_id = ? AND guild_id = ?", (sender_new, ctx.author.id, ctx.guild.id))
            # Update receiver
            con.execute("""
                INSERT INTO economy (user_id, guild_id, xp, coins, level, xp_boost_until)
                VALUES (?, ?, 0, ?, 1, NULL)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET coins = coins + excluded.coins
            """, (target.id, ctx.guild.id, amount))

        await ctx.reply(f"🪙 **Transaction complete!** Gifted `{amount} coins` to {target.mention}. Keep grinding together! 🦾")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
