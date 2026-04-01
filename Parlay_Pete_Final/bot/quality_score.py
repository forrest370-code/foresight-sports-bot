"""
Quality Score Engine for ParlayPete.
Calculates reputation scores based on Accuracy, Timing, Conviction, Volume, and Consistency.
Assigns tiers: Ghost, Strategist, Analyst, Participant, Observer.
"""
import math
from datetime import datetime, timezone, timedelta


# Tier definitions
TIERS = [
    {"name": "Ghost", "emoji": "👻", "min_score": 0.95, "tag": "GHOST"},
    {"name": "Strategist", "emoji": "🎯", "min_score": 0.80, "tag": "STRATEGIST"},
    {"name": "Analyst", "emoji": "📊", "min_score": 0.60, "tag": "ANALYST"},
    {"name": "Participant", "emoji": "🟢", "min_score": 0.40, "tag": "PARTICIPANT"},
    {"name": "Observer", "emoji": "🧊", "min_score": 0.0, "tag": "OBSERVER"},
]

# Pick type multipliers
PICK_TYPE_MULTIPLIERS = {
    "potd": 1.5,    # POTD = higher conviction, 1 per day, reasoning required
    "spread": 1.0,
    "ml": 1.0,
    "over": 1.0,
    "under": 1.0,
    "parlay": 1.25,  # Parlays = higher risk/reward
}


def get_tier(quality_score: float) -> dict:
    """Get tier info for a quality score."""
    for tier in TIERS:
        if quality_score >= tier["min_score"]:
            return tier
    return TIERS[-1]


def get_tier_display(quality_score: float) -> str:
    """Get formatted tier badge string."""
    tier = get_tier(quality_score)
    return f"{tier['emoji']} {tier['name']}"


def calculate_accuracy(picks: list) -> float:
    """
    Accuracy component (50% weight).
    Simple win rate over resolved picks.
    """
    resolved = [p for p in picks if p["status"] in ("won", "lost")]
    if not resolved:
        return 0.5  # Neutral starting score

    wins = sum(1 for p in resolved if p["status"] == "won")
    return wins / len(resolved)


def calculate_timing(picks: list) -> float:
    """
    Timing component (30% weight).
    How early before game time was the pick locked?
    Earlier picks = higher score.
    Picks made 6+ hours before game = 1.0
    Picks made < 30 min before game = 0.2
    """
    scored_picks = []

    for pick in picks:
        if pick["status"] not in ("won", "lost"):
            continue

        created = pick.get("created_at", "")
        game_time = pick.get("commence_time")

        if not created or not game_time:
            scored_picks.append(0.5)  # Unknown timing = neutral
            continue

        try:
            if isinstance(created, str):
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            else:
                created_dt = created

            if isinstance(game_time, str):
                game_dt = datetime.fromisoformat(game_time.replace("Z", "+00:00"))
            else:
                game_dt = game_time

            hours_before = (game_dt - created_dt).total_seconds() / 3600

            if hours_before >= 6:
                scored_picks.append(1.0)
            elif hours_before >= 3:
                scored_picks.append(0.8)
            elif hours_before >= 1:
                scored_picks.append(0.6)
            elif hours_before >= 0.5:
                scored_picks.append(0.4)
            else:
                scored_picks.append(0.2)
        except (ValueError, TypeError):
            scored_picks.append(0.5)

    if not scored_picks:
        return 0.5

    return sum(scored_picks) / len(scored_picks)


def calculate_conviction(picks: list) -> float:
    """
    Conviction component (20% weight).
    Higher units = higher conviction.
    POTD picks get a multiplier.
    Correct high-unit picks score highest.
    """
    scored_picks = []

    for pick in picks:
        if pick["status"] not in ("won", "lost"):
            continue

        units = pick.get("units", 1.0)
        pick_type = pick.get("pick_type", "spread")
        won = pick["status"] == "won"

        # Base conviction from units (1u = 0.4, 2u = 0.6, 3u+ = 0.8)
        if units >= 3:
            base = 0.8
        elif units >= 2:
            base = 0.6
        else:
            base = 0.4

        # Apply pick type multiplier
        multiplier = PICK_TYPE_MULTIPLIERS.get(pick_type, 1.0)
        score = min(base * multiplier, 1.0)

        # Correct high-conviction picks are rewarded more
        if won:
            score = min(score * 1.2, 1.0)
        else:
            score = score * 0.7  # Wrong high-conviction picks hurt more

        scored_picks.append(score)

    if not scored_picks:
        return 0.5

    return sum(scored_picks) / len(scored_picks)


def calculate_volume_adjustment(total_resolved: int) -> float:
    """
    Volume adjustment (15% weight).
    Penalizes users with too few picks.
    5 picks = 0.25, 10 = 0.5, 20 = 0.75, 50+ = 1.0
    """
    if total_resolved >= 50:
        return 1.0
    elif total_resolved >= 20:
        return 0.75
    elif total_resolved >= 10:
        return 0.5
    elif total_resolved >= 5:
        return 0.25
    else:
        return 0.1


def calculate_consistency(weekly_results: list[float]) -> float:
    """
    Consistency adjustment (10% weight).
    Measures standard deviation of weekly win rates.
    Lower variance = higher consistency score.
    """
    if len(weekly_results) < 2:
        return 0.5  # Not enough data

    mean = sum(weekly_results) / len(weekly_results)
    variance = sum((x - mean) ** 2 for x in weekly_results) / len(weekly_results)
    std_dev = math.sqrt(variance)

    # Lower std_dev = higher score. 0 std = 1.0, 0.5 std = 0.0
    score = max(0.0, 1.0 - (std_dev * 2))
    return score


async def calculate_quality_score(db, user_id: int) -> dict:
    """
    Calculate the full Quality Score for a user.

    Returns:
        {
            "score": float (0.0 - 1.0),
            "tier": dict,
            "components": {
                "accuracy": float,
                "timing": float,
                "conviction": float,
                "volume": float,
                "consistency": float,
            },
            "total_resolved": int,
        }
    """
    # Get last 50 resolved picks (rolling window)
    cursor = await db.db.execute(
        """SELECT p.*, 
           (SELECT commence_time FROM picks WHERE id = p.id) as commence_time
           FROM picks p
           WHERE p.user_id = ? AND p.status IN ('won', 'lost')
           ORDER BY p.resolved_at DESC
           LIMIT 50""",
        (user_id,),
    )
    picks_raw = await cursor.fetchall()
    picks = [dict(row) for row in picks_raw]

    total_resolved = len(picks)

    if total_resolved == 0:
        return {
            "score": 0.5,
            "tier": get_tier(0.5),
            "components": {
                "accuracy": 0.5,
                "timing": 0.5,
                "conviction": 0.5,
                "volume": 0.1,
                "consistency": 0.5,
            },
            "total_resolved": 0,
        }

    # Calculate each component
    accuracy = calculate_accuracy(picks)
    timing = calculate_timing(picks)
    conviction = calculate_conviction(picks)
    volume = calculate_volume_adjustment(total_resolved)

    # Weekly consistency — get win rates per week
    weekly_results = []
    cursor = await db.db.execute(
        """SELECT 
            strftime('%Y-%W', resolved_at) as week,
            COUNT(CASE WHEN status = 'won' THEN 1 END) * 1.0 / COUNT(*) as win_rate
           FROM picks
           WHERE user_id = ? AND status IN ('won', 'lost')
           GROUP BY week
           ORDER BY week DESC
           LIMIT 8""",
        (user_id,),
    )
    weekly_rows = await cursor.fetchall()
    weekly_results = [row["win_rate"] for row in weekly_rows]
    consistency = calculate_consistency(weekly_results)

    # Weighted composite score
    # Core: Accuracy 50% + Timing 30% + Conviction 20% = base score
    base_score = (accuracy * 0.50) + (timing * 0.30) + (conviction * 0.20)

    # Adjustments: Volume and Consistency modify the base
    # Volume scales the score down if not enough picks
    # Consistency gives a small bonus/penalty
    adjusted_score = base_score * (0.75 + (volume * 0.15) + (consistency * 0.10))

    # Clamp to 0.0 - 1.0
    final_score = max(0.0, min(1.0, adjusted_score))

    return {
        "score": round(final_score, 3),
        "tier": get_tier(final_score),
        "components": {
            "accuracy": round(accuracy, 3),
            "timing": round(timing, 3),
            "conviction": round(conviction, 3),
            "volume": round(volume, 3),
            "consistency": round(consistency, 3),
        },
        "total_resolved": total_resolved,
    }


def format_quality_score(qs: dict, username: str) -> str:
    """Format Quality Score for display in /record."""
    tier = qs["tier"]
    c = qs["components"]

    score_bar = _score_bar(qs["score"])

    lines = [
        f"{tier['emoji']} <b>{tier['name']}</b> — Quality Score: {qs['score']:.2f}",
        f"{score_bar}",
        f"",
        f"Accuracy: {c['accuracy']:.0%} (50% weight)",
        f"Timing: {c['timing']:.0%} (30% weight)",
        f"Conviction: {c['conviction']:.0%} (20% weight)",
        f"Volume: {c['volume']:.0%} adj | Consistency: {c['consistency']:.0%} adj",
        f"Resolved picks: {qs['total_resolved']}",
    ]
    return "\n".join(lines)


def _score_bar(score: float, width: int = 20) -> str:
    """Generate a text-based score bar."""
    filled = int(score * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}] {score:.2f}"
