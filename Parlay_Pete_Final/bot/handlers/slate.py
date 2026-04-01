from aiogram import Router, types
from aiogram.filters import Command
import aiohttp
from datetime import datetime, timezone

from bot.config import ODDS_API_KEY
from bot.utils import VALID_SPORTS

router = Router()

# Map our sport codes to Odds API sport keys
SPORT_MAP = {
    "NFL": "americanfootball_nfl",
    "NBA": "basketball_nba",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
    "NCAAF": "americanfootball_ncaaf",
    "NCAAB": "basketball_ncaab",
    "MMA": "mma_mixed_martial_arts",
    "UFC": "mma_mixed_martial_arts",
    "SOCCER": "soccer_epl",
    "EPL": "soccer_epl",
    "MLS": "soccer_usa_mls",
    "TENNIS": "tennis_atp_french_open",
}


async def fetch_odds(sport_key: str) -> list | None:
    if not ODDS_API_KEY or ODDS_API_KEY == "your_odds_api_key_here":
        return None

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "spreads,totals",
        "oddsFormat": "american",
        "dateFormat": "iso",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except Exception:
        return None


def format_game(game: dict) -> str:
    """Format a single game with spread and total."""
    home = game.get("home_team", "?")
    away = game.get("away_team", "?")
    start = game.get("commence_time", "")

    # Parse start time
    try:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        time_str = dt.strftime("%I:%M %p ET")
    except (ValueError, AttributeError):
        time_str = "TBD"

    # Extract spread and total from first bookmaker
    spread_str = ""
    total_str = ""

    for bookmaker in game.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market["key"] == "spreads" and not spread_str:
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == home:
                        point = outcome.get("point", 0)
                        spread_str = f"{home} {'+' if point > 0 else ''}{point}"
                        break
            elif market["key"] == "totals" and not total_str:
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == "Over":
                        total_str = f"O/U {outcome.get('point', '?')}"
                        break
        if spread_str and total_str:
            break

    return f"  {away} @ {home} | {spread_str} | {total_str} | {time_str}"


@router.message(Command("slate"))
async def cmd_slate(message: types.Message, db: Database = None):
    parts = (message.text or "").split()

    if len(parts) < 2:
        await message.reply(
            "📝 <b>Today's slate:</b>\n"
            "<code>/slate NBA</code>\n"
            "<code>/slate MLB</code>\n"
            "<code>/slate NHL</code>\n\n"
            f"All sports: {', '.join(sorted(SPORT_MAP.keys()))}",
            parse_mode="HTML",
        )
        return

    sport = parts[1].upper()
    if sport not in SPORT_MAP:
        await message.reply(
            f"❌ Pete doesn't cover that sport.\n"
            f"Try: {', '.join(sorted(SPORT_MAP.keys()))}",
            parse_mode="HTML",
        )
        return

    if not ODDS_API_KEY or ODDS_API_KEY == "your_odds_api_key_here":
        await message.reply(
            "⚠️ Odds API not configured yet. Pete needs an API key.\n"
            "Get one free at the-odds-api.com and add it to .env",
            parse_mode="HTML",
        )
        return

    await message.reply("🔍 Pete's checking the board...", parse_mode="HTML")

    games = await fetch_odds(SPORT_MAP[sport])

    if games is None:
        await message.reply("❌ Couldn't reach the odds API. Try again in a minute.")
        return

    if not games:
        await message.reply(f"📭 No {sport} games on the board today.")
        return

    # Limit to first 15 games
    games = games[:15]
    today = datetime.now(timezone.utc).strftime("%b %d")

    lines = [f"📋 <b>Today's {sport} Slate — {today}</b>", ""]
    for game in games:
        lines.append(format_game(game))

    lines.append("")
    lines.append(f"<i>{len(games)} games on the board. Lock it in → /pick</i>")

    await message.reply("\n".join(lines), parse_mode="HTML")
