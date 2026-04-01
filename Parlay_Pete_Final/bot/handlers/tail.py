from aiogram import Router, types
from aiogram.filters import Command

from bot.database import Database

router = Router()


@router.message(Command("tail"))
async def cmd_tail(message: types.Message, db: Database):
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
            "📝 <b>Tail a sharp:</b>\n"
            "<code>/tail @username</code>\n\n"
            "You'll get notified when they post a pick.\n"
            "Use <code>/tail stop @username</code> to unfollow.",
            parse_mode="HTML",
        )
        return

    # Handle /tail stop @username
    if parts[1].lower() == "stop" and len(parts) >= 3:
        target_name = parts[2].lstrip("@")
        # Look up target user
        cursor = await db.db.execute(
            "SELECT telegram_id FROM users WHERE username = ?", (target_name,)
        )
        target = await cursor.fetchone()
        if not target:
            await message.reply(f"❌ Pete doesn't know @{target_name}. They need to make a pick first.")
            return

        await db.db.execute(
            "DELETE FROM follows WHERE follower_id = ? AND target_id = ?",
            (message.from_user.id, target["telegram_id"]),
        )
        await db.db.commit()
        await message.reply(f"✅ Unfollowed @{target_name}. You're on your own now.")
        return

    # Handle /tail @username
    target_name = parts[1].lstrip("@")

    if target_name.lower() == (message.from_user.username or "").lower():
        await message.reply("🤦 You can't tail yourself. Pete's embarrassed for you.")
        return

    cursor = await db.db.execute(
        "SELECT telegram_id FROM users WHERE username = ?", (target_name,)
    )
    target = await cursor.fetchone()
    if not target:
        await message.reply(f"❌ Pete doesn't know @{target_name}. They need to make a pick first.")
        return

    # Check if already following
    cursor = await db.db.execute(
        "SELECT 1 FROM follows WHERE follower_id = ? AND target_id = ?",
        (message.from_user.id, target["telegram_id"]),
    )
    exists = await cursor.fetchone()
    if exists:
        await message.reply(f"👀 You're already tailing @{target_name}. Pete's got you covered.")
        return

    await db.db.execute(
        "INSERT INTO follows (follower_id, target_id) VALUES (?, ?)",
        (message.from_user.id, target["telegram_id"]),
    )
    await db.db.commit()

    # Get target's record for context
    record = await db.get_user_record(target["telegram_id"])
    wins = record["wins"]
    losses = record["losses"]
    net = round(record["units_won"] - record["units_lost"], 1)
    net_display = f"+{net}" if net >= 0 else str(net)

    await message.reply(
        f"🔔 <b>Now tailing @{target_name}</b>\n"
        f"Their record: {wins}-{losses} | {net_display}u\n\n"
        f"<i>Pete will let you know when they post a pick.</i>",
        parse_mode="HTML",
    )
