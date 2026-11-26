"""Shared normalization of H3 verdict flags (Story 8.3)."""

from typing import Any

_TRUE_VERDICTS = frozenset({"true", "1", "yes", "oui"})


def verdict_flag(value: Any) -> bool:
    """Normalize a verdict without treating ``"false"`` as a truthy flag.

    Literal booleans, the integer ``1`` (e.g. a checkpointed rejection) and a
    small set of explicit affirmative strings are accepted. Any other value —
    including ``"false"``, ``0`` and ``2`` — is a rejection-free negative. The
    approval flag itself remains strictly ``is True`` at every call site.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_VERDICTS
    return isinstance(value, int) and value == 1
