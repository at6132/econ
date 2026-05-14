"""Shared types for action handlers (ActionOk / ActionErr / ActionResult).

Every player-facing or NPC-facing action returns an ``ActionResult``: either
``ActionOk(ok=True)`` on success or ``ActionErr(ok=False, reason="...")`` on
expected failure. Never raise for expected failures; never return None.
"""

from __future__ import annotations

from typing import Literal, TypedDict, Union


class ActionOk(TypedDict):
    ok: Literal[True]


class ActionErr(TypedDict):
    ok: Literal[False]
    reason: str


ActionResult = Union[ActionOk, ActionErr]
