from aiogram import Router, types
from aiogram.filters import Command

from bot.database import Database
from bot.scoring import calculate_user_quality_score

router = Router()


@router.message(Command("score"))
async def cmd_score(message: types.Message, db: Database):
    if not message.from_user:
        return

    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )

    qs_data = await calculate_user_quality_score(db, message.from_user.id)
    qs = qs_data["quality_score"]
    tier = qs_data["tier"]
    n = qs_data["picks_scored"]

    if n == 0:
        await message.reply(
            f"🏅 <b>Quality Score: 0.500</b> (neutral)\n"
            f"{tier['emoji']} Tier: <b>{tier['name']}</b>\n\n"
            f"Pete hasn't scored you yet. Make some picks first.",
            parse_mode="HTML",
        )
        return

    acc = qs_data["accuracy"]
    timing = qs_data["timing_avg"]
    conviction = qs_data["conviction_avg"]

    # Visual bar
    filled = round(qs * 10)
    bar = "█" * filled + "░" * (10 - filled)

    # Next tier info
    next_tier = None
    for t in [{"name": "Participant", "min": 0.40}, {"name": "Analyst", "min": 0.60},
              {"name": "Strategist", "min": 0.80}, {"name": "Oracle", "min": 0.95}]:
        if qs < t["min"]:
            next_tier = t
            break

    next_str = ""
    if next_tier:
        gap = round(next_tier["min"] - qs, 3)
        next_str = f"\n📍 {gap:.3f} to <b>{next_tier['name']}</b>"

    username = message.from_user.username or message.from_user.full_name

    await message.reply(
        f"🏅 <b>@{username} — Quality Score</b>\n\n"
        f"<b>{qs:.3f}</b> [{bar}]\n"
        f"{tier['emoji']} Tier: <b>{tier['name']}</b>"
        f"{next_str}\n\n"
        f"📈 Accuracy: {acc:.1%}\n"
        f"⏱ Timing: {timing:.2f}\n"
        f"💪 Conviction: {conviction:.2f}\n"
        f"📊 {n} picks scored\n\n"
        f"<i>POTD picks earn 1.3x conviction. Parlays earn 1.5x.\n"
        f"Pick early, pick bold, pick right.</i>",
        parse_mode="HTML",
    )
