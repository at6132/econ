"""Lua eval gate (optional ``lupa``)."""

from __future__ import annotations

import os

import pytest

from realm.lua_sandbox import eval_user_lua_chunk


def test_eval_disabled_without_env() -> None:
    os.environ.pop("REALM_LUA_EVAL", None)
    r = eval_user_lua_chunk("return 1", tick=0, purpose="t")
    assert r.get("ok") is False


def test_eval_forbidden_pattern() -> None:
    pytest.importorskip("lupa")
    os.environ["REALM_LUA_EVAL"] = "1"
    try:
        r = eval_user_lua_chunk("return require('x')", tick=0, purpose="t")
        assert r.get("ok") is False
    finally:
        os.environ.pop("REALM_LUA_EVAL", None)


def test_eval_simple_chunk_when_enabled() -> None:
    pytest.importorskip("lupa")
    os.environ["REALM_LUA_EVAL"] = "1"
    try:
        r = eval_user_lua_chunk("return tick + #purpose", tick=3, purpose="ab")
        assert r.get("ok") is True
        assert r.get("result") == 5
    finally:
        os.environ.pop("REALM_LUA_EVAL", None)
