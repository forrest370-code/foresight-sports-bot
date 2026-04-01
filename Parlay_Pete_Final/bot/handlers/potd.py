from aiogram import Router, types
from aiogram.filters import Command
from datetime import datetime, timezone

from bot.database import Database
from bot.utils import parse_pick
from bot.odds_api import validate_pick

router = Router()


@router.message(Command("potd"))
async def cmd_potd(message: types.Message, db: Database):
    if not message.text or not message.from_user:
        return

    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )

    raw = message.text.replace("/potd", "", 1).strip()
    if not raw:
        await message.reply(
            "⭐ <b>Pete's Pick of the Day rules:</b>\n"
            "<code>/potd NBA Celtics -4 3u Great matchup tonight</code>\n\n"
            "Sport • Team • Line • Units • <b>Your reasoning</b>\n"
            "One per day. Make it count.",
            parse_mode="HTML",
        )
        return

    # Check if user already posted a POTD today
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cursor = await db.db.execute(
        """SELECT id FROM picks
           WHERE user_id = ? AND pick_type = 'potd'
           AND date(created_at) = ?""",
        (message.from_user.id, today),
    )
    existing = await cursor.fetchone()
    if existing:
        await message.reply(
            "🚫 You already used your POTD today. Pete only allows one per day.\n"
            "Make tomorrow's count.",
            parse_mode="HTML",
        )
        return

    pick = parse_pick("/pick " + raw)
    if not pick:
        await message.reply(
            "❌ Pete can't read that. Try:\n"
            "<code>/potd NBA Celtics -4 3u Great matchup tonight</code>",
            parse_mode="HTML",
        )
        return

    # Validate against real games
    validation = await validate_pick(pick["sport"], pick["team"])
    if not validation["valid"]:
        await message.reply(
            f"🚫 <b>POTD rejected.</b>\n\n{validation['error']}",
            parse_mode="HTML",
        )
        return

    # Extract reasoning
    import re
    parts = raw.split()
    reasoning = ""
    reason_parts = []
    for i, part in enumerate(parts):
        if part.lower().endswith("u") and part[:-1].replace(".", "").isdigit():
            reason_parts = parts[i + 1:]
            break

    if not reason_parts:
        for i, part in enumerate(parts):
            if i >= 3 and not re.match(r"^[+-]?\d+\.?\d*$", part) and part.upper() != "ML":
                reason_parts = parts[i:]
                break

    reasoning = " ".join(reason_parts) if reason_parts else "No reasoning provided. Bold move."

    pick_id = await db.create_pick(
        user_id=message.from_user.id,
        sport=pick["sport"],
        team=pick["team"],
        line=pick["line"],
        units=pick["units"],
        odds=None,
        pick_type="potd",
    )

    if validation.get("game"):
        await db.db.execute(
            "UPDATE picks SET game_id = ? WHERE id = ?",
            (validation["game"].get("id"), pick_id),
        )
        await db.db.commit()

    username = message.from_user.username or message.from_user.full_name
    line_display = ""
    if pick["pick_type"] == "ml":
        line_display = "ML"
    elif pick.get("line"):
        line_display = pick["line"]

    matchup = ""
    if validation.get("matchup"):
        matchup = f"\n📍 {validation['matchup']}"

    text = (
        f"⭐ <b>PICK OF THE DAY</b>\n"
        f"\n"
        f"@{username} — {pick['sport']} {pick['team']} {line_display} | {pick['units']}u\n"
        f"{matchup}\n"
        f"\n"
        f"💬 <i>\"{reasoning}\"</i>\n"
        f"\n"
        f"POTD #{pick_id} | {datetime.now(timezone.utc).strftime('%b %d, %I:%M %p UTC')}\n"
        f"\n"
        f"<i>Pete's watching this one closely.</i>"
    )
    await message.reply(text, parse_mode="HTML")
