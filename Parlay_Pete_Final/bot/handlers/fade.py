from aiogram import Router, types
from aiogram.filters import Command

from bot.database import Database

router = Router()


@router.message(Command("fade"))
async def cmd_fade(message: types.Message, db: Database):
    if not message.from_user:
        return

    await db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )

    parts = (message.text or "").split()

    if len(parts) < 2:
        await message.reply(
            "📝 <b>Fade someone:</b>\n"
            "<code>/fade @username</code>\n\n"
            "Get notified when they pick — so you can take the other side.\n"
            "Use <code>/fade stop @username</code> to stop fading.",
            parse_mode="HTML",
        )
        return

    # Handle /fade stop @username
    if parts[1].lower() == "stop" and len(parts) >= 3:
        target_name = parts[2].lstrip("@")
        cursor = await db.db.execute(
            "SELECT telegram_id FROM users WHERE username = ?", (target_name,)
        )
        target = await cursor.fetchone()
        if not target:
            await message.reply(f"❌ Pete doesn't know @{target_name}.")
            return

        await db.db.execute(
            "DELETE FROM fades WHERE fader_id = ? AND target_id = ?",
            (message.from_user.id, target["telegram_id"]),
        )
        await db.db.commit()
        await message.reply(f"✅ Stopped fading @{target_name}. Mercy granted.")
        return

    # Handle /fade @username
    target_name = parts[1].lstrip("@")

    if target_name.lower() == (message.from_user.username or "").lower():
        await message.reply("🤡 Fading yourself? Pete respects the self-awareness but no.")
        return

    cursor = await db.db.execute(
        "SELECT telegram_id FROM users WHERE username = ?", (target_name,)
    )
    target = await cursor.fetchone()
    if not target:
        await message.reply(f"❌ Pete doesn't know @{target_name}. They need to make a pick first.")
        return

    # Check if already fading
    cursor = await db.db.execute(
        "SELECT 1 FROM fades WHERE fader_id = ? AND target_id = ?",
        (message.from_user.id, target["telegram_id"]),
    )
    exists = await cursor.fetchone()
    if exists:
        await message.reply(f"🎯 You're already fading @{target_name}. Pete admires the commitment.")
        return

    await db.db.execute(
        "INSERT INTO fades (fader_id, target_id) VALUES (?, ?)",
        (message.from_user.id, target["telegram_id"]),
    )
    await db.db.commit()

    # Get target's record
    record = await db.get_user_record(target["telegram_id"])
    wins = record["wins"]
    losses = record["losses"]
    net = round(record["units_won"] - record["units_lost"], 1)
    net_display = f"+{net}" if net >= 0 else str(net)

    await message.reply(
        f"🎯 <b>Now fading @{target_name}</b>\n"
        f"Their record: {wins}-{losses} | {net_display}u\n\n"
        f"<i>Pete will alert you when they pick. Take the other side at your own risk.</i>",
        parse_mode="HTML",
    )
