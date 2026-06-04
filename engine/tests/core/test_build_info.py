"""Build manifest must stay aligned with Godot (realm_build.json)."""

from __future__ import annotations

import json
from pathlib import Path

from realm.core.build_info import REALM_BUILD_ID, load_build_manifest, version_payload
from realm.core.player_economy import PLAYER_STARTING_CASH_CENTS


def test_realm_build_json_matches_player_economy() -> None:
    manifest = load_build_manifest()
    assert manifest["player_starting_cash_cents"] == PLAYER_STARTING_CASH_CENTS


def test_version_payload_shape() -> None:
    payload = version_payload()
    assert payload["ok"] is True
    assert payload["build_id"] == REALM_BUILD_ID
    assert payload["player_starting_cash_cents"] == PLAYER_STARTING_CASH_CENTS


def test_realm_build_json_is_valid_json() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    raw = json.loads((repo_root / "realm_build.json").read_text(encoding="utf-8"))
    assert isinstance(raw["build_id"], str) and raw["build_id"]
    assert int(raw["player_starting_cash_cents"]) == PLAYER_STARTING_CASH_CENTS
