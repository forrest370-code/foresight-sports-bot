import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Required environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")

# Optional environment variables
ADMIN_USER_IDS = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_USER_IDS", "").split(",")
    if uid.strip()
]
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/chalkboard.db")

# Startup validation
_REQUIRED = {
    "BOT_TOKEN": BOT_TOKEN,
    "ODDS_API_KEY": ODDS_API_KEY,
}
_missing = [name for name, val in _REQUIRED.items() if not val]
if _missing:
    print(
        f"ERROR: Missing required environment variables: {', '.join(_missing)}\n"
        "Set them in your .env file or in Railway's environment settings.",
        file=sys.stderr,
    )
    sys.exit(1)
