"""Async engine, session factory, and the request-scoped DB dependency."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rishivan.config import settings

engine = create_async_engine(settings.database_url, echo=settings.DEBUG)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

