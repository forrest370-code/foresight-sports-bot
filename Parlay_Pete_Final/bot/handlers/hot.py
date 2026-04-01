from aiogram import Router, types
from aiogram.filters import Command

from bot.database import Database

router = Router()


@router.message(Command("hot"))
async def cmd_hot(message: types.Message, db: Database):
    # Find users on 5+ win streaks
    # Get all users who have resolved picks
    cursor = await db.db.execute(
        "SELECT DISTINCT user_id FROM picks WHERE status IN ('won', 'lost')"
    )
    user_rows = await cursor.fetchall()

    hot_users = []
    cold_users = []

    for row in user_rows:
        user_id = row["user_id"]
        # Get last 20 resolved picks in order
        cursor = await db.db.execute(
            """SELECT status FROM picks
               WHERE user_id = ? AND status IN ('won', 'lost')
               ORDER BY resolved_at DESC LIMIT 20""",
            (user_id,),
        )
        picks = await cursor.fetchall()
        if not picks:
            continue

        # Count streak
        streak_type = picks[0]["status"]
        count = 0
        for p in picks:
            if p["status"] == streak_type:
                count += 1
            else:
                break

        if count >= 5 and streak_type == "won":
            # Get user info
            cursor = await db.db.execute(
                "SELECT username, display_name FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            user = await cursor.fetchone()
            name = f"@{user['username']}" if user and user["username"] else (user["display_name"] if user else "Unknown")
            hot_users.append((name, count))

        elif count >= 5 and streak_type == "lost":
            cursor = await db.db.execute(
                "SELECT username, display_name FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            user = await cursor.fetchone()
            name = f"@{user['username']}" if user and user["username"] else (user["display_name"] if user else "Unknown")
            cold_users.append((name, count))

    # Sort by streak length
    hot_users.sort(key=lambda x: x[1], reverse=True)
    cold_users.sort(key=lambda x: x[1], reverse=True)

    lines = ["🔥 <b>Who's Hot / Who's Not</b>", ""]

    if hot_users:
        lines.append("<b>🔥 ON FIRE:</b>")
        for name, count in hot_users:
            lines.append(f"  {name} — {count}W streak")
        lines.append("")
    else:
        lines.append("🔥 Nobody's on a 5+ win streak right now.")
        lines.append("")

    if cold_users:
        lines.append("<b>🧊 ICE COLD (fade material):</b>")
        for name, count in cold_users:
            lines.append(f"  {name} — {count}L streak")
        lines.append("")

    if not hot_users and not cold_users:
        lines.append("<i>Not enough data yet. Keep picking.</i>")
    else:
        lines.append("<i>Pete sees everything. Streaks don't lie.</i>")

    await message.reply("\n".join(lines), parse_mode="HTML")
