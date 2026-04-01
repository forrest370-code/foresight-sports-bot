from aiogram import Router, types
from aiogram.filters import Command

from bot.config import ADMIN_USER_IDS
from bot.database import Database
from bot.utils import format_win, format_loss

router = Router()


@router.message(Command("resolve"))
async def cmd_resolve(message: types.Message, db: Database):
    if not message.from_user:
        return

    # Admin check
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.reply("🚫 Admin only. Pete doesn't take orders from you.")
        return

    parts = (message.text or "").split()
    # /resolve <pick_id> <won|lost|push>
    if len(parts) < 3:
        await message.reply(
            "📝 <b>How to resolve:</b>\n"
            "<code>/resolve 42 won</code>\n"
            "<code>/resolve 42 lost</code>\n"
            "<code>/resolve 42 push</code>\n\n"
            "Pick ID + result",
            parse_mode="HTML",
        )
        return

    try:
        pick_id = int(parts[1])
    except ValueError:
        await message.reply("❌ Pick ID must be a number.")
        return

    result = parts[2].lower()
    if result not in ("won", "lost", "push"):
        await message.reply("❌ Result must be: won, lost, or push")
        return

    # Resolve the pick
    await db.resolve_pick(pick_id, result)

    # Get pick details for the notification
    cursor = await db.db.execute(
        "SELECT p.*, u.username, u.display_name FROM picks p JOIN users u ON p.user_id = u.telegram_id WHERE p.id = ?",
        (pick_id,),
    )
    pick = await cursor.fetchone()

    if not pick:
        await message.reply(f"❌ Pick #{pick_id} not found.")
        return

    username = pick["username"] or pick["display_name"] or "Unknown"

    # Get updated record
    record = await db.get_user_record(pick["user_id"])
    net = round(record["units_won"] - record["units_lost"], 1)
    wagered = record["units_wagered"]
    roi = round((net / wagered * 100), 1) if wagered > 0 else 0.0

    if result == "won":
        text = format_win(
            username, pick_id, pick["team"], pick["line"], pick["units"],
            record["wins"], record["losses"], net, roi,
        )
    elif result == "lost":
        text = format_loss(
            username, pick_id, pick["team"], pick["line"], pick["units"],
            record["wins"], record["losses"], net, roi,
        )
    else:
        text = f"➖ @{username} PUSH: {pick['team']} {pick['line'] or ''}\n0u | Pick #{pick_id}"

    await message.reply(text, parse_mode="HTML")
