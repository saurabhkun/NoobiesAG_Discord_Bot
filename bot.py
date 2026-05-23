# ══════════════════════════════════════════════════════
#  bot.py  —  Entry point: loads cogs and starts bot
# ══════════════════════════════════════════════════════

import asyncio
import traceback
import discord
from discord.ext import commands

import database as db
from config import BOT_TOKEN, TIER_ROLES

# ── Intents ────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


# ── Bot subclass ───────────────────────────────────────

class Bot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        """Called once before the bot connects. Load cogs here."""
        db.init_db()
        print("[DB] Database initialised.")

        cogs = [
            "cogs.help",
            "cogs.setup",
            "cogs.admin",
            "cogs.progress",
            "cogs.codeforces",
            "cogs.problems",
            "cogs.contests",
            "cogs.stats",
            "cogs.social",
            "cogs.scheduler",
            "cogs.economy",
            "cogs.roadmap",
            "cogs.doubts",
            "cogs.analytics",
            "cogs.achievements",
            "cogs.seasons",
            "cogs.community",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"   [OK] Loaded cog: {cog}")
            except Exception:
                print(f"   [ERROR] Failed to load cog: {cog}")
                traceback.print_exc()

    async def on_ready(self) -> None:
        print(f"\n[Bot] Logged in as {self.user} (ID: {self.user.id})")
        print(f"   Guilds  : {len(self.guilds)}")
        print(f"   Latency : {round(self.latency * 1000)} ms")

        # ── Role hierarchy sanity check ────────────────
        tier_names = {t["name"] for t in TIER_ROLES}
        for guild in self.guilds:
            bot_member = guild.get_member(self.user.id)
            if bot_member is None:
                continue
            bot_top = bot_member.top_role
            problem = [
                r for r in guild.roles
                if r.name in tier_names and r >= bot_top
            ]
            if problem:
                names = ", ".join(f"'{r.name}'" for r in problem)
                print(f"\n[WARNING] [{guild.name}] ROLE HIERARCHY ISSUE!")
                print(f"   Bot's top role '{bot_top.name}' is BELOW: {names}")
                print(f"   -> Go to Server Settings -> Roles and drag '{bot_top.name}'")
                print(f"     ABOVE all tier roles, otherwise role assignment will fail.\n")
            else:
                print(f"   [{guild.name}] Role hierarchy OK (bot top role: '{bot_top.name}')")
        print()

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Global command error handler."""
        if isinstance(error, commands.CommandNotFound):
            return  # Silently ignore unknown commands

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                f"❌ Missing argument: `{error.param.name}`. "
                f"Run `!help {ctx.command}` for usage."
            )
            return

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(
                f"⏳ Slow down! Try again in `{error.retry_after:.1f}s`."
            )
            return

        # Unexpected error — log it and notify the user
        print(f"[Error] Command '{ctx.command}': {error}")
        traceback.print_exc()
        await ctx.reply("⚠️ An unexpected error occurred. Please try again later.")


from keep_alive import keep_alive

# ── Runner ─────────────────────────────────────────────

async def main() -> None:
    async with Bot() as bot:
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())

