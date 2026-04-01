# FORESIGHT — ParlayPete Sports Bot

## Project Overview
Telegram sports pick-tracking bot for the Foresight ecosystem. Lives in @ForesightSports group. Bot display name: "Parlay Pete". Username: @ParlayPete_bot.

## What This Bot Does
Tracks sports picks (spreads, moneylines, over/unders, parlays) for users in a Telegram group. Every pick is timestamped, locked, and public. Records are permanent — no deletions. Leaderboard ranks by ROI and units profit.

## Tech Stack
- Python 3.11+
- aiogram 3.x (Telegram bot framework)
- SQLite (database — single file, no server needed)
- The Odds API (sports lines and scores)

## Architecture
```
foresight-sports-bot/
├── CLAUDE.md              # This file
├── .env                   # API keys (never commit)
├── requirements.txt       # Python dependencies
├── bot/
│   ├── __init__.py
│   ├── main.py            # Bot entry point
│   ├── config.py          # Load env vars
│   ├── database.py        # SQLite setup + queries
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── pick.py        # /pick command
│   │   ├── parlay.py      # /parlay command
│   │   ├── record.py      # /record command
│   │   ├── leaderboard.py # /leaderboard command
│   │   ├── resolve.py     # /resolve command (admin only)
│   │   ├── potd.py        # /potd command (Phase 2)
│   │   ├── slate.py       # /slate command (Phase 2)
│   │   ├── tail.py        # /tail command (Phase 2)
│   │   ├── fade.py        # /fade command (Phase 2)
│   │   └── hot.py         # /hot command (Phase 2)
│   ├── models.py          # Data models
│   ├── odds_api.py        # The Odds API integration
│   └── utils.py           # Formatting, parsing helpers
└── tests/
    └── test_pick_parser.py
```

## Core Commands (Phase 1 — Launch)
| Command | Example | What It Does |
|---------|---------|-------------|
| /pick | /pick NFL Chiefs -3.5 2u | Lock a straight bet. Timestamped, public. |
| /parlay | /parlay NBA Celtics -4 + Lakers ML | Multi-leg parlay. Combined odds auto-calculated. |
| /record | /record or /record @user | W-L, units P&L, ROI, streak. |
| /leaderboard | /leaderboard or /leaderboard NFL | Top 20 by units profit. |
| /resolve | /resolve [game_id] [result] | Admin only. Settles a game. |

## Phase 2 Commands (Week 2-3)
/potd, /tail, /fade, /hot, /slate

## Bot Personality
Name: Parlay Pete. Tone: Your degenerate best friend who has a perfect memory and zero chill. Funny, sports-native, slightly unhinged.
- Lock message: "🔒 Pete's got it. Locked and loaded."
- Win: "✅ @user CASHES: [pick details] | +X units 💰"
- Loss: "❌ @user DOWN: [pick details] | -X units. Pete remembers."
- Record: Pete talks in third person. "Pete's records show: 47-38, +12.4u. Not bad, kid."

## Channel Routing (Separation of Concerns)
- This bot operates ONLY in @ForesightSports (interactive group)
- The Radar bot is SEPARATE — posts to @ForesightRadar (read-only channel)
- Results cross-posted to @ForesightVault after resolution
- Weekly leaderboard posted to @ForesightHQ

## Database Schema
- users: telegram_id, username, display_name, created_at
- picks: id, user_id, sport, team, line, units, odds, pick_type (spread/ml/ou), status (pending/won/lost/push), created_at, resolved_at, game_id
- parlays: id, user_id, created_at, status, total_odds
- parlay_legs: id, parlay_id, sport, team, line, pick_type, status
- follows: follower_id, target_id (for /tail)
- fades: fader_id, target_id (for /fade)

## Environment Variables (.env)
```
TELEGRAM_BOT_TOKEN=your_token_here
ODDS_API_KEY=your_key_here
ADMIN_USER_IDS=comma_separated_telegram_ids
DATABASE_PATH=./data/chalkboard.db
```

## Key Rules
1. Every pick is immutable after submission. No edits, no deletes.
2. All picks are posted publicly in the group — no private picks.
3. ROI = (total units won - total units lost) / total units wagered * 100
4. Default unit size is 1u if not specified.
5. Picks cannot be placed after game start time (when odds API data is available).
6. Admin-only commands check ADMIN_USER_IDS before executing.
