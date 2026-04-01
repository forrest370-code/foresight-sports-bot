import re
from datetime import datetime, timezone

VALID_SPORTS = {"NFL", "NBA", "MLB", "NHL", "NCAAF", "NCAAB", "UFC", "MMA", "TENNIS", "SOCCER", "EPL", "MLS"}


def parse_pick(text: str) -> dict | None:
    """
    Parse a /pick command into structured data.

    Formats accepted:
      /pick NFL Chiefs -3.5 2u
      /pick NBA Lakers ML 1u
      /pick NHL Oilers o5.5 3u
      /pick MLB Yankees +1.5
    """
    text = text.strip()
    if text.startswith("/pick"):
        text = text[5:].strip()

    parts = text.split()
    if len(parts) < 2:
        return None

    # Extract sport
    sport = parts[0].upper()
    if sport not in VALID_SPORTS:
        return None

    # Extract units (look for Xu or X.Xu pattern at end)
    units = 1.0
    remaining = parts[1:]
    if remaining and re.match(r"^\d+\.?\d*u$", remaining[-1], re.IGNORECASE):
        units = float(remaining[-1][:-1])
        remaining = remaining[:-1]

    if not remaining:
        return None

    # Extract line type and value
    team_parts = []
    line = None
    pick_type = "spread"

    for i, part in enumerate(remaining):
        upper = part.upper()

        # Moneyline
        if upper == "ML":
            pick_type = "ml"
            continue

        # Over/Under
        if upper.startswith("O") and re.match(r"^[oO]\d+\.?\d*$", part):
            line = part
            pick_type = "over"
            continue
        if upper.startswith("U") and re.match(r"^[uU]\d+\.?\d*$", part):
            line = part
            pick_type = "under"
            continue

        # Spread (negative or positive number)
        if re.match(r"^[+-]?\d+\.?\d*$", part):
            line = part
            pick_type = "spread"
            continue

        # Team name word
        team_parts.append(part)

    if not team_parts:
        return None

    team = " ".join(team_parts)

    return {
        "sport": sport,
        "team": team,
        "line": line,
        "units": units,
        "pick_type": pick_type,
    }


def parse_parlay(text: str) -> dict | None:
    """
    Parse a /parlay command.

    Format: /parlay NBA Celtics -4 + Lakers ML 2u
    Legs separated by '+'
    """
    text = text.strip()
    if text.startswith("/parlay"):
        text = text[7:].strip()

    # Extract units from end
    units = 1.0
    parts = text.split()
    if parts and re.match(r"^\d+\.?\d*u$", parts[-1], re.IGNORECASE):
        units = float(parts[-1][:-1])
        text = " ".join(parts[:-1])

    # Split by +
    leg_strings = [s.strip() for s in text.split("+")]
    if len(leg_strings) < 2:
        return None

    legs = []
    for leg_str in leg_strings:
        parsed = parse_pick(f"/pick {leg_str}")
        if not parsed:
            return None
        legs.append(parsed)

    return {"units": units, "legs": legs}


def format_pick_confirmation(username: str, pick: dict, pick_id: int) -> str:
    """Format Pete's lock-in message."""
    line_display = ""
    if pick["pick_type"] == "ml":
        line_display = "ML"
    elif pick["pick_type"] in ("over", "under"):
        line_display = pick["line"] if pick["line"] else pick["pick_type"].upper()
    elif pick["line"]:
        line_display = pick["line"]

    parts = [
        f"🔒 <b>Pete's got it.</b>",
        f"",
        f"@{username} — {pick['sport']} {pick['team']} {line_display} | {pick['units']}u",
        f"Pick #{pick_id} | {datetime.now(timezone.utc).strftime('%b %d, %I:%M %p UTC')}",
        f"",
        f"<i>Locked and loaded. No takebacks, pal.</i>",
    ]
    return "\n".join(parts)


def format_parlay_confirmation(username: str, legs: list[dict], parlay_id: int, units: float) -> str:
    """Format parlay lock-in message."""
    leg_lines = []
    for i, leg in enumerate(legs, 1):
        line_display = ""
        if leg["pick_type"] == "ml":
            line_display = "ML"
        elif leg["pick_type"] in ("over", "under"):
            line_display = leg["line"] if leg["line"] else leg["pick_type"].upper()
        elif leg.get("line"):
            line_display = leg["line"]
        leg_lines.append(f"  Leg {i}: {leg['sport']} {leg['team']} {line_display}")

    parts = [
        f"🔒 <b>PETE LOVES THIS PARLAY</b>",
        f"",
        f"@{username} — {len(legs)}-leg parlay | {units}u",
        *leg_lines,
        f"",
        f"Parlay #{parlay_id} | {datetime.now(timezone.utc).strftime('%b %d, %I:%M %p UTC')}",
        f"",
        f"<i>All legs locked. Pete's sweating with you.</i>",
    ]
    return "\n".join(parts)


def format_record(username: str, record: dict, streak: str, sport: str | None = None) -> str:
    """Format user record display."""
    wins = record["wins"]
    losses = record["losses"]
    pushes = record["pushes"]
    pending = record["pending"]
    net = round(record["units_won"] - record["units_lost"], 1)
    wagered = record["units_wagered"]
    roi = round((net / wagered * 100), 1) if wagered > 0 else 0.0

    net_display = f"+{net}" if net >= 0 else str(net)
    sport_label = f" ({sport.upper()})" if sport else ""

    # Pete's commentary based on performance
    if roi > 10:
        comment = "Pete's impressed. Don't let it go to your head."
    elif roi > 0:
        comment = "In the green. Pete's watching."
    elif roi == 0 and wins == 0:
        comment = "Fresh slate. Show Pete what you got."
    elif roi > -5:
        comment = "Barely underwater. Pete believes in you. Maybe."
    else:
        comment = "Rough patch. Pete's seen worse. Barely."

    parts = [
        f"📋 <b>Pete's records — @{username}</b>{sport_label}",
        f"",
        f"Record: {wins}-{losses}" + (f"-{pushes}P" if pushes else ""),
        f"Units: {net_display}u | ROI: {roi}%",
        f"{streak}",
        f"Pending: {pending} picks",
        f"",
        f"<i>{comment}</i>",
    ]
    return "\n".join(parts)


def format_leaderboard(rows: list, sport: str | None = None) -> str:
    """Format top-20 leaderboard."""
    sport_label = f" — {sport.upper()}" if sport else ""

    if not rows:
        return f"🏆 <b>Pete's Leaderboard{sport_label}</b>\n\nNobody qualified yet. Pete needs 5+ resolved picks to rank you."

    lines = [f"🏆 <b>Pete's Leaderboard{sport_label}</b>", ""]

    for i, row in enumerate(rows, 1):
        name = f"@{row['username']}" if row["username"] else row["display_name"] or "Unknown"
        net = round(row["net_units"], 1)
        net_display = f"+{net}" if net >= 0 else str(net)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")

        lines.append(
            f"{medal} {name} — {row['wins']}-{row['losses']} | {net_display}u | {row['roi']}% ROI"
        )

    return "\n".join(lines)


def format_win(username: str, pick_id: int, team: str, line: str | None, units: float,
               record_wins: int, record_losses: int, net_units: float, roi: float) -> str:
    """Format win notification."""
    net_display = f"+{round(net_units, 1)}" if net_units >= 0 else str(round(net_units, 1))
    line_str = f" {line}" if line else ""
    return (
        f"✅ @{username} CASHES: {team}{line_str} 💰\n"
        f"+{units}u | Record: {record_wins}-{record_losses} | {net_display}u | {round(roi, 1)}% ROI"
    )


def format_loss(username: str, pick_id: int, team: str, line: str | None, units: float,
                record_wins: int, record_losses: int, net_units: float, roi: float) -> str:
    """Format loss notification."""
    net_display = f"+{round(net_units, 1)}" if net_units >= 0 else str(round(net_units, 1))
    line_str = f" {line}" if line else ""
    return (
        f"❌ @{username} DOWN: {team}{line_str}\n"
        f"-{units}u | Record: {record_wins}-{record_losses} | {net_display}u | {round(roi, 1)}% ROI\n"
        f"<i>Pete remembers.</i>"
    )
