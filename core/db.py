"""PostgreSQL database connection and migration runner."""

from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        from core.config import load_config

        config = load_config()
        raw_url = config.database.url
        dsn = raw_url.replace("postgresql+asyncpg://", "postgresql://")
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _run_migration(conn)


async def _run_migration(conn: asyncpg.Connection):
    """Apply all pending migrations in order, skipping already-applied ones."""
    # Ensure tracking table exists
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT NOW())"
    )

    # Bootstrap: if tables exist but _migrations is empty, mark 001 as applied
    row = await conn.fetchrow(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'memories')"
    )
    tables_exist = row and row[0]
    if tables_exist:
        already_tracked = await conn.fetchrow("SELECT 1 FROM _migrations WHERE name = '001_init.sql'")
        if not already_tracked:
            await conn.execute("INSERT INTO _migrations (name) VALUES ('001_init.sql')")

    # Find all .sql migration files sorted by name
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for mf in migration_files:
        name = mf.name
        row = await conn.fetchrow("SELECT 1 FROM _migrations WHERE name = $1", name)
        if row:
            continue  # already applied
        sql = mf.read_text()
        await conn.execute(sql)
        await conn.execute("INSERT INTO _migrations (name) VALUES ($1)", name)
