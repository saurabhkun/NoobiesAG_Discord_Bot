# 🖥️ noobiesAG - CP Discord Bot

[![Made with Python](https://img.shields.io/badge/Made%20with-Python-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Discord.py](https://img.shields.io/badge/Discord.py-2.x-blue?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![Database SQLite](https://img.shields.io/badge/Database-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

A feature-rich Discord bot built for Competitive Programming communities. Track progress, compete with friends, and level up your CP journey.

---

## ✨ Features

### 📋 Progress Tracking

- **Daily Consistency Tracker:** Log your daily coding activity with standard check-ins.
- **Anti-Cheat Validation:** Restricts progress submissions to a single calendar-day submission strictly based on the Indian Standard Time (IST) timezone.
- **Hoist Rank Roles:** Dynamically assigns hoisted server roles as you cross consistency milestones.

### ⚔️ Codeforces Integration

- **Stats Viewer:** Retrieve rich metrics, current ratings, tier standings, and recent accepted solutions.
- **Virtual Duels:** Initiate synchronous 2-hour practice duels against rivals over auto-selected average-rated problems.
- **Problem Recommender:** Suggests unsolved problems matching your target rating difficulty.

### 📈 Performance Analytics

- **PIL-Drawn Heatmap:** Renders a gorgeous, dark-themed Codeforces contribution calendar grid using Pillow.
- **Weakness Finder:** Scans your recent 200 submissions to identify your weakest (highest WA rate) and strongest tags.
- **Expected Rating Delta:** Estimate rating changes for finished contests using a custom log-expectation math formula.
- **Upsolving Backlog:** Instantly import uncompleted contest problems to a persistent personal database backlog.

### 🪙 Gamified Economy & Virtual Shop

- **XP and Coins System:** Earn XP and coins for consistency, roadmap topics, doubt solving, resource sharing, and duels.
- **Progressive Level Ups:** Celebrate leveling up every 500 XP with server updates and coin boosts.
- **Interactive Upgrades Shop:** Buy Streak Freezes, XP multipliers, custom role colors, and problem skips using earned coins.

### 🎯 Roadmaps & Achievement Badges

- **Checkpoint Roadmaps:** Built-in 4-phase CP learning guide with structured checklists and percentage meters.
- **Automatic Badges:** Automatically checks, awards, and announces 12 premium milestone achievement badges.

### 💬 Doubt Forums & Community Engagement

- **Doubt Tagging:** Spawn private, dedicated forum threads for doubt resolution, and reward helpers.
- **Anonymous Tip Box:** Post anonymous CP advice with auto-pin checks triggered by community pushpins.
- **LFT Pool & ICPC Teams:** Queue up in a matchmaking lobby, and auto-build text/VC workspaces with your two partners.
- **Resource Tracker:** Auto-detect and log educational YouTube/Codeforces blog links in a designated channel.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- pip (Python package installer)
- An active Discord bot account (via Discord Developer Portal)

### Installation Steps

1.  **Clone the Repository:**

    ```bash
    git clone https://github.com/saurabhkun/NoobiesAG_Discord_Bot
    ```

2.  **Navigate to the Directory:**

    ```bash
    cd NoobiesAG_Discord_Bot
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### How to Get a Discord Bot Token

1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2.  Click **New Application**, give it a name, and click **Create**.
3.  Navigate to the **Bot** tab on the left.
4.  Click **Add Bot** and confirm.
5.  Under **Token**, click **Reset Token** and copy the secret key.
6.  Scroll down to **Privileged Gateway Intents** and enable **Presence Intent**, **Server Members Intent**, and **Message Content Intent**.
7.  Go to **OAuth2** -> **URL Generator**, select the scopes `bot` and `applications.commands`, select administrator permissions, and paste the generated URL into a browser to invite the bot to your server.

### Configuration

1.  Create a `.env` file in the project root.
2.  Open it and input your copied Discord Bot Token:
    ```env
    DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
    ```
3.  Open `config.py` and customize local channel names, phase ranges, custom tier roles, and database file paths if needed.

### Running the Bot

Once configured, boot the bot by running:

```bash
python bot.py
```

---

## 📁 Project Structure

```
NoobiesAG_Discord_Bot/
├── .env                  # Environment variables (DISCORD_TOKEN)
├── .gitignore            # Git ignore rules
├── LICENSE               # MIT License
├── README.md             # This file
├── bot.py                # Entry point — loads cogs and starts the bot
├── config.py             # Central configuration (channels, roles, tiers)
├── database.py           # All SQLite database operations
├── requirements.txt      # Python dependencies
├── cogs/                 # Discord.py command extensions
│   ├── achievements.py   # 12 automatic achievement badges
│   ├── admin.py          # Admin commands (setup, reset)
│   ├── analytics.py      # Heatmaps, weakness finder, rating predictor
│   ├── codeforces.py     # CF handle linking & submission polling
│   ├── community.py      # Anonymous tips, ICPC teams, resource tracker
│   ├── contests.py       # Upcoming contests & weekly mini-contests
│   ├── doubts.py         # Doubt forum threads & resolution
│   ├── economy.py        # XP, coins, shop, leveling system
│   ├── help.py           # Interactive paginated help menu
│   ├── problems.py       # Problem recommender & virtual duels
│   ├── progress.py       # Daily consistency tracker & leaderboard
│   ├── roadmap.py        # CP learning roadmap checklists
│   ├── scheduler.py      # Daily announcements & streak resets
│   ├── seasons.py        # Monthly competitive seasons & Hall of Fame
│   ├── setup.py          # Server initialization (channels, roles)
│   ├── social.py         # Study groups, partner finder, private VCs
│   └── stats.py          # CF stats viewer & head-to-head comparisons
└── utils/
    └── helpers.py        # Shared utilities (tier progress, embeds, bars)
```

---

## ⚙️ Configuration File Overview

You can adjust bot configurations inside `config.py`:

- `PROGRESS_CHANNEL`: Name of the text channel for progress check-in announcements.
- `CF_ACTIVITY_CHANNEL`: Name of the channel where duels, seasons, and contest updates are posted.
- `SETUP_CATEGORY`: Category folder under which new ICPC team channels and doubts are organized.
- `CF_POLL_INTERVAL`: Fetch frequency (in seconds) for tracking Codeforces submissions.
- `DB_PATH`: Path to the SQLite database file (default: `bot_data.db`).

All of these values can also be set via environment variables in the `.env` file.

---

## 📋 Commands

### 📋 Progress Tracker Module

| Command             | Description                                                                  | Example            |
| :------------------ | :--------------------------------------------------------------------------- | :----------------- |
| `!progress`         | View your current day, rank tier, phase milestones, and progress statistics. | `!progress`        |
| `!leaderboard`      | See the top 10 grinders on the server ranked by their current day.           | `!leaderboard`     |
| `!freeze`           | Activate streak freeze to protect consistency for 1 day.                     | `!freeze`          |
| `!setcf <handle>`   | Link your Codeforces handle/username to your Discord account.                | `!setcf tourist`   |
| `!unsetcf`          | Unlink your Codeforces handle from your Discord account.                     | `!unsetcf`         |
| `!cfstats [handle]` | Show Codeforces profile metrics, total solves, and last 5 accepted problems. | `!cfstats tourist` |

### ⚔️ Codeforces Module

| Command                 | Description                                                                | Example                   |
| :---------------------- | :------------------------------------------------------------------------- | :------------------------ |
| `!giveproblem <rating>` | Suggest a random unsolved Codeforces problem matching a difficulty rating. | `!giveproblem 1400`       |
| `!virtualduel @user`    | Start a 2-hour virtual duel over an unsolved average-rated problem.        | `!virtualduel @tourist`   |
| `!compare @u1 @u2`      | Compare Codeforces statistics and solving profiles side-by-side.           | `!compare @tourist @Benq` |

### 🏆 Contests Module

| Command          | Description                                                                   | Example          |
| :--------------- | :---------------------------------------------------------------------------- | :--------------- |
| `!contests`      | Display the next 5 upcoming scheduled contests on Codeforces.                 | `!contests`      |
| `!weeklyresults` | View live standings, problems, and solves for the active weekly mini-contest. | `!weeklyresults` |

### 🤝 Social Module

| Command                 | Description                                                              | Example                            |
| :---------------------- | :----------------------------------------------------------------------- | :--------------------------------- |
| `!findpartner <rating>` | Find practice partners on the server within 200 rating points of target. | `!findpartner 1500`                |
| `!creategroup <name>`   | Create a co-working study group of up to 5 members with a unique name.   | `!creategroup dynamic_programming` |
| `!joingroup <name>`     | Join an existing active study group on the server.                       | `!joingroup dynamic_programming`   |
| `!leavegroup`           | Leave your current study group.                                          | `!leavegroup`                      |
| `!groupstats`           | View aggregate consistency progress and combined solves of your group.   | `!groupstats`                      |
| `!createvc @user`       | Establish a temporary private voice channel for practicing with a user.  | `!createvc @tourist`               |

### ⚙️ Admin Module

| Command                | Description                                                               | Example                   |
| :--------------------- | :------------------------------------------------------------------------ | :------------------------ |
| `!setup`               | Admin command to initialize server category, channels, and hoisted roles. | `!setup`                  |
| `!resetprogress @user` | Admin override to wipe a member's consistency streak to Day 0.            | `!resetprogress @tourist` |

### 📈 Analytics Module

| Command               | Description                                                                   | Example                |
| :-------------------- | :---------------------------------------------------------------------------- | :--------------------- |
| `!predict <id>`       | Estimate your Codeforces rating change delta for a recently finished contest. | `!predict 1934`        |
| `!heatmap [@user]`    | Generate a beautiful contribution heatmap image of your Codeforces solves.    | `!heatmap @tourist`    |
| `!weakness`           | Analyze your last 200 submissions to find weakest and strongest tags.         | `!weakness`            |
| `!upsolve <id>`       | Scan a contest and add unsolved problems directly to your upsolving backlog.  | `!upsolve 1934`        |
| `!myupsolves`         | Display all pending upsolve problems in your database backlog.                | `!myupsolves`          |
| `!solvedupsolve <id>` | Mark a pending upsolve problem in your backlog list as resolved.              | `!solvedupsolve 1934A` |

### 🪙 Economy Module

| Command             | Description                                                                     | Example                          |
| :------------------ | :------------------------------------------------------------------------------ | :------------------------------- |
| `!xp [@user]`       | Show your current XP level, total XP, and a custom progress bar to next level.  | `!xp @tourist`                   |
| `!balance [@user]`  | Show your coin balance.                                                         | `!balance`                       |
| `!xpleaderboard`    | Display top 10 users ranked by overall economy level and XP.                    | `!xpleaderboard`                 |
| `!shop`             | Browse available boosters, skips, custom color tags, and upgrades.              | `!shop`                          |
| `!buy <item_name>`  | Purchase an upgrade item from the shop (Streak Freeze, Custom Color, XP Boost). | `!buy custom_role_color #FF5733` |
| `!give @user <amt>` | Gift coins from your balance to another user.                                   | `!give @tourist 100`             |

### 🎯 Achievements Module

| Command         | Description                                                                 | Example         |
| :-------------- | :-------------------------------------------------------------------------- | :-------------- |
| `!achievements` | Show all 12 automatic achievement badges with unlocked and locked statuses. | `!achievements` |

### 🎯 Roadmaps & Seasons Module

| Command              | Description                                                                 | Example               |
| :------------------- | :-------------------------------------------------------------------------- | :-------------------- |
| `!roadmap`           | Show full roadmap checklist embed with completed and pending topics.        | `!roadmap`            |
| `!done <topic>`      | Mark a roadmap topic completed, awarding +50 XP and +10 coins.              | `!done binary search` |
| `!mytopics`          | Show completions percentage and progress bar for completed topics.          | `!mytopics`           |
| `!tplearnors`        | Leaderboard showcasing the top 5 users on the server by topic count.        | `!tplearnors`         |
| `!season`            | Show details for the active season, days remaining, and your rank.          | `!season`             |
| `!seasonleaderboard` | Show the top 10 players for the active month's season.                      | `!seasonleaderboard`  |
| `!halloffame`        | Display all past season champions archived permanently in the Hall of Fame. | `!halloffame`         |

### 💬 Doubts & Community Module

| Command             | Description                                                               | Example                            |
| :------------------ | :------------------------------------------------------------------------ | :--------------------------------- |
| `!doubt <topic>`    | Raise a doubt and start a custom forum thread.                            | `!doubt dynamic programming`       |
| `!solved [@helper]` | Mark doubt solved inside an active thread and reward the helper.          | `!solved @tourist`                 |
| `!opendoubts`       | Show active unresolved doubts list.                                       | `!opendoubts`                      |
| `!mydoubts`         | Check your personal doubts raised history.                                | `!mydoubts`                        |
| `!tip <content>`    | Submit a CP tip to the tips channel anonymously.                          | `!tip Read the constraints first!` |
| `!lookingforteam`   | Register yourself in the ICPC team formation partner search pool.         | `!lookingforteam`                  |
| `!formteam @u1 @u2` | Form an ICPC team with 2 partners, auto-generating private VC/Text rooms. | `!formteam @tourist @Benq`         |

### ❓ Help Module

| Command              | Description                                                                          | Example              |
| :------------------- | :----------------------------------------------------------------------------------- | :------------------- |
| `!help [command]`    | Display the interactive paginated help menu or view details for a specific command.   | `!help virtualduel`  |

---

## 🏆 Rank System

As you check in and grind consistency, you will climb the server ranks. Hoisted Discord roles are distributed automatically based on day milestones:

| Rank Tier         | Day Range    | Color Hex | Key Permissions Unlocked           |
| :---------------- | :----------- | :-------- | :--------------------------------- |
| **🔘 Beginner**   | Days 1 - 9   | `#95A5A6` | Basic messaging and channel access |
| **🟢 Consistent** | Days 10 - 14 | `#2ECC71` | Custom nickname self-management    |
| **🔵 Dedicated**  | Days 15 - 19 | `#3498DB` | Attachment of practice screenshots |
| **🟣 Grinder**    | Days 20 - 24 | `#9B59B6` | Add reactions and external emojis  |
| **🟠 Elite**      | Days 25 - 29 | `#E67E22` | Link embeds and rich media uploads |
| **🌟 Legend**     | Day 30+      | `#F1C40F` | Ultimate veteran status            |

---

## 🎯 Achievement Badges

Earn milestones to unlock premium badges. Unlocks grant **+200 XP**, **+100 coins**, and post updates in `#progress-updates`:

- **🔥 On Fire:** Maintain a 7-day consistency streak.
- **🌟 Legendary:** Reach the prestigious Legend tier (Day 30).
- **⚡ Speedrunner:** Solve a virtual duel problem within 10 minutes.
- **💎 Diamond Hands:** Grind 30 days straight without breaking your streak.
- **🧠 Big Brain:** Solve a CF problem rated 400+ points above your CF rating.
- **🏆 Champion:** Win a weekly server mini-contest at Sunday 9 PM.
- **📚 Scholar:** Complete all roadmap topics in any phase.
- **🤝 Helper:** Get mentioned as the helper in 10 solved doubts.
- **🎯 Sharpshooter:** Reach a 10-day consistency streak.
- **👑 Season King:** Rank 1st in the Season Leaderboard when it ends.
- **🚀 Rockstar:** Reach 1900+ CF rating (Expert+).
- **💡 Guru:** Share 20 educational resources.

---

## 🤝 Contributing

Contributions make the open-source community an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.

---

```text
                                $$\       $$\                      $$$$$$\   $$$$$$\  
                              $$ |      \__|                    $$  __$$\ $$  __$$\ 
$$$$$$$\   $$$$$$\   $$$$$$\  $$$$$$$\  $$\  $$$$$$\   $$$$$$$\ $$ /  $$ |$$ /  \__|
$$  __$$\ $$  __$$\ $$  __$$\ $$  __$$\ $$ |$$  __$$\ $$  _____|$$$$$$$$ |$$ |$$$$\ 
$$ |  $$ |$$ /  $$ |$$ /  $$ |$$ |  $$ |$$ |$$$$$$$$ |\$$$$$$\  $$  __$$ |$$ |\_$$ |
$$ |  $$ |$$ |  $$ |$$ |  $$ |$$ |  $$ |$$ |$$   ____| \____$$\ $$ |  $$ |$$ |  $$ |
$$ |  $$ |\$$$$$$  |\$$$$$$  |$$$$$$$  |$$ |\$$$$$$$\ $$$$$$$  |$$ |  $$ |\$$$$$$  |
\__|  \__| \______/  \______/ \_______/ \__| \_______|\_______/ \__|  \__| \______/ 
                                                                                    
                                                                                    
                                                                                    
```

<p align="center">
  <a href="https://github.com/saurabhkun/NoobiesAG_Discord_Bot">
    <img src="https://img.shields.io/github/stars/saurabhkun/NoobiesAG_Discord_Bot?style=social" alt="Star the Repo">
  </a>
</p>

<p align="center">
  💬 <a href="https://discord.gg/SuzXH6QqE7">Join our Support Server</a> | Made with motivation for the CP community
</p>
