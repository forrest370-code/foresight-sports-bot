from aiogram import Router, types
from aiogram.filters import Command

from bot.database import Database
from bot.utils import parse_pick, format_pick_confirmation
from bot.odds_api import validate_pick
from bot.quality_score import calculate_quality_score

router = Router()


@router.message(Command("pick"))
async def cmd_pick(message: types.Message, db: Database):
    if not message.text or not message.from_user:
        return

    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )

    raw = message.text.replace("/pick", "", 1).strip()
    if not raw:
        await message.reply(
            "📝 <b>Tell Pete what you like:</b>\n"
            "<code>/pick NBA Lakers ML 1u</code>\n"
            "<code>/pick NHL Oilers o5.5 3u</code>\n"
            "<code>/pick MLB Yankees -1.5 2u</code>\n\n"
            "Sport • Team • Line • Units",
            parse_mode="HTML",
        )
        return

    pick = parse_pick(message.text)
    if not pick:
        await message.reply(
            "❌ Pete can't read that. Try:\n"
            "<code>/pick NBA Lakers ML 1u</code>",
            parse_mode="HTML",
        )
        return

    # Validate against real scheduled games
    validation = await validate_pick(pick["sport"], pick["team"])

    if not validation["valid"]:
        await message.reply(
            f"🚫 <b>Pick rejected.</b>\n\n{validation['error']}",
            parse_mode="HTML",
        )
        return

    # Build matchup info from API data
    matchup_info = ""
    if validation.get("matchup"):
        matchup_info = validation["matchup"]
    if validation.get("line_info"):
        li = validation["line_info"]
        if li.get("spread") is not None and pick["pick_type"] == "spread":
            actual_spread = li["spread"]
            matchup_info += f" | Line: {'+' if actual_spread > 0 else ''}{actual_spread}"
        if li.get("moneyline") is not None and pick["pick_type"] == "ml":
            ml = li["moneyline"]
            matchup_info += f" | ML: {'+' if ml > 0 else ''}{ml}"

    # Save to database
    game_id = None
    if validation.get("game"):
        game_id = validation["game"].get("id")

    pick_id = await db.create_pick(
        user_id=message.from_user.id,
        sport=pick["sport"],
        team=pick["team"],
        line=pick["line"],
        units=pick["units"],
        odds=None,
        pick_type=pick["pick_type"],
    )

    if game_id:
        await db.db.execute(
            "UPDATE picks SET game_id = ? WHERE id = ?", (game_id, pick_id)
        )
        await db.db.commit()

    username = message.from_user.username or message.from_user.full_name

    # Get user's tier for badge
    qs = await calculate_quality_score(db, message.from_user.id)
    tier = qs["tier"]

    confirmation = format_pick_confirmation(username, pick, pick_id)

    # Add tier badge
    confirmation = f"{tier['emoji']} {tier['name']}\n" + confirmation

    if matchup_info:
        confirmation += f"\n📍 {matchup_info}"

    await message.reply(confirmation, parse_mode="HTML")

    # Auto fade alert for Observer-tier users
    if tier["tag"] == "OBSERVER" and qs["total_resolved"] >= 10:
        line_display = pick.get("line") or pick.get("pick_type", "").upper()
        fade_alert = (
            f"🧊 <b>FADE ALERT</b>\n\n"
            f"Observer-tier @{username} just picked {pick['sport']} {pick['team']} {line_display}\n"
            f"QS: {qs['score']:.2f} | Fade material? You decide."
        )
        await message.answer(fade_alert, parse_mode="HTML")
