"""LangGraph Checkpointer factory and utilities for PostgreSQL and in-memory test environments."""

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from iryx.core.config import get_settings

logger = logging.getLogger("iryx.orchestrator.checkpointer")

_memory_saver_instance: MemorySaver | None = None
_postgres_saver_instance: BaseCheckpointSaver | None = None


def get_memory_saver() -> MemorySaver:
    """Return a process-wide MemorySaver instance for test or in-memory execution."""
    global _memory_saver_instance
    if _memory_saver_instance is None:
        _memory_saver_instance = MemorySaver()
    return _memory_saver_instance


def reset_memory_saver() -> None:
    """Reset the process-wide MemorySaver instance (useful between test runs)."""
    global _memory_saver_instance
    _memory_saver_instance = MemorySaver()


def normalize_postgres_url(url: str) -> str:
    """Convert SQLAlchemy postgres connection URLs to standard psycopg/libpq connection URLs."""
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql://", 1)
    return url


def get_checkpointer(
    database_url: str | None = None,
    force_memory: bool = False,
) -> BaseCheckpointSaver:
    """Factory returning appropriate LangGraph checkpointer based on configuration and environment.

    In production/PostgreSQL environments, returns a configured PostgresSaver instance.
    In testing, SQLite or memory-forced modes, returns a MemorySaver instance.
    """
    settings = get_settings()
    url = database_url or settings.database_url

    if force_memory or settings.environment == "test" or url.startswith("sqlite"):
        return get_memory_saver()

    if url.startswith("postgresql"):
        global _postgres_saver_instance
        if _postgres_saver_instance is None:
            try:
                from langgraph.checkpoint.postgres import PostgresSaver
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool

                clean_url = normalize_postgres_url(url)
                pool = ConnectionPool(
                    clean_url,
                    max_size=10,
                    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                    open=True,
                )
                saver = PostgresSaver(pool)
                try:
                    saver.setup()
                except Exception as setup_exc:
                    logger.debug("Checkpointer setup note: %s", setup_exc)
                _postgres_saver_instance = saver
            except Exception as exc:
                logger.warning(
                    "Could not initialize PostgresSaver (%s). Falling back to MemorySaver.",
                    exc,
                )
                return get_memory_saver()
        return _postgres_saver_instance

    return get_memory_saver()


def get_checkpointer_dependency() -> BaseCheckpointSaver:
    """FastAPI dependency yielding the configured checkpointer."""
    return get_checkpointer()
