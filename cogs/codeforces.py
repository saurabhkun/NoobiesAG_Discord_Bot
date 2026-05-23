# ══════════════════════════════════════════════════════
#  cogs/codeforces.py  —  Codeforces tracker cog
# ══════════════════════════════════════════════════════

import asyncio
import aiohttp
import discord
from discord.ext import commands, tasks

import database as db
from config import CF_ACTIVITY_CHANNEL, CF_POLL_INTERVAL, CF_SUBMISSION_COUNT
from utils.helpers import cf_submission_embed


class Codeforces(commands.Cog):
    """Cog for linking Codeforces accounts and tracking accepted submissions."""

    CF_BASE = "https://codeforces.com/api"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None

    # ── Session lifecycle ──────────────────────────────

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession()
        self.poll_submissions.start()

    async def cog_unload(self) -> None:
        self.poll_submissions.cancel()
        if self._session:
            await self._session.close()

    # ── HTTP helpers ───────────────────────────────────

    async def _get_json(self, url: str) -> dict | None:
        """Perform a GET request and return parsed JSON, or None on error."""
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except Exception:
            return None

    async def _verify_handle(self, handle: str) -> bool:
        """Return True if the CF handle corresponds to a real user."""
        data = await self._get_json(f"{self.CF_BASE}/user.info?handles={handle}")
        return data is not None and data.get("status") == "OK"

    # ── Commands ───────────────────────────────────────

    @commands.command(name="setcf")
    async def set_cf(self, ctx: commands.Context, handle: str = None) -> None:
        """Link your Codeforces handle: !setcf <handle>"""
        if handle is None:
            await ctx.reply("❌ Usage: `!setcf <your_codeforces_handle>`")
            return

        verifying_msg = await ctx.reply(
            f"🔍 Verifying Codeforces handle **{handle}**…"
        )

        if not await self._verify_handle(handle):
            await verifying_msg.edit(
                content=(
                    f"❌ Could not find a Codeforces account with handle **{handle}**.\n"
                    "Please double-check the spelling and try again."
                )
            )
            return

        db.save_cf_user(ctx.author.id, str(ctx.author), handle)
        await verifying_msg.edit(
            content=(
                f"✅ Your Codeforces handle has been linked to **{handle}**!\n"
                "I'll start tracking your submissions every 5 minutes. 🏅"
            )
        )

    @commands.command(name="mycf")
    async def my_cf(self, ctx: commands.Context) -> None:
        """Check which Codeforces handle is linked to your account."""
        row = db.get_cf_user(ctx.author.id)
        if row:
            profile_url = f"https://codeforces.com/profile/{row['cf_handle']}"
            await ctx.reply(
                f"🔗 Your linked handle: **[{row['cf_handle']}]({profile_url})**"
            )
        else:
            await ctx.reply(
                "ℹ️ No Codeforces handle linked yet. Use `!setcf <handle>` to register."
            )

    @commands.command(name="unsetcf", aliases=["unlinkcf", "removecf"])
    async def unset_cf(self, ctx: commands.Context) -> None:
        """Unlink your Codeforces handle."""
        removed = db.delete_cf_user(ctx.author.id)
        if removed:
            await ctx.reply(
                "✅ Your Codeforces handle has been unlinked. "
                "Use `!setcf <handle>` to link a new one."
            )
        else:
            await ctx.reply(
                "ℹ️ You don't have a Codeforces handle linked. "
                "Use `!setcf <handle>` to register."
            )

    # ── Background poller ──────────────────────────────


    @tasks.loop(seconds=CF_POLL_INTERVAL)
    async def poll_submissions(self) -> None:
        """Check recent submissions for every registered user every 5 minutes."""
        try:
            users = db.get_all_cf_users()
            if not users:
                return

            for row in users:
                user_id     = row["user_id"]
                username    = row["username"]
                cf_handle   = row["cf_handle"]
                last_sub_id = row["last_sub_id"]

                try:
                    url = (
                        f"{self.CF_BASE}/user.status"
                        f"?handle={cf_handle}&count={CF_SUBMISSION_COUNT}"
                    )
                    data = await self._get_json(url)
                    if data is None or data.get("status") != "OK":
                        continue

                    submissions: list[dict] = data["result"]
                    new_accepted: list[dict] = []
                    highest_id = last_sub_id

                    if not submissions:
                        continue

                    for sub in submissions:
                        sub_id = sub["id"]
                        if sub_id > highest_id:
                            highest_id = sub_id

                    # If first registration (last_sub_id == 0)
                    if last_sub_id == 0:
                        if highest_id > 0:
                            db.update_last_sub_id(user_id, highest_id)
                        continue

                    for sub in submissions:
                        sub_id = sub["id"]
                        if sub_id > last_sub_id and sub.get("verdict") == "OK":
                            new_accepted.append(sub)

                    # Advance watermark regardless of accepted status
                    if highest_id > last_sub_id:
                        db.update_last_sub_id(user_id, highest_id)

                    if not new_accepted:
                        continue

                    # Post into every guild's #cf-activity channel
                    for guild in self.bot.guilds:
                        channel = discord.utils.get(
                            guild.channels, name=CF_ACTIVITY_CHANNEL
                        )
                        if channel is None:
                            continue

                        member = guild.get_member(user_id)
                        mention = member.mention if member else f"**{username}**"

                        for sub in new_accepted:
                            problem      = sub["problem"]
                            p_name       = problem.get("name", "Unknown Problem")
                            contest_id   = problem.get("contestId", "")
                            p_index      = problem.get("index", "")
                            p_rating     = problem.get("rating")
                            problem_url  = (
                                f"https://codeforces.com/contest/{contest_id}/problem/{p_index}"
                                if contest_id else "https://codeforces.com"
                            )

                            embed = cf_submission_embed(
                                mention      = mention,
                                cf_handle    = cf_handle,
                                problem_name = p_name,
                                problem_url  = problem_url,
                                contest_id   = contest_id,
                                rating       = p_rating,
                            )
                            await channel.send(embed=embed)

                except Exception as exc:
                    print(f"[CF Poller] Error for {cf_handle}: {exc}")

                # Small pause between users to avoid hammering the CF API
                await asyncio.sleep(1.5)
        except Exception as e:
            print(f"[CF Poller Task] Outer Loop Error: {e}")

    @poll_submissions.before_loop
    async def before_poll(self) -> None:
        await self.bot.wait_until_ready()

    @poll_submissions.error
    async def poll_error(self, error: Exception) -> None:
        print(f"[CF Poller] Task crashed: {error}")
        # Auto-restart after 60 s
        await asyncio.sleep(60)
        self.poll_submissions.restart()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Codeforces(bot))
