from aiogram import Router, types
from aiogram.filters import Command

from bot.database import Database
from bot.utils import parse_parlay, format_parlay_confirmation
from bot.odds_api import validate_pick

router = Router()


@router.message(Command("parlay"))
async def cmd_parlay(message: types.Message, db: Database):
    if not message.text or not message.from_user:
        return

    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )

    raw = message.text.replace("/parlay", "", 1).strip()
    if not raw:
        await message.reply(
            "📝 <b>Pete's favorite command.</b>\n"
            "<code>/parlay NBA Celtics -4 + Lakers ML 2u</code>\n\n"
            "Separate legs with <b>+</b>\n"
            "Units at the end (default 1u)",
            parse_mode="HTML",
        )
        return

    result = parse_parlay(message.text)
    if not result:
        await message.reply(
            "❌ Pete can't read that parlay. Try:\n"
            "<code>/parlay NBA Celtics -4 + Lakers ML 2u</code>\n\n"
            "Each leg needs: Sport Team Line",
            parse_mode="HTML",
        )
        return

    # Validate every leg against real games
    matchup_lines = []
    for i, leg in enumerate(result["legs"], 1):
        validation = await validate_pick(leg["sport"], leg["team"])
        if not validation["valid"]:
            await message.reply(
                f"🚫 <b>Parlay rejected — Leg {i} failed.</b>\n\n"
                f"Leg {i}: {leg['sport']} {leg['team']}\n"
                f"{validation['error']}",
                parse_mode="HTML",
            )
            return
        if validation.get("matchup"):
            matchup_lines.append(f"  Leg {i}: {validation['matchup']}")

    parlay_id = await db.create_parlay(
        user_id=message.from_user.id,
        units=result["units"],
        legs=result["legs"],
    )

    username = message.from_user.username or message.from_user.full_name
    confirmation = format_parlay_confirmation(username, result["legs"], parlay_id, result["units"])

    if matchup_lines:
        confirmation += "\n📍 " + "\n".join(matchup_lines)

    await message.reply(confirmation, parse_mode="HTML")
