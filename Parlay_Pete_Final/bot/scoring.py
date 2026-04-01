"""
ParlayPete Quality Score Engine

The Quality Score is a rolling weighted average over the last 50 resolved picks.
It determines a user's tier, displayed rank, and eventually their influence in the DAO.

Components (from Foresight Strategic Plan):
  - Accuracy (50%): Win rate across resolved picks
  - Timing (30%): How early the pick was made before game time (earlier = higher)
  - Conviction (20%): Pick type multiplier + unit size relative to user's average

Pick Type Multipliers:
  - /pick (straight): 1.0x base
  - /parlay: 1.5x multiplier (higher risk = more reward for correct calls)
  - /potd: 1.3x multiplier (higher conviction signal — limited to 1/day)

Tier Structure:
  Observer    < 0.40   — Basic access
  Participant 0.40-0.59 — Standard
  Analyst     0.60-0.79 — Enhanced
  Strategist  0.80-0.94 — High influence
  Oracle      0.95-1.0  — Maximum influence

Score decays toward 0.5 (neutral) after 60 days of inactivity.
New users start at 0.5.
"""

import math
from datetime import datetime, timezone, timedelta


# Pick type multipliers
PICK_TYPE_MULTIPLIER = {
    "spread": 1.0,
    "ml": 1.0,
    "over": 1.0,
    "under": 1.0,
    "potd": 1.3,
    "parlay": 1.5,
}

# Tier definitions
TIERS = [
    {"name": "Observer", "emoji": "👁", "min": 0.0, "max": 0.399},
    {"name": "Participant", "emoji": "🎯", "min": 0.40, "max": 0.599},
    {"name": "Analyst", "emoji": "📊", "min": 0.60, "max": 0.799},
    {"name": "Strategist", "emoji": "🧠", "min": 0.80, "max": 0.949},
    {"name": "Oracle", "emoji": "👁‍🗨", "min": 0.95, "max": 1.0},
]


def get_tier(quality_score: float) -> dict:
    """Get the tier for a given quality score."""
    for tier in reversed(TIERS):
        if quality_score >= tier["min"]:
            return tier
    return TIERS[0]


def calculate_timing_score(pick_created_at: str, game_commence_time: str | None) -> float:
    """
    Score 0.0-1.0 based on how early the pick was placed before game time.

    - 24+ hours early = 1.0 (maximum timing score)
    - 12 hours early = 0.8
    - 6 hours early = 0.6
    - 2 hours early = 0.4
    - 30 min early = 0.2
    - After game start = 0.1 (minimum — shouldn't happen with validation)
    - No game time data = 0.5 (neutral)
    """
    if not game_commence_time:
        return 0.5  # No timing data, give neutral score

    try:
        pick_time = datetime.fromisoformat(pick_created_at.replace("Z", "+00:00"))
        game_time = datetime.fromisoformat(game_commence_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 0.5

    hours_before = (game_time - pick_time).total_seconds() / 3600

    if hours_before <= 0:
        return 0.1
    elif hours_before < 0.5:
        return 0.2
    elif hours_before < 2:
        return 0.3 + (hours_before - 0.5) / 1.5 * 0.1
    elif hours_before < 6:
        return 0.4 + (hours_before - 2) / 4 * 0.2
    elif hours_before < 12:
        return 0.6 + (hours_before - 6) / 6 * 0.2
    elif hours_before < 24:
        return 0.8 + (hours_before - 12) / 12 * 0.15
    else:
        return min(1.0, 0.95 + (hours_before - 24) / 48 * 0.05)


def calculate_conviction_score(units: float, avg_units: float, pick_type: str) -> float:
    """
    Score 0.0-1.0 based on conviction level.

    Factors:
    - Unit size relative to user's average (bigger = more conviction)
    - Pick type multiplier (POTD and parlay show higher conviction)
    """
    # Unit ratio: how much bigger is this pick vs their average?
    if avg_units <= 0:
        avg_units = 1.0
    unit_ratio = units / avg_units

    # Base conviction from unit size (capped at 1.0)
    # 1x average = 0.5, 2x = 0.75, 3x+ = approaching 1.0
    base = min(1.0, 0.3 + 0.2 * unit_ratio)

    # Apply pick type multiplier
    multiplier = PICK_TYPE_MULTIPLIER.get(pick_type, 1.0)

    # POTD gets a conviction boost because you only get one per day
    # Parlay gets a boost because it's inherently higher risk
    boosted = base * multiplier

    return min(1.0, boosted)


def calculate_pick_quality_score(
    won: bool,
    timing_score: float,
    conviction_score: float,
) -> float:
    """
    Calculate the quality score contribution of a single resolved pick.

    Accuracy (50%) + Timing (30%) + Conviction (20%) = single pick QS

    Returns 0.0-1.0
    """
    accuracy = 1.0 if won else 0.0
    return (accuracy * 0.50) + (timing_score * 0.30) + (conviction_score * 0.20)


async def calculate_user_quality_score(db, user_id: int) -> dict:
    """
    Calculate the full Quality Score for a user.

    Uses a rolling window of the last 50 resolved picks.
    Returns a dict with score, tier, and component breakdown.
    """
    # Get last 50 resolved picks with timing data
    cursor = await db.db.execute(
        """SELECT p.status, p.units, p.pick_type, p.created_at, p.game_id,
                  p.resolved_at
           FROM picks p
           WHERE p.user_id = ? AND p.status IN ('won', 'lost')
           ORDER BY p.resolved_at DESC
           LIMIT 50""",
        (user_id,),
    )
    picks = await cursor.fetchall()

    if not picks:
        return {
            "quality_score": 0.50,
            "tier": get_tier(0.50),
            "accuracy": 0.0,
            "timing_avg": 0.5,
            "conviction_avg": 0.5,
            "picks_scored": 0,
            "pick_scores": [],
        }

    # Get user's average unit size for conviction calculation
    cursor = await db.db.execute(
        "SELECT AVG(units) as avg_units FROM picks WHERE user_id = ? AND status IN ('won', 'lost')",
        (user_id,),
    )
    avg_row = await cursor.fetchone()
    avg_units = avg_row["avg_units"] if avg_row and avg_row["avg_units"] else 1.0

    pick_scores = []
    total_accuracy = 0
    total_timing = 0
    total_conviction = 0

    for pick in picks:
        won = pick["status"] == "won"
        if won:
            total_accuracy += 1

        # Get game commence time if we have a game_id
        game_time = None
        if pick["game_id"]:
            # We store commence time in the future — for now use created_at + estimated gap
            # In production this would query the stored game data
            pass

        timing = calculate_timing_score(pick["created_at"], game_time)
        conviction = calculate_conviction_score(pick["units"], avg_units, pick["pick_type"])
        pick_qs = calculate_pick_quality_score(won, timing, conviction)

        total_timing += timing
        total_conviction += conviction

        pick_scores.append({
            "won": won,
            "timing": timing,
            "conviction": conviction,
            "pick_qs": pick_qs,
            "pick_type": pick["pick_type"],
        })

    n = len(picks)
    accuracy_rate = total_accuracy / n
    timing_avg = total_timing / n
    conviction_avg = total_conviction / n

    # Weighted QS from components
    raw_qs = (accuracy_rate * 0.50) + (timing_avg * 0.30) + (conviction_avg * 0.20)

    # Volume adjustment: fewer picks = pulled toward 0.5
    # At 5 picks, 50% pull toward neutral. At 20+, minimal pull.
    volume_factor = min(1.0, n / 20)
    adjusted_qs = (raw_qs * volume_factor) + (0.5 * (1 - volume_factor))

    # Consistency adjustment: check standard deviation of recent pick scores
    if len(pick_scores) >= 5:
        scores = [p["pick_qs"] for p in pick_scores]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std_dev = math.sqrt(variance)

        # Lower std_dev = more consistent = small bonus (up to 0.05)
        # Higher std_dev = inconsistent = small penalty
        consistency_bonus = max(-0.05, min(0.05, (0.25 - std_dev) * 0.1))
        adjusted_qs += consistency_bonus

    # Clamp to 0.0-1.0
    final_qs = max(0.0, min(1.0, adjusted_qs))

    # Inactivity decay
    if picks:
        last_resolved = picks[0]["resolved_at"]
        if last_resolved:
            try:
                last_time = datetime.fromisoformat(last_resolved.replace("Z", "+00:00"))
                days_inactive = (datetime.now(timezone.utc) - last_time).days
                if days_inactive > 60:
                    # Decay toward 0.5 — lose 1% of distance per day after 60 days
                    decay_days = days_inactive - 60
                    decay_factor = 0.99 ** decay_days
                    final_qs = 0.5 + (final_qs - 0.5) * decay_factor
            except (ValueError, AttributeError):
                pass

    tier = get_tier(final_qs)

    return {
        "quality_score": round(final_qs, 3),
        "tier": tier,
        "accuracy": round(accuracy_rate, 3),
        "timing_avg": round(timing_avg, 3),
        "conviction_avg": round(conviction_avg, 3),
        "picks_scored": n,
        "pick_scores": pick_scores,
    }


def format_quality_score_display(qs_data: dict, username: str) -> str:
    """Format the full quality score breakdown for /record."""
    qs = qs_data["quality_score"]
    tier = qs_data["tier"]
    acc = qs_data["accuracy"]
    timing = qs_data["timing_avg"]
    conviction = qs_data["conviction_avg"]
    n = qs_data["picks_scored"]

    if n == 0:
        return (
            f"\n\n🏅 <b>Quality Score:</b> 0.500 (neutral)\n"
            f"{tier['emoji']} Tier: <b>{tier['name']}</b>\n"
            f"<i>Make picks to build your score.</i>"
        )

    # Build a visual bar for QS
    filled = round(qs * 10)
    bar = "█" * filled + "░" * (10 - filled)

    return (
        f"\n\n🏅 <b>Quality Score:</b> {qs:.3f}\n"
        f"[{bar}]\n"
        f"{tier['emoji']} Tier: <b>{tier['name']}</b>\n"
        f"\n"
        f"📈 Accuracy: {acc:.1%} (50% weight)\n"
        f"⏱ Timing: {timing:.3f} (30% weight)\n"
        f"💪 Conviction: {conviction:.3f} (20% weight)\n"
        f"📊 Based on last {n} resolved picks"
    )


def format_leaderboard_qs(row: dict, rank: int) -> str:
    """Format a single leaderboard entry with Quality Score."""
    name = f"@{row['username']}" if row.get("username") else row.get("display_name", "Unknown")
    net = round(row["net_units"], 1)
    net_display = f"+{net}" if net >= 0 else str(net)
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}.")

    qs = row.get("quality_score", 0.5)
    tier = get_tier(qs)

    return (
        f"{medal} {name} — {row['wins']}-{row['losses']} | "
        f"{net_display}u | {row['roi']}% ROI | "
        f"QS: {qs:.2f} {tier['emoji']}"
    )
