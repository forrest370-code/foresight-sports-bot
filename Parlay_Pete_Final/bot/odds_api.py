"""
Odds API integration for ParlayPete.
Validates picks against real scheduled games and fetches live lines.
"""
import aiohttp
from datetime import datetime, timezone, timedelta
from bot.config import ODDS_API_KEY

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

# Common team name aliases — maps what users might type to what the API returns
TEAM_ALIASES = {
    # NBA
    "CELTICS": "Boston Celtics", "BOS": "Boston Celtics", "BOSTON": "Boston Celtics",
    "NETS": "Brooklyn Nets", "BKN": "Brooklyn Nets", "BROOKLYN": "Brooklyn Nets",
    "KNICKS": "New York Knicks", "NYK": "New York Knicks",
    "76ERS": "Philadelphia 76ers", "SIXERS": "Philadelphia 76ers", "PHI": "Philadelphia 76ers", "PHILLY": "Philadelphia 76ers",
    "RAPTORS": "Toronto Raptors", "TOR": "Toronto Raptors", "TORONTO": "Toronto Raptors",
    "BULLS": "Chicago Bulls", "CHI": "Chicago Bulls", "CHICAGO": "Chicago Bulls",
    "CAVS": "Cleveland Cavaliers", "CAVALIERS": "Cleveland Cavaliers", "CLE": "Cleveland Cavaliers",
    "PISTONS": "Detroit Pistons", "DET": "Detroit Pistons", "DETROIT": "Detroit Pistons",
    "PACERS": "Indiana Pacers", "IND": "Indiana Pacers", "INDIANA": "Indiana Pacers",
    "BUCKS": "Milwaukee Bucks", "MIL": "Milwaukee Bucks", "MILWAUKEE": "Milwaukee Bucks",
    "HAWKS": "Atlanta Hawks", "ATL": "Atlanta Hawks", "ATLANTA": "Atlanta Hawks",
    "HORNETS": "Charlotte Hornets", "CHA": "Charlotte Hornets", "CHARLOTTE": "Charlotte Hornets",
    "HEAT": "Miami Heat", "MIA": "Miami Heat", "MIAMI": "Miami Heat",
    "MAGIC": "Orlando Magic", "ORL": "Orlando Magic", "ORLANDO": "Orlando Magic",
    "WIZARDS": "Washington Wizards", "WAS": "Washington Wizards", "WASHINGTON": "Washington Wizards",
    "NUGGETS": "Denver Nuggets", "DEN": "Denver Nuggets", "DENVER": "Denver Nuggets",
    "TIMBERWOLVES": "Minnesota Timberwolves", "WOLVES": "Minnesota Timberwolves", "MIN": "Minnesota Timberwolves",
    "THUNDER": "Oklahoma City Thunder", "OKC": "Oklahoma City Thunder",
    "BLAZERS": "Portland Trail Blazers", "POR": "Portland Trail Blazers", "PORTLAND": "Portland Trail Blazers",
    "JAZZ": "Utah Jazz", "UTA": "Utah Jazz", "UTAH": "Utah Jazz",
    "WARRIORS": "Golden State Warriors", "GSW": "Golden State Warriors",
    "CLIPPERS": "LA Clippers", "LAC": "LA Clippers",
    "LAKERS": "Los Angeles Lakers", "LAL": "Los Angeles Lakers",
    "SUNS": "Phoenix Suns", "PHX": "Phoenix Suns", "PHOENIX": "Phoenix Suns",
    "KINGS": "Sacramento Kings", "SAC": "Sacramento Kings", "SACRAMENTO": "Sacramento Kings",
    "SPURS": "San Antonio Spurs", "SAS": "San Antonio Spurs",
    "MAVS": "Dallas Mavericks", "MAVERICKS": "Dallas Mavericks", "DAL": "Dallas Mavericks", "DALLAS": "Dallas Mavericks",
    "ROCKETS": "Houston Rockets", "HOU": "Houston Rockets", "HOUSTON": "Houston Rockets",
    "GRIZZLIES": "Memphis Grizzlies", "MEM": "Memphis Grizzlies", "MEMPHIS": "Memphis Grizzlies",
    "PELICANS": "New Orleans Pelicans", "NOP": "New Orleans Pelicans",
    # NFL
    "CHIEFS": "Kansas City Chiefs", "KC": "Kansas City Chiefs",
    "BILLS": "Buffalo Bills", "BUF": "Buffalo Bills", "BUFFALO": "Buffalo Bills",
    "DOLPHINS": "Miami Dolphins",
    "PATRIOTS": "New England Patriots", "PATS": "New England Patriots", "NE": "New England Patriots",
    "JETS": "New York Jets", "NYJ": "New York Jets",
    "RAVENS": "Baltimore Ravens", "BAL": "Baltimore Ravens", "BALTIMORE": "Baltimore Ravens",
    "BENGALS": "Cincinnati Bengals", "CIN": "Cincinnati Bengals", "CINCINNATI": "Cincinnati Bengals",
    "BROWNS": "Cleveland Browns",
    "STEELERS": "Pittsburgh Steelers", "PIT": "Pittsburgh Steelers", "PITTSBURGH": "Pittsburgh Steelers",
    "TEXANS": "Houston Texans",
    "COLTS": "Indianapolis Colts",
    "JAGUARS": "Jacksonville Jaguars", "JAGS": "Jacksonville Jaguars", "JAX": "Jacksonville Jaguars",
    "TITANS": "Tennessee Titans", "TEN": "Tennessee Titans",
    "BRONCOS": "Denver Broncos",
    "CHARGERS": "Los Angeles Chargers", "LAC_NFL": "Los Angeles Chargers",
    "RAIDERS": "Las Vegas Raiders", "LV": "Las Vegas Raiders",
    "COMMANDERS": "Washington Commanders",
    "COWBOYS": "Dallas Cowboys",
    "GIANTS": "New York Giants", "NYG": "New York Giants",
    "EAGLES": "Philadelphia Eagles",
    "BEARS": "Chicago Bears",
    "LIONS": "Detroit Lions",
    "PACKERS": "Green Bay Packers", "GB": "Green Bay Packers",
    "VIKINGS": "Minnesota Vikings",
    "FALCONS": "Atlanta Falcons",
    "PANTHERS": "Carolina Panthers", "CAR": "Carolina Panthers",
    "SAINTS": "New Orleans Saints", "NO": "New Orleans Saints",
    "BUCCANEERS": "Tampa Bay Buccaneers", "BUCS": "Tampa Bay Buccaneers", "TB": "Tampa Bay Buccaneers",
    "CARDINALS": "Arizona Cardinals", "ARI": "Arizona Cardinals",
    "RAMS": "Los Angeles Rams", "LAR": "Los Angeles Rams",
    "49ERS": "San Francisco 49ers", "NINERS": "San Francisco 49ers", "SF": "San Francisco 49ers",
    "SEAHAWKS": "Seattle Seahawks", "SEA": "Seattle Seahawks",
    # MLB
    "YANKEES": "New York Yankees", "NYY": "New York Yankees",
    "RED SOX": "Boston Red Sox", "REDSOX": "Boston Red Sox",
    "BLUE JAYS": "Toronto Blue Jays", "BLUEJAYS": "Toronto Blue Jays",
    "RAYS": "Tampa Bay Rays",
    "ORIOLES": "Baltimore Orioles",
    "WHITE SOX": "Chicago White Sox", "WHITESOX": "Chicago White Sox",
    "GUARDIANS": "Cleveland Guardians",
    "TIGERS": "Detroit Tigers",
    "ROYALS": "Kansas City Royals",
    "TWINS": "Minnesota Twins",
    "ASTROS": "Houston Astros",
    "ANGELS": "Los Angeles Angels",
    "ATHLETICS": "Oakland Athletics", "AS": "Oakland Athletics",
    "MARINERS": "Seattle Mariners",
    "RANGERS": "Texas Rangers", "TEX": "Texas Rangers",
    "BRAVES": "Atlanta Braves",
    "MARLINS": "Miami Marlins",
    "METS": "New York Mets", "NYM": "New York Mets",
    "PHILLIES": "Philadelphia Phillies",
    "NATIONALS": "Washington Nationals",
    "CUBS": "Chicago Cubs",
    "REDS": "Cincinnati Reds",
    "BREWERS": "Milwaukee Brewers",
    "PIRATES": "Pittsburgh Pirates",
    "CARDINALS_MLB": "St. Louis Cardinals",
    "DIAMONDBACKS": "Arizona Diamondbacks", "DBACKS": "Arizona Diamondbacks",
    "ROCKIES": "Colorado Rockies", "COL": "Colorado Rockies",
    "DODGERS": "Los Angeles Dodgers", "LAD": "Los Angeles Dodgers",
    "PADRES": "San Diego Padres", "SD": "San Diego Padres",
    # NHL
    "BRUINS": "Boston Bruins",
    "SABRES": "Buffalo Sabres",
    "RED WINGS": "Detroit Red Wings", "REDWINGS": "Detroit Red Wings",
    "PANTHERS_NHL": "Florida Panthers",
    "CANADIENS": "Montreal Canadiens", "HABS": "Montreal Canadiens",
    "SENATORS": "Ottawa Senators", "SENS": "Ottawa Senators",
    "LIGHTNING": "Tampa Bay Lightning", "BOLTS": "Tampa Bay Lightning",
    "MAPLE LEAFS": "Toronto Maple Leafs", "LEAFS": "Toronto Maple Leafs",
    "HURRICANES": "Carolina Hurricanes", "CANES": "Carolina Hurricanes",
    "BLUE JACKETS": "Columbus Blue Jackets",
    "DEVILS": "New Jersey Devils", "NJ": "New Jersey Devils",
    "ISLANDERS": "New York Islanders", "NYI": "New York Islanders",
    "FLYERS": "Philadelphia Flyers",
    "PENGUINS": "Pittsburgh Penguins", "PENS": "Pittsburgh Penguins",
    "CAPITALS": "Washington Capitals", "CAPS": "Washington Capitals",
    "BLACKHAWKS": "Chicago Blackhawks",
    "AVALANCHE": "Colorado Avalanche", "AVS": "Colorado Avalanche",
    "STARS": "Dallas Stars",
    "WILD": "Minnesota Wild",
    "PREDATORS": "Nashville Predators", "PREDS": "Nashville Predators",
    "BLUES": "St. Louis Blues", "STL": "St. Louis Blues",
    "JETS_NHL": "Winnipeg Jets",
    "FLAMES": "Calgary Flames", "CGY": "Calgary Flames",
    "OILERS": "Edmonton Oilers", "EDM": "Edmonton Oilers",
    "CANUCKS": "Vancouver Canucks", "VAN": "Vancouver Canucks",
    "DUCKS": "Anaheim Ducks", "ANA": "Anaheim Ducks",
    "COYOTES": "Utah Hockey Club",
    "GOLDEN KNIGHTS": "Vegas Golden Knights", "VGK": "Vegas Golden Knights", "KNIGHTS": "Vegas Golden Knights",
    "KRAKEN": "Seattle Kraken",
    "SHARKS": "San Jose Sharks", "SJ": "San Jose Sharks",
}


def resolve_team_name(user_input: str) -> str:
    """Try to match user input to a known team name."""
    upper = user_input.upper().strip()
    if upper in TEAM_ALIASES:
        return TEAM_ALIASES[upper]
    return user_input


async def fetch_upcoming_games(sport: str) -> list | None:
    """Fetch upcoming games with odds for a sport."""
    sport_key = SPORT_MAP.get(sport.upper())
    if not sport_key:
        return None

    if not ODDS_API_KEY or ODDS_API_KEY == "your_odds_api_key_here":
        return None

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "spreads,h2h,totals",
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


def find_game_for_team(games: list, team_name: str) -> dict | None:
    """Find a game where the given team is playing."""
    resolved = resolve_team_name(team_name)
    resolved_upper = resolved.upper()

    for game in games:
        home = game.get("home_team", "")
        away = game.get("away_team", "")

        # Check against full team names and also partial matches
        if (resolved_upper in home.upper() or
            resolved_upper in away.upper() or
            home.upper() in resolved_upper or
            away.upper() in resolved_upper or
            resolved == home or
            resolved == away):

            # Check game hasn't already started
            start_str = game.get("commence_time", "")
            try:
                start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if start_time <= datetime.now(timezone.utc):
                    continue  # Game already started, skip
            except (ValueError, AttributeError):
                pass

            return game

    return None


def get_line_from_game(game: dict, team_name: str) -> dict:
    """Extract the spread, moneyline, and total for a team from a game."""
    resolved = resolve_team_name(team_name)
    result = {
        "home_team": game.get("home_team", ""),
        "away_team": game.get("away_team", ""),
        "commence_time": game.get("commence_time", ""),
        "spread": None,
        "moneyline": None,
        "total": None,
        "game_id": game.get("id", ""),
    }

    for bookmaker in game.get("bookmakers", [])[:1]:  # Use first bookmaker
        for market in bookmaker.get("markets", []):
            if market["key"] == "spreads":
                for outcome in market.get("outcomes", []):
                    if resolved.upper() in outcome["name"].upper() or outcome["name"].upper() in resolved.upper():
                        result["spread"] = outcome.get("point")
                        break
            elif market["key"] == "h2h":
                for outcome in market.get("outcomes", []):
                    if resolved.upper() in outcome["name"].upper() or outcome["name"].upper() in resolved.upper():
                        result["moneyline"] = outcome.get("price")
                        break
            elif market["key"] == "totals":
                for outcome in market.get("outcomes", []):
                    if outcome["name"] == "Over":
                        result["total"] = outcome.get("point")
                        break

    return result


async def validate_pick(sport: str, team: str) -> dict:
    """
    Validate a pick against real scheduled games.

    Returns:
        {
            "valid": True/False,
            "error": "error message if invalid",
            "game": game data if valid,
            "line_info": line details if valid,
            "matchup": "Team A vs Team B" if valid,
        }
    """
    if sport.upper() not in SPORT_MAP:
        return {"valid": False, "error": f"Pete doesn't cover that sport."}

    if not ODDS_API_KEY or ODDS_API_KEY == "your_odds_api_key_here":
        # If no API key, allow picks without validation (graceful degradation)
        return {"valid": True, "game": None, "line_info": None, "matchup": None}

    games = await fetch_upcoming_games(sport)

    if games is None:
        # API error — allow the pick but warn
        return {"valid": True, "game": None, "line_info": None, "matchup": None}

    if not games:
        return {"valid": False, "error": f"No {sport.upper()} games on the board right now. Is it even in season?"}

    game = find_game_for_team(games, team)

    if not game:
        # Build list of teams playing today for helpful error
        teams_today = set()
        for g in games:
            start_str = g.get("commence_time", "")
            try:
                start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                if start_time > datetime.now(timezone.utc):
                    home_short = g.get("home_team", "").split()[-1]
                    away_short = g.get("away_team", "").split()[-1]
                    teams_today.add(home_short)
                    teams_today.add(away_short)
            except (ValueError, AttributeError):
                pass

        if teams_today:
            team_list = ", ".join(sorted(teams_today)[:20])
            return {
                "valid": False,
                "error": f"Pete can't find a {sport.upper()} game for \"{team}\" today.\n\nTeams on the board: {team_list}",
            }
        else:
            return {"valid": False, "error": f"No upcoming {sport.upper()} games found for \"{team}\"."}

    line_info = get_line_from_game(game, team)
    matchup = f"{game.get('away_team', '?')} @ {game.get('home_team', '?')}"

    return {
        "valid": True,
        "game": game,
        "line_info": line_info,
        "matchup": matchup,
    }
