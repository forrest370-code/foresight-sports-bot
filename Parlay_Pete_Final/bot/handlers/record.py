from aiogram import Router, types
from aiogram.filters import Command

from bot.database import Database
from bot.utils import VALID_SPORTS
from bot.quality_score import calculate_quality_score, format_quality_score

router = Router()


@router.message(Command("record"))
async def cmd_record(message: types.Message, db: Database):
    if not message.from_user:
        return

    parts = (message.text or "").split()
    target_user_id = message.from_user.id
    target_username = message.from_user.username or message.from_user.full_name
    sport = None

    for part in parts[1:]:
        if part.startswith("@"):
            # Look up user by username
            lookup_name = part.lstrip("@")
            cursor = await db.db.execute(
                "SELECT telegram_id, username, display_name FROM users WHERE username = ?",
                (lookup_name,),
            )
            user_row = await cursor.fetchone()
            if not user_row:
                await message.reply(f"❌ Pete doesn't know @{lookup_name}. They need to make a pick first.")
                return
            target_user_id = user_row["telegram_id"]
            target_username = user_row["username"] or user_row["display_name"]
        elif part.upper() in VALID_SPORTS:
            sport = part.upper()

    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )

    # Get basic record
    record = await db.get_user_record(target_user_id, sport)
    streak = await db.get_user_streak(target_user_id)

    # Calculate Quality Score
    qs = await calculate_quality_score(db, target_user_id)
    tier = qs["tier"]

    wins = record["wins"]
    losses = record["losses"]
    pushes = record["pushes"]
    pending = record["pending"]
    net = round(record["units_won"] - record["units_lost"], 1)
    wagered = record["units_wagered"]
    roi = round((net / wagered * 100), 1) if wagered > 0 else 0.0

    net_display = f"+{net}" if net >= 0 else str(net)
    sport_label = f" ({sport})" if sport else ""

    # Pete's commentary based on tier
    comments = {
        "GHOST": "Pete's never seen anyone this sharp. Respect.",
        "STRATEGIST": "Top tier. Pete tips his hat.",
        "ANALYST": "Solid track record. Keep climbing.",
        "PARTICIPANT": "In the mix. Room to grow.",
        "OBSERVER": "Rough stretch. The board doesn't lie.",
    }
    comment = comments.get(tier["tag"], "")

    text = (
        f"{tier['emoji']} <b>@{target_username}</b> — {tier['name']}{sport_label}\n"
        f"\n"
        f"<b>Record:</b> {wins}-{losses}" + (f"-{pushes}P" if pushes else "") + "\n"
        f"<b>Units:</b> {net_display}u | <b>ROI:</b> {roi}%\n"
        f"{streak}\n"
        f"Pending: {pending} picks\n"
        f"\n"
    )

    # Add Quality Score breakdown
    text += format_quality_score(qs, target_username)
    text += f"\n\n<i>{comment}</i>"

    await message.reply(text, parse_mode="HTML")
