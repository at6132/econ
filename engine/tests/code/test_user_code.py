"""User-code layer helpers (validation + status shape)."""

from __future__ import annotations

from realm.code.user_code import code_layer_public_status, validate_user_source


def test_validate_empty_source_ok() -> None:
    r = validate_user_source("")
    assert r["ok"] is True
    assert r.get("lines") == 0


def test_validate_counts_lines() -> None:
    r = validate_user_source("a\nb\nc")
    assert r["ok"] is True
    assert r.get("lines") == 3


def test_validate_rejects_oversize() -> None:
    r = validate_user_source("x" * (300_000))
    assert r["ok"] is False


def test_validate_rejects_non_string() -> None:
    r = validate_user_source(1)  # type: ignore[arg-type]
    assert r["ok"] is False


def test_public_status_shape() -> None:
    s = code_layer_public_status()
    assert s.get("phase") == "stub"
    assert isinstance(s.get("lua_runtime"), bool)
    assert "lua" in s
    assert "max_source_bytes" in s
    assert s.get("eval_requires_env") == "REALM_LUA_EVAL=1"
