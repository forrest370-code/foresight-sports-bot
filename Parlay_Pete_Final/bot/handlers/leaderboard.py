from aiogram import Router, types
from aiogram.filters import Command

from bot.database import Database
from bot.utils import VALID_SPORTS
from bot.quality_score import calculate_quality_score, get_tier_display

router = Router()


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: types.Message, db: Database):
    parts = (message.text or "").split()
    sport = None

    for part in parts[1:]:
        if part.upper() in VALID_SPORTS:
            sport = part.upper()

    rows = await db.get_leaderboard(sport)

    sport_label = f" — {sport}" if sport else ""

    if not rows:
        await message.reply(
            f"🏆 <b>Pete's Leaderboard{sport_label}</b>\n\n"
            f"Nobody qualified yet. Pete needs 5+ resolved picks to rank you.",
            parse_mode="HTML",
        )
        return

    lines = [f"🏆 <b>Pete's Leaderboard{sport_label}</b>", ""]

    for i, row in enumerate(rows, 1):
        user_id = row["telegram_id"]
        name = f"@{row['username']}" if row["username"] else row["display_name"] or "Unknown"
        net = round(row["net_units"], 1)
        net_display = f"+{net}" if net >= 0 else str(net)
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")

        # Get tier for this user
        qs = await calculate_quality_score(db, user_id)
        tier = qs["tier"]

        lines.append(
            f"{medal} {tier['emoji']} {name} — {row['wins']}-{row['losses']} | "
            f"{net_display}u | {row['roi']}% ROI | QS: {qs['score']:.2f}"
        )

    lines.append("")
    lines.append("<i>QS = Quality Score. Pete ranks by units but the score tells the real story.</i>")

    await message.reply("\n".join(lines), parse_mode="HTML")
