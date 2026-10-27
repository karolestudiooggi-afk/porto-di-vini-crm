from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings


_pool: AsyncConnectionPool | None = None


def _make_pool(conninfo: str) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        conninfo,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"row_factory": dict_row, "prepare_threshold": None},
    )


def get_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("pool não inicializado (lifespan não rodou)")
    return _pool


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _pool
    _pool = _make_pool(settings.database_url)
    try:
        await _pool.open()
        yield
    finally:
        await _pool.close()
        _pool = None


async def get_conn() -> AsyncIterator[AsyncConnection]:
    async with get_pool().connection() as conn:
        yield conn
