import aiosqlite
import os
from datetime import datetime, timezone


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()

    async def close(self):
        if self.db:
            await self.db.close()

    async def _create_tables(self):
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sport TEXT NOT NULL,
                team TEXT NOT NULL,
                line TEXT,
                units REAL NOT NULL DEFAULT 1.0,
                odds INTEGER,
                pick_type TEXT NOT NULL DEFAULT 'spread',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT,
                game_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS parlays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                units REAL NOT NULL DEFAULT 1.0,
                total_odds INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS parlay_legs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parlay_id INTEGER NOT NULL,
                sport TEXT NOT NULL,
                team TEXT NOT NULL,
                line TEXT,
                pick_type TEXT NOT NULL DEFAULT 'spread',
                status TEXT NOT NULL DEFAULT 'pending',
                FOREIGN KEY (parlay_id) REFERENCES parlays(id)
            );

            CREATE TABLE IF NOT EXISTS follows (
                follower_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (follower_id, target_id),
                FOREIGN KEY (follower_id) REFERENCES users(telegram_id),
                FOREIGN KEY (target_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS fades (
                fader_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (fader_id, target_id),
                FOREIGN KEY (fader_id) REFERENCES users(telegram_id),
                FOREIGN KEY (target_id) REFERENCES users(telegram_id)
            );

            CREATE INDEX IF NOT EXISTS idx_picks_user ON picks(user_id);
            CREATE INDEX IF NOT EXISTS idx_picks_status ON picks(status);
            CREATE INDEX IF NOT EXISTS idx_picks_sport ON picks(sport);
            CREATE INDEX IF NOT EXISTS idx_parlays_user ON parlays(user_id);
        """)
        await self.db.commit()

    # ── User operations ──

    async def upsert_user(self, telegram_id: int, username: str | None, display_name: str | None):
        await self.db.execute(
            """INSERT INTO users (telegram_id, username, display_name)
               VALUES (?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 username = excluded.username,
                 display_name = excluded.display_name""",
            (telegram_id, username, display_name),
        )
        await self.db.commit()

    # ── Pick operations ──

    async def create_pick(self, user_id: int, sport: str, team: str, line: str | None,
                          units: float, odds: int | None, pick_type: str) -> int:
        cursor = await self.db.execute(
            """INSERT INTO picks (user_id, sport, team, line, units, odds, pick_type)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, sport.upper(), team, line, units, odds, pick_type),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def resolve_pick(self, pick_id: int, result: str):
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE picks SET status = ?, resolved_at = ? WHERE id = ?",
            (result, now, pick_id),
        )
        await self.db.commit()

    async def get_pending_picks(self, sport: str | None = None):
        if sport:
            cursor = await self.db.execute(
                "SELECT * FROM picks WHERE status = 'pending' AND sport = ? ORDER BY created_at DESC",
                (sport.upper(),),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM picks WHERE status = 'pending' ORDER BY created_at DESC"
            )
        return await cursor.fetchall()

    async def get_user_picks(self, user_id: int, sport: str | None = None):
        if sport:
            cursor = await self.db.execute(
                "SELECT * FROM picks WHERE user_id = ? AND sport = ? ORDER BY created_at DESC",
                (user_id, sport.upper()),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM picks WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
        return await cursor.fetchall()

    # ── Record / Stats ──

    async def get_user_record(self, user_id: int, sport: str | None = None):
        params = [user_id]
        sport_filter = ""
        if sport:
            sport_filter = " AND sport = ?"
            params.append(sport.upper())

        cursor = await self.db.execute(
            f"""SELECT
                COUNT(CASE WHEN status = 'won' THEN 1 END) as wins,
                COUNT(CASE WHEN status = 'lost' THEN 1 END) as losses,
                COUNT(CASE WHEN status = 'push' THEN 1 END) as pushes,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COALESCE(SUM(CASE WHEN status = 'won' THEN units ELSE 0 END), 0) as units_won,
                COALESCE(SUM(CASE WHEN status = 'lost' THEN units ELSE 0 END), 0) as units_lost,
                COALESCE(SUM(CASE WHEN status IN ('won', 'lost') THEN units ELSE 0 END), 0) as units_wagered
            FROM picks WHERE user_id = ?{sport_filter}""",
            params,
        )
        return await cursor.fetchone()

    async def get_user_streak(self, user_id: int) -> str:
        cursor = await self.db.execute(
            """SELECT status FROM picks
               WHERE user_id = ? AND status IN ('won', 'lost')
               ORDER BY resolved_at DESC LIMIT 20""",
            (user_id,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return "No resolved picks"

        streak_type = rows[0]["status"]
        count = 0
        for row in rows:
            if row["status"] == streak_type:
                count += 1
            else:
                break

        emoji = "🔥" if streak_type == "won" else "🥶"
        label = "W" if streak_type == "won" else "L"
        return f"{emoji} {count}{label} streak"

    # ── Leaderboard ──

    async def get_leaderboard(self, sport: str | None = None, limit: int = 20):
        sport_filter = ""
        params = []
        if sport:
            sport_filter = " AND p.sport = ?"
            params.append(sport.upper())

        cursor = await self.db.execute(
            f"""SELECT
                u.telegram_id,
                u.username,
                u.display_name,
                COUNT(CASE WHEN p.status = 'won' THEN 1 END) as wins,
                COUNT(CASE WHEN p.status = 'lost' THEN 1 END) as losses,
                COALESCE(SUM(CASE WHEN p.status = 'won' THEN p.units ELSE 0 END), 0)
                  - COALESCE(SUM(CASE WHEN p.status = 'lost' THEN p.units ELSE 0 END), 0) as net_units,
                CASE WHEN SUM(CASE WHEN p.status IN ('won','lost') THEN p.units ELSE 0 END) > 0
                  THEN ROUND(
                    (SUM(CASE WHEN p.status = 'won' THEN p.units ELSE 0 END)
                     - SUM(CASE WHEN p.status = 'lost' THEN p.units ELSE 0 END))
                    / SUM(CASE WHEN p.status IN ('won','lost') THEN p.units ELSE 0 END) * 100, 1)
                  ELSE 0 END as roi
            FROM picks p
            JOIN users u ON p.user_id = u.telegram_id
            WHERE p.status IN ('won', 'lost'){sport_filter}
            GROUP BY u.telegram_id
            HAVING (wins + losses) >= 5
            ORDER BY net_units DESC
            LIMIT ?""",
            params + [limit],
        )
        return await cursor.fetchall()

    # ── Parlay operations ──

    async def create_parlay(self, user_id: int, units: float, legs: list[dict]) -> int:
        cursor = await self.db.execute(
            "INSERT INTO parlays (user_id, units) VALUES (?, ?)",
            (user_id, units),
        )
        parlay_id = cursor.lastrowid
        for leg in legs:
            await self.db.execute(
                """INSERT INTO parlay_legs (parlay_id, sport, team, line, pick_type)
                   VALUES (?, ?, ?, ?, ?)""",
                (parlay_id, leg["sport"].upper(), leg["team"], leg.get("line"), leg.get("pick_type", "spread")),
            )
        await self.db.commit()
        return parlay_id

    async def get_parlay(self, parlay_id: int):
        cursor = await self.db.execute("SELECT * FROM parlays WHERE id = ?", (parlay_id,))
        parlay = await cursor.fetchone()
        if not parlay:
            return None, []
        cursor = await self.db.execute(
            "SELECT * FROM parlay_legs WHERE parlay_id = ?", (parlay_id,)
        )
        legs = await cursor.fetchall()
        return parlay, legs

    async def resolve_parlay_leg(self, leg_id: int, result: str):
        await self.db.execute(
            "UPDATE parlay_legs SET status = ? WHERE id = ?", (result, leg_id)
        )
        await self.db.commit()

    async def check_parlay_complete(self, parlay_id: int) -> str | None:
        cursor = await self.db.execute(
            "SELECT status FROM parlay_legs WHERE parlay_id = ?", (parlay_id,)
        )
        legs = await cursor.fetchall()
        statuses = [leg["status"] for leg in legs]

        if "pending" in statuses:
            return None

        if "lost" in statuses:
            return "lost"
        if all(s in ("won", "push") for s in statuses):
            return "won"
        return None
