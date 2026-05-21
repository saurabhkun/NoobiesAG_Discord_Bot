# ══════════════════════════════════════════════════════
#  database.py  —  All SQLite database operations
# ══════════════════════════════════════════════════════

import sqlite3
from datetime import datetime, timezone
from config import DB_PATH

# ── Internal connection ────────────────────────────────

def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ── Initialisation ─────────────────────────────────────

def init_db() -> None:
    """Create all tables if they don't exist yet."""
    with _connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS progress (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT    NOT NULL,
                current_day  INTEGER NOT NULL DEFAULT 0,
                updated_at   TEXT    NOT NULL,
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS cf_users (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT    NOT NULL,
                cf_handle    TEXT    NOT NULL,
                last_sub_id  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS study_groups (
                group_name  TEXT PRIMARY KEY,
                creator_id  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_members (
                group_name  TEXT NOT NULL,
                user_id     INTEGER NOT NULL,
                PRIMARY KEY (group_name, user_id),
                FOREIGN KEY (group_name) REFERENCES study_groups(group_name) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS virtual_duels (
                challenger_id   INTEGER NOT NULL,
                challenged_id   INTEGER NOT NULL,
                problem_name    TEXT NOT NULL,
                problem_url     TEXT NOT NULL,
                problem_rating  INTEGER NOT NULL,
                start_time      TEXT NOT NULL,
                duration        INTEGER NOT NULL,
                status          TEXT NOT NULL, -- 'active', 'challenger_won', 'challenged_won', 'draw', 'expired'
                winner_id       INTEGER,
                PRIMARY KEY (challenger_id, challenged_id, start_time)
            );

            CREATE TABLE IF NOT EXISTS private_vcs (
                channel_id   INTEGER PRIMARY KEY,
                user1_id     INTEGER NOT NULL,
                user2_id     INTEGER NOT NULL,
                empty_since  TEXT -- ISO timestamp or NULL
            );

            CREATE TABLE IF NOT EXISTS streak_freezes (
                user_id           INTEGER PRIMARY KEY,
                last_freeze_used  TEXT -- YYYY-MM-DD
            );

            CREATE TABLE IF NOT EXISTS roadmap_progress (
                user_id      INTEGER NOT NULL,
                guild_id     INTEGER NOT NULL,
                topic        TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id, topic)
            );

            CREATE TABLE IF NOT EXISTS doubts (
                thread_id   INTEGER PRIMARY KEY,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                topic       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'open',
                created_at  TEXT NOT NULL,
                resolved_at TEXT,
                resolved_by INTEGER
            );

            CREATE TABLE IF NOT EXISTS upsolves (
                user_id      INTEGER NOT NULL,
                guild_id     INTEGER NOT NULL,
                problem_id   TEXT NOT NULL,
                contest_id   INTEGER NOT NULL,
                problem_name TEXT NOT NULL,
                rating       INTEGER,
                link         TEXT NOT NULL,
                solved       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, guild_id, problem_id)
            );

            CREATE TABLE IF NOT EXISTS economy (
                user_id        INTEGER NOT NULL,
                guild_id       INTEGER NOT NULL,
                xp             INTEGER NOT NULL DEFAULT 0,
                coins          INTEGER NOT NULL DEFAULT 0,
                level          INTEGER NOT NULL DEFAULT 1,
                xp_boost_until TEXT,
                PRIMARY KEY (user_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS achievements (
                user_id         INTEGER NOT NULL,
                guild_id        INTEGER NOT NULL,
                achievement_key TEXT NOT NULL,
                unlocked_at     TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id, achievement_key)
            );

            CREATE TABLE IF NOT EXISTS seasons (
                guild_id      INTEGER NOT NULL,
                season_number INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                points        INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, season_number, user_id)
            );

            CREATE TABLE IF NOT EXISTS hall_of_fame (
                guild_id      INTEGER NOT NULL,
                season_number INTEGER NOT NULL,
                winner_id     INTEGER NOT NULL,
                winner_name   TEXT NOT NULL,
                points        INTEGER NOT NULL,
                ended_at      TEXT NOT NULL,
                PRIMARY KEY (guild_id, season_number)
            );

            CREATE TABLE IF NOT EXISTS tips (
                tip_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                message_id  INTEGER,
                tip_content TEXT NOT NULL,
                upvotes     INTEGER NOT NULL DEFAULT 0,
                downvotes   INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teams (
                team_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id         INTEGER NOT NULL,
                team_name        TEXT NOT NULL,
                leader_id        INTEGER NOT NULL,
                text_channel_id  INTEGER NOT NULL,
                voice_channel_id INTEGER NOT NULL,
                created_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS team_members (
                team_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (team_id, user_id),
                FOREIGN KEY (team_id) REFERENCES teams (team_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS resources (
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                link       TEXT NOT NULL,
                shared_at  TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, link)
            );

            CREATE TABLE IF NOT EXISTS lft_pool (
                user_id   INTEGER NOT NULL,
                guild_id  INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            );
        """)
        # Alter progress table to add last_updated if it's an existing db
        try:
            con.execute("ALTER TABLE progress ADD COLUMN last_updated TEXT")
        except sqlite3.OperationalError:
            pass


# ── Progress helpers ───────────────────────────────────

def save_progress(user_id: int, username: str, day: int) -> None:
    """Insert or update a user's current progress day."""
    from datetime import datetime, timezone, timedelta
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist_tz).isoformat()
    now_utc = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        con.execute(
            """
            INSERT INTO progress (user_id, username, current_day, updated_at, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username     = excluded.username,
                current_day  = excluded.current_day,
                updated_at   = excluded.updated_at,
                last_updated = excluded.last_updated
            """,
            (user_id, username, day, now_utc, now_ist),
        )


def get_progress(user_id: int) -> sqlite3.Row | None:
    """Return the progress row for a user, or None if not found."""
    with _connect() as con:
        return con.execute(
            "SELECT * FROM progress WHERE user_id = ?", (user_id,)
        ).fetchone()


def get_all_progress() -> list[sqlite3.Row]:
    """Return all users' progress rows."""
    with _connect() as con:
        return con.execute("SELECT * FROM progress").fetchall()


# ── Codeforces helpers ─────────────────────────────────

def save_cf_user(user_id: int, username: str, cf_handle: str) -> None:
    """Link a Discord user to a Codeforces handle (upsert)."""
    with _connect() as con:
        con.execute(
            """
            INSERT INTO cf_users (user_id, username, cf_handle, last_sub_id)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                cf_handle = excluded.cf_handle
            """,
            (user_id, username, cf_handle),
        )


def get_cf_user(user_id: int) -> sqlite3.Row | None:
    """Return the CF row for a specific user, or None."""
    with _connect() as con:
        return con.execute(
            "SELECT * FROM cf_users WHERE user_id = ?", (user_id,)
        ).fetchone()


def get_all_cf_users() -> list[sqlite3.Row]:
    """Return all registered CF users."""
    with _connect() as con:
        return con.execute("SELECT * FROM cf_users").fetchall()


def update_last_sub_id(user_id: int, sub_id: int) -> None:
    """Store the most-recently-seen submission ID for a user."""
    with _connect() as con:
        con.execute(
            "UPDATE cf_users SET last_sub_id = ? WHERE user_id = ?",
            (sub_id, user_id),
        )


def reset_progress(user_id: int) -> None:
    """Delete a user's progress row entirely."""
    with _connect() as con:
        con.execute("DELETE FROM progress WHERE user_id = ?", (user_id,))


def delete_cf_user(user_id: int) -> bool:
    """Unlink a user's CF handle. Returns True if a row was deleted."""
    with _connect() as con:
        cur = con.execute("DELETE FROM cf_users WHERE user_id = ?", (user_id,))
        return cur.rowcount > 0


# ── Study Group Helpers ────────────────────────────────

def create_group(group_name: str, creator_id: int) -> None:
    """Create a new study group and add the creator as its first member."""
    with _connect() as con:
        con.execute(
            "INSERT INTO study_groups (group_name, creator_id) VALUES (?, ?)",
            (group_name, creator_id),
        )
        con.execute(
            "INSERT INTO group_members (group_name, user_id) VALUES (?, ?)",
            (group_name, creator_id),
        )


def join_group(group_name: str, user_id: int) -> None:
    """Add a member to a study group."""
    with _connect() as con:
        con.execute(
            "INSERT INTO group_members (group_name, user_id) VALUES (?, ?)",
            (group_name, user_id),
        )


def get_group(group_name: str) -> sqlite3.Row | None:
    """Return the study group row, or None."""
    with _connect() as con:
        return con.execute(
            "SELECT * FROM study_groups WHERE group_name = ?", (group_name,)
        ).fetchone()


def get_group_members(group_name: str) -> list[sqlite3.Row]:
    """Return the user rows for group members, joining progress/cf if available."""
    with _connect() as con:
        return con.execute(
            """
            SELECT gm.user_id, p.username, p.current_day, cfu.cf_handle
            FROM group_members gm
            LEFT JOIN progress p ON gm.user_id = p.user_id
            LEFT JOIN cf_users cfu ON gm.user_id = cfu.user_id
            WHERE gm.group_name = ?
            """,
            (group_name,),
        ).fetchall()


def get_user_group(user_id: int) -> sqlite3.Row | None:
    """Get the group membership row for a user."""
    with _connect() as con:
        return con.execute(
            "SELECT * FROM group_members WHERE user_id = ?", (user_id,)
        ).fetchone()


def leave_group(group_name: str, user_id: int) -> None:
    """Remove a user from a group. If no members left, delete group."""
    with _connect() as con:
        con.execute(
            "DELETE FROM group_members WHERE group_name = ? AND user_id = ?",
            (group_name, user_id),
        )
        # Check if empty
        rem = con.execute(
            "SELECT COUNT(*) as count FROM group_members WHERE group_name = ?",
            (group_name,),
        ).fetchone()
        if rem["count"] == 0:
            con.execute("DELETE FROM study_groups WHERE group_name = ?", (group_name,))


def get_all_groups() -> list[sqlite3.Row]:
    """Get all study groups."""
    with _connect() as con:
        return con.execute("SELECT * FROM study_groups").fetchall()


# ── Virtual Duel Helpers ───────────────────────────────

def create_duel(
    challenger_id: int,
    challenged_id: int,
    problem_name: str,
    problem_url: str,
    problem_rating: int,
    start_time: str,
    duration: int,
) -> None:
    """Create a virtual duel in active status."""
    with _connect() as con:
        con.execute(
            """
            INSERT INTO virtual_duels (
                challenger_id, challenged_id, problem_name, problem_url,
                problem_rating, start_time, duration, status, winner_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', NULL)
            """,
            (
                challenger_id, challenged_id, problem_name, problem_url,
                problem_rating, start_time, duration
            ),
        )


def get_active_duel(user_id: int) -> sqlite3.Row | None:
    """Get the active duel involving this user."""
    with _connect() as con:
        return con.execute(
            """
            SELECT * FROM virtual_duels
            WHERE status = 'active' AND (challenger_id = ? OR challenged_id = ?)
            """,
            (user_id, user_id),
        ).fetchone()


def update_duel_status(
    challenger_id: int, challenged_id: int, start_time: str, status: str, winner_id: int | None
) -> None:
    """Update duel status and winner."""
    with _connect() as con:
        con.execute(
            """
            UPDATE virtual_duels
            SET status = ?, winner_id = ?
            WHERE challenger_id = ? AND challenged_id = ? AND start_time = ?
            """,
            (status, winner_id, challenger_id, challenged_id, start_time),
        )


def get_all_active_duels() -> list[sqlite3.Row]:
    """Get all active duels."""
    with _connect() as con:
        return con.execute("SELECT * FROM virtual_duels WHERE status = 'active'").fetchall()


# ── Private VC Helpers ─────────────────────────────────

def create_vc(channel_id: int, user1_id: int, user2_id: int) -> None:
    """Log a private VC creation."""
    with _connect() as con:
        con.execute(
            "INSERT INTO private_vcs (channel_id, user1_id, user2_id, empty_since) VALUES (?, ?, ?, NULL)",
            (channel_id, user1_id, user2_id),
        )


def get_active_vc(user_id: int) -> sqlite3.Row | None:
    """Get any active private VC involving the user."""
    with _connect() as con:
        return con.execute(
            "SELECT * FROM private_vcs WHERE user1_id = ? OR user2_id = ?",
            (user_id, user_id),
        ).fetchone()


def get_vc(channel_id: int) -> sqlite3.Row | None:
    """Get a private VC record."""
    with _connect() as con:
        return con.execute(
            "SELECT * FROM private_vcs WHERE channel_id = ?", (channel_id,)
        ).fetchone()


def update_vc_empty_since(channel_id: int, empty_since: str | None) -> None:
    """Update empty_since status."""
    with _connect() as con:
        con.execute(
            "UPDATE private_vcs SET empty_since = ? WHERE channel_id = ?",
            (empty_since, channel_id),
        )


def delete_vc(channel_id: int) -> None:
    """Delete a VC record."""
    with _connect() as con:
        con.execute("DELETE FROM private_vcs WHERE channel_id = ?", (channel_id,))


def get_all_vcs() -> list[sqlite3.Row]:
    """Get all recorded private VCs."""
    with _connect() as con:
        return con.execute("SELECT * FROM private_vcs").fetchall()


# ── Streak Freeze Helpers ──────────────────────────────

def use_freeze(user_id: int, last_freeze_used: str) -> None:
    """Set the last freeze used date (YYYY-MM-DD)."""
    with _connect() as con:
        con.execute(
            """
            INSERT INTO streak_freezes (user_id, last_freeze_used)
            VALUES (?, ?)
            ON CONFLICT (user_id) DO UPDATE SET last_freeze_used = excluded.last_freeze_used
            """,
            (user_id, last_freeze_used),
        )


def get_freeze(user_id: int) -> sqlite3.Row | None:
    """Get streak freeze row for user."""
    with _connect() as con:
        return con.execute(
            "SELECT * FROM streak_freezes WHERE user_id = ?", (user_id,)
        ).fetchone()

