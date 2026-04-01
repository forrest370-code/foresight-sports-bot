import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from bot.config import BOT_TOKEN
from bot.database import Database
from bot.handlers import pick, parlay, record, leaderboard, resolve, potd, tail, fade, hot, slate, score

# Logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Database instance
db = Database("./data/parlaypete.db")


async def cmd_start(message: types.Message):
    """Handle /start command."""
    await message.reply(
        "👋 <b>What's good. I'm Pete.</b>\n\n"
        "I track every sports pick you make. Spreads, moneylines, over/unders, parlays. "
        "Everything gets timestamped and locked. No edits. No deletes. Your record is permanent.\n\n"
        "📝 <b>Commands:</b>\n"
        "/pick — straight bet\n"
        "/parlay — multi-leg parlay\n"
        "/potd — pick of the day\n"
        "/score — your Quality Score + tier\n"
        "/record — your W-L, units, ROI\n"
        "/leaderboard — top 20 sharps\n"
        "/slate — today's games + lines\n"
        "/tail — follow a sharp's picks\n"
        "/fade — bet against someone\n"
        "/hot — who's on a streak\n\n"
        "<i>Tap any command above to see how it works.\n"
        "Prove you're sharp or get exposed. Pete sees all.</i>",
        parse_mode="HTML",
    )


async def cmd_help(message: types.Message):
    """Handle /help command."""
    await message.reply(
        "📋 <b>Pete's Full Menu:</b>\n\n"
        "<b>🔒 Make picks:</b>\n"
        "/pick — straight bet\n"
        "  <i>e.g. pick NFL Chiefs -3.5 2u</i>\n"
        "/parlay — multi-leg parlay\n"
        "  <i>e.g. parlay NBA Celtics -4 + Lakers ML 2u</i>\n"
        "/potd — pick of the day with reasoning (1/day)\n"
        "  <i>e.g. potd NFL Bills -7 3u Great matchup</i>\n\n"
        "<b>📊 Check records:</b>\n"
        "/record — your stats + Quality Score breakdown\n"
        "/score — quick Quality Score + tier check\n"
        "/leaderboard — top 20 by profit + QS\n\n"
        "<b>👀 Social:</b>\n"
        "/tail — follow a sharp's picks\n"
        "/fade — get alerts to bet the other side\n"
        "/hot — who's on a 5+ win/loss streak\n\n"
        "<b>📋 Info:</b>\n"
        "/slate — today's games with lines for any sport\n\n"
        "<b>Sports:</b> NFL, NBA, MLB, NHL, NCAAF, NCAAB, UFC, TENNIS, SOCCER, EPL, MLS\n\n"
        "<i>Every pick locked. Every record public. Pete remembers everything.</i>",
        parse_mode="HTML",
    )


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set. Check your .env file.")
        sys.exit(1)

    # Initialize bot and dispatcher — force IPv4 to avoid IPv6 SSL issues
    import socket
    session = AiohttpSession()
    session._connector_init["family"] = socket.AF_INET
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
        session=session,
    )
    dp = Dispatcher()

    # Connect database
    await db.connect()
    logger.info("Database connected.")

    # Middleware to inject db into handlers
    @dp.message.middleware()
    async def db_middleware(handler, event, data):
        data["db"] = db
        return await handler(event, data)

    # Register command handlers
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_help, Command("help"))
    dp.include_router(pick.router)
    dp.include_router(parlay.router)
    dp.include_router(record.router)
    dp.include_router(leaderboard.router)
    dp.include_router(resolve.router)
    dp.include_router(potd.router)
    dp.include_router(tail.router)
    dp.include_router(fade.router)
    dp.include_router(hot.router)
    dp.include_router(slate.router)
    dp.include_router(score.router)

    # Start polling
    logger.info("ParlayPete is live. Let's ride.")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
