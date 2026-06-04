"""Engine ↔ Godot build identity (shared ``realm_build.json`` at repo root)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, TypedDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST_PATH = _REPO_ROOT / "realm_build.json"


class BuildManifest(TypedDict):
    build_id: str
    player_starting_cash_cents: int


@lru_cache(maxsize=1)
def load_build_manifest() -> BuildManifest:
    raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    build_id = str(raw["build_id"]).strip()
    cash = int(raw["player_starting_cash_cents"])
    if not build_id:
        raise ValueError("realm_build.json: build_id must be non-empty")
    if cash <= 0:
        raise ValueError("realm_build.json: player_starting_cash_cents must be positive")
    return BuildManifest(build_id=build_id, player_starting_cash_cents=cash)


REALM_BUILD_ID: Final[str] = load_build_manifest()["build_id"]


def version_payload() -> dict[str, Any]:
    from realm.core.player_economy import PLAYER_STARTING_CASH_CENTS

    manifest = load_build_manifest()
    if manifest["player_starting_cash_cents"] != PLAYER_STARTING_CASH_CENTS:
        raise RuntimeError(
            "realm_build.json player_starting_cash_cents "
            f"({manifest['player_starting_cash_cents']}) != "
            f"player_economy.PLAYER_STARTING_CASH_CENTS ({PLAYER_STARTING_CASH_CENTS})"
        )
    return {
        "ok": True,
        "build_id": manifest["build_id"],
        "player_starting_cash_cents": PLAYER_STARTING_CASH_CENTS,
        "features": {
            "ensure_player_starting_cash": True,
            "dev_reset_returns_player_cash": True,
        },
    }
