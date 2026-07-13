from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from atip_api.config import get_settings
from atip_api.resilience import db_retrying


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> AsyncEngine:
    # pre_ping transparently replaces connections that died while pooled
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        # acquire the pooled connection up front with backoff so a transient
        # outage at request start is retried instead of failing the request;
        # mid-transaction statement failures are NOT retried (integrity first)
        async for attempt in db_retrying():
            with attempt:
                try:
                    await session.connection()
                except BaseException:
                    await session.rollback()
                    raise
        yield session
